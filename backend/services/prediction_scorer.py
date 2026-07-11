"""
[Phase 10-2] 결과 채점(Prediction Scorer) — 동결된 예측을 실측과 대조.

10-1이 예측을 *동결*했다면, 10-2는 `resolve_by` 시점이 도래한 예측을 꺼내
실측 시계열과 대조해 적중/실패를 라벨한다. 이게 "엔진이 정교하게 일관되게
틀려도" 잡아내는 진실 고리의 닫힘이다.

Token-Zero: LLM 호출 없음. 채점은 전부 산술(가격 수익률·이벤트 빈도 비교).

────────────────────────────────────────────────────────────────────────────
연구자 관점에서 박아둔 4대 원칙 (사회과학 측정 엄밀성)
────────────────────────────────────────────────────────────────────────────
① 방향 적중 ≠ 인과 입증.
   "유가가 올랐다"가 맞아도, 엔진이 지목한 메커니즘(호르무즈 긴장) 때문인지는
   이 채점이 증명하지 못한다(공통원인·우연 가능). → 라벨은 '방향 실현(directional
   realization)'일 뿐이며 score_reason에 비인과 단서를 항상 남긴다.

② 데이터 부족은 MISS가 아니라 UNRESOLVED.
   엔진의 예측력 실패와 '잴 데이터가 없음'은 다른 사건이다. 후자를 MISS로 처리하면
   적중률이 부당하게 깎인다. baseline 이벤트가 빈약하면(<MIN_BASELINE) UNRESOLVED.

③ Out-of-sample 보존(미래참조 차단).
   채점 창은 created_at *이후*만 본다(가격·이벤트 모두 forward window). 결과를 미리
   아는 백필/소급 예측은 eligible_for_calibration=0으로 격리해 캘리브레이션(10-3)
   집계에서 제외한다(retrodiction이 적중률을 부풀리는 것 차단).

④ 효과 크기 vs 통계적 방향 분리.
   임계(threshold_pct)가 명시된 예측은 *방향 일치 + 크기 도달* 둘 다 충족해야 HIT.
   방향만 맞고 크기 미달이면 MISS(이유에 '방향 적중·임계 미달' 명시) — 실질 유의성
   (CLAUDE.md §9-0 ②)을 형식 유의와 섞지 않는다.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_INTEL_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# ── 채점 임계·가드 (근거 주석과 함께 상수화 — 차후 config 이관 후보) ─────────────
MIN_BASELINE_EVENTS = 5     # 이벤트 비율 변화를 논하려면 기준선이 최소 이만큼 필요 (Poisson 잡음 방어)
FLAT_EPS_PCT = 0.05         # |수익률| < 0.05% 는 사실상 무변동 — 방향 판정 보류 신호
MARKET_FETCH_BUFFER_D = 5   # 거래일 공백(주말·휴장) 보정용 양끝 버퍼

# 비인과 단서 (방향 적중이 메커니즘을 입증하지 않음 — 원칙 ①)
_MARKET_CAVEAT = "방향 실현일 뿐(메커니즘 비입증) · raw 수익률(시장요인 미통제)"
_EVENT_CAVEAT = "방향 실현일 뿐(메커니즘 비입증) · 이벤트 빈도 비교(공통충격 미통제)"


# ── 스키마 마이그레이션 (채점 결과 컬럼 보장) ───────────────────────────────────

def _ensure_score_columns(con: sqlite3.Connection) -> None:
    """prediction_log에 채점 결과 컬럼을 idempotent 추가 (기존 행은 기본값 수용)."""
    existing = {r[1] for r in con.execute("PRAGMA table_info(prediction_log)")}
    add = {
        "realized_pct":             "REAL",
        "realized_direction":       "TEXT",
        "score_reason":             "TEXT",
        # 기본 1 — 10-1의 정상 forward 예측은 모두 캘리브레이션 적격.
        # 백필/소급(retrodiction) 행만 0으로 명시 격리.
        "eligible_for_calibration": "INTEGER DEFAULT 1",
    }
    for col, decl in add.items():
        if col not in existing:
            con.execute(f"ALTER TABLE prediction_log ADD COLUMN {col} {decl}")


# ── 실측 조회 (Token-Zero 산술) ────────────────────────────────────────────────

def _fetch_market_outcome(
    ticker: str, start: date, end: date
) -> tuple[float, str] | None:
    """
    [start, end] 구간의 raw 가격 변화율(%)과 방향을 반환. 데이터 없으면 None.

    start 당일 종가(없으면 직후 첫 거래일) → end 종가(없으면 직전 거래일) 비교.
    """
    try:
        import pandas as pd
        import yfinance as yf

        df = yf.download(
            ticker,
            start=(start - timedelta(days=MARKET_FETCH_BUFFER_D)).isoformat(),
            end=(end + timedelta(days=MARKET_FETCH_BUFFER_D)).isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return None
        close = df["Close"]
        if isinstance(close, pd.DataFrame):  # 단일 티커도 가끔 2D로 옴
            close = close.iloc[:, 0]
        close = close.dropna()
        if close.empty:
            return None

        ts_start = pd.Timestamp(start)
        ts_end = pd.Timestamp(end)
        # start 이상 첫 종가 / end 이하 마지막 종가 (forward — 미래참조 차단)
        on_start = close[close.index >= ts_start]
        on_end = close[close.index <= ts_end]
        if on_start.empty or on_end.empty:
            return None
        p0 = float(on_start.iloc[0])
        p1 = float(on_end.iloc[-1])
        if p0 == 0:
            return None
        pct = (p1 - p0) / p0 * 100.0
        direction = "up" if pct > 0 else "down"
        return round(pct, 4), direction
    except Exception as exc:  # noqa: BLE001
        logger.warning("[10-2] 시장 실측 조회 실패 %s: %s", ticker, exc)
        return None


def _count_events(con: sqlite3.Connection, region: str, lo: date, hi: date) -> int:
    """event_archive에서 [lo, hi) 구간 region 이벤트 수 (forward window)."""
    row = con.execute(
        "SELECT COUNT(*) FROM event_archive "
        "WHERE region_code = ? AND timestamp >= ? AND timestamp < ?",
        (region, lo.isoformat(), hi.isoformat()),
    ).fetchone()
    return int(row[0]) if row else 0


def _fetch_event_outcome(
    con: sqlite3.Connection, region: str, created: date, resolve_by: date, horizon: int
) -> tuple[float, str, int] | None:
    """
    이벤트 빈도 변화율과 방향 반환. (realized_pct, direction, baseline_n)

    baseline = [created - horizon, created)  ─ 등길이 사전 창
    outcome  = [created, resolve_by]         ─ 등길이 사후 창 (forward)
    기준선이 빈약하면(<MIN_BASELINE_EVENTS) None → UNRESOLVED 유도.
    """
    base_lo = created - timedelta(days=horizon)
    baseline_n = _count_events(con, region, base_lo, created)
    outcome_n = _count_events(con, region, created, resolve_by + timedelta(days=1))
    if baseline_n < MIN_BASELINE_EVENTS:
        return None
    pct = (outcome_n - baseline_n) / baseline_n * 100.0
    direction = "up" if outcome_n > baseline_n else "down"
    return round(pct, 2), direction, baseline_n


# ── 라벨링 (HIT / MISS / UNRESOLVED) ───────────────────────────────────────────

def _label(
    predicted: str, threshold: float | None, realized_pct: float, realized_dir: str
) -> tuple[str, str]:
    """예측 방향·임계 vs 실측 → (status, reason). 원칙 ①④ 적용."""
    dir_match = (predicted == realized_dir)
    mag = abs(realized_pct)

    if mag < FLAT_EPS_PCT:
        # 사실상 무변동 — 방향 적중을 주장하기엔 신호가 없음
        return "UNRESOLVED", f"무변동(|{realized_pct}%|<{FLAT_EPS_PCT}) — 방향 판정 보류"

    if not dir_match:
        return "MISS", f"방향 반대(예측 {predicted} · 실측 {realized_dir} {realized_pct}%)"

    # 방향 일치
    if threshold is not None and mag < threshold:
        # 원칙 ④ — 방향은 맞았으나 실질 크기 미달
        return "MISS", f"방향 적중·임계 미달(실측 {mag}% < 임계 {threshold}%)"

    thr_note = f"·임계 {threshold}% 충족" if threshold is not None else "(방향 전용)"
    return "HIT", f"방향 적중(실측 {realized_pct}%){thr_note}"


# ── 단건 채점 ──────────────────────────────────────────────────────────────────

def score_prediction(con: sqlite3.Connection, row: sqlite3.Row, as_of: date) -> dict:
    """PENDING 예측 1건 채점. DB 갱신은 호출부에서. 결과 dict 반환."""
    created = datetime.fromisoformat(row["created_at"]).date()
    resolve_by = date.fromisoformat(row["resolve_by"])
    kind = row["target_kind"]
    predicted = row["direction"]
    threshold = row["threshold_pct"]

    # 채점 비대상(scorable=0)은 만기 시 UNRESOLVED 종결 — 영구 PENDING 방지 +
    # dedup 슬롯 해제. 이 가드가 kind 분기보다 먼저여야 unclear 방향의 market 행이
    # 시장 채점에 흘러들어 무조건 MISS 되는 오판을 막는다. UNRESOLVED는 비종결 —
    # 질적 예측의 인간 사후 채점(HIT/MISS로 UPDATE)은 열려 있다.
    if not row["scorable"]:
        reason = ("질적 타깃 — 자동 채점 비대상(인간 사후 채점 후보)"
                  if kind == "qualitative"
                  else "방향 불명 — 자동 채점 비대상")
        return _result(row, "UNRESOLVED", None, "", reason, as_of)

    if kind == "market":
        out = _fetch_market_outcome(row["target"], created, resolve_by)
        if out is None:
            return _result(row, "UNRESOLVED", None, "", "시장 데이터 없음/불충분", as_of)
        realized_pct, realized_dir = out
        base_caveat = _MARKET_CAVEAT

    elif kind == "event_series":
        out = _fetch_event_outcome(con, row["target"], created, resolve_by, row["horizon_days"])
        if out is None:
            return _result(row, "UNRESOLVED", None, "",
                           f"기준선 이벤트<{MIN_BASELINE_EVENTS} — 비율 산정 불가", as_of)
        realized_pct, realized_dir, _ = out
        base_caveat = _EVENT_CAVEAT

    else:
        # qualitative 등 — 자동 채점 대상 아님 (10-1에서 scorable=0)
        return _result(row, "UNRESOLVED", None, "", "질적 타깃 — 자동 채점 비대상", as_of)

    status, reason = _label(predicted, threshold, realized_pct, realized_dir)
    return _result(row, status, realized_pct, realized_dir,
                   f"{reason} | {base_caveat}", as_of)


def _result(row, status, realized_pct, realized_dir, reason, as_of) -> dict:
    return {
        "prediction_id": row["prediction_id"],
        "status": status,
        "realized_pct": realized_pct,
        "realized_direction": realized_dir,
        "score_reason": reason,
        "scored_at": as_of.isoformat(),
    }


# ── 배치 채점 ──────────────────────────────────────────────────────────────────

def score_due_predictions(as_of: date | None = None, dry_run: bool = False) -> dict:
    """
    resolve_by가 도래한 PENDING 예측을 일괄 채점 (scorable=0은 UNRESOLVED 종결).

    as_of: 채점 기준일 (기본 오늘 UTC). dry_run: DB 미반영(미리보기).
    반환: 집계 요약 (적중률은 eligible_for_calibration=1 인 HIT/MISS만 대상 — 원칙 ③).
    """
    as_of = as_of or datetime.now(timezone.utc).date()
    con = sqlite3.connect(_INTEL_DB)
    con.row_factory = sqlite3.Row
    _ensure_score_columns(con)

    # scorable=0도 만기 시 인출 — score_prediction 상단 가드가 UNRESOLVED로 종결
    # (구 필터 'AND scorable = 1'은 채점 비대상을 영구 PENDING에 가뒀다)
    due = con.execute(
        "SELECT * FROM prediction_log "
        "WHERE status = 'PENDING' AND resolve_by <= ? "
        "ORDER BY resolve_by",
        (as_of.isoformat(),),
    ).fetchall()

    results = [score_prediction(con, r, as_of) for r in due]

    if not dry_run:
        for res in results:
            con.execute(
                "UPDATE prediction_log SET status=?, realized_pct=?, "
                "realized_direction=?, score_reason=?, scored_at=?, outcome_value=? "
                "WHERE prediction_id=?",
                (res["status"], res["realized_pct"], res["realized_direction"],
                 res["score_reason"], res["scored_at"], res["realized_pct"],
                 res["prediction_id"]),
            )
        con.commit()

    # ── 집계 (원칙 ③ — 캘리브레이션 적격만, retrodiction 격리) ──────────────────
    elig_ids = {
        r["prediction_id"] for r in due
        if (r["eligible_for_calibration"] if "eligible_for_calibration" in r.keys() else 1)
    }
    judged = [x for x in results
              if x["status"] in ("HIT", "MISS") and x["prediction_id"] in elig_ids]
    hits = sum(1 for x in judged if x["status"] == "HIT")
    unresolved = sum(1 for x in results if x["status"] == "UNRESOLVED")
    summary = {
        "as_of": as_of.isoformat(),
        "due": len(due),
        "scored": len([x for x in results if x["status"] in ("HIT", "MISS")]),
        "hit": hits,
        "miss": len(judged) - hits,
        "unresolved": unresolved,
        # ⚠️ 런 단위 값 — 누적 적중률로 승격 금지 ("0.526" 오승격 사고, T3 채택위 07-11).
        # 누적·기준선 대비는 skill 블록(cumulative_skill_summary)이 유일 원천.
        "hit_rate_eligible": round(hits / len(judged), 3) if judged else None,
        "skill": cumulative_skill_summary(con),
        "dry_run": dry_run,
    }
    con.close()
    return summary


def _wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """이항 비율의 Wilson 95% 신뢰구간 — 소표본에서 정규근사보다 정직."""
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (round(center - half, 3), round(center + half, 3))


def cumulative_skill_summary(con: sqlite3.Connection) -> dict:
    """누적 적중률을 base rate 기준선 대비로 보고 — T3 채택위(2026-07-11) 후보② 집행.

    문헌 근거(Ward 2010 동형): 원시 적중률은 base rate 대비 skill 없인 정보가 아니다.
    기준선 3종 병기(단일 기준선 선택의 자의성 해소 — 반박석 조건):
      coin           — 0.5 (무정보 동전)
      const_majority — 실현 방향 분포의 다수 방향만 내는 상수 예측기
      persistence    — 동일 target의 직전 실현 방향을 그대로 내는 예측기(계산 가능 쌍만)
    ⚠️ 이 수치도 최적화 표적 아님. 독립성 주의: 표본이 소수 티커에 클러스터링돼
    (T6 판례: 유사복제) 유의성 해석은 클러스터 보정 전 잠정 — n_targets 병기.
    """
    rows = con.execute(
        "SELECT target, status, realized_direction, scored_at FROM prediction_log "
        "WHERE status IN ('HIT','MISS') AND IFNULL(eligible_for_calibration, 1) = 1 "
        "ORDER BY scored_at"
    ).fetchall()
    n = len(rows)
    if not n:
        return {"n": 0}
    hits = sum(1 for r in rows if r[1] == "HIT")
    realized = [r[2] for r in rows if r[2] in ("up", "down")]
    maj = max(set(realized), key=realized.count) if realized else None
    const_rate = round(realized.count(maj) / len(realized), 3) if realized else None
    prev: dict = {}
    persist_ok = persist_n = 0
    for tgt, _st, rdir, _at in rows:
        if rdir not in ("up", "down"):
            continue
        if tgt in prev:
            persist_n += 1
            persist_ok += int(prev[tgt] == rdir)
        prev[tgt] = rdir
    lo, hi = _wilson_ci(hits, n)
    best_base = max(0.5, const_rate or 0.5)
    return {
        "n": n,
        "n_targets": len({r[0] for r in rows}),
        "hit_rate": round(hits / n, 3),
        "wilson95": [lo, hi],
        "baseline_coin": 0.5,
        "baseline_const_majority": const_rate,
        "baseline_const_direction": maj,
        "baseline_persistence": ([round(persist_ok / persist_n, 3), persist_n] if persist_n else None),
        "verdict": ("기준선 상회 — 클러스터 보정 전 잠정"
                    if lo > best_base
                    else "skill 검출 불가 — CI가 기준선 이하 포함"),
    }


def main() -> None:
    """CLI: python -m services.prediction_scorer [--dry-run] [--as-of YYYY-MM-DD]"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Phase 10-2 예측 결과 채점")
    ap.add_argument("--dry-run", action="store_true", help="DB 미반영 미리보기")
    ap.add_argument("--as-of", type=str, default=None, help="채점 기준일 YYYY-MM-DD")
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    s = score_due_predictions(as_of=as_of, dry_run=args.dry_run)
    print(
        f"[10-2 채점] as_of={s['as_of']} 도래={s['due']} "
        f"→ HIT {s['hit']} · MISS {s['miss']} · UNRESOLVED {s['unresolved']} "
        f"| 적격 적중률={s['hit_rate_eligible']}"
        + (" (DRY-RUN)" if s["dry_run"] else "")
    )
    print("  ⚠ 적중률은 '방향 실현' 빈도일 뿐 인과 입증·base-rate 보정 아님(→ 10-3 캘리브레이션).")


if __name__ == "__main__":
    main()
