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
_RE_SINGLE_SHOCK = re.compile(
    r"(펠로시|바이든|트럼프|시진핑|푸틴|\d{4}년\s*\d{1,2}월|\d{4}-\d{2}-\d{2}"
    r"|방문|선언|협정|조약|제재\s*발표|공습|침공|합의|정상회담"
    r"|사건|사태|충격|쇼크)",
    re.IGNORECASE,
)

# CROSS_SECTION: 국가간 비교·횡단면 분석
# "일수록|할수록" = "국가일수록", "높을수록" 등 한국어 비교 표현 (tilde 없이 매칭)
_RE_CROSS_SECTION = re.compile(
    r"(국가(들|간|별)\s*(비교|차이|격차)|일수록|할수록|국가가\s*많을수록"
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
_RE_NETWORK = re.compile(
    r"(전이|확산|spillover|contagion|파급|연결망|네트워크\s*효과"
    r"|전염|연쇄\s*반응|도미노)",
    re.IGNORECASE,
)

# NONLINEAR: 임계·체제 전환(정량화 가능 — 8-gate 통과한 것)
_RE_NONLINEAR_QUANTIFIABLE = re.compile(
    r"(임계(값|점|치)|역치|tipping\s*point|비선형|threshold"
    r"|체제\s*전환|구조\s*변화|레짐\s*전환)",
    re.IGNORECASE,
)


def classify_signature(
    query_text: str,
    linear_testable: bool = True,
    has_paired_timeseries: bool = True,
) -> DataSignature:
    """
    쿼리 텍스트 + spec 속성으로 DataSignature를 결정한다.

    linear_testable=False면 8-gate 이미 처리 → UNQUANTIFIABLE.
    has_paired_timeseries=False면 PAIRED_TIMESERIES 미선택.
    """
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
_IMPLEMENTED_METHODS: set[str] = {"granger", "structural_arg", "event_study", "panel_regression"}


def filter_implemented(methods: list[str]) -> tuple[list[str], list[str]]:
    """구현된 방법과 stub(미구현) 방법을 분리한다."""
    implemented = [m for m in methods if m in _IMPLEMENTED_METHODS]
    stubs       = [m for m in methods if m not in _IMPLEMENTED_METHODS]
    return implemented, stubs
