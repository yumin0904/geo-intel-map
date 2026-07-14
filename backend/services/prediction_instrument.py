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
    # [T3 채택위 2026-07-11, 후보① 축소 채택 — 기록/보고 분리] 생성 시점 서버 신뢰도(0~100).
    # ⚠️ 확률이 아니다 — LLM 표명이 아닌 서버 결정론 산출(§19-D)의 무보정 원값. Brier·캘리브레이션
    # 보고층은 원전 정독 게이트(Ward·Hegre 본문+LLM-확률 타당성 문헌) 뒤 — 이 필드는 유량 보존만
    # 한다(생성 ~434건/일, 지연 1일 = 수백 건 원값 유실 — 반박석 실측).
    confidence_at_creation: int | None = None
    # [위원회 20260712 집행⑤] 상류 추출 성공 여부의 명시 boolean 신호. dependent_var가
    # "미식별"/빈 값이면 0(추출 실패), 아니면 1(정상 추출). status enum과 별개 축 —
    # status는 결과(outcome)를, 이 필드는 추출(extraction) 단계를 말한다. 축 분리
    # 유지가 목적이므로 이 필드로 status 파생 로직을 짜지 않는다.
    extraction_ok: int | None = None


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


# 티커가 가리키는 실물의 별칭. IV 텍스트에 이 중 하나가 있으면 IV와 DV가 같은 것을 가리킨다.
_TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "CL=F":  ("WTI", "서부텍사스", "West Texas"),
    "BZ=F":  ("Brent", "브렌트"),
    "NG=F":  ("TTF", "Henry Hub", "헨리허브", "천연가스 가격", "가스 가격", "Natural Gas Price"),
    "GLD":   ("금값", "금 가격", "Gold Price", "금 시세"),
    "^KS11": ("KOSPI", "코스피"),
    "KRW=X": ("원/달러", "원달러", "Korean Won per"),
    "CNY=X": ("위안/달러", "위안달러", "Chinese Yuan per"),
    "TSM":   ("TSMC 주가", "TSM 주가"),
    "ITA":   ("ITA 주가", "방산 ETF"),
}


def _antecedent_fields(rec) -> dict:
    """전건(IV)을 **구조화**해서 저장한다 — B28.

    **DV는 정량 7필드인데 IV는 TEXT 한 칸이었다.** 명사구로는 참·거짓을 물을 수 없어서
    `prediction_scorer`가 IV를 **한 번도 안 읽었고**, 채점된 82건이 전부 무효가 됐다.

    파싱 못 하면 **전부 None** — 그러면 만기에 채점기가 `UNRESOLVED`로 종결한다.
    **지어내지 않는다.**
    """
    from services.antecedent import parse

    ant = parse(rec.independent_var, rec.region_code)
    if ant is None:
        return {"iv_metric": None, "iv_region": None, "iv_direction": None,
                "iv_threshold": None, "iv_window_days": None}
    return {"iv_metric": ant.metric, "iv_region": ant.region, "iv_direction": ant.direction,
            "iv_threshold": ant.threshold, "iv_window_days": ant.window_days}


def _iv_extraction_failed(independent_var: str, h1: str) -> bool:
    """IV 필드가 H1 문장을 통째로 삼켰는가 — 전건이 분리되지 않은 상태.

    추출기가 "X가 오르면 Y가 오른다"에서 X만 떼는 데 실패하고 문장 전체를 IV에 넣은 경우다.
    전건을 분리하지 못했으면 전건을 잴 수도 없다 → 채점 대상에서 뺀다.
    이것은 동어반복과 **다른 병**이다(폐기 #36: 진단이 다르면 처방이 다르다. 뭉개지 마라).
    """
    iv, h = (independent_var or "").strip(), (h1 or "").strip()
    if not iv or not h or len(iv) <= 45:
        return False
    return iv[:30] in h


def _is_tautological(independent_var: str, target: str | None) -> bool:
    """분리된 IV가 target 자신을 가리키는가 — "IF X THEN X" 검출.

    가격을 가격으로 예측하는 것은 지정학 가설이 아니다. 대소문자 무시 부분일치.
    ⚠️ 호출 전에 _iv_extraction_failed로 거를 것 — H1을 삼킨 IV는 후행절까지 텍스트에 품고
    있어 여기서 무조건 참이 된다(오탐). 실측: 그렇게 걸리는 30건 중 상당수의 전건은
    정상 지정학 변수였다(예: "bab_el_mandeb ACLED 건수 증가가 WTI 유가를…" → target CL=F).
    """
    if not target or not independent_var:
        return False
    iv = independent_var.lower()
    return any(a.lower() in iv for a in _TICKER_ALIASES.get(target, ()))


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

    # UNQUANTIFIABLE 게이트 (권역위 2026-07-14, 사용자 승인 — 헌법 §18-A.2 집행).
    # 8-gate가 "정량화 불가"로 분류한 가설에 ticker가 물리면 _classify_target이
    # market·scorable=True를 주고, prediction_scorer는 independent_var를 **읽지 않는다**
    # (score_prediction: target 등락만 본다). 그 결과 "북한 내 AI 접근성 → GLD" 같은
    # 가설이 금값 랠리 한 번에 HIT를 받았다 — 선행절이 관측 불가능한 채로 후행절만 채점.
    # 실측 2026-07-14: 43건이 scorable=1로 8/15 만기 대기 중이었다(전건 동결).
    # 이 파일 docstring(L16-17)이 이미 이 규칙을 선언해 놓고 지키지 않았다(패턴 E).
    if scorable and getattr(spec, "data_signature", "") == "UNQUANTIFIABLE":
        scorable = False

    # 전건 게이트 2종 (18-①위원회 2026-07-14, 사용자 승인). 순서가 중요하다 — 진단이 다르다.
    _iv = getattr(spec, "independent_var", "") or ""
    if scorable and _iv_extraction_failed(_iv, spec.h1 or ""):
        # ① 전건이 분리되지 않았다. 못 뗀 전건은 잴 수 없다. 실측 30건.
        scorable = False
    elif scorable and _is_tautological(_iv, target):
        # ② 동어반복 — IV가 target 그 자체다. "IF X THEN X"는 지정학 가설이 아니라
        #    가격 자기예측이다. 실측 8건: IV "WTI 유가(USD/배럴) 상승률" → target CL=F(=WTI).
        #    발원지는 LLM의 실수가 아니라 배관이었다 — theory_comparator가 FRED 시세를
        #    "실측 — Brent Crude Oil Price: … (최근 추세, 사전계산) [FRED]"로 주입하면
        #    LLM이 그 줄을 독립변수로 되받아 썼다. 그 주입은 신선도 게이트로 막았고(같은
        #    위원회), 이 가드는 그래도 새어 나오는 것을 채점에서 거른다(2층 방어).
        scorable = False

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
        # [집행⑤] dependent_var가 "미식별"/빈 값이면 상류 추출 실패(0), 아니면 성공(1).
        # 이 시점까지 살아남은 레코드(위 unclear+미식별 조기 return 통과분)는 이미 DV가
        # 채워졌거나 정직한 무방향 질적 가설이므로 대부분 1이 되지만, dependent_var가
        # 다른 경로로 빈 채 남는 잔여 케이스를 위해 실값 재확인한다.
        extraction_ok=0 if (spec.dependent_var or "").strip() in ("", "미식별") else 1,
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
    # [T3 채택위 07-11] 기존 DB에 confidence_at_creation 소급 추가 (idempotent —
    # 구 행은 NULL 유지: 생성 시점 원값이 없으므로 소급 부여 금지, 원칙 ③ retrodiction 격리)
    cols = {r[1] for r in con.execute("PRAGMA table_info(prediction_log)")}
    if "confidence_at_creation" not in cols:
        con.execute("ALTER TABLE prediction_log ADD COLUMN confidence_at_creation INTEGER")
    # [위원회 20260712 집행⑤] extraction_ok 소급 추가 (idempotent, 동일 패턴) — 파싱
    # 실패의 명시 boolean 신호. status enum은 불가침(반박석 축 오염 반론 수용,
    # PARSE_FAILED 상태 신설 기각 — 추출 성공 축과 결과(outcome) 축을 분리해 오염을
    # 막는다). 구 행은 NULL 유지(생성 시점 원값 없음, retrodiction 격리 동일 원칙).
    if "extraction_ok" not in cols:
        con.execute("ALTER TABLE prediction_log ADD COLUMN extraction_ok INTEGER")
    # 채점 배치(10-2)가 만기 예측을 빠르게 찾도록 인덱스
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_prediction_resolve "
        "ON prediction_log (status, resolve_by)"
    )


def _is_duplicate(con: sqlite3.Connection, rec: PredictionRecord) -> bool:
    """같은 채점 신원의 PENDING 예측이 이미 있으면 중복 (재실행 스팸 방지).

    [T3 채택위 2026-07-11] h1 정확 문자열 비교 제거 — 재생성 런마다 문구 변형 h1이
    dedup을 우회해 PENDING이 증식(605→807 실측, 반박석 원인 특정: 231행 구 키).
    채점 신원 = (target, direction, threshold_pct, horizon_days): 이 4필드가 같으면
    만기 시 동일하게 채점되므로 문구가 달라도 같은 예측이다. 서로 다른 논지의 진짜
    별개 예측은 임계·기간·타깃 중 하나는 다르다.
    """
    row = con.execute(
        "SELECT 1 FROM prediction_log "
        "WHERE target = ? AND direction = ? "
        "AND IFNULL(threshold_pct, -1) = IFNULL(?, -1) AND horizon_days = ? "
        "AND status = 'PENDING' LIMIT 1",
        (rec.target, rec.direction, rec.threshold_pct, rec.horizon_days),
    ).fetchone()
    return row is not None


def log_predictions(specs: list["HypothesisSpec"], query: str,
                    confidence: int | None = None) -> list[PredictionRecord]:
    """
    검증 완료된 specs → 반증가능 예측 적재. 적재된 레코드 목록 반환.

    confidence: 생성 시점 서버 신뢰도(0~100, §19-D 결정론 산출·패널티 반영) —
    confidence_at_creation에 동결. 확률 아님(기록/보고 분리 — T3 채택위 07-11).
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
            if rec is not None:
                rec.confidence_at_creation = confidence
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
                    scorable, status, outcome_value, scored_at, confidence_at_creation,
                    extraction_ok,
                    iv_metric, iv_region, iv_direction, iv_threshold, iv_window_days
                ) VALUES (
                    :prediction_id, :created_at, :query, :h1, :independent_var, :dependent_var,
                    :target, :target_kind, :direction, :threshold_pct, :horizon_days, :resolve_by,
                    :region_code, :data_signature, :inference_grade, :method, :exploratory,
                    :scorable, :status, :outcome_value, :scored_at, :confidence_at_creation,
                    :extraction_ok,
                    :iv_metric, :iv_region, :iv_direction, :iv_threshold, :iv_window_days
                )
                """,
                {**asdict(rec), "exploratory": int(rec.exploratory), "scorable": int(rec.scorable),
                 **_antecedent_fields(rec)},
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
