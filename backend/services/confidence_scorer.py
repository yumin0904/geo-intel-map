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

def apply_data_void_penalty(confidence: int, event_stats_regions: int, cascade_links: int) -> int:
    """
    ACLED 이벤트와 Cascade가 없을 때 신뢰도 상한을 제한한다 (P0-B).

    둘 다 0 → 상한 60 (데이터 공백, 순수 서술 수준)
    하나만 0 → 상한 72 (부분 공백)
    """
    if event_stats_regions == 0 and cascade_links == 0:
        return min(confidence, 60)
    if event_stats_regions == 0 or cascade_links == 0:
        return min(confidence, 72)
    return confidence


# §P0-A 인사이트 완결성 검사 ──────────────────────────────────────────────────

_REQUIRED_SECTIONS = [
    "[관찰]", "[주장]", "[가설]", "[근거]", "[한계]", "[경쟁설명]", "[검증포인트]", "[문헌공백]",
]
_VALID_ENDINGS = {".", "다", "임", "됨", ")", "음", "?"}

# H1 줄 탐지 — 잘린 H1은 저장 거부 (P0 fix: 다중 카드의 두 번째 H1 잘림 포착)
_RE_H1_LINE = re.compile(r'H1\s*[:：]\s*.+', re.MULTILINE)


def validate_insight_completeness(text: str) -> tuple[bool, str]:
    """
    Gemini 출력이 완결된 인사이트 카드를 포함하는지 검사한다.

    검사 항목:
      1. 필수 8개 섹션 존재 여부 ([문헌공백] 포함)
      2. 모든 H1 문장 완결 여부 (두 번째 카드 H1 잘림 포착)
      3. 전체 텍스트 마지막 문장 완결 여부

    Returns:
        (True, "완결") — 저장 허용
        (False, "오류 설명") — 저장 거부
    """
    for section in _REQUIRED_SECTIONS:
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
_VERIFICATION_CAPS: dict[str, int] = {
    "PENDING":  75,
    "PARTIAL":  88,
    "VERIFIED": 100,  # 상한 없음
}


def apply_verification_cap(confidence: int, verification_status: str) -> int:
    """
    Granger 검증 상태에 따라 신뢰도 점수에 상한 캡을 적용한다 (§22-B).

    PENDING  → 최대 75점 (가설 미검증)
    PARTIAL  → 최대 88점 (경향성 확인, p<0.15)
    VERIFIED → 상한 없음 (Granger p<0.05 충족)
    """
    cap = _VERIFICATION_CAPS.get(verification_status, 75)
    return min(confidence, cap)
