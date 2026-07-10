"""
[Phase 10-1] 예측 계측(Prediction Instrument) — 반증가능 예측 적재.

목적: 엔진이 인사이트를 낼 때마다 "무엇이, 어느 방향으로, 언제까지" 일어날지
*반증 가능한 형태*로 로그에 박아둔다. 나중에(10-2) 그 시점이 오면 실측값과 대조해
적중/실패를 채점한다. 이 기록이 없으면 "엔진이 정교하게 일관되게 틀려도" 잡을 수 없다.

철학(Phase 10): LLM 심판의 '형식 점수'는 박사 흉내일 뿐, 박사는 *맞아서* 박사다.
→ 결론의 적중(correctness)을 사후 검증하려면, 먼저 *예측을 동결*해야 한다.

Token-Zero: 이 모듈은 LLM을 호출하지 않는다. 방향·타깃·시점은 모두 결정론 파싱.
채점(10-2)도 실측 시계열 대조(산술)뿐이라 LLM 불필요.

설계 원칙:
  - 예측은 H1이 *주장하는* 방향을 동결한다 (분석 시점의 관측치가 아니라 미래 주장).
  - 시장 ticker·지역 이벤트 시계열처럼 *산술로 채점 가능한* 타깃만 scorable=True.
  - 질적(UNQUANTIFIABLE·과정추적) 가설도 기록은 하되 scorable=False로 표시
    (자동 채점 대상 아님 — 정직하게 "이건 수치 적중을 못 잰다"고 남긴다).
"""

from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.hypothesis_extractor import HypothesisSpec

logger = logging.getLogger(__name__)

_INTEL_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# ── 시점(horizon) 기본값 — 타깃 종류별 채점 유예 기간 ────────────────────────────
# 시장 지표는 충격 반영이 빠르고(수일~수주), 분쟁 이벤트 시계열은 누적·확산에
# 더 긴 창이 필요하다. best_lag(검정에서 추정된 지연)이 있으면 그것을 우선 쓴다.
# (CLAUDE.md §10: 매직넘버 지양 — 차후 config 이관 후보. 현재는 근거 주석과 함께 상수화.)
_HORIZON_DAYS: dict[str, int] = {
    "market":       30,   # 시장 반영 1개월
    "event_series": 90,   # 분쟁 패턴 변화 1분기
    "qualitative":  180,  # 질적 — 채점 안 하지만 검토 리마인더 용도
}

# ── 방향 어휘 (H1 종속변수 동사 → up/down) ──────────────────────────────────────
# H1 형식: "X가 증가할 때 Y가 통계적으로 유의하게 {증가|감소|...}한다"
# 종속변수(Y) 쪽 동사가 예측 방향이다. extractor의 동사군과 어휘를 맞춘다.
_UP_TOKENS = (
    "증가", "상승", "강화", "확대", "악화", "심화", "격화", "확산",
    "증대", "높아", "커지", "늘어", "발생",
)
_DOWN_TOKENS = (
    "감소", "하락", "축소", "개선", "약화", "낮아", "작아", "줄어",
    "상실", "완화",
)
# "통계적으로 유의하게 <동사>" 패턴 — 종속변수 방향 캡처
_DV_VERB_RE = re.compile(
    r"유의(?:하게|미한|성)?\s*(?:으로)?\s*"
    r"(증가|감소|상승|하락|강화|약화|확대|축소|악화|개선|심화|완화|증대|발생|상실)"
)
# H1에 명시된 임계(%) — "1.5% 이상", "2%p" 등
_THRESHOLD_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


@dataclass
class PredictionRecord:
    """반증가능 예측 1건 — prediction_log 1행."""
    prediction_id: str
    created_at: str            # ISO UTC
    query: str
    h1: str
    independent_var: str
    dependent_var: str
    target: str                # ticker | dependent_region | dependent_var 텍스트
    target_kind: str           # market | event_series | qualitative
    direction: str             # up | down | unclear
    threshold_pct: float | None
    horizon_days: int
    resolve_by: str            # created_at + horizon_days (ISO date)
    region_code: str | None
    data_signature: str
    inference_grade: str
    method: str                # headline_method
    exploratory: bool
    scorable: bool             # 10-2 자동 채점 대상 여부
    status: str = "PENDING"    # PENDING → HIT | MISS | UNRESOLVED (10-2)
    outcome_value: float | None = None  # 채점 시 실측값
    scored_at: str | None = None


def _detect_direction(spec: "HypothesisSpec") -> str:
    """H1 종속변수 동사에서 예측 방향(up/down)을 결정론 파싱."""
    m = _DV_VERB_RE.search(spec.h1 or "")
    token = m.group(1) if m else ""
    if token in _UP_TOKENS:
        return "up"
    if token in _DOWN_TOKENS:
        return "down"
    # 폴백: 명시 동사 없으면 H1 전체에서 최초 방향 토큰 탐색 (덜 정확 → 그래도 unclear보다 정보)
    h1 = spec.h1 or ""
    for t in _UP_TOKENS:
        if t in h1:
            return "up"
    for t in _DOWN_TOKENS:
        if t in h1:
            return "down"
    return "unclear"


def _detect_threshold(h1: str) -> float | None:
    """H1에 명시된 임계 퍼센트(예: '1.5% 이상')를 추출. 없으면 None(방향만 예측)."""
    m = _THRESHOLD_RE.search(h1 or "")
    return float(m.group(1)) if m else None


def _classify_target(spec: "HypothesisSpec") -> tuple[str, str, bool]:
    """
    예측 타깃과 채점가능성 분류.

    Returns: (target, target_kind, scorable)
      - ticker 있음            → market       (yfinance 산술 채점 가능)
      - dependent_region 있음  → event_series (ACLED 이벤트 수 산술 채점 가능)
      - 둘 다 없음             → qualitative  (수치 채점 불가 — 정직하게 표시)
    """
    if getattr(spec, "ticker", None):
        return spec.ticker, "market", True
    dep_region = getattr(spec, "dependent_region", None)
    if dep_region:
        return dep_region, "event_series", True
    # 질적 가설(UNQUANTIFIABLE·과정추적)은 수치 타깃이 없다 → 기록만, 채점 제외
    return (spec.dependent_var or "—"), "qualitative", False


# 선언문·파편 h1 필터 (큐 8 소급 정화의 상류 차단, 2026-07-11) — "정량 가설 없음"은
# 정직한 무가설 선언이지 예측이 아니다. 기존 unclear+DV미식별 가드는 scorable=0 행을
# 우회시켜 이런 행이 계속 적재됐다(실측: 07-10 적재분 포함 27건). 체크리스트 파편
# ("작성 시도했으나…") 동류. 좁게 유지 — 가설 본문+논평 병기는 '가설 없음' 자기선언만 거른다.
_DECLARATION_H1 = re.compile(r"가설\s*없음|정량\s*가설이?\s*(?:부재|불가)|작성\s*시도했으나")


def build_prediction(spec: "HypothesisSpec", query: str) -> PredictionRecord | None:
    """단일 HypothesisSpec → 반증가능 PredictionRecord (Token-Zero).

    None 반환 = 추출 실패 산물(방향 unclear + DV 미식별) 또는 선언문 h1 — 등재 대상 아님.
    """
    now = datetime.now(timezone.utc)
    if _DECLARATION_H1.search(spec.h1 or ""):
        return None            # 선언문은 예측 로그가 아니라 카드 본문의 소관
    target, target_kind, scorable = _classify_target(spec)
    direction = _detect_direction(spec)

    # 시점: best_lag(검정 추정 지연) 우선, 없으면 타깃별 기본값
    best_lag = getattr(spec, "best_lag", None)
    horizon = _HORIZON_DAYS.get(target_kind, 90)
    if best_lag and best_lag > 0 and target_kind == "market":
        # 시장 검정 지연은 보통 일/거래일 단위 → 그대로 일수로 사용 (최소 7일 보장)
        horizon = max(best_lag, 7)

    mr = getattr(spec, "method_result", None) or {}
    if scorable and direction == "unclear":
        # DV까지 미식별이면 가설이 아니라 상류 추출 실패 산물(오류 문구 속 키워드에
        # ticker가 물려 market으로 오분류되는 경로 실측) — 등재 자체를 거른다.
        # '미식별'은 파싱 실패와 "정직한 무방향 가설"을 가르는 구조 신호다.
        if (spec.dependent_var or "").strip() in ("", "미식별"):
            return None
        # 정직한 무방향 수치 가설은 질적 트랙과 동일하게 기록만 — 자동 채점 제외
        scorable = False

    return PredictionRecord(
        prediction_id=uuid.uuid4().hex,
        created_at=now.isoformat(),
        query=query[:500],
        h1=spec.h1 or "",
        independent_var=getattr(spec, "independent_var", "") or "",
        dependent_var=getattr(spec, "dependent_var", "") or "",
        target=target,
        target_kind=target_kind,
        direction=direction,
        threshold_pct=_detect_threshold(spec.h1 or ""),
        horizon_days=horizon,
        resolve_by=(now + timedelta(days=horizon)).date().isoformat(),
        region_code=getattr(spec, "region_code", None),
        data_signature=getattr(spec, "data_signature", "") or "",
        inference_grade=getattr(spec, "inference_grade", "기술적") or "기술적",
        method=mr.get("headline_method", "") or "",
        exploratory=bool(getattr(spec, "exploratory", False)),
        scorable=scorable,
    )


def _ensure_table(con: sqlite3.Connection) -> None:
    """prediction_log 테이블 보장 (idempotent)."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_log (
            prediction_id   TEXT PRIMARY KEY,
            created_at      TEXT NOT NULL,
            query           TEXT,
            h1              TEXT,
            independent_var TEXT,
            dependent_var   TEXT,
            target          TEXT,
            target_kind     TEXT,
            direction       TEXT,
            threshold_pct   REAL,
            horizon_days    INTEGER,
            resolve_by      TEXT,
            region_code     TEXT,
            data_signature  TEXT,
            inference_grade TEXT,
            method          TEXT,
            exploratory     INTEGER,
            scorable        INTEGER,
            status          TEXT DEFAULT 'PENDING',
            outcome_value   REAL,
            scored_at       TEXT
        )
        """
    )
    # 채점 배치(10-2)가 만기 예측을 빠르게 찾도록 인덱스
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_prediction_resolve "
        "ON prediction_log (status, resolve_by)"
    )


def _is_duplicate(con: sqlite3.Connection, rec: PredictionRecord) -> bool:
    """같은 H1·타깃·방향의 PENDING 예측이 이미 있으면 중복 (재실행 스팸 방지)."""
    row = con.execute(
        "SELECT 1 FROM prediction_log "
        "WHERE h1 = ? AND target = ? AND direction = ? AND status = 'PENDING' LIMIT 1",
        (rec.h1, rec.target, rec.direction),
    ).fetchone()
    return row is not None


def log_predictions(specs: list["HypothesisSpec"], query: str) -> list[PredictionRecord]:
    """
    검증 완료된 specs → 반증가능 예측 적재. 적재된 레코드 목록 반환.

    호출부(intel_query)에서 try/except로 감싸 실패해도 SSE 흐름을 막지 않도록 한다.
    """
    if not specs:
        return []
    recs: list[PredictionRecord] = []
    try:
        con = sqlite3.connect(_INTEL_DB)
        _ensure_table(con)
        skipped = 0
        for spec in specs:
            rec = build_prediction(spec, query)
            if rec is None:            # 추출 실패 산물 — 미등재 (관측성은 카운터로 보존)
                skipped += 1
                continue
            if _is_duplicate(con, rec):
                continue
            con.execute(
                """
                INSERT INTO prediction_log (
                    prediction_id, created_at, query, h1, independent_var, dependent_var,
                    target, target_kind, direction, threshold_pct, horizon_days, resolve_by,
                    region_code, data_signature, inference_grade, method, exploratory,
                    scorable, status, outcome_value, scored_at
                ) VALUES (
                    :prediction_id, :created_at, :query, :h1, :independent_var, :dependent_var,
                    :target, :target_kind, :direction, :threshold_pct, :horizon_days, :resolve_by,
                    :region_code, :data_signature, :inference_grade, :method, :exploratory,
                    :scorable, :status, :outcome_value, :scored_at
                )
                """,
                {**asdict(rec), "exploratory": int(rec.exploratory), "scorable": int(rec.scorable)},
            )
            recs.append(rec)
        con.commit()
        con.close()
        scorable_n = sum(1 for r in recs if r.scorable)
        logger.info(
            "[10-1 instrument] 예측 %d건 적재 (채점가능 %d · 질적 %d · 추출실패 스킵 %d)",
            len(recs), scorable_n, len(recs) - scorable_n, skipped,
        )
    except Exception as exc:  # noqa: BLE001 — 계측 실패가 분석 흐름을 막으면 안 됨
        logger.warning("[10-1 instrument] 예측 적재 실패: %s", exc)
    return recs
