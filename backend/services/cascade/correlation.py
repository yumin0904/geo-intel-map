"""
correlation.py — Cascade 룰 Granger 인과성 사후 검증

Granger 인과분석 (Clive Granger, 1969 노벨경제학상):
  "X가 Y를 Granger-인과한다" = Y의 과거값만으로 예측한 것보다
  X의 과거값도 포함할 때 Y 예측 정확도가 통계적으로 유의하게 개선된다.

정치외교학 적용:
  "분쟁 강도 시계열이 시장 지표 변동을 t-1 ~ t-5일 지연으로 Granger-인과하는가?"
  → 기존 cascade 룰의 통계적 근거를 사후 검증한다.

검정 방법:
  - 이벤트 시계열 X: region별 일별 severity 합산 (event_archive)
  - 시장 시계열 Y: 일별 % 변동 (FRED DB 또는 yfinance)
  - statsmodels.tsa.stattools.grangercausalitytests F-test
  - maxlag=5 (거래일 1주), p < 0.05 = 유의

★ Granger 비유의(Non-significant) 결과가 의미하는 바:
  지정학 충격 → 시장 전이는 비선형(Non-linear) 구조다.
  평균적 conflict intensity(낮은 severity의 일상 이벤트)는 시장에 신호를 주지 않는다.
  오직 임계값(threshold)을 초과한 극단 사건만 전이를 일으킨다.
  → 이는 기존 cascade engine의 "event-specific yfinance 검증" 방식을 통계적으로 정당화한다.
  → Farrell & Newman(2019) 무기화된 상호의존이 "chokepoint shock"에서만 발현됨을 뒷받침한다.

출력:
  {rule_id, region, ticker, p_value, best_lag, n_obs, supported, theory, note}
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import warnings
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# ── PERF-1/2: 모듈 레벨 TTL 캐시 ─────────────────────────────────────────────
# 동일 쿼리가 반복될 때 yfinance 네트워크 I/O와 statsmodels 재계산을 건너뛴다.

_CacheEntry = tuple[Any, float]   # (value, expire_at)
_market_cache:  dict[tuple, _CacheEntry] = {}   # PERF-1: ticker 시계열 캐시
_granger_cache: dict[tuple, _CacheEntry] = {}   # PERF-2: Granger 결과 캐시

_MARKET_TTL  = 6 * 3600   # 6시간 — 과거 시장 데이터는 변하지 않음
_GRANGER_TTL = 1 * 3600   # 1시간 — 같은 지역·티커 쌍 재계산 방지


def _cache_get(store: dict, key: tuple) -> Any:
    """TTL 캐시에서 값 조회. 만료 시 None 반환."""
    entry = store.get(key)
    if entry is None:
        return None
    value, expire_at = entry
    if time.monotonic() > expire_at:
        del store[key]
        return None
    return value


def _cache_set(store: dict, key: tuple, value: Any, ttl: float) -> None:
    store[key] = (value, time.monotonic() + ttl)

_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "intel.db"

# 임계값은 config가 단일 진실원 (매직넘버 금지 — 헌법 §7)
_THR_PATH = Path(__file__).resolve().parents[2] / "config" / "granger_thresholds.yaml"
_THR: dict = yaml.safe_load(_THR_PATH.read_text(encoding="utf-8"))
_MAX_MISSING_SHARE: float = float(_THR.get("max_missing_share", 0.30))
_COVERAGE_MIN_RATIO: float = float(_THR.get("coverage_min_ratio", 0.20))

# historical_macro_indices DB에서 직접 조회 가능한 티커 → indicator 매핑
# FRED 원본 + yfinance 로컬 캐시 (baseline_bulk_ingest.py --yfinance 로 적재)
_TICKER_TO_FRED: dict[str, str] = {
    "CL=F":  "wti",
    "KRW=X": "usd_krw",
    "ZW=F":  "wheat_futures",
    "GLD":   "gold_etf",
    "TSM":   "tsm_stock",
    "ITA":   "defense_etf",
    "NG=F":  "natgas_futures",
    # AR-2: historical_macro_indices에 적재돼 있으나 미매핑이던 일별 시계열
    "BZ=F":  "brent",      # Brent 원유 (WTI와 구분 — 유럽·중동 벤치마크)
    "TWD=X": "usd_twd",    # 대만 달러 (대만해협 긴장의 직접 종속변수)
    "^VIX":  "vix",        # 변동성지수 (안전자산 도피 proxy)
}

# P4-4 후보 스캔용 티커 확장 목록: ticker → (fred_indicator | None, 한국어 레이블)
_SCAN_TICKERS: dict[str, tuple[str | None, str]] = {
    "CL=F":  ("wti",            "WTI 원유 선물"),
    "GLD":   ("gold_etf",       "금 ETF (SPDR)"),
    "KRW=X": ("usd_krw",        "원/달러 환율"),
    "ZW=F":  ("wheat_futures",  "밀 선물 (CBOT)"),
    "TSM":   ("tsm_stock",      "TSMC ADR"),
    "ITA":   ("defense_etf",    "미 방산 ETF"),
    "NG=F":  ("natgas_futures",  "천연가스 선물"),
    "SOXX":  (None,             "반도체 ETF (iShares)"),
    "QQQ":   (None,             "나스닥100 ETF"),
    "TIP":   (None,             "물가연동채 ETF"),
    "DX=F":  (None,             "달러인덱스 선물"),
}

# 이미 _VALIDATION_PAIRS에 등록된 페어 — 후보 스캔에서 제외
_EXISTING_PAIRS: set[tuple[str, str]] = {
    ("ukraine",          "ZW=F"),
    ("bab_el_mandeb",    "CL=F"),
    ("middle_east",      "GLD"),
    ("korean_peninsula", "KRW=X"),
    ("north_korea",      "KRW=X"),
    ("taiwan_strait",    "TSM"),
    ("east_china_sea",   "ITA"),
    ("malacca",          "NG=F"),
    # P4-4 승인 룰 (2026-05-30)
    ("taiwan_strait",    "SOXX"),   # taiwan_strait_conflict_to_soxx
    ("south_china_sea",  "ITA"),    # south_china_sea_to_defense (severity 교정)
}

# Cascade 룰 → Granger 검증 페어 정의
# chain_input 룰(중간 단계)은 제외, 1차 트리거 룰만 검증
_VALIDATION_PAIRS: list[dict] = [
    {
        "rule_id":   "ukraine_conflict_to_wheat",
        "region":    "ukraine",
        "ticker":    "ZW=F",
        "direction": "up",
        "theory":    "Resource Weaponization (Hirschman 1945)",
        "note":      "우크라이나 분쟁 강도가 글로벌 밀 공급 차질 우려로 선물가에 전이",
    },
    {
        "rule_id":   "bab_el_mandeb_tension_to_oil",
        "region":    "bab_el_mandeb",
        "ticker":    "CL=F",
        "direction": "up",
        "theory":    "SLOC 차단 → 자원무기화 (Mahan 1890 + Hirschman 1945)",
        "note":      "홍해·바브엘만데브 봉쇄 위협이 원유 공급 차질 프리미엄을 형성",
    },
    {
        "rule_id":   "middle_east_conflict_to_gold",
        "region":    "middle_east",
        "ticker":    "GLD",
        "direction": "up",
        "theory":    "Risk-off → 안전자산 도피 (Kahneman & Tversky)",
        "note":      "중동 긴장 고조 시 금 ETF 수요 증가 — 리스크오프 전형 패턴",
    },
    {
        "rule_id":   "korean_peninsula_to_krw",
        "region":    "korean_peninsula",
        "ticker":    "KRW=X",
        "direction": "up",
        "theory":    "Alliance Dilemma (Snyder 1984)",
        "note":      "한반도 긴장이 원/달러 환율 상승(원화 약세) 유발 여부 검증",
    },
    {
        "rule_id":   "north_korea_missile_to_krw",
        "region":    "north_korea",
        "ticker":    "KRW=X",
        "direction": "up",
        "theory":    "Alliance Dilemma / A2AD",
        "note":      "북한 도발(고강도)과 한반도 일반 시위의 시장 반응 차이 비교",
    },
    {
        "rule_id":   "taiwan_strait_to_tsm",
        "region":    "taiwan_strait",
        "ticker":    "TSM",
        "direction": "down",
        "theory":    "Weaponized Interdependence (Farrell & Newman 2019)",
        "note":      "반도체 공급망 집중 → 대만해협 긴장이 TSMC 주가로 직접 전이",
    },
    {
        "rule_id":   "east_china_sea_to_defense",
        "region":    "east_china_sea",
        "ticker":    "ITA",
        "direction": "up",
        "theory":    "A2/AD 위협 → 방산투자 확대 (Biddle 2001)",
        "note":      "동중국해 긴장이 글로벌 방산주(ITA ETF) 수요에 미치는 영향",
    },
    {
        "rule_id":   "malacca_to_lng",
        "region":    "malacca",
        "ticker":    "NG=F",
        "direction": "up",
        "theory":    "SLOC 취약성 (Mahan 1890) — 말라카 LNG 의존도",
        "note":      "말라카 해협 분쟁이 아시아 LNG 현물가에 미치는 영향",
    },
]

# ── 분석 기간 (이벤트 아카이브 × 거시지표 겹치는 구간) ───────────────────────
_START_DATE = date(2024, 6, 1)
_END_DATE   = date.today()  # 항상 오늘까지 분석

# Granger 검정 최대 지연일 (거래일 1주)
_MAX_LAG = 5


@dataclass
class GrangerResult:
    rule_id:   str
    region:    str
    ticker:    str
    direction: str
    p_value:   float | None   # 최적 지연에서의 F-test p-value
    best_lag:  int | None     # 가장 유의한 지연일
    n_obs:     int            # 분석에 사용된 관측값 수
    supported: bool           # p < 0.05
    theory:    str
    note:      str
    # 극단 이벤트 분석 결과 (상위 25% 이벤트 → 다음 날 수익률)
    extreme_return_pct:   float | None = None  # 극단 이벤트 다음 날 평균 수익률 %
    normal_return_pct:    float | None = None  # 일반 이벤트 다음 날 평균 수익률 %
    n_extreme_events:     int = 0
    extreme_threshold_sv: float | None = None  # 극단 임계 severity
    error:     str | None = None  # 오류 발생 시 메시지


# ── 수집 커버리지 게이트 (B01 수리, 2026-07-14) ───────────────────────────────
#
#  무엇이 문제였나
#  ─────────────
#  reindex(fill_value=0.0)가 **"수집이 없던 날"과 "사건이 0건인 날"을 같은 0으로**
#  만들었다. 실측(2026-07-14, 24개월 창 731일):
#
#      전역 이벤트가 1건이라도 있는 날   399일 (54.6%)
#      전역 이벤트가 0건인 날            332일 (45.4%)  ← 전부 "전쟁 없음"으로 투입됐다
#      그중 2025-08 ~ 2026-03            8개월 통짜 구멍 (한 건도 없음)
#
#  그래서 Granger에 들어간 IV의 절반이 실제 관측이 아니라 우리가 써넣은 0이었다.
#  현존 VERIFIED 3건 전부가 이 위에 서 있다.
#
#  진짜 0과 결측을 어떻게 가르나
#  ────────────────────────────
#  **전역 이벤트 수가 신호다.** 수집이 돌던 구간에는 매일 수백~수천 건이 들어온다.
#  어느 날 전 세계 이벤트가 0건이라면 그날 세계가 평화로웠던 게 아니라 **그날 수집이
#  없었던 것**이다. 따라서:
#
#      전역 이벤트 ≥1건인 날 + 이 지역엔 없음  →  0.0   (진짜 0. 사건이 안 일어났다)
#      전역 이벤트 0건인 날                    →  NaN   (결측. 재지 못했다)
#
#  NaN은 하류에서 저절로 정직해진다 — Granger 직전 pd.concat(...).dropna()가 그 날을
#  검정에서 빼기 때문이다. 0은 빠지지 않는다. 그게 위조와 결측의 차이다.
#
#  그리고 결측이 임계를 넘으면 0건을 반환하지 않고 **던진다**(InsufficientCoverageError).
#  "관계 없다"와 "못 쟀다"는 다른 사실이고, 조용히 0을 돌려주면 둘이 같아진다.
#  (FIRMS 사고와 정확히 같은 병 — 07-13 journal 참조.)
#
class InsufficientCoverageError(RuntimeError):
    """검정 창의 수집 공백이 임계를 넘었다 — 검정을 성립시키지 않는다.

    상위 러너들은 이 예외를 잡아 결과의 `error` 필드에 기록한다. 그 결과는
    p_value=None·supported=False로 남아 **"검정했으나 관계 없음"과 구별된다.**
    """


@lru_cache(maxsize=16)
def _coverage_days(start_iso: str, end_iso: str) -> frozenset[str]:
    """이 창에서 **수집이 실재한 날** 집합.

    ⚠️ [B01 위원회 2026-07-14 — 반박석 적발] 문턱이 '≥1건'이면 가드가 자기 병을 다시 만든다.
    실측: 수집일로 인정된 444일 중 **전역 <10건인 날이 19일, <100건인 날이 48일**이다.
    정상 수집일의 일평균은 625건이다 — 전역 3건 들어온 날은 수집이 정상이었던 게 아니라
    **잡이 거의 실패한 날**이다. 그런데 '≥1건' 문턱은 그날을 "수집 정상"으로 확정하고,
    그러면 그날 8개 지역 전부의 0이 **"진짜 0"으로 주조된다.** B01이 죽인 위조를 B01의
    게이트가 48일치 되살린다 — 폐기 원장 패턴 E(자기 표적을 놓치는 가드)의 네 번째 실사례.

    처방: 절대 문턱(1건)이 아니라 **정상 수집일 대비 상대 문턱**. 창 내 일별 건수의
    중앙값 대비 _COVERAGE_MIN_RATIO 미만인 날은 수집이 온전했다고 보지 않는다 → NaN.
    중앙값을 쓰는 이유는 구멍(0건인 날)이 평균을 끌어내려 문턱을 스스로 낮추기 때문이다.
    """
    con = sqlite3.connect(_DB_PATH)
    try:
        rows = con.execute(
            "SELECT DATE(timestamp) AS day, COUNT(*) AS n FROM event_archive "
            "WHERE DATE(timestamp) BETWEEN ? AND ? GROUP BY day",
            (start_iso, end_iso),
        ).fetchall()
    finally:
        con.close()

    counts = {r[0]: int(r[1]) for r in rows if r[0]}
    if not counts:
        return frozenset()

    # 문턱: 비어있지 않은 날들의 중앙값 × ratio (0건인 날은 애초에 후보가 아니라 제외)
    ordered = sorted(counts.values())
    median = ordered[len(ordered) // 2]
    floor = max(1, int(median * _COVERAGE_MIN_RATIO))

    covered = frozenset(d for d, n in counts.items() if n >= floor)
    thin = len(counts) - len(covered)
    if thin:
        logger.warning(
            "[커버리지] 부분 수집일 %d일을 결측으로 강등 — 전역 건수 < %d "
            "(정상일 중앙값 %d의 %.0f%%). 잡이 거의 실패한 날을 '사건 0건'으로 "
            "주조하지 않는다.", thin, floor, median, _COVERAGE_MIN_RATIO * 100,
        )
    return covered


def apply_coverage(raw: pd.Series, idx: pd.DatetimeIndex,
                   covered: frozenset[str], label: str,
                   max_missing_share: float = _MAX_MISSING_SHARE) -> pd.Series:
    """일별 원계열을 커버리지 인식 계열로 만든다 (수집 공백 = NaN, 진짜 0 = 0.0).

    순수 함수(DB 없음) — 회귀 테스트가 이 판정을 직접 검증한다.
    결측 비율이 max_missing_share를 넘으면 InsufficientCoverageError.
    """
    series = raw.reindex(idx).astype(float)  # 원계열에 없는 날은 일단 전부 NaN
    covered_mask = pd.Series(
        [d.strftime("%Y-%m-%d") in covered for d in idx], index=idx
    )

    # 수집된 날인데 이 계열엔 이벤트가 없다 → 진짜 0 (사건이 안 일어난 것)
    series = series.mask(covered_mask & series.isna(), 0.0)
    # 수집이 없던 날은 NaN 그대로 — 여기에 0을 쓰는 것이 위조였다

    n = len(series)
    n_missing = int(series.isna().sum())
    share = (n_missing / n) if n else 1.0

    if share > max_missing_share:
        raise InsufficientCoverageError(
            f"[커버리지] {label}: 검정 창 {n}일 중 **수집 공백 {n_missing}일"
            f"({share:.1%})** — 임계 {max_missing_share:.0%} 초과. 검정 미수행. "
            f"구 동작은 이 공백을 0(=사건 없음)으로 채워 넣었다. "
            f"이것은 '관계 없음'이 아니라 '측정 불가'다 — 소스 최신화(data_gap)가 유일한 해소."
        )

    logger.info("[커버리지] %s: %d일 중 관측 %d · 결측 %d(%.1f%%)",
                label, n, n - n_missing, n_missing, share * 100)
    return series


# ── 이벤트 시계열 구축 ────────────────────────────────────────────────────────

# event_archive region_code 별칭 매핑 — hypothesis_extractor와 DB 코드 불일치 보정
_REGION_ALIAS: dict[str, str] = {
    "eastern_europe": "ukraine",  # DB에 ukraine으로 저장됨
}


def _load_event_series(region: str, start: date, end: date,
                       country: str | None = None) -> pd.Series:
    """event_archive에서 region별 일별 severity 합산 시계열을 반환한다.

    country: 지정 시 payload.country가 그 국가인 이벤트만 집계(A-1 필터). IV가 특정 국가를
        지목한 경우 구성타당도 게이트가 결정 — region에 섞인 타국 이벤트를 배제해 순수
        대상 시계열을 뽑는다. 예: "북한 도발"→country="North Korea"면 korean_peninsula의
        남한 시위를 배제하고 북한 미사일만 센다.
    """
    region = _REGION_ALIAS.get(region, region)  # 별칭 보정
    con = sqlite3.connect(_DB_PATH)
    where = "region_code = ? AND DATE(timestamp) BETWEEN ? AND ?"
    params: list = [region, start.isoformat(), end.isoformat()]
    if country:
        where += " AND json_extract(payload, '$.country') = ?"
        params.append(country)
    df = pd.read_sql_query(
        f"""
        SELECT DATE(timestamp) AS day,
               SUM(severity)   AS sev_sum,
               COUNT(*)        AS cnt
        FROM event_archive
        WHERE {where}
        GROUP BY day
        ORDER BY day
        """,
        con,
        params=tuple(params),
        parse_dates=["day"],
    )
    con.close()

    if df.empty:
        return pd.Series(dtype=float, name="event_severity")

    idx = pd.date_range(start, end, freq="D")
    # [B01 수리] 수집 공백은 NaN, 수집된 날의 무사건은 0.0 — 아래 apply_coverage 참조.
    # 구 코드: reindex(idx, fill_value=0.0) ← 8개월 데이터 공백을 "전쟁 없음"으로 위조
    covered = _coverage_days(start.isoformat(), end.isoformat())
    label = f"event_severity[{region}{'/' + country if country else ''}]"
    series = apply_coverage(df.set_index("day")["sev_sum"], idx, covered, label)
    series.name = "event_severity"

    nonzero = int((series > 0).sum())

    # ── stale vs sparse 진단 (평가 위원회 2026-07-06) ──────────────────────────
    # 낮은 n의 원인을 구별한다: 이벤트가 실제로 드문가(sparse), 아니면 소스가 낡아
    # 창의 최근 구간이 통째로 비었나(stale)? reindex fill_value=0.0이 데이터 공백을
    # "이벤트 없음"으로 위조하므로, today() 앵커 창에서 stale이 sparse로 오진될 수 있다
    # (미사일: CNS 소스 2024-11 정체 → 24mo 창의 83%가 데이터 공백). 오진 시 처방이
    # 갈린다 — sparse는 방법(주간전환·구조적 라우팅), stale은 소스 최신화가 답이다.
    last_data = df["day"].max().date()
    stale_gap_days = (end - last_data).days
    if nonzero < 10 and stale_gap_days > 90:
        logger.warning(
            "[stale] region=%s: 최신 데이터 %s, 창 종료 %s → 최근 %d일 데이터 공백. "
            "낮은 n(비제로 %d일)은 sparse가 아니라 stale — lookback 확대 아닌 소스 최신화 대상.",
            region, last_data, end, stale_gap_days, nonzero,
        )

    # sparse 지역 (비제로 일수 < 10): 주간 집계로 자동 전환해 Granger 분산 확보.
    # ⚠️ 이 스위치는 lookback 종속이다 — 창을 넓히면 비제로일이 임계 10을 넘겨 조용히
    #    꺼지고, 대부분이 0인 일별 계열에 Granger가 돌아 식별이 오히려 약해진다. lookback
    #    확대 논의 시 이 결합을 반드시 함께 검토할 것(위원회 2026-07-06, granger_thresholds.yaml).
    if nonzero < 10:
        # [B01 수리] min_count=1 — pandas의 sum()은 기본적으로 NaN을 0으로 세므로,
        # 통째로 결측인 주가 "그 주엔 사건 0건"으로 되살아난다. 위조를 여기서 다시
        # 만들지 않으려면 관측이 하나도 없는 주는 NaN으로 남겨야 한다.
        series = series.resample("W").sum(min_count=1)
        series.name = "event_severity_weekly"

    return series


def _load_extreme_event_series(
    region: str,
    start: date,
    end: date,
    p_quantile: float = 0.90,
) -> pd.Series | None:
    """
    [B8] P90 극단 이벤트 시계열.

    이론적 근거 (Farrell & Newman 2019 임계 효과):
    평균 분쟁 강도는 시장에 신호를 주지 않는다. 임계값을 넘는 극단 사건만
    공급망·투자 심리를 통해 시장으로 전이된다. 따라서 Granger 독립변수를
    전체 severity 대신 P90 초과분(excess severity)으로 대체하면 비선형 신호를
    선형 검정에서 포착할 수 있다.

    반환: 임계값 초과분 시계열 (기본값 미달 시 None).
    반환 시리즈가 일별이므로 시장 시계열도 일별 유지 가능 (고빈도 종속변수).
    """
    base = _load_event_series(region, start, end)
    if base is None or len(base) == 0:
        return None

    # weekly로 집계된 sparse 시리즈는 극단 검정 대상 아님 (관측 부족)
    if "weekly" in str(base.name):
        return None

    nonzero = base[base > 0]
    if len(nonzero) < 20:  # 비제로 이벤트 최소 20일 필요
        return None

    threshold = float(nonzero.quantile(p_quantile))
    if threshold <= 0:
        return None

    # 임계값 초과분: 일상 이벤트 노이즈 제거, 극단 신호만 보존
    extreme = (base - threshold).clip(lower=0)
    extreme.name = "event_severity_p90"

    if (extreme > 0).sum() < 10:
        return None

    return extreme


def _load_global_conflict_series(
    start: date, end: date, exclude: list[str] | None = None,
) -> pd.Series:
    """
    [B4] 전세계 일별 분쟁 강도 합산 시계열 — 사건→사건 Granger의 통제변수(Z).

    공통 충격(계절성·글로벌 불안정)이 여러 지역 분쟁을 동시에 움직이는 교란을
    통제하기 위해, 검정 대상 두 지역을 제외한 전세계 severity 합산을 사용한다.
    """
    region = _REGION_ALIAS  # noqa: 별칭 일관성 참조
    exclude = [_REGION_ALIAS.get(r, r) for r in (exclude or [])]
    con = sqlite3.connect(_DB_PATH)
    placeholders = ",".join("?" * len(exclude)) if exclude else ""
    where_excl = f"AND region_code NOT IN ({placeholders})" if exclude else ""
    df = pd.read_sql_query(
        f"""
        SELECT DATE(timestamp) AS day, SUM(severity) AS sev_sum
        FROM event_archive
        WHERE region_code IS NOT NULL
          AND DATE(timestamp) BETWEEN ? AND ?
          {where_excl}
        GROUP BY day
        ORDER BY day
        """,
        con,
        params=(start.isoformat(), end.isoformat(), *exclude),
        parse_dates=["day"],
    )
    con.close()
    if df.empty:
        return pd.Series(dtype=float, name="global_conflict")
    idx = pd.date_range(start, end, freq="D")
    # [B01 수리] 통제변수 Z도 같은 위조를 겪었다. 통제변수가 가짜 0이면 통제 자체가
    # 가짜다 — 오히려 교란을 "통제했다"고 주장하며 편의를 주입한다.
    covered = _coverage_days(start.isoformat(), end.isoformat())
    series = apply_coverage(df.set_index("day")["sev_sum"], idx, covered, "global_conflict")
    series.name = "global_conflict"
    return series


# ── 시장 시계열 구축 ──────────────────────────────────────────────────────────

def _load_fred_series(indicator: str, start: date, end: date) -> pd.Series | None:
    """historical_macro_indices에서 일별 % 변동 시계열을 반환한다."""
    con = sqlite3.connect(_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT date, value
        FROM historical_macro_indices
        WHERE indicator = ?
          AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        con,
        params=(indicator, start.isoformat(), end.isoformat()),
        parse_dates=["date"],
    )
    con.close()

    if len(df) < 30:
        logger.warning("[correlation] FRED %s: 데이터 부족 (%d행)", indicator, len(df))
        return None

    # [B01 수리] 구 코드: .asfreq("D").ffill()
    #   거래일 계열을 일별로 늘리고 주말·휴일을 직전 종가로 채웠다. 그 다음 pct_change를
    #   하면 주말마다 **수익률 0%가 창조된다** — 시장이 "움직이지 않았다"는 관측이 아니라
    #   애초에 열리지 않은 날이다. DV의 31~33%가 이 가짜 0%였다(STATUS 실측).
    #   거짓 0은 분산을 죽이고 자기상관을 만들어 Granger를 양쪽으로 오염시킨다.
    #
    #   처방: 늘리지 않는다. 실제 거래일 관측에서만 수익률을 계산한다. 이벤트 계열과의
    #   결합은 pd.concat(...).dropna()가 알아서 거래일에 맞춘다(비거래일은 검정에서 빠진다).
    series = df.set_index("date")["value"].sort_index()
    pct = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    pct.name = "market_return"
    return pct


async def _download_yfinance(ticker: str, start: date, end: date) -> pd.Series | None:
    """yfinance에서 일별 종가 % 변동 시계열을 반환한다."""
    try:
        import yfinance as yf  # requirements.txt에 이미 포함
        df = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: yf.download(
                ticker,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=True,
                progress=False,
            ),
        )
        if df is None or len(df) < 30:
            logger.warning("[correlation] yfinance %s: 데이터 부족", ticker)
            return None

        close = df["Close"].squeeze()
        pct = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        pct.index = pct.index.normalize()
        pct.name = "market_return"
        return pct
    except Exception as exc:
        logger.warning("[correlation] yfinance %s 실패: %s", ticker, exc)
        return None


async def _get_market_series(ticker: str, start: date, end: date) -> pd.Series | None:
    """FRED DB 우선 → yfinance 폴백으로 시장 시계열을 반환한다. (PERF-1: 6h TTL 캐시)"""
    cache_key = (ticker, start.isoformat(), end.isoformat())
    cached = _cache_get(_market_cache, cache_key)
    if cached is not None:
        logger.debug("[correlation] market_cache HIT %s", ticker)
        return cached

    fred_id = _TICKER_TO_FRED.get(ticker)
    if fred_id:
        series = _load_fred_series(fred_id, start, end)
        if series is not None and len(series) >= 30:
            _cache_set(_market_cache, cache_key, series, _MARKET_TTL)
            return series

    series = await _download_yfinance(ticker, start, end)
    if series is not None:
        _cache_set(_market_cache, cache_key, series, _MARKET_TTL)
    return series


# ── Granger 검정 ──────────────────────────────────────────────────────────────

def _adf_stationary(series: pd.Series, alpha: float = 0.05) -> bool | None:
    """
    [B1] ADF 단위근 검정으로 정상성을 판정한다.

    H0: 단위근 존재(비정상). p < alpha → H0 기각 → 정상.
    검정 불가(표본 부족·분산 0) 시 None 반환.
    """
    s = series.dropna()
    if len(s) < 20 or s.std() == 0:
        return None
    try:
        from statsmodels.tsa.stattools import adfuller
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pval = adfuller(s, autolag="AIC")[1]
        return bool(pval < alpha)
    except Exception:
        return None


def _run_granger(
    event_series: pd.Series,
    market_series: pd.Series,
    max_lag: int = _MAX_LAG,
) -> tuple[float | None, int | None, int, float | None, dict]:
    """
    Granger **선행성(precedence)** F-test. (p_value, best_lag, n_obs, f_statistic, meta) 반환.

    ⚠️ 학술적 주의 (검증층 정직 격하):
      Granger 인과는 **예측적 선행성**이지 구조적·반사실적 인과가 아니다.
      본 검정은 **양변량**이며 **교란변수를 통제하지 않는다** (B3 조건부 Granger 차기).
      유의 결과는 "인과추론 사다리"의 '선행성' 칸까지만 주장 가능.

    적용된 계량 가드:
      [B1] ADF 정상성 검정 → 비정상이면 1차 차분 (Granger-Newbold 1974 허위회귀 방지)
      [B2] lag = AIC 기준 사전 고정 (min-p 명세탐색 폐기 → p값 의미 보존)

    statsmodels grangercausalitytests: [Y, X] 컬럼 순서. H0: X 과거값이 Y 예측에 무의미.
    meta: {differenced, lag_method, stationary_y_pre, stationary_x_pre}
    """
    meta: dict = {"differenced": False, "lag_method": "AIC",
                  "bivariate_uncontrolled": True}
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
        from statsmodels.tsa.vector_ar.var_model import VAR

        combined = pd.concat(
            [market_series.rename("Y"), event_series.rename("X")], axis=1
        ).dropna()

        if len(combined) < max_lag + 20:
            logger.warning("[correlation] 관측값 부족: %d", len(combined))
            return None, None, len(combined), None, meta
        if combined["X"].std() == 0:
            logger.warning("[correlation] 이벤트 분산=0")
            return None, None, len(combined), None, meta

        # ── [B1] 정상성 검정 → 컬럼별 독립 1차 차분 ────────────────────────
        # 시장 Y는 이미 수익률(pct_change, 정상)인 경우가 많으므로 컬럼별로 판정해
        # 비정상인 컬럼만 차분한다. 두 컬럼 일괄 차분은 정상 컬럼을 과차분(over-difference).
        y_stat = _adf_stationary(combined["Y"])
        x_stat = _adf_stationary(combined["X"])
        meta["stationary_y_pre"] = y_stat
        meta["stationary_x_pre"] = x_stat
        diffed_cols = []
        if x_stat is False:
            combined["X"] = combined["X"].diff()
            diffed_cols.append("X")
        if y_stat is False:
            combined["Y"] = combined["Y"].diff()
            diffed_cols.append("Y")
        if diffed_cols:
            combined = combined.dropna()
            meta["differenced"] = True
            meta["differenced_cols"] = diffed_cols
            if len(combined) < max_lag + 20 or combined["X"].std() == 0:
                logger.warning("[correlation] 차분 후 관측값 부족: %d", len(combined))
                return None, None, len(combined), None, meta

        # ── [B2] lag = AIC 사전 고정 (min-p 탐색 폐기) ─────────────────────
        best_lag = 1
        try:
            max_aic_lag = min(max_lag, len(combined) // 5)
            if max_aic_lag >= 1:
                var_model = VAR(combined[["Y", "X"]])
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    lag_order = var_model.select_order(maxlags=max_aic_lag)
                aic = lag_order.aic
                best_lag = int(aic) if aic and aic >= 1 else 1
        except Exception:
            best_lag = 1

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = grangercausalitytests(
                combined[["Y", "X"]], maxlag=best_lag, verbose=False
            )

        # AIC가 고른 lag의 결과만 사용 (min-p 탐색 안 함)
        res = results[best_lag][0]["ssr_ftest"]
        p_value = float(res[1])
        f_stat  = float(res[0])

        logger.debug(
            "[correlation] Granger lag=%d(AIC) p=%.4f F=%.3f n=%d diff=%s",
            best_lag, p_value, f_stat, len(combined), meta["differenced"],
        )
        return p_value, best_lag, len(combined), round(f_stat, 3), meta

    except Exception as exc:
        logger.error("[correlation] Granger 검정 실패: %s", exc)
        return None, None, 0, None, meta


# ── [B3] 조건부 Granger (통제변수) ────────────────────────────────────────────

# 통제변수 후보: 글로벌 위험 선호(VIX) — 지정학 충격과 시장을 동시에 움직이는 공통 교란.
# VIX 실패 시 S&P500(시장 전체 움직임)로 대체.
_CONTROL_CANDIDATES: list[tuple[str, str]] = [("^VIX", "VIX"), ("SPY", "S&P500")]


async def _get_control_series(start: date, end: date) -> tuple[pd.Series | None, str | None]:
    """[B3] 조건부 Granger용 통제변수 시계열(일별 % 변동)을 반환한다."""
    for ticker, label in _CONTROL_CANDIDATES:
        s = await _download_yfinance(ticker, start, end)
        if s is not None and len(s) >= 30:
            s = s.copy()
            s.name = "Z"
            return s, label
    return None, None


def _run_conditional_granger(
    event_series: pd.Series,
    market_series: pd.Series,
    control_series: pd.Series,
    max_lag: int = _MAX_LAG,
) -> tuple[float | None, int | None, int, float | None, dict]:
    """
    [B3] 통제변수 Z **조건부** Granger — VAR.test_causality.

    X→Y 선행성을 Z(글로벌 위험 VIX) 통제 하에 검정한다.
    3변량 VAR에서 X의 시차계수가 Y 방정식에서 결합 0인지 F-검정 →
    Y 자기시차 + Z를 통제한 뒤에도 X가 Y 예측에 기여하는지 본다.
    이로써 양변량 교란(공통 위험요인) 문제를 완화한다 (여전히 인과 단정 불가).

    반환: (p_value, best_lag, n_obs, f_statistic, meta)
    """
    meta: dict = {"controlled": True, "lag_method": "AIC",
                  "differenced": False, "bivariate_uncontrolled": False}
    try:
        from statsmodels.tsa.vector_ar.var_model import VAR

        combined = pd.concat(
            [market_series.rename("Y"), event_series.rename("X"),
             control_series.rename("Z")],
            axis=1,
        ).dropna()

        if len(combined) < max_lag + 25:
            return None, None, len(combined), None, meta
        if combined["X"].std() == 0:
            return None, None, len(combined), None, meta

        # [B1] 컬럼별 독립 차분
        diffed = []
        for col in ("X", "Y", "Z"):
            if _adf_stationary(combined[col]) is False:
                combined[col] = combined[col].diff()
                diffed.append(col)
        if diffed:
            combined = combined.dropna()
            meta["differenced"] = True
            meta["differenced_cols"] = diffed
            if len(combined) < max_lag + 25 or combined["X"].std() == 0:
                return None, None, len(combined), None, meta

        # [B2] AIC 사전 고정 lag
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = VAR(combined[["Y", "X", "Z"]])
            sel = model.select_order(maxlags=min(max_lag, len(combined) // 6))
            best_lag = int(sel.aic) if sel.aic and sel.aic >= 1 else 1
            res = model.fit(best_lag)
            test = res.test_causality("Y", ["X"], kind="f")

        p_value = float(test.pvalue)
        f_stat  = float(test.test_statistic)
        logger.debug(
            "[correlation] 조건부 Granger(Z통제) lag=%d p=%.4f F=%.3f n=%d diff=%s",
            best_lag, p_value, f_stat, len(combined), meta["differenced"],
        )
        return p_value, best_lag, len(combined), round(f_stat, 3), meta

    except Exception as exc:
        logger.warning("[correlation] 조건부 Granger 실패: %s", exc)
        return None, None, 0, None, meta


def _run_extreme_correlation(
    event_series: pd.Series,
    market_series: pd.Series,
    top_pct: float = 0.25,
) -> dict:
    """
    극단 이벤트(상위 top_pct) 발생일과 시장 수익률의 관계를 분석한다.

    지정학 충격은 비선형: 평균 이벤트는 시장에 영향 없고,
    임계값을 넘는 극단 사건만 전이를 일으킨다 (Farrell & Newman 2019).
    이 함수는 그 비선형성을 측정한다.

    반환:
      avg_return_extreme: 극단 이벤트일 다음 날 평균 수익률
      avg_return_normal:  일반 이벤트일 다음 날 평균 수익률
      n_extreme:          극단 이벤트 관측 수
    """
    combined = pd.concat(
        [market_series.rename("Y"), event_series.rename("X")], axis=1
    ).dropna()

    if len(combined) < 30 or combined["X"].std() == 0:
        return {"avg_return_extreme": None, "avg_return_normal": None, "n_extreme": 0}

    threshold = combined["X"].quantile(1 - top_pct)
    nonzero = combined["X"] > 0
    extreme = combined["X"] >= threshold

    # 다음 날 수익률 기준 비교 (lag=1)
    next_day_return = combined["Y"].shift(-1)

    avg_ext = float(next_day_return[extreme & nonzero].mean()) if (extreme & nonzero).sum() > 0 else None
    avg_norm = float(next_day_return[~extreme & nonzero].mean()) if (~extreme & nonzero).sum() > 0 else None

    return {
        "avg_return_extreme": round(avg_ext * 100, 4) if avg_ext is not None else None,
        "avg_return_normal":  round(avg_norm * 100, 4) if avg_norm is not None else None,
        "n_extreme":          int((extreme & nonzero).sum()),
        "threshold_severity": round(float(threshold), 1),
    }


# ── 전체 룰 검증 ─────────────────────────────────────────────────────────────

async def run_correlation_analysis(
    start: date = _START_DATE,
    end:   date = _END_DATE,
) -> list[dict]:
    """
    정의된 모든 Validation Pair에 대해 Granger 검정을 실행하고 결과를 반환한다.

    반환 예시:
    [
      {
        "rule_id": "ukraine_conflict_to_wheat",
        "region": "ukraine",
        "ticker": "ZW=F",
        "p_value": 0.031,
        "best_lag": 2,
        "n_obs": 482,
        "supported": true,
        "theory": "Resource Weaponization ...",
        "note": "..."
      },
      ...
    ]
    """
    results: list[GrangerResult] = []

    for pair in _VALIDATION_PAIRS:
        rule_id = pair["rule_id"]
        region  = pair["region"]
        ticker  = pair["ticker"]

        logger.info("[correlation] %s 검증 중 (region=%s, ticker=%s)", rule_id, region, ticker)

        try:
            # 두 시계열 비동기 병렬 로드
            event_task  = asyncio.get_event_loop().run_in_executor(
                None, _load_event_series, region, start, end
            )
            market_task = _get_market_series(ticker, start, end)
            event_series, market_series = await asyncio.gather(event_task, market_task)

            if market_series is None or len(market_series) < 30:
                results.append(GrangerResult(
                    rule_id=rule_id, region=region, ticker=ticker,
                    direction=pair["direction"], p_value=None, best_lag=None,
                    n_obs=0, supported=False,
                    theory=pair["theory"], note=pair["note"],
                    error="시장 데이터 로드 실패",
                ))
                continue

            if len(event_series) == 0 or event_series.sum() == 0:
                results.append(GrangerResult(
                    rule_id=rule_id, region=region, ticker=ticker,
                    direction=pair["direction"], p_value=None, best_lag=None,
                    n_obs=0, supported=False,
                    theory=pair["theory"], note=pair["note"],
                    error=f"region={region} 이벤트 없음",
                ))
                continue

            p_val, best_lag, n_obs, _f, _meta = _run_granger(event_series, market_series)

            # 극단 이벤트 비선형 분석 (Granger 비유의 이유 진단)
            extreme = _run_extreme_correlation(event_series, market_series)

            results.append(GrangerResult(
                rule_id=rule_id, region=region, ticker=ticker,
                direction=pair["direction"],
                p_value=round(p_val, 4) if p_val is not None else None,
                best_lag=best_lag,
                n_obs=n_obs,
                supported=(p_val is not None and p_val < 0.05),
                theory=pair["theory"],
                note=pair["note"],
                extreme_return_pct=extreme.get("avg_return_extreme"),
                normal_return_pct=extreme.get("avg_return_normal"),
                n_extreme_events=extreme.get("n_extreme", 0),
                extreme_threshold_sv=extreme.get("threshold_severity"),
            ))

        except Exception as exc:
            logger.error("[correlation] %s 오류: %s", rule_id, exc)
            results.append(GrangerResult(
                rule_id=rule_id, region=region, ticker=ticker,
                direction=pair["direction"], p_value=None, best_lag=None,
                n_obs=0, supported=False,
                theory=pair["theory"], note=pair["note"],
                error=str(exc),
            ))

    return [asdict(r) for r in results]


# ── 요약 통계 ────────────────────────────────────────────────────────────────

def summarize_results(results: list[dict]) -> dict:
    """검정 결과를 요약해 학습용 해설을 붙인다."""
    valid     = [r for r in results if r["p_value"] is not None]
    supported = [r for r in valid if r["supported"]]
    n_total   = len(results)
    n_valid   = len(valid)
    n_sup     = len(supported)

    # 극단 이벤트 분석: 방향 일치 여부 (예: direction=up이면 extreme_return > normal_return 기대)
    directional_match = 0
    directional_valid = 0
    for r in valid:
        ext = r.get("extreme_return_pct")
        norm = r.get("normal_return_pct")
        if ext is None or norm is None:
            continue
        directional_valid += 1
        direction = r.get("direction", "up")
        diff = ext - norm
        if (direction == "up" and diff > 0) or (direction == "down" and diff < 0):
            directional_match += 1

    directional_rate = round(directional_match / directional_valid, 2) if directional_valid else 0

    return {
        "total_rules":          n_total,
        "tested":               n_valid,
        "granger_supported":    n_sup,
        "granger_not_supported":n_valid - n_sup,
        "granger_support_rate": round(n_sup / n_valid, 2) if n_valid else 0,
        "extreme_directional_match": directional_match,
        "extreme_directional_rate":  directional_rate,
        "analysis_period": f"{_START_DATE} ~ {_END_DATE}",
        "method":          "Granger Causality F-test (statsmodels, maxlag=5, daily severity)",
        "key_finding": (
            f"일별 Granger 검정: {n_sup}/{n_valid}개 유의 (선형·평균 수준에서 관계 없음). "
            f"극단 이벤트(상위 25%) 분석: {directional_match}/{directional_valid}개 방향 일치 ({int(directional_rate*100)}%). "
            "→ 지정학 충격은 비선형(Non-linear) — 임계값 초과 사건에서만 시장 전이 발현."
        ),
        "theory_implication": (
            "Granger 비유의는 cascade 엔진의 event-specific 검증 방식을 정당화한다. "
            "Farrell & Newman(2019) 무기화된 상호의존은 '평상시 경제 압력'이 아닌 "
            "'chokepoint 봉쇄 같은 극단 충격'에서만 활성화된다는 이론과 일치."
        ),
    }


# ── P4-4 후보 스캔 ────────────────────────────────────────────────────────────

def _get_all_regions(start: date, end: date, min_events: int = 20) -> list[str]:
    """event_archive에서 이벤트가 충분한 region_code 목록을 반환한다."""
    con = sqlite3.connect(_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT region_code, COUNT(*) AS cnt
        FROM event_archive
        WHERE region_code IS NOT NULL
          AND region_code != ''
          AND DATE(timestamp) BETWEEN ? AND ?
        GROUP BY region_code
        HAVING cnt >= ?
        ORDER BY cnt DESC
        """,
        con,
        params=(start.isoformat(), end.isoformat(), min_events),
    )
    con.close()
    return df["region_code"].tolist()


@dataclass
class CandidateResult(GrangerResult):
    """Granger 스캔으로 발굴된 신규 룰 후보."""
    inferred_direction:    str   = "up"
    inferred_window_hours: int   = 48
    inferred_threshold_pct: float = 1.0
    score:                 float = 1.0   # p값 기반 — 낮을수록 유의
    ticker_label:          str   = ""


async def run_candidate_scan(
    p_threshold:       float = 0.10,  # 기존 룰 검증(0.05)보다 완화된 후보 기준
    min_extreme_events: int  = 5,
    start: date = _START_DATE,
    end:   date = _END_DATE,
) -> list[dict]:
    """
    모든 region × ticker 조합을 스캔해 유망한 Cascade 룰 후보를 반환한다.

    이미 _VALIDATION_PAIRS에 등록된 페어는 제외한다.
    후보 선별 기준:
      1. Granger p < p_threshold (기본 0.10)
      2. 또는 극단 이벤트 방향 일치 + n_extreme >= min_extreme_events

    반환: 후보 목록 (점수 오름차순 — p값 낮을수록 상위)
    """
    regions = _get_all_regions(start, end)
    candidates: list[CandidateResult] = []

    for region in regions:
        # 이벤트 시계열은 region당 한 번만 로드
        try:
            event_series = await asyncio.get_event_loop().run_in_executor(
                None, _load_event_series, region, start, end
            )
        except InsufficientCoverageError as exc:
            # [B01] 수집 공백이 임계 초과 — 이 region은 후보 스캔에서 제외한다.
            # 조용히 넘기지 않고 남긴다: 스캔에 안 나온 이유가 "신호 없음"이 아니라
            # "못 쟀음"임을 구별할 수 있어야 한다.
            logger.warning("[scan] %s 제외 — %s", region, exc)
            continue
        if len(event_series) == 0 or event_series.sum() == 0:
            continue

        for ticker, (fred_id, ticker_label) in _SCAN_TICKERS.items():
            if (region, ticker) in _EXISTING_PAIRS:
                continue

            try:
                market_series = await _get_market_series(ticker, start, end)
                if market_series is None or len(market_series) < 30:
                    continue

                p_val, best_lag, n_obs, _f, _meta = _run_granger(event_series, market_series)
                extreme = _run_extreme_correlation(event_series, market_series)

                # 후보 여부 판정
                granger_ok = p_val is not None and p_val < p_threshold
                n_ext = extreme.get("n_extreme", 0)
                ext_ret = extreme.get("avg_return_extreme")
                norm_ret = extreme.get("avg_return_normal")
                extreme_ok = (
                    n_ext >= min_extreme_events
                    and ext_ret is not None
                    and norm_ret is not None
                    and ext_ret != norm_ret
                )

                if not granger_ok and not extreme_ok:
                    continue

                # 방향 추론: 극단 이벤트 평균 수익률 부호로 판단
                inferred_dir = "up" if (ext_ret or 0.0) >= 0 else "down"

                # window_hours 추론: best_lag × 24, 최소 24, 최대 168
                inferred_window = 48
                if best_lag is not None:
                    inferred_window = min(max(best_lag * 24, 24), 168)

                # threshold_pct 추론: |극단 수익률| × 0.5, 0.5 단위 반올림, 최소 0.5
                inferred_threshold = 1.0
                if ext_ret is not None:
                    raw = abs(ext_ret) * 0.5
                    inferred_threshold = max(round(raw * 2) / 2, 0.5)

                score = p_val if p_val is not None else 0.99

                rule_id = (
                    f"{region}_to_{ticker.replace('=', '').replace('^', '').lower()}"
                )
                p_str = f"{p_val:.4f}" if p_val is not None else "N/A"
                note = (
                    f"자동 생성 후보 | Granger p={p_str} | "
                    f"극단 수익률={ext_ret:+.2f}% vs 일반={norm_ret:+.2f}%"
                    if ext_ret is not None
                    else f"자동 생성 후보 | Granger p={p_str}"
                )

                candidates.append(CandidateResult(
                    rule_id=rule_id,
                    region=region,
                    ticker=ticker,
                    direction=inferred_dir,
                    p_value=round(p_val, 4) if p_val is not None else None,
                    best_lag=best_lag,
                    n_obs=n_obs,
                    supported=(p_val is not None and p_val < 0.05),
                    theory="TODO",
                    note=note,
                    extreme_return_pct=ext_ret,
                    normal_return_pct=norm_ret,
                    n_extreme_events=n_ext,
                    extreme_threshold_sv=extreme.get("threshold_severity"),
                    inferred_direction=inferred_dir,
                    inferred_window_hours=inferred_window,
                    inferred_threshold_pct=inferred_threshold,
                    score=score,
                    ticker_label=ticker_label,
                ))

            except Exception as exc:
                logger.warning("[candidate_scan] %s × %s 오류: %s", region, ticker, exc)

    candidates.sort(key=lambda x: x.score)
    return [asdict(c) for c in candidates]


def generate_yaml_draft(candidates: list[dict], top_n: int = 10) -> str:
    """
    상위 후보를 YAML draft 형식으로 변환한다.
    ★ 인간 승인 전까지 cascade_rules.yaml에 포함하지 말 것.
    status: draft 라인을 제거해야 엔진이 룰을 인식한다.
    """
    lines = [
        "# ═══════════════════════════════════════════════════════════════════════",
        "# CASCADE RULE CANDIDATES — P4-4 자동 생성 초안",
        "# ★ 인간 승인 필수: 각 룰을 검토 후 cascade_rules.yaml로 이동할 것",
        "# ★ status: draft 라인을 제거해야 엔진이 해당 룰을 인식한다",
        f"# 생성일: {date.today().isoformat()} | "
        f"후보 수: {len(candidates)} | 상위 {min(top_n, len(candidates))}개 출력",
        "# ═══════════════════════════════════════════════════════════════════════",
        "",
    ]

    for i, c in enumerate(candidates[:top_n]):
        direction_ko = "상승" if c.get("inferred_direction") == "up" else "하락"
        name = f"{c['region']} 긴장 → {c.get('ticker_label', c['ticker'])} {direction_ko}"

        p_str = f"{c['p_value']:.4f}" if c.get("p_value") is not None else "N/A"
        granger_line = (
            f"Granger p={p_str}, lag={c.get('best_lag')}d, n={c.get('n_obs')}"
        )
        ext_ret  = c.get("extreme_return_pct")
        norm_ret = c.get("normal_return_pct")
        extreme_line = (
            f"극단 수익률 {ext_ret:+.2f}% vs 일반 {norm_ret:+.2f}% "
            f"(n_extreme={c.get('n_extreme_events', 0)})"
            if ext_ret is not None and norm_ret is not None
            else "극단 이벤트 분석 없음"
        )

        # threshold_sv는 일별 severity 합산의 75분위수 — 개별 이벤트 severity(0~100)와 단위가 다름.
        # 100 초과 시 일별 집계값으로 판단해 기본값 50을 사용한다.
        sv = c.get("extreme_threshold_sv")
        severity_min = min(int(sv), 100) if (sv is not None and sv <= 100) else 50

        lines += [
            f"# ── 후보 #{i+1} ──────────────────────────────────────────────────",
            f"# {granger_line}",
            f"# {extreme_line}",
            f"- id: {c['rule_id']}",
            f"  name: \"{name}\"  # ★ 검토 후 수정",
            "  status: draft  # ★ 이 라인 제거 전까지 엔진에서 무시됨",
            "  trigger:",
            "    source_type: conflict",
            f"    region: {c['region']}",
            f"    severity_min: {severity_min}  "
            "# 극단 이벤트 임계값 기반 자동 추정 — 검토 필요",
            "  expected_response:",
            "    source_type: market",
            f"    ticker: \"{c['ticker']}\"  # {c.get('ticker_label', '')}",
            f"    direction: {c.get('inferred_direction', 'up')}  "
            "# 극단 수익률 부호 기반 추론",
            f"    window_hours: {c.get('inferred_window_hours', 48)}  "
            "# Granger best_lag × 24",
            f"    threshold_pct: {c.get('inferred_threshold_pct', 1.0)}",
            "  chainable: true  # ★ 검토 후 수정",
            f"  chain_output: \"TODO_{c['rule_id']}\"  # ★ 입력 필요",
            "  theory:",
            "    framework: \"TODO: 이론 프레임워크\"  # ★ 입력 필요",
            "    reference: \"TODO: 참고문헌\"  # ★ 입력 필요",
            "    learning_note: >-",
            "      TODO: 학습 노트 입력 필요.",
            f"      [자동 생성 근거: {granger_line}]",
            f"      [{extreme_line}]",
            "",
        ]

    return "\n".join(lines)
