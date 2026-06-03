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
