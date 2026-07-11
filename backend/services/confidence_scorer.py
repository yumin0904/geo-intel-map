"""
services/confidence_scorer.py

§19-D 기준으로 Gemini 출력 마크다운에서 신뢰도 점수(0~100)를 역산한다.

산출 기준:
  수치 데이터 직접 인용  +30
  1차 사료 참조          +20
  반증 가능 가설 포함    +20
  경쟁 이론 비교 포함    +15
  연쇄 고리 강도 명시    +15
  ─────────────────────────
  합계 최대              100

60 미만 → provisional=True
"""
from __future__ import annotations

import re

# ── §19-D 항목별 탐지 패턴 ───────────────────────────────────────────────────

# 1. 수치 데이터 직접 인용 (+30)
#    숫자 + 단위(%, bn, Mbpd, 건, 억, GDP 등) 또는 연도+수치 조합
_RE_NUMERIC = re.compile(
    r"\d+\.?\d*\s*(?:%|bn|Mbpd|Mboe|USD|달러|\$|GDP|억|조|만|건|개국|개|명|km|nm)",
    re.IGNORECASE,
)
# SIPRI/EIA 수치 컨텍스트에서 자주 나오는 패턴 (예: "5.9%", "109bn")
_RE_NUMERIC_FALLBACK = re.compile(r"\b\d{2,}[\.,]\d+|\b\d{4,}\b")

# 2. 1차 사료 참조 (+20) — 신뢰할 수 있는 데이터 기관명
_PRIMARY_SOURCES = [
    "SIPRI", "EIA", "ACLED", "COW", "Kiel", "CSIS", "IISS", "IMF",
    "World Bank", "세계은행", "UN ", "OCHA", "NATO", "국방부", "외교부",
    "Chatham", "RAND", "Brookings", "ECFR", "War on the Rocks",
    "Reuters", "BBC", "Al Jazeera", "AP통신",
]

# 3. 반증 가능 가설 (+20)
_RE_HYPOTHESIS = re.compile(
    r"H1[\s:：]|H0[\s:：]|\[가설\]|반증\s*가능|통계적으로\s*유의|"
    r"증가할\s*때|감소할\s*때|높아질수록|낮아질수록|통제변수",
    re.IGNORECASE,
)

# 4. 경쟁 이론 비교 (+15)
_RE_COMPETING = re.compile(
    r"\[경쟁설명\]|\[경쟁\s*이론\]|대안\s*이론|경쟁\s*이론|"
    r"반례[\s:：]|기각\s*근거|설명력\s*하락|다른\s*설명",
    re.IGNORECASE,
)

# 5. 연쇄 고리 강도 명시 (+15)
_RE_CHAIN_STRENGTH = re.compile(
    r"\bHIGH\b|\bMEDIUM\b|\bLOW\b|"
    r"고리\s*강도|연쇄\s*강도|강도[\s:：]\s*(높|중|낮|HIGH|MEDIUM|LOW)",
    re.IGNORECASE,
)


# §P0-B 데이터 공백 패널티 ────────────────────────────────────────────────────

def apply_data_void_penalty(
    confidence: int,
    event_stats_regions: int,
    cascade_links: int,
    structured_sources: int = 0,
) -> int:
    """
    ACLED 이벤트·Cascade가 없을 때 신뢰도 상한을 제한한다 (P0-B).

    [Cycle 7-D L1-a] 정형 수치 소스 보정 추가.
    ACLED/Cascade가 없어도 WBK·ITU·HIIK·CSIS·semi·FRED·SIPRI·V-DEM 등
    정형 수치 데이터가 충분하면 "순수 서술"이 아니므로 상한을 완화한다.

    structured_sources: 비어있지 않은 정형 수치 소스 개수.

    판정:
      ACLED + Cascade 둘 다 존재  → 캡 없음 (동적 인과 근거 완비)
      한 축만 존재               → 정형 보강 시 80, 아니면 72
      둘 다 없음                 → 정형 소스 개수로 차등:
                                    ≥3 → 85 / 2 → 78 / 1 → 70 / 0 → 60
    """
    has_acled   = event_stats_regions > 0
    has_cascade = cascade_links > 0

    # 동적 인과 근거(이벤트 시계열 + Cascade) 완비 → 캡 없음
    if has_acled and has_cascade:
        return confidence

    # 한 축의 동적 데이터 존재 → 정형 보강 시 상한 상향
    if has_acled or has_cascade:
        base_cap = 80 if structured_sources >= 3 else 72
        return min(confidence, base_cap)

    # ACLED·Cascade 둘 다 없음 — 정형 수치 소스만으로 근거 평가
    if structured_sources >= 3:
        return min(confidence, 85)   # 풍부한 정형 데이터 — 횡단면 근거 충분
    if structured_sources == 2:
        return min(confidence, 78)
    if structured_sources == 1:
        return min(confidence, 70)
    return min(confidence, 60)        # 진짜 데이터 공백 (순수 서술)


# §P0-A 인사이트 완결성 검사 ──────────────────────────────────────────────────

_REQUIRED_SECTIONS = [
    "[관찰]", "[주장]", "[가설]", "[근거]", "[한계]", "[경쟁설명]", "[검증포인트]", "[문헌공백]",
]
# [최종검토위 2026-07-11] verify 산출물은 §19-A 6단계 구조라 insight 8섹션 검사가 전건
# FAIL(14/14 실측) — 확증 발행 경로 관통률 0%의 근원. 모드별 필수 섹션 분기(반박석 4a).
_REQUIRED_SECTIONS_VERIFY = [
    "[단계 1]", "[단계 2]", "[단계 3]", "[단계 4]", "[단계 5]", "[단계 6]", "최종 판정",
]
_VALID_ENDINGS = {".", "다", "임", "됨", ")", "음", "?"}

# H1 줄 탐지 — 잘린 H1은 저장 거부 (P0 fix: 다중 카드의 두 번째 H1 잘림 포착)
_RE_H1_LINE = re.compile(r'H1\s*[:：]\s*.+', re.MULTILINE)


def validate_insight_completeness(text: str, mode: str = "insight") -> tuple[bool, str]:
    """
    Gemini 출력이 완결된 카드를 포함하는지 검사한다 (모드별 필수 섹션).

    검사 항목:
      1. 필수 섹션 존재 — insight/presentation: 8섹션, verify: [단계 1~6]+최종 판정
         (최종검토위 2026-07-11 — 모드 무관 8섹션 검사가 verify 발행 경로를 전건 차단하던 결함 수리)
      2. 모든 H1 문장 완결 여부 (두 번째 카드 H1 잘림 포착)
      3. 전체 텍스트 마지막 문장 완결 여부

    Returns:
        (True, "완결") — 저장 허용
        (False, "오류 설명") — 저장 거부
    """
    required = _REQUIRED_SECTIONS_VERIFY if mode == "verify" else _REQUIRED_SECTIONS
    for section in required:
        if section not in text:
            return False, f"미완성: {section} 섹션 없음"

    # H1 문장 완결 — 모든 H1 줄 검사 (다중 카드 잘림 포착)
    for h1_match in _RE_H1_LINE.finditer(text):
        h1_line = h1_match.group().rstrip()
        if h1_line and h1_line[-1] not in _VALID_ENDINGS:
            return False, f"H1 문장 미완성: '{h1_line[-20:]}...'"

    last_char = text.rstrip()[-1] if text.rstrip() else ""
    if last_char not in _VALID_ENDINGS:
        return False, f"마지막 문장 미완성 (마지막 글자: '{last_char}')"

    return True, "완결"


def score_output(text: str) -> dict:
    """
    Gemini 출력 마크다운에서 §19-D 5개 항목을 탐지해 신뢰도 점수를 산출한다.

    Returns:
        {
          "confidence": int (0~100),
          "provisional": bool,
          "breakdown": {
            "numeric_citation":  int (+30 or 0),
            "primary_source":    int (+20 or 0),
            "hypothesis":        int (+20 or 0),
            "competing_theory":  int (+15 or 0),
            "chain_strength":    int (+15 or 0),
          },
          "evidence": {항목: 발견된 예시 문자열 (없으면 None)}
        }
    """
    bd: dict[str, int] = {
        "numeric_citation": 0,
        "primary_source":   0,
        "hypothesis":       0,
        "competing_theory": 0,
        "chain_strength":   0,
    }
    ev: dict[str, str | None] = {k: None for k in bd}

    # 1. 수치 데이터
    m = _RE_NUMERIC.search(text)
    if not m:
        # 단위 없어도 구체적 수치가 충분히 있으면 절반 점수
        m2 = _RE_NUMERIC_FALLBACK.search(text)
        if m2 and len(_RE_NUMERIC_FALLBACK.findall(text)) >= 3:
            bd["numeric_citation"] = 15
            ev["numeric_citation"] = m2.group()[:30]
    else:
        bd["numeric_citation"] = 30
        ev["numeric_citation"] = m.group()[:30]

    # 2. 1차 사료
    for src in _PRIMARY_SOURCES:
        if src.lower() in text.lower():
            bd["primary_source"] = 20
            ev["primary_source"] = src
            break

    # 3. 반증 가능 가설
    m = _RE_HYPOTHESIS.search(text)
    if m:
        bd["hypothesis"] = 20
        ev["hypothesis"] = m.group()[:40]

    # 4. 경쟁 이론
    m = _RE_COMPETING.search(text)
    if m:
        bd["competing_theory"] = 15
        ev["competing_theory"] = m.group()[:40]

    # 5. 연쇄 고리 강도
    m = _RE_CHAIN_STRENGTH.search(text)
    if m:
        bd["chain_strength"] = 15
        ev["chain_strength"] = m.group()[:30]

    total = sum(bd.values())
    return {
        "confidence":  total,
        "provisional": total < 60,
        "breakdown":   bd,
        "evidence":    ev,
    }


# §22-B 신뢰도 상한 캡 (IA-Engine-D)
# ⚠️ DEPRECATED (2026-06-06 학술 정합성 재설계 A1):
#   이 캡은 '증거 충실도'(신뢰도)와 '인과 검증'(Granger)을 한 숫자로 뭉개는
#   Goodhart 결함이었다. 두 축을 분리(증거 등급 + 추론 등급)하면서 호출 폐기.
#   함수는 하위 호환·참고용으로만 유지. intel_query는 더 이상 호출하지 않는다.
_VERIFICATION_CAPS: dict[str, int] = {
    "PENDING":  75,
    "PARTIAL":  88,
    "VERIFIED": 100,
}


def apply_verification_cap(confidence: int, verification_status: str) -> int:
    """[DEPRECATED — A1 2축 분리로 폐기] Granger 상태별 신뢰도 상한. 더는 호출되지 않음."""
    cap = _VERIFICATION_CAPS.get(verification_status, 75)
    return min(confidence, cap)
