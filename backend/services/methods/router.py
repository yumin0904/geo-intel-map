"""
services/methods/router.py  (9-0)

Method Router — 데이터 모양으로 방법집합을 사전 선언한다.

핵심 원칙:
  - 결과 보기 전에 방법집합을 결정 (결과 주도 선택 금지).
  - 순차 fallback("안 되면 다른 것") 금지 — method-level p-해킹 차단.
  - 방법집합 = {주 방법 1개 + 강건성 방법 0~n개}. 삼각측량 목적.

시그니처 분류 우선순위 (위에서 아래로 첫 번째 매칭):
  1. UNQUANTIFIABLE  — 8-gate 판정(linear_testable=False)
  2. SINGLE_SHOCK    — 특정 날짜·명명 사건 키워드
  3. CROSS_SECTION   — 국가간 비교·시간축 없음 키워드
  4. COUNTERFACTUAL  — 반사실·제재·"없었다면" 키워드
  5. NETWORK_DIFFUSION — 확산·전이·네트워크 키워드
  6. NONLINEAR       — 임계·체제(정량화 가능) 키워드
  7. PAIRED_TIMESERIES — 기본 (시계열 쌍이 있으면)
"""
from __future__ import annotations

import logging
import re

from services.methods.base import DataSignature, SIGNATURE_METHOD_MAP

logger = logging.getLogger(__name__)

# ── 시그니처별 키워드 패턴 ──────────────────────────────────────────────────────

# SINGLE_SHOCK: 특정 날짜·명명 사건 (이벤트스터디 적합)
# 주의: "충격"·"사건"은 일반 어휘라 과도 오탐 유발(taiwan_semiconductor, salt_typhoon) → 제거.
# 날짜·인명·구체 행위 동사만 남겨 false-positive 방지.
_RE_SINGLE_SHOCK = re.compile(
    r"(펠로시|바이든|트럼프|시진핑|푸틴|\d{4}년\s*\d{1,2}월|\d{4}-\d{2}-\d{2}"
    r"|방문|선언|협정|조약|제재\s*발표|공습|침공|합의|정상회담"
    r"|사태|쇼크)",
    re.IGNORECASE,
)

# CROSS_SECTION: 국가간 비교·횡단면 분석
# "국가들의" 추가: "사헬 국가들의 거버넌스" 등 다국가 비교 프레임 포착.
_RE_CROSS_SECTION = re.compile(
    r"(국가(들|간|별)\s*(비교|차이|격차|의)|일수록|할수록|국가가\s*많을수록"
    r"|패널\s*분석|국가\s*고정효과|횡단|cross.?section|panel"
    r"|높을수록|낮을수록|클수록|작을수록|많을수록|적을수록)",
    re.IGNORECASE,
)

# COUNTERFACTUAL: 반사실·단일 단위 정책 효과
_RE_COUNTERFACTUAL = re.compile(
    r"(없었다면|없었을\s*때|가정했을\s*때|반사실|합성\s*통제|제재\s*효과"
    r"|정책\s*효과|counterfactual|synthetic\s*control)",
    re.IGNORECASE,
)

# NETWORK_DIFFUSION: 전이·확산·연결망
# "연쇄 효과" 추가: "연쇄 반응"만 있던 것을 "연쇄 효과"까지 포함 (ukraine, hormuz 쿼리 패턴).
_RE_NETWORK = re.compile(
    r"(전이|확산|spillover|contagion|파급|연결망|네트워크\s*효과"
    r"|전염|연쇄\s*(반응|효과|충격|전파)|도미노)",
    re.IGNORECASE,
)

# NONLINEAR: 임계·체제 전환(정량화 가능 — 8-gate 통과한 것)
_RE_NONLINEAR_QUANTIFIABLE = re.compile(
    r"(임계(값|점|치)|역치|tipping\s*point|비선형|threshold"
    r"|체제\s*전환|구조\s*변화|레짐\s*전환)",
    re.IGNORECASE,
)

# ── [9-Q 쿼리-우선 라우팅] 이론 판별(theory adjudication) 감지 ──────────────────
# 배경: 방법은 '질문의 논리적 형태'에서 선택돼야 한다(9-0 설계). 그런데 기존 파이프라인은
#   LLM이 만든 H1(정량화된 대리변수·ticker)에서 linear_testable을 계산 → 조작화가 방법 선택을
#   오염시키는 '순서 역전'이 발생했다. "마한 vs 미어샤이머" 같은 이론 판별 질문은 두 이론이
#   같은 관측치를 예측(관측적 동등성)하므로 공변(Granger) 검정으로 판별 불가 → 과정추적/구조적
#   논증 대상이다. 이를 조작화 이전, '쿼리'에서 직접 감지한다.
#
# 이론 토큰: 명명된 IR 이론/-이즘 (예: 현실주의, 자유주의, 해양력 이론, 회색지대 이론, ~ 이론)
_THEORY_TOKEN = (
    r"(?:현실주의|자유주의|해양력\s*이론|회색지대\s*이론|하이브리드\s*전쟁\s*이론"
    r"|억지\s*이론|동맹\s*딜레마|상호의존\s*이론|[가-힣]{2,}\s*이론)"
)
# 두 이론이 '와/과'로 병치 + 비교/판별(어느 쪽이 더 설명력) 요구
_RE_THEORY_ADJUDICATION = re.compile(
    _THEORY_TOKEN + r".{0,45}?(?:와|과)\s*.{0,45}?" + _THEORY_TOKEN +
    r".{0,40}?(?:비교|중\s*어느|어느\s*쪽|더\s*(?:잘\s*)?설명|설명력)",
    re.DOTALL,
)
# 해석형(interpretive) 질문 — 측정 도구가 없는 결과를 '왜/어떻게'로 묻는 질문.
#   예: 억지 '실패한 이유'(귀속), 딜레마 '어떻게 회피하는지'(메커니즘), 역량 '공백'(측정불가).
#   이론 판별과 마찬가지로 공변(Granger) 검정 부적합 → 과정추적/구조적 논증 대상.
_RE_INTERPRETIVE = re.compile(
    r"실패한?\s*이유|실패\s*원인"                                # 귀속(attribution): 왜 실패했나
    r"|어떻게\s*.{0,12}?(회피|하는지|막는지|바꾸는지|작동하는지)"   # 메커니즘: 어떻게 ~하나
    r"|역량\s*공백|공백을\s*.{0,8}?분석",                        # 측정불가 공백(gap)
    re.DOTALL,
)

# 정량 오버라이드 — 측정가능 변수·수치·통계기법·데이터출처가 명시되면 UNQUANTIFIABLE 아님.
#   예: "무역 의존도(자유주의)와 군사력 격차(현실주의) 중 어느 변수가 …를 수치로 검증"은
#   두 이론이 아니라 두 '변수' 비교 → CROSS_SECTION 유지. "미치는 영향/지수(WGI·HIIK)"도 측정 프레임.
_RE_QUANT_OVERRIDE = re.compile(
    r"수치로|데이터로|어느\s*변수|%\s*gdp|gdp\s*대비|시계열|패널|hhi|car"
    r"|이벤트\s*스터디|비정상수익|고정효과|회귀|지수\s*\(|wgi|hiik"
    r"|미치는\s*(영향|충격|연쇄)",
    re.IGNORECASE,
)


def unquantifiable_question_reason(query_text: str) -> str | None:
    """
    [9-Q 쿼리-우선] 질문의 '논리 형태'가 공변(Granger) 검정 부적합인지 판정하고 사유를 반환.

    조작화(H1의 정량화·ticker) 이전, 원본 쿼리에서 직접 감지 — 방법을 질문에서 선택하기 위함.
    정량 신호(수치·데이터출처·측정영향)가 있으면 None(정량 케이스 보호).
    """
    text = query_text or ""
    if _RE_QUANT_OVERRIDE.search(text):
        return None
    if _RE_THEORY_ADJUDICATION.search(text):
        return (
            "이론 판별형 질문(복수 이론 비교) — 두 이론이 같은 관측치를 예측(관측적 동등성)"
            "하므로 공변(Granger) 검정으로 판별 불가"
        )
    if _RE_INTERPRETIVE.search(text):
        return (
            "해석형 질문(메커니즘·귀속·역량공백을 '왜/어떻게'로 물음) — 측정 도구가 없는 "
            "결과를 묻는 질문이라 공변 검정 부적합"
        )
    return None


def is_theory_adjudication(query_text: str) -> bool:
    """쿼리가 '복수 이론 판별' 질문인지 감지한다 (관측적 동등성 → 공변검정 부적합).

    하위호환 유지용. 통합 판정은 `unquantifiable_question_reason` 사용.
    """
    text = query_text or ""
    if _RE_QUANT_OVERRIDE.search(text):
        return False
    return bool(_RE_THEORY_ADJUDICATION.search(text))


def classify_signature(
    query_text: str,
    linear_testable: bool = True,
    has_paired_timeseries: bool = True,
) -> DataSignature:
    """
    쿼리 텍스트 + spec 속성으로 DataSignature를 결정한다.

    [9-Q 쿼리-우선] 이론 판별형·해석형 질문은 조작화(linear_testable/ticker)와 무관하게
      UNQUANTIFIABLE로 직행 — 방법을 '질문의 논리 형태'에서 선택하기 위함.
    linear_testable=False면 8-gate 이미 처리 → UNQUANTIFIABLE.
    has_paired_timeseries=False면 PAIRED_TIMESERIES 미선택.
    """
    if unquantifiable_question_reason(query_text):
        return "UNQUANTIFIABLE"

    if not linear_testable:
        return "UNQUANTIFIABLE"

    text = query_text or ""

    if _RE_SINGLE_SHOCK.search(text):
        return "SINGLE_SHOCK"
    if _RE_CROSS_SECTION.search(text):
        return "CROSS_SECTION"
    if _RE_COUNTERFACTUAL.search(text):
        return "COUNTERFACTUAL"
    if _RE_NETWORK.search(text):
        return "NETWORK_DIFFUSION"
    if _RE_NONLINEAR_QUANTIFIABLE.search(text):
        return "NONLINEAR"
    if has_paired_timeseries:
        return "PAIRED_TIMESERIES"

    # 시계열 쌍도 없고 다른 시그니처도 없으면 기술적 수준
    return "UNQUANTIFIABLE"


def select_method_set(signature: DataSignature) -> list[str]:
    """
    시그니처 → 방법집합 반환 (사전 선언).

    반환 리스트의 첫 번째가 주 방법, 나머지는 삼각측량 강건성 방법.
    9-A~E 어댑터 미구현 방법은 "stub" 마킹 — 결과 미산출, grader에서 무시.
    """
    methods = SIGNATURE_METHOD_MAP.get(signature, ["structural_arg"])
    logger.debug("[router] signature=%s → methods=%s", signature, methods)
    return methods


# 구현된 방법 목록 — 어댑터 파일 존재 여부
# 9-A event_study 완료(2026-06-17), 9-B panel_regression 완료(2026-06-17), 9-C~E는 stub
_IMPLEMENTED_METHODS: set[str] = {
    "granger", "structural_arg",
    "event_study", "panel_regression",
    "process_tracing",   # [9-Q 우선순위 3] UNQUANTIFIABLE → Van Evera 4검정 스캐폴딩
}


def filter_implemented(methods: list[str]) -> tuple[list[str], list[str]]:
    """구현된 방법과 stub(미구현) 방법을 분리한다."""
    implemented = [m for m in methods if m in _IMPLEMENTED_METHODS]
    stubs       = [m for m in methods if m not in _IMPLEMENTED_METHODS]
    return implemented, stubs
