"""
services/entity_parser.py

자연어 쿼리 → 지정학 엔티티 결정론적 추출 (Token-Zero).

LLM을 일절 사용하지 않는다. 키워드·패턴 매핑만으로
지역·행위자·섹터·모드를 추출해 intel_analyzer에 전달한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 쿼리 모드 감지 키워드 ─────────────────────────────────────────────────
# 모드별로 Gemini 프롬프트 형식과 Thinking ON/OFF가 달라진다.
_MODE_KEYWORDS: dict[str, list[str]] = {
    "presentation": [
        "발표", "프레젠테이션", "주제", "주제 선정", "슬라이드",
        "논문", "리포트", "보고서", "각도", "어떻게 발표",
        "presentation", "slide", "topic", "report",
    ],
    "verify": [
        "검증", "맞아", "근거", "사실이야", "틀렸어", "확인",
        "verify", "fact check", "evidence", "is it true",
    ],
    # "insight"는 기본값 — 위 두 가지에 해당 없으면 자동 선택
}

# ── 지역 코드 매핑 ────────────────────────────────────────────────────────
# regions.yaml 코드 + 한국어·영어 별칭 모두 수용
_REGION_ALIASES: dict[str, list[str]] = {
    "hormuz": [
        "호르무즈", "hormuz", "strait of hormuz", "페르시아만", "persian gulf",
    ],
    "bab_el_mandeb": [
        "바브엘만데브", "bab el mandeb", "bab-el-mandeb", "후티", "홍해", "red sea",
        "예멘", "아덴만", "gulf of aden",
    ],
    "malacca": [
        "말라카", "malacca", "malacca strait", "말라카 해협",
    ],
    "taiwan_strait": [
        "대만", "타이완", "taiwan", "대만해협", "taiwan strait",
        "tsmc", "반도체 섬", "양안",
    ],
    "south_china_sea": [
        "남중국해", "south china sea", "스프래틀리", "파라셀", "spratly", "paracel",
        "구단선", "nine dash line",
    ],
    "korean_peninsula": [
        "한반도", "korean peninsula", "한국", "korea", "북한", "north korea",
        "dmz", "비무장지대",
    ],
    "ukraine": [
        "우크라이나", "ukraine", "러우전쟁", "러시아-우크라이나",
        "russia ukraine", "돈바스", "donbas", "donbass", "크림", "crimea",
        "젤렌스키", "푸틴",
    ],
    "middle_east": [
        "중동", "middle east", "이스라엘", "가자", "gaza", "israel",
        "헤즈볼라", "hezbollah", "하마스", "hamas", "레바논", "lebanon",
        "이란", "iran", "시리아", "syria",
    ],
    "east_china_sea": [
        "동중국해", "east china sea", "센카쿠", "senkaku", "댜오위다오", "diaoyu",
    ],
    "suez": [
        "수에즈", "suez", "수에즈 운하", "suez canal",
    ],
}

# ── 행위자(국가) 매핑 — ISO3 ──────────────────────────────────────────────
_ACTOR_ALIASES: dict[str, list[str]] = {
    "CHN": ["중국", "china", "prc", "pla", "중화인민공화국", "베이징", "beijing"],
    "USA": ["미국", "usa", "us", "united states", "america", "워싱턴", "washington", "pentagon"],
    "RUS": ["러시아", "russia", "러시아 연방", "모스크바", "moscow", "크렘린", "kremlin"],
    "IRN": ["이란", "iran", "테헤란", "tehran", "혁명수비대", "irgc"],
    "TWN": ["대만", "taiwan", "타이완", "taipei", "타이베이"],
    "KOR": ["한국", "south korea", "대한민국", "서울", "seoul"],
    "PRK": ["북한", "north korea", "dprk", "평양", "pyongyang", "김정은"],
    "JPN": ["일본", "japan", "도쿄", "tokyo", "자위대", "jsdf"],
    "SAU": ["사우디", "saudi", "saudi arabia", "리야드", "riyadh", "aramco"],
    "ISR": ["이스라엘", "israel", "이스라엘 방위군", "idf", "텔아비브", "tel aviv"],
    "UKR": ["우크라이나", "ukraine", "키이우", "kyiv", "zelensky", "젤렌스키"],
    "IND": ["인도", "india", "뉴델리", "new delhi", "모디", "modi"],
    "AUS": ["호주", "australia", "캔버라", "canberra", "aukus"],
    "NLD": ["네덜란드", "netherlands", "asml", "holland"],
    "TUR": ["터키", "turkey", "튀르키예", "turkiye", "앙카라", "ankara", "에르도안"],
}

# ── 섹터 감지 키워드 ──────────────────────────────────────────────────────
_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "maritime": [
        "해양", "해군", "선박", "항만", "해협", "슬록", "sloc",
        "chokepoint", "초크포인트", "잠수함", "submarine", "naval",
    ],
    "energy": [
        "에너지", "원유", "석유", "가스", "lng", "파이프라인", "pipeline",
        "유가", "oil", "gas", "opec", "자원", "resource",
    ],
    "techno": [
        "반도체", "chip", "semiconductor", "5g", "ai", "인공지능",
        "tsmc", "asml", "희토류", "rare earth", "gallium", "공급망", "supply chain",
        "사이버", "cyber", "드론", "drone", "위성", "satellite",
    ],
    "indo_pacific": [
        "인도태평양", "indo-pacific", "indo pacific", "a2ad", "a2/ad",
        "제1열도선", "first island chain", "쿼드", "quad", "aukus",
        "핵잠", "ssn", "ssbn",
    ],
    "gray_zone": [
        "회색지대", "gray zone", "grey zone", "하이브리드", "hybrid",
        "프록시", "proxy", "비정규전", "irregular", "살라미", "salami",
        "제재", "sanctions", "covert", "coercion",
    ],
    "cyber": [
        "사이버전", "사이버 공격", "cyberwar", "cyberattack", "apt",
        "랜섬웨어", "ransomware", "해킹", "hack", "허위정보", "disinformation",
        "인지전", "cognitive war", "information operation",
    ],
}

# ── 시간 범위 감지 ────────────────────────────────────────────────────────
_ERA_KEYWORDS: dict[str, list[str]] = {
    "hot":         ["최근", "지금", "현재", "오늘", "이번 주", "recent", "current", "now"],
    "us_china_rivalry": ["미중", "us-china", "미중 갈등", "미중 경쟁"],
    "post_cold":   ["탈냉전", "post cold war", "90년대", "2000년대"],
    "cold_war":    ["냉전", "cold war", "소련", "soviet"],
}


@dataclass
class ParsedQuery:
    """entity_parser 출력 — intel_analyzer의 검색 파라미터."""

    raw_query: str
    mode: str = "insight"              # "insight" | "presentation" | "verify"
    regions: list[str] = field(default_factory=list)    # regions.yaml 코드
    actors: list[str] = field(default_factory=list)     # ISO3
    sectors: list[str] = field(default_factory=list)    # 6대 섹터
    era: str | None = None             # temporal_era 필터 (library 검색용)
    thinking: bool = False             # Gemini Thinking ON 여부

    def to_dict(self) -> dict:
        return {
            "raw_query": self.raw_query,
            "mode": self.mode,
            "regions": self.regions,
            "actors": self.actors,
            "sectors": self.sectors,
            "era": self.era,
            "thinking": self.thinking,
        }


def parse_query(query: str) -> ParsedQuery:
    """
    자연어 쿼리 → ParsedQuery 결정론적 추출.

    Token-Zero: LLM 호출 없음. 키워드 매핑만 사용.
    """
    q_lower = query.lower()

    # ── 1. 모드 감지 ──────────────────────────────────────────────────────
    mode = "insight"
    for m, keywords in _MODE_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            mode = m
            break

    # ── 2. 지역 감지 (복수 허용) ──────────────────────────────────────────
    regions: list[str] = []
    for region_code, aliases in _REGION_ALIASES.items():
        if any(alias in q_lower for alias in aliases):
            regions.append(region_code)

    # ── 3. 행위자 감지 (복수 허용) ───────────────────────────────────────
    actors: list[str] = []
    for iso3, aliases in _ACTOR_ALIASES.items():
        if any(alias in q_lower for alias in aliases):
            actors.append(iso3)

    # ── 4. 섹터 감지 (복수 허용) ─────────────────────────────────────────
    sectors: list[str] = []
    for sector, keywords in _SECTOR_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            sectors.append(sector)

    # 지역에서 섹터 보완 (지역만 언급해도 관련 섹터 자동 추가)
    _REGION_TO_SECTOR: dict[str, list[str]] = {
        "ukraine":          ["gray_zone", "energy"],
        "taiwan_strait":    ["indo_pacific", "techno", "maritime"],
        "hormuz":           ["energy", "maritime"],
        "bab_el_mandeb":    ["maritime", "gray_zone"],
        "south_china_sea":  ["maritime", "indo_pacific"],
        "korean_peninsula": ["indo_pacific"],
        "middle_east":      ["gray_zone", "energy"],
        "malacca":          ["maritime", "energy"],
        "suez":             ["maritime", "energy"],
    }
    for r in regions:
        for s in _REGION_TO_SECTOR.get(r, []):
            if s not in sectors:
                sectors.append(s)

    # ── 5. 시간 범위 감지 ─────────────────────────────────────────────────
    era: str | None = None
    for era_code, keywords in _ERA_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            era = era_code
            break

    # ── 6. Thinking ON/OFF 결정 ───────────────────────────────────────────
    # presentation·verify 모드 또는 복수 지역/섹터 교차 분석 → Thinking ON
    thinking = mode in ("presentation", "verify") or (
        len(regions) >= 2 or len(sectors) >= 3
    )

    return ParsedQuery(
        raw_query=query,
        mode=mode,
        regions=regions,
        actors=actors,
        sectors=sectors,
        era=era,
        thinking=thinking,
    )
