"""
[P5] 룰·사례 부패 감시 — cascade 룰북의 기대반응을 누적 데이터로 상시 반증.

데이터효용위(2026-07-12, geo-os [[20260712-data-utility-committee]]) 채택안 P5.
cascade_rules.yaml의 기대반응(ticker·direction·threshold)을 룩백 구간의 실측
트리거 전수로 재평가한다 — cascade_links는 임계 통과 성공례만 기록하므로
(선택 편향) 링크가 아니라 **트리거 이벤트 원본**에서 재계산한다.

산출은 부패 플래그(report-only)뿐이다 (v1.1 — 정비위 3보정 후 의미론):
  consistent     — 조건부 실현율 ≥ 무조건부 base rate, 룰 현행 유지
  watch          — base rate 하회하나 이항검정 비유의 — 관측 지속
  decay_flag     — base rate 유의 하회(이항 단측 p<0.05) → 인간 룰개정 리뷰 후보
  insufficient_n — 평가 가능 트리거 < 5 — 판정 유보(무변동≠부패)
룰 자동 재작성 금지(Goodhart) — YAML은 이 스크립트가 절대 만지지 않는다.
CLAUDE.md 이론 필드의 "반례" 요건을 실데이터로 채우는 상시화가 목적.

트리거 의미론은 cascade/engine.py 미러: source_type='conflict' ·
region_code · severity>=severity_min · 날짜별 최고심각도 1건 샘플링.
시장 대조는 prediction_scorer와 동일 원칙(forward window·raw 수익률·
방향 실현≠인과). 티커당 yf.download 1회 배치 — 저비용.

실행: cd backend && .venv/bin/python scripts/rule_decay_audit.py [--lookback-days 180]
배선: collect_standalone 편승, 주 1회 자체 스로틀(기존 산출물 6일 미만이면 스킵).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parent.parent
_DB = _BACKEND / "db" / "intel.db"
_RULES = _BACKEND / "config" / "cascade_rules.yaml"
_OUT = _BACKEND.parent / "exports" / "rule_decay_audit.json"

_MIN_EVALUABLE = 5      # 판정에 필요한 최소 평가 가능 트리거

# ── 3보정 (원장·룰북 정비위 2026-07-12 — 반박석 3결함 실측 채택) ──────────
# ① base rate 보정: 실현율<0.5 고정 임계는 시장 드리프트와 룰 부패를 구분 못 함
#    (KOSPI 상승장이면 모든 down 룰이 자동 decay). → 같은 티커·같은 창의 무조건부
#    방향 실현율을 기준선으로, 이항검정 유의 하회만 decay_flag.
# ② 서브임계 노이즈 대칭 제외: |pct| < _NOISE_EPS_PCT 는 방향 판정 불능(무변동) —
#    반례 63건 중 27%가 |0.5%| 미만 실측. 적중·반례 양쪽에서 대칭 제외(편향 방지).
# ③ 트리거 창 비중첩화: 연속 분쟁일 트리거의 창 중첩 = 동일 가격이동 중복 계상
#    (유사복제) → 직전 평가 트리거로부터 window일 미경과 트리거는 스킵.
_NOISE_EPS_PCT = 0.5
_DECAY_ALPHA = 0.05     # base rate 유의 하회 판정 (이항 단측)


def _load_market_rules() -> list[dict]:
    """conflict 트리거 → market 기대반응 룰만 (체인·비시장 룰은 v1 제외)."""
    rules = yaml.safe_load(_RULES.read_text(encoding="utf-8"))
    out = []
    for r in rules:
        trig, resp = r.get("trigger", {}), r.get("expected_response", {})
        if trig.get("source_type") == "conflict" and resp.get("source_type") == "market":
            out.append(r)
    return out


def _daily_triggers(con: sqlite3.Connection, region: str, sev_min: float,
                    since: date) -> list[str]:
    """events+event_archive에서 트리거 일자 목록 (날짜별 1건 — engine 샘플링 미러)."""
    days: set[str] = set()
    for table in ("events", "event_archive"):
        try:
            rows = con.execute(
                f"SELECT DISTINCT substr(timestamp,1,10) FROM {table} "
                "WHERE source_type='conflict' AND region_code=? AND severity>=? "
                "AND timestamp>=?",
                (region, sev_min, since.isoformat()),
            ).fetchall()
            days.update(r[0] for r in rows)
        except sqlite3.OperationalError:
            continue
    return sorted(days)


def _price_series(ticker: str, since: date):
    """티커 종가 시계열 1회 배치 조회 (실패 시 None)."""
    try:
        import pandas as pd
        import yfinance as yf
        df = yf.download(ticker, start=(since - timedelta(days=7)).isoformat(),
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return close.dropna()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[P5] 시세 조회 실패 %s: %s", ticker, exc)
        return None


def _window_outcome(close, day: str, window_hours: int) -> tuple[float, str] | None:
    """트리거일 이후 window 구간 수익률·방향 (forward — 미래참조 없음)."""
    import pandas as pd
    d0 = pd.Timestamp(day)
    d1 = d0 + pd.Timedelta(days=max(1, math.ceil(window_hours / 24)))
    seg0 = close[close.index >= d0]
    if seg0.empty:
        return None
    p0 = float(seg0.iloc[0])
    seg1 = close[(close.index > seg0.index[0]) & (close.index <= d1)]
    if seg1.empty or p0 == 0:
        return None                       # 창 내 후속 거래일 없음 — 평가 불능
    p1 = float(seg1.iloc[-1])
    pct = (p1 - p0) / p0 * 100.0
    return round(pct, 4), ("up" if pct > 0 else "down")


def _dedup_windows(days: list[str], window_days: int) -> list[str]:
    """보정 ③ — 직전 평가 트리거의 창이 안 끝난 트리거는 스킵(중복 계상 방지)."""
    import pandas as pd
    kept: list[str] = []
    last = None
    for d in days:
        ts = pd.Timestamp(d)
        if last is None or (ts - last).days >= window_days:
            kept.append(d)
            last = ts
    return kept


def _base_rate(close, expected: str, window_hours: int) -> tuple[float, int] | None:
    """보정 ① — 무조건부 방향 실현율: 전 거래일을 가상 트리거로 동일 창 평가.

    창 중첩 없이(window 간격 stride) 표집, 서브임계 노이즈 대칭 제외(보정 ② 동일 적용).
    """
    wd = max(1, math.ceil(window_hours / 24))
    n = match = 0
    idx = list(close.index)
    for i in range(0, len(idx) - 1, wd):
        out = _window_outcome(close, str(idx[i].date()), window_hours)
        if out is None:
            continue
        pct, realized = out
        if abs(pct) < _NOISE_EPS_PCT:
            continue
        n += 1
        match += int(realized == expected)
    return (match / n, n) if n else None


def audit(lookback_days: int = 180, db_path: Path | str = _DB) -> dict:
    from scipy.stats import binomtest
    since = date.today() - timedelta(days=lookback_days)
    con = sqlite3.connect(str(db_path))
    results = []
    try:
        series_cache: dict[str, object] = {}
        base_cache: dict[tuple, tuple | None] = {}
        for rule in _load_market_rules():
            trig, resp = rule["trigger"], rule["expected_response"]
            ticker, expected = resp["ticker"], resp["direction"]
            window_h = resp.get("window_hours", 48)
            wd = max(1, math.ceil(window_h / 24))
            days = _daily_triggers(con, trig["region"], trig.get("severity_min", 0), since)
            days_dedup = _dedup_windows(days, wd)          # 보정 ③
            if ticker not in series_cache:
                series_cache[ticker] = _price_series(ticker, since)
            close = series_cache[ticker]

            n_eval = match = thr_pass = noise_excluded = 0
            counter_examples: list[dict] = []
            if close is not None:
                for day in days_dedup:
                    out = _window_outcome(close, day, window_h)
                    if out is None:
                        continue
                    pct, realized = out
                    if abs(pct) < _NOISE_EPS_PCT:          # 보정 ② — 대칭 제외
                        noise_excluded += 1
                        continue
                    n_eval += 1
                    if realized == expected:
                        match += 1
                        if abs(pct) >= float(resp.get("threshold_pct") or 0):
                            thr_pass += 1
                    else:
                        counter_examples.append({"day": day, "realized_pct": pct})

            bkey = (ticker, expected, window_h)
            if bkey not in base_cache:
                base_cache[bkey] = _base_rate(close, expected, window_h) if close is not None else None
            base = base_cache[bkey]
            base_rate, base_n = base if base else (None, 0)

            rate = round(match / n_eval, 3) if n_eval else None
            # 보정 ① — verdict: base rate 유의 하회만 decay_flag (이항 단측)
            binom_p = None
            if n_eval >= _MIN_EVALUABLE and base_rate is not None:
                binom_p = round(binomtest(match, n_eval, base_rate,
                                          alternative="less").pvalue, 4)
                if binom_p < _DECAY_ALPHA:
                    verdict = "decay_flag"
                elif rate < base_rate:
                    verdict = "watch"        # 하회하나 비유의 — 관측 지속
                else:
                    verdict = "consistent"
            else:
                verdict = "insufficient_n"
            results.append({
                "rule_id": rule["id"], "dormant": bool(rule.get("dormant")),
                "ticker": ticker, "expected": expected,
                "triggers": len(days), "triggers_dedup": len(days_dedup),
                "evaluable": n_eval, "noise_excluded": noise_excluded,
                "direction_match": match, "realization_rate": rate,
                "base_rate": round(base_rate, 3) if base_rate is not None else None,
                "base_n": base_n, "binom_p": binom_p,
                "threshold_pass": thr_pass, "n_counter_examples": len(counter_examples),
                "counter_examples": counter_examples[-5:],   # 최근 5건만 동봉
                "verdict": verdict,
            })

        links_last = con.execute(
            "SELECT MAX(created_at) FROM cascade_links").fetchone()[0]
    finally:
        con.close()

    flagged = [r["rule_id"] for r in results if r["verdict"] == "decay_flag"]
    return {
        "schema_version": "1.1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": lookback_days,
        "rules_audited": len(results),
        "decay_flagged": flagged,
        "cascade_links_last_created": links_last,   # 엔진 유휴 관찰(부수)
        "note": ("report-only — 룰 수정은 인간 결정. 방향 실현율은 인과 입증 아님"
                 "(공통충격 미통제). decay_flag=반례 우세, 룰개정 리뷰 후보."),
        "results": results,
    }


def export(lookback_days: int = 180) -> Path:
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(audit(lookback_days), ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return _OUT


def is_fresh(max_age_days: int = 6) -> bool:
    """주 1회 스로틀 — 기존 산출물이 신선하면 스킵."""
    if not _OUT.exists():
        return False
    try:
        gen = json.loads(_OUT.read_text())["generated_at"]
        age = datetime.now(timezone.utc) - datetime.strptime(
            gen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return age.days < max_age_days
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="P5 룰 부패 감시 (report-only)")
    ap.add_argument("--lookback-days", type=int, default=180)
    args = ap.parse_args()
    p = export(args.lookback_days)
    d = json.loads(p.read_text())
    print(f"rule_decay_audit.json → {p}")
    print(f"  룰 {d['rules_audited']}개 감사 · decay_flag: {d['decay_flagged'] or '없음'}"
          f" · links 최종 생성 {d['cascade_links_last_created']}")
    for r in d["results"]:
        print(f"  {r['rule_id']}: 실현율 {r['realization_rate']} "
              f"(평가 {r['evaluable']}/{r['triggers']}) → {r['verdict']}")
