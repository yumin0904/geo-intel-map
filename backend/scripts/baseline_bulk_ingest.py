"""
baseline_bulk_ingest.py — FRED 거시지표 + Comtrade 무역 + yfinance 시장 베이스라인 적재

사용법:
    cd backend
    source .venv/bin/activate

    # FRED만 (3년치 WTI·금·원달러·대만달러·VIX)
    python scripts/baseline_bulk_ingest.py --fred

    # yfinance 시장 지표 (ZW=F·GLD·TSM·ITA·NG=F 로컬 캐시 — Granger 분석 안정화)
    python scripts/baseline_bulk_ingest.py --yfinance

    # Comtrade CSV만
    python scripts/baseline_bulk_ingest.py --comtrade data/comtrade_hs27.csv

    # 전부
    python scripts/baseline_bulk_ingest.py --fred --yfinance --comtrade data/*.csv

    # dry-run (DB 저장 없이 건수 확인)
    python scripts/baseline_bulk_ingest.py --fred --dry-run

필수 환경변수 (--fred 시):
    FRED_API_KEY=...  (https://fred.stlouisfed.org/docs/api/api_key.html 무료 등록)

Comtrade CSV 다운로드:
    1. https://comtradeplus.un.org/ 접속
    2. 조건: Frequency=Annual, HS codes 27/8542/26, 관련 국가 선택
    3. CSV 내보내기 후 --comtrade 옵션으로 경로 전달
    지원 포맷: Comtrade API v1 레거시 / v2 신형 모두 자동 감지
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_DB_PATH = _ROOT / "db" / "intel.db"
_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# FRED 적재 대상 시리즈
FRED_SERIES: dict[str, str] = {
    "wti":     "DCOILWTICO",   # WTI 원유 (달러/배럴)
    "brent":   "DCOILBRENTEU", # 브렌트유 (달러/배럴) — LBMA 금 시리즈가 API 접근 제한
    "usd_krw": "DEXKOUS",      # 원달러 환율 (KRW per 1 USD)
    "usd_twd": "DEXTAUS",      # 대만달러 환율 (TWD per 1 USD)
    "vix":     "VIXCLS",       # CBOE VIX 변동성 지수
    # gold: GOLDAMGBD228NLBM — LBMA 라이선스 제한으로 FRED API 400, stages.py yfinance fallback 사용
}

# yfinance 로컬 캐시 대상 — Granger 분석 시 네트워크 의존 제거
# indicator 이름은 correlation.py _TICKER_TO_FRED 매핑과 반드시 일치해야 한다
YFINANCE_TICKERS: dict[str, str] = {
    "ZW=F": "wheat_futures",   # 밀 선물 — 우크라이나 곡물 루트 (Resource Weaponization)
    "GLD":  "gold_etf",        # 금 ETF — 리스크오프 안전자산 (Kahneman & Tversky)
    "TSM":  "tsm_stock",       # TSMC — 반도체 공급망 집중 (Weaponized Interdependence)
    "ITA":  "defense_etf",     # 방산 ETF — A2/AD 긴장 → 방산투자 (Biddle 2001)
    "NG=F": "natgas_futures",  # 천연가스 선물 — 말라카 LNG 초크포인트 (Mahan 1890)
}

# 적재 대상 HS 코드 (Comtrade)
TARGET_HS_CODES = {"27", "8542", "26"}


# ── DB 연결 ──────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    """필요한 테이블이 없으면 생성한다 (schema.sql 의 일부)."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS historical_macro_indices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id   TEXT NOT NULL,
            indicator   TEXT NOT NULL,
            date        TEXT NOT NULL,
            value       REAL NOT NULL,
            source      TEXT DEFAULT 'FRED',
            ingested_at TEXT NOT NULL,
            UNIQUE (series_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_macro_indicator
            ON historical_macro_indices(indicator, date);

        CREATE TABLE IF NOT EXISTS historical_trade_matrix (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            period           TEXT NOT NULL,
            reporter_iso     TEXT NOT NULL,
            partner_iso      TEXT NOT NULL,
            hs_code          TEXT NOT NULL,
            trade_flow       TEXT NOT NULL,
            trade_value_usd  REAL,
            netweight_kg     REAL,
            dependency_ratio REAL,
            source           TEXT DEFAULT 'UN_Comtrade',
            ingested_at      TEXT NOT NULL,
            UNIQUE (period, reporter_iso, partner_iso, hs_code, trade_flow)
        );
        CREATE INDEX IF NOT EXISTS idx_trade_reporter
            ON historical_trade_matrix(reporter_iso, partner_iso, hs_code);
    """)


# ── FRED 적재 ────────────────────────────────────────────────────────────────

async def _fetch_fred_series(
    series_id: str, api_key: str, start: str, end: str
) -> list[tuple[str, float]]:
    """FRED API에서 일별 관측값을 (date, value) 리스트로 반환한다."""
    try:
        import httpx
    except ImportError:
        logger.error("httpx 미설치. pip install httpx")
        return []

    params = {
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_FRED_BASE, params=params)
            resp.raise_for_status()
        rows = []
        for obs in resp.json().get("observations", []):
            val_str = obs.get("value", ".")
            if val_str == ".":  # FRED 결측값
                continue
            try:
                rows.append((obs["date"], float(val_str)))
            except (ValueError, KeyError):
                pass
        return rows
    except Exception as e:
        logger.error("[FRED] %s 조회 실패: %s", series_id, e)
        return []


async def ingest_fred(con: sqlite3.Connection, years: int, dry_run: bool) -> dict:
    api_key = os.getenv("FRED_API_KEY", "")
    if not api_key:
        logger.error("[FRED] FRED_API_KEY 환경변수가 없습니다. .env에 추가하세요.")
        return {}

    now = datetime.now(timezone.utc)
    start_date = f"{now.year - years}-{now.month:02d}-{now.day:02d}"
    end_date = now.strftime("%Y-%m-%d")

    logger.info("[FRED] 기간: %s ~ %s (%d년치)", start_date, end_date, years)

    now_iso = now.isoformat()
    summary: dict[str, int] = {}

    for indicator, series_id in FRED_SERIES.items():
        observations = await _fetch_fred_series(series_id, api_key, start_date, end_date)
        if not observations:
            summary[indicator] = 0
            continue

        if dry_run:
            logger.info("[FRED] dry-run — %s (%s): %d건", indicator, series_id, len(observations))
            summary[indicator] = len(observations)
            continue

        inserted = 0
        with con:
            for date, value in observations:
                try:
                    con.execute(
                        """
                        INSERT OR IGNORE INTO historical_macro_indices
                        (series_id, indicator, date, value, ingested_at)
                        VALUES (?,?,?,?,?)
                        """,
                        (series_id, indicator, date, value, now_iso),
                    )
                    inserted += 1
                except sqlite3.Error as e:
                    logger.debug("[FRED] INSERT 실패 (%s %s): %s", indicator, date, e)

        logger.info("[FRED] %s (%s): %d건 → INSERT %d건", indicator, series_id, len(observations), inserted)
        summary[indicator] = inserted
        await asyncio.sleep(0.5)  # FRED API rate limit 방지

    return summary


# ── yfinance 로컬 캐시 적재 ──────────────────────────────────────────────────

async def ingest_yfinance(con: sqlite3.Connection, years: int, dry_run: bool) -> dict:
    """
    YFINANCE_TICKERS를 historical_macro_indices에 적재한다.

    Granger 분석(correlation.py)이 네트워크 없이 DB에서 직접 읽을 수 있도록
    일별 종가를 미리 캐시한다. 이렇게 하면 yfinance 일시 장애·rate limit 시에도
    분석이 "데이터 없음"으로 실패하지 않는다.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("[yfinance] yfinance 미설치. pip install yfinance")
        return {}

    now = datetime.now(timezone.utc)
    start_date = f"{now.year - years}-{now.month:02d}-{now.day:02d}"
    end_date = now.strftime("%Y-%m-%d")
    now_iso = now.isoformat()

    logger.info("[yfinance] 기간: %s ~ %s (%d년치)", start_date, end_date, years)
    summary: dict[str, int] = {}

    for ticker, indicator in YFINANCE_TICKERS.items():
        try:
            df = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda t=ticker: yf.download(
                    t,
                    start=start_date,
                    end=end_date,
                    auto_adjust=True,
                    progress=False,
                ),
            )
            if df is None or len(df) < 10:
                logger.warning("[yfinance] %s: 데이터 부족 (%d행)", ticker, len(df) if df is not None else 0)
                summary[ticker] = 0
                continue

            close = df["Close"].squeeze()
            rows = [(d.strftime("%Y-%m-%d"), float(v)) for d, v in close.items() if v == v]

            if dry_run:
                logger.info("[yfinance] dry-run — %s (%s): %d건", ticker, indicator, len(rows))
                summary[ticker] = len(rows)
                continue

            inserted = 0
            with con:
                for date_str, value in rows:
                    try:
                        con.execute(
                            """
                            INSERT OR IGNORE INTO historical_macro_indices
                            (series_id, indicator, date, value, ingested_at)
                            VALUES (?,?,?,?,?)
                            """,
                            (ticker, indicator, date_str, value, now_iso),
                        )
                        inserted += 1
                    except sqlite3.Error as e:
                        logger.debug("[yfinance] INSERT 실패 (%s %s): %s", indicator, date_str, e)

            logger.info("[yfinance] %s (%s): %d건 → INSERT %d건", ticker, indicator, len(rows), inserted)
            summary[ticker] = inserted

        except Exception as exc:
            logger.error("[yfinance] %s 실패: %s", ticker, exc)
            summary[ticker] = 0

    return summary


# ── Comtrade CSV 적재 ────────────────────────────────────────────────────────

def _detect_columns(headers: list[str]) -> tuple[dict[str, str], float] | tuple[None, float]:
    """CSV 헤더를 분석해 (컬럼명 매핑, 금액 배수)를 반환한다. 인식 실패 시 (None, 1)."""
    h = {c.strip().lower(): c.strip() for c in headers}

    # WITS (World Integrated Trade Solution)
    # ReporterISO3, PartnerISO3, ProductCode, Year, TradeFlowCode, TradeValue in 1000 USD
    if "reporteriso3" in h and "tradecode" not in h and "tradevalue in 1000 usd" in h:
        return {
            "period":       h.get("year", "Year"),
            "reporter_iso": h.get("reporteriso3", "ReporterISO3"),
            "partner_iso":  h.get("partneriso3", "PartnerISO3"),
            "hs_code":      h.get("productcode", "ProductCode"),
            "trade_flow":   h.get("tradeflowcode", "TradeFlowCode"),  # 5=Import, 6=Export
            "value":        h.get("tradevalue in 1000 usd", "TradeValue in 1000 USD"),
            "netweight":    None,  # WITS에는 순중량 없음
        }, 1000.0  # 1,000 USD 단위 → USD 변환

    # Comtrade v2 신형 (comtradeplus.un.org)
    if "reporteriso" in h and "primaryvalue" in h:
        return {
            "period":       h.get("refyear", "refYear"),
            "reporter_iso": h.get("reporteriso", "reporterISO"),
            "partner_iso":  h.get("partneriso", "partnerISO"),
            "hs_code":      h.get("cmdcode", "cmdCode"),
            "trade_flow":   h.get("flowcode", "flowCode"),  # M / X
            "value":        h.get("primaryvalue", "primaryValue"),
            "netweight":    h.get("netwgt", "netWgt"),
        }, 1.0

    # Comtrade v1 레거시 (comtrade.un.org/data)
    if "reporter iso" in h and "trade value (us$)" in h:
        return {
            "period":       h.get("year", "Year"),
            "reporter_iso": h.get("reporter iso", "Reporter ISO"),
            "partner_iso":  h.get("partner iso", "Partner ISO"),
            "hs_code":      h.get("commodity code", "Commodity Code"),
            "trade_flow":   h.get("trade flow code", "Trade Flow Code"),  # 1=Import, 2=Export
            "value":        h.get("trade value (us$)", "Trade Value (US$)"),
            "netweight":    h.get("netweight (kg)", "Netweight (kg)"),
        }, 1.0

    return None, 1.0


def _normalize_flow(raw: str) -> str:
    """무역 흐름 코드를 'M' / 'X'로 정규화한다."""
    r = str(raw).strip().upper()
    if r in ("M", "IMP", "IMPORT", "1", "5"):   # 5 = WITS Import
        return "M"
    if r in ("X", "EXP", "EXPORT", "2", "6"):   # 6 = WITS Export
        return "X"
    return r


def _parse_comtrade_csv(filepath: Path) -> list[dict]:
    """Comtrade/WITS CSV 파일을 파싱해 정규화된 행 목록을 반환한다."""
    rows: list[dict] = []
    with open(filepath, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        col, value_multiplier = _detect_columns(list(headers))
        if col is None:
            logger.error("[Comtrade] 알 수 없는 CSV 형식: %s (헤더: %s)", filepath.name, headers[:5])
            return []

        for raw in reader:
            hs = str(raw.get(col["hs_code"], "")).strip().lstrip("0") or ""
            if hs not in TARGET_HS_CODES:
                continue

            flow = _normalize_flow(raw.get(col["trade_flow"], ""))
            if flow not in ("M", "X"):
                continue

            try:
                val = float(str(raw.get(col["value"], "") or "0").replace(",", "") or "0")
                val *= value_multiplier  # WITS: ×1000, Comtrade: ×1
            except ValueError:
                val = 0.0

            wgt = None
            if col.get("netweight"):
                try:
                    wgt_raw = str(raw.get(col["netweight"], "") or "").replace(",", "")
                    wgt = float(wgt_raw) if wgt_raw else None
                except ValueError:
                    wgt = None

            rows.append({
                "period":       str(raw.get(col["period"], "")).strip()[:4],
                "reporter_iso": str(raw.get(col["reporter_iso"], "")).strip().upper(),
                "partner_iso":  str(raw.get(col["partner_iso"], "")).strip().upper(),
                "hs_code":      hs,
                "trade_flow":   flow,
                "trade_value":  val,
                "netweight":    wgt,
            })

    return rows


def _compute_dependency(rows: list[dict]) -> list[dict]:
    """WLD(전 세계) 행을 기준으로 dependency_ratio를 계산한다.

    WLD 행이 없으면 모든 파트너의 합계로 대체한다.
    """
    # world_total 맵: (period, reporter_iso, hs_code, trade_flow) → total_value
    world_total: dict[tuple, float] = {}
    for r in rows:
        if r["partner_iso"] in ("WLD", "0", "WORLD"):
            key = (r["period"], r["reporter_iso"], r["hs_code"], r["trade_flow"])
            world_total[key] = r["trade_value"]

    # WLD 행이 없는 그룹은 sum으로 대체
    sums: dict[tuple, float] = {}
    for r in rows:
        if r["partner_iso"] in ("WLD", "0", "WORLD"):
            continue
        key = (r["period"], r["reporter_iso"], r["hs_code"], r["trade_flow"])
        sums[key] = sums.get(key, 0.0) + r["trade_value"]

    result = []
    for r in rows:
        key = (r["period"], r["reporter_iso"], r["hs_code"], r["trade_flow"])
        total = world_total.get(key) or sums.get(key) or 0.0
        dep = round(r["trade_value"] / total, 6) if total > 0 else None
        result.append({**r, "dependency_ratio": dep})

    return result


def ingest_comtrade(con: sqlite3.Connection, filepaths: list[Path], dry_run: bool) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    summary: dict[str, int] = {}

    for fp in filepaths:
        if not fp.exists():
            logger.warning("[Comtrade] 파일 없음: %s", fp)
            continue

        rows = _parse_comtrade_csv(fp)
        if not rows:
            summary[fp.name] = 0
            continue

        rows = _compute_dependency(rows)

        if dry_run:
            hs_counts = {}
            for r in rows:
                hs_counts[r["hs_code"]] = hs_counts.get(r["hs_code"], 0) + 1
            logger.info("[Comtrade] dry-run — %s: %d건 %s", fp.name, len(rows), hs_counts)
            summary[fp.name] = len(rows)
            continue

        inserted = 0
        with con:
            for r in rows:
                try:
                    con.execute(
                        """
                        INSERT OR REPLACE INTO historical_trade_matrix
                        (period, reporter_iso, partner_iso, hs_code, trade_flow,
                         trade_value_usd, netweight_kg, dependency_ratio, ingested_at)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            r["period"], r["reporter_iso"], r["partner_iso"],
                            r["hs_code"], r["trade_flow"],
                            r["trade_value"], r["netweight"],
                            r["dependency_ratio"], now_iso,
                        ),
                    )
                    inserted += 1
                except sqlite3.Error as e:
                    logger.debug("[Comtrade] INSERT 실패: %s", e)

        logger.info("[Comtrade] %s: %d건 파싱 → %d건 INSERT", fp.name, len(rows), inserted)
        summary[fp.name] = inserted

    return summary


# ── 메인 ─────────────────────────────────────────────────────────────────────

async def main(
    run_fred: bool,
    run_yfinance: bool,
    comtrade_files: list[Path],
    years: int,
    dry_run: bool,
) -> None:
    t0 = time.perf_counter()
    con = _connect()
    if not dry_run:
        _ensure_schema(con)
        logger.info("[Baseline] DB 스키마 확인: %s", _DB_PATH)

    fred_summary: dict = {}
    yf_summary: dict = {}
    comtrade_summary: dict = {}

    if run_fred:
        logger.info("[Baseline] FRED 적재 시작 (%d개 시리즈, %d년치)", len(FRED_SERIES), years)
        fred_summary = await ingest_fred(con, years, dry_run)

    if run_yfinance:
        logger.info("[Baseline] yfinance 로컬 캐시 적재 시작 (%d개 티커, %d년치)", len(YFINANCE_TICKERS), years)
        yf_summary = await ingest_yfinance(con, years, dry_run)

    if comtrade_files:
        logger.info("[Baseline] Comtrade 적재 시작 (%d개 파일)", len(comtrade_files))
        comtrade_summary = ingest_comtrade(con, comtrade_files, dry_run)

    con.close()
    elapsed = time.perf_counter() - t0

    print("\n" + "=" * 60)
    print(f"베이스라인 적재 완료 {'(dry-run)' if dry_run else ''}")
    print(f"  소요 시간: {elapsed:.1f}초")
    if fred_summary:
        print("\n[FRED 결과]")
        for indicator, cnt in fred_summary.items():
            series_id = FRED_SERIES[indicator]
            print(f"  {indicator:10s} ({series_id}): {cnt:,}건")
    if yf_summary:
        print("\n[yfinance 결과]")
        for ticker, cnt in yf_summary.items():
            indicator = YFINANCE_TICKERS[ticker]
            print(f"  {ticker:8s} ({indicator}): {cnt:,}건")
    if comtrade_summary:
        print("\n[Comtrade 결과]")
        for fname, cnt in comtrade_summary.items():
            print(f"  {fname}: {cnt:,}건")
    if not run_fred and not run_yfinance and not comtrade_files:
        print("  실행 옵션 없음. --fred, --yfinance, 또는 --comtrade <파일> 을 지정하세요.")
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FRED 거시지표 + yfinance 시장 + Comtrade 무역 데이터를 intel.db에 적재한다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--fred", action="store_true", help="FRED 거시지표 적재")
    parser.add_argument("--yfinance", action="store_true", help="yfinance 시장 지표 로컬 캐시 적재 (ZW=F·GLD·TSM·ITA·NG=F)")
    parser.add_argument(
        "--comtrade", nargs="+", metavar="CSV", help="Comtrade CSV 파일 경로 (복수 가능)"
    )
    parser.add_argument("--years", type=int, default=3, help="FRED/yfinance 조회 연수 (기본: 3)")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 건수 확인")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    comtrade_paths = [Path(p) for p in (args.comtrade or [])]
    asyncio.run(main(
        run_fred=args.fred,
        run_yfinance=args.yfinance,
        comtrade_files=comtrade_paths,
        years=args.years,
        dry_run=args.dry_run,
    ))
