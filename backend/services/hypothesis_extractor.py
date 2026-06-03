"""
services/hypothesis_extractor.py

Gemini 출력 마크다운에서 [가설] 섹션을 파싱해 HypothesisSpec 목록을 반환한다.
Token-Zero 원칙: LLM 없이 정규식+키워드 매핑만 사용.

변수 매핑 전략:
  independent_var (지역/행위자 기반) → region_code → event_archive 시계열
  dependent_var   (지표 키워드 기반) → ticker       → market/indicator 시계열
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# ── 데이터 모델 ───────────────────────────────────────────────────────────────

VerificationStatus = Literal["PENDING", "PARTIAL", "VERIFIED"]


@dataclass
class HypothesisSpec:
    h1: str                              # 반증 가능 형태 H1 텍스트
    h0: str                              # 귀무가설 (자동 생성)
    independent_var: str                 # 원문 독립변수 기술
    dependent_var: str                   # 원문 종속변수 기술
    control_vars: list[str] = field(default_factory=list)
    region_code: str | None = None       # event_archive 조회용
    ticker: str | None = None            # 시장/지표 시계열 조회용
    verification_status: VerificationStatus = "PENDING"
    granger_p: float | None = None
    best_lag: int | None = None
    n_obs: int = 0
    error: str | None = None


# ── region 키워드 매핑 ────────────────────────────────────────────────────────
# independent_var 텍스트에서 지역/행위자를 식별해 event_archive region_code로 변환

_REGION_MAP: list[tuple[list[str], str]] = [
    (["우크라이나", "ukraine", "러시아", "russia", "동유럽", "eastern europe"], "eastern_europe"),
    (["대만", "taiwan", "남중국해", "south china", "반도체", "tsmc"], "taiwan_strait"),
    (["호르무즈", "hormuz", "이란", "iran", "걸프", "gulf", "페르시아"], "hormuz"),
    (["한반도", "korean", "북한", "dprk", "조선"], "korean_peninsula"),
    (["홍해", "red sea", "바브엘만데브", "bab el", "예멘", "후티", "houthi"], "bab_el_mandeb"),
    (["수에즈", "suez", "이집트", "egypt"], "suez"),
    (["중동", "middle east", "이스라엘", "israel", "팔레스타인"], "middle_east"),
    (["말라카", "malacca", "동남아", "southeast asia"], "malacca"),
    (["사헬", "sahel", "아프리카", "africa", "말리", "niger"], "sahel"),
]

# ── ticker 키워드 매핑 ────────────────────────────────────────────────────────
# dependent_var 텍스트에서 지표를 식별해 correlation.py 호환 ticker로 변환

_TICKER_MAP: list[tuple[list[str], str, str]] = [
    # (키워드 목록, ticker, 설명)
    (["wti", "원유", "유가", "crude", "oil", "brent"], "CL=F", "WTI 원유 선물"),
    (["천연가스", "natural gas", "가스", "lng", "ng=f"], "NG=F", "천연가스 선물"),
    (["tsmc", "tsm", "반도체", "semiconductor", "파운드리"], "TSM", "TSMC 주가"),
    (["원달러", "usd/krw", "krw", "원화", "환율", "usd_krw", "달러원"], "KRW=X", "원/달러 환율"),
    (["밀", "wheat", "소맥", "곡물", "grain"], "ZW=F", "밀 선물"),
    (["금", "gold", "gld", "귀금속"], "GLD", "금 ETF"),
    (["방산", "defense", "무기", "ita", "군비"], "ITA", "방산 ETF"),
    (["soxx", "반도체etf", "semiconductor etf", "chips"], "SOXX", "반도체 ETF"),
]

# ── 정규식 ────────────────────────────────────────────────────────────────────

# [가설] H1: "..." 형태 (따옴표 있거나 없는 형태 모두 처리)
_RE_H1 = re.compile(
    r'\[가설\]\s*H1\s*[:：]\s*[""""]?(.+?)[""""]?\s*$',
    re.MULTILINE | re.IGNORECASE,
)

# (통제변수: X, Y) 추출
_RE_CONTROL = re.compile(
    r'통제변수\s*[:：]\s*([^\n\)]+)',
    re.IGNORECASE,
)

# "X가 증가할 때 Y가" 구조에서 독립/종속변수 추출
_RE_WHEN_THEN = re.compile(
    r'(.+?)\s*(?:가|이|이\s*)?(?:증가|상승|강화|확대|악화|발생|감소|하락)할\s*때.{0,10}?(.+?)\s*(?:가|이|이\s*)?(?:통계적|유의|증가|감소|상승|하락)',
    re.IGNORECASE,
)


def _match_region(text: str) -> str | None:
    """텍스트에서 region_code를 결정론적으로 추출한다."""
    text_lower = text.lower()
    for keywords, code in _REGION_MAP:
        if any(kw in text_lower for kw in keywords):
            return code
    return None


def _match_ticker(text: str) -> tuple[str, str] | None:
    """텍스트에서 (ticker, 설명)을 결정론적으로 추출한다."""
    text_lower = text.lower()
    for keywords, ticker, desc in _TICKER_MAP:
        if any(kw in text_lower for kw in keywords):
            return ticker, desc
    return None


def _make_h0(h1: str) -> str:
    """H1 텍스트에서 귀무가설 H0를 자동 생성한다."""
    # "통계적으로 유의하게 변화한다" 이후 전체를 귀무가설 표현으로 대체
    h0 = re.sub(
        r'통계적으로\s*유의하게\s*(증가|감소|상승|하락|변화).*',
        '통계적으로 유의한 관계가 없다.',
        h1,
    )
    if h0 == h1:  # 패턴 미매칭 시 일반 형태
        h0 = "위의 독립변수와 종속변수 사이에 통계적으로 유의한 관계가 없다."
    return h0


def extract_hypotheses(text: str) -> list[HypothesisSpec]:
    """
    Gemini 출력 마크다운에서 HypothesisSpec 목록을 추출한다.
    인사이트 카드 2~3개에서 각각 [가설] 섹션을 파싱한다.
    """
    specs: list[HypothesisSpec] = []

    for m in _RE_H1.finditer(text):
        h1_raw = m.group(1).strip()
        if not h1_raw or len(h1_raw) < 10:
            continue

        # 통제변수 추출 (H1 텍스트 내 또는 인근 줄)
        control_vars: list[str] = []
        ctrl_m = _RE_CONTROL.search(h1_raw)
        if ctrl_m:
            control_vars = [v.strip() for v in ctrl_m.group(1).split(",") if v.strip()]
            # 통제변수 괄호 제거한 순수 H1
            h1_clean = _RE_CONTROL.sub("", h1_raw).strip().rstrip("()")
        else:
            h1_clean = h1_raw

        # 독립/종속변수 추출 시도
        wt_m = _RE_WHEN_THEN.search(h1_clean)
        if wt_m:
            independent_var = wt_m.group(1).strip()
            dependent_var = wt_m.group(2).strip()
        else:
            # 구조 파싱 실패 시 전체 H1을 독립변수로 사용
            independent_var = h1_clean
            dependent_var = ""

        # region/ticker 매핑 — H1 전체 + 독립/종속변수 합쳐서 검색
        combined_text = f"{h1_clean} {independent_var} {dependent_var}"
        region_code = _match_region(combined_text)
        ticker_match = _match_ticker(combined_text)
        ticker = ticker_match[0] if ticker_match else None

        spec = HypothesisSpec(
            h1=h1_clean,
            h0=_make_h0(h1_clean),
            independent_var=independent_var or h1_clean[:60],
            dependent_var=dependent_var or "미식별",
            control_vars=control_vars,
            region_code=region_code,
            ticker=ticker,
        )
        specs.append(spec)

    return specs
