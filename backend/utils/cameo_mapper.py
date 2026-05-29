"""
cameo_mapper.py — GDELT CAMEO 코드 → 7대 축 IntelligenceMetadata 결정론적 매핑

CLAUDE.md §14 Token-Zero Tagging Rule:
  실시간 첩보 태깅에 LLM 절대 미사용.
  ActorType1Code / EventRootCode / GoldsteinScale 세 필드만으로 축 5·6·7을 확정한다.
  축 1~4는 region_code + timestamp에서 파생.

매핑 기준 (CLAUDE.md §14-A):
  level_of_analysis  ← Actor1Type1Code
    IGO, MNI, IXM, IGU, NGM → systemic
    GOV, MIL, COP, LEG, ELI, SPY, JUD → state_domestic
    REB, INS, NGO, CVL, OPP, REL, STU → non_state

  instrument_of_power ← EventRootCode (2자리)
    01~05 → diplomatic
    16    → economic
    17~20 → military
    그 외  → informational

  strategic_posture   ← GoldsteinScale
    ≤ -5.0 → revisionist
    그 외   → status_quo
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Literal

from models.intelligence import IntelligenceMetadata

# ── 축 5: Waltz 분석 수준 ────────────────────────────────────────────────────
# Actor1Type1Code 기준 (CAMEO actor type 코드표)
_SYSTEMIC_TYPES: frozenset[str] = frozenset({
    "IGO",  # 정부간기구 (UN, NATO, ASEAN...)
    "MNI",  # 다국적 기업
    "IXM",  # 국제 운동/단체
    "IGU",  # 국제 연합 기구
    "NGM",  # 다국적 NGO
})

_STATE_DOMESTIC_TYPES: frozenset[str] = frozenset({
    "GOV",  # 정부
    "MIL",  # 군
    "COP",  # 경찰/법집행
    "LEG",  # 의회/입법
    "ELI",  # 엘리트
    "SPY",  # 정보기관
    "JUD",  # 사법부
})

_NON_STATE_TYPES: frozenset[str] = frozenset({
    "REB",  # 반군
    "INS",  # 반란군/무장세력
    "NGO",  # 비정부기구
    "CVL",  # 민간인
    "OPP",  # 야당
    "REL",  # 종교단체
    "STU",  # 학생/청년운동
    "MED",  # 미디어
    "BUS",  # 기업 (국내)
})


def _map_level(actor1_type_code: str) -> Literal["systemic", "state_domestic", "non_state"]:
    """Actor1Type1Code → Waltz 분석 수준."""
    code = (actor1_type_code or "").strip().upper()
    if code in _SYSTEMIC_TYPES:
        return "systemic"
    if code in _NON_STATE_TYPES:
        return "non_state"
    # GOV/MIL 등 명시 코드이거나 미상이면 state_domestic (국가가 기본 행위자)
    return "state_domestic"


# ── 축 6: DIME 권력 수단 ─────────────────────────────────────────────────────
# EventRootCode 2자리 정수 기준 (CAMEO verb code table)
def _map_instrument(event_root_code: str) -> Literal["diplomatic", "informational", "military", "economic"]:
    """EventRootCode → DIME 권력 수단."""
    try:
        code_int = int((event_root_code or "0").strip()[:2])
    except ValueError:
        return "informational"

    if 1 <= code_int <= 5:
        # 01=성명, 02=호소, 03=표현, 04=협의, 05=외교협력
        return "diplomatic"
    if code_int == 16:
        # 16=경제제재·봉쇄
        return "economic"
    if 17 <= code_int <= 20:
        # 17=강압, 18=공격, 19=전투, 20=대량파괴
        return "military"
    # 06~15, 21+ — 정보전·비난·위협·시위 등
    return "informational"


# ── 축 7: 전략 태세 ──────────────────────────────────────────────────────────
def _map_posture(goldstein_scale: float) -> Literal["status_quo", "revisionist"]:
    """GoldsteinScale ≤ -5.0 → revisionist (현상타파 의도 강함)."""
    return "revisionist" if goldstein_scale <= -5.0 else "status_quo"


# ── 축 3: 섹터 주도 ──────────────────────────────────────────────────────────
# region_code → sector_lead (지역이 가장 명확한 섹터 결정인자)
_REGION_SECTOR: dict[str, Literal["maritime", "energy", "techno", "alliance", "gray_zone"]] = {
    "taiwan_strait":    "maritime",
    "south_china_sea":  "maritime",
    "east_china_sea":   "maritime",
    "korean_strait":    "maritime",
    "malacca":          "maritime",
    "bab_el_mandeb":    "maritime",
    "suez":             "maritime",
    "red_sea":          "maritime",
    "hormuz":           "energy",
    "persian_gulf":     "energy",
    "ukraine":          "alliance",
    "eastern_europe":   "alliance",
    "korean_peninsula": "alliance",
    "middle_east":      "gray_zone",
}


def _map_sector(
    region_code: str | None,
    instrument: Literal["diplomatic", "informational", "military", "economic"],
) -> Literal["maritime", "energy", "techno", "alliance", "gray_zone"] | None:
    """region_code 우선 → instrument 보조 → None."""
    if region_code and region_code in _REGION_SECTOR:
        return _REGION_SECTOR[region_code]
    # 지역 매핑 없으면 instrument로 추론
    if instrument == "economic":
        return "energy"  # 경제 강압 → 자원 에너지 섹터
    if instrument == "informational":
        return "gray_zone"
    return None


# ── 축 4: 시대 배경 ──────────────────────────────────────────────────────────
_HOT_WINDOW = timedelta(days=7)
_US_CHINA_RIVALRY_START = datetime(2017, 1, 1, tzinfo=timezone.utc)  # 트럼프 1기 취임, 미·중 경쟁 본격화
_POST_COLD_START = datetime(1991, 12, 26, tzinfo=timezone.utc)       # 소련 해체


def _map_temporal_era(timestamp: datetime) -> Literal["cold_war", "post_cold", "us_china_rivalry", "hot"]:
    """타임스탬프 → 시대 배경."""
    now = datetime.now(timezone.utc)
    if now - timestamp <= _HOT_WINDOW:
        return "hot"
    if timestamp >= _US_CHINA_RIVALRY_START:
        return "us_china_rivalry"
    if timestamp >= _POST_COLD_START:
        return "post_cold"
    return "cold_war"


# ── GKG 테마 → 7대 축 매핑 ──────────────────────────────────────────────────
# GKG 테마 코드 → (instrument_of_power, strategic_posture 보정 여부)
# Token-Zero: 결정론적 prefix 매칭만 사용
_GKG_THEME_TO_INSTRUMENT: dict[str, str] = {
    "WA_":                 "military",      # 무기류
    "MILITARY":            "military",
    "CONFLICT":            "military",
    "TAX_FNCACT_REBEL":    "military",
    "TAX_FNCACT_MILPERS":  "military",
    "CRISISLEX_":          "military",
    "PROTEST":             "informational", # 시위는 정보전 범주
    "SANCTIONS":           "economic",
    "EPU_POLICY_":         "economic",
    "MARITIME_":           "military",
    "UNGP_":               "diplomatic",
}

_GKG_THEME_TO_SECTOR: dict[str, str] = {
    "MARITIME_":   "maritime",
    "WA_":         "gray_zone",
    "SANCTIONS":   "energy",
    "CRISISLEX_":  "gray_zone",
    "MILITARY":    "alliance",
    "CONFLICT":    "gray_zone",
}


def map_gkg_themes_to_tags(
    themes: list[str],
    tone: float,
    existing_instrument: str | None = None,
    existing_sector: str | None = None,
) -> dict:
    """GKG 테마 목록 + 톤 점수 → 7대 축 보강 정보 반환.

    CLAUDE.md §14-A Token-Zero Rule 준수: LLM 호출 없이 결정론적 매핑.

    Args:
        themes:              GkgRecord.themes (분쟁 관련 테마 코드 목록)
        tone:                V2Tone overall (음수 = 적대적)
        existing_instrument: 기존 CAMEO 매핑 결과 (있으면 GKG 결과로 덮어쓰지 않음)
        existing_sector:     기존 sector_lead

    Returns:
        dict with keys: instrument_of_power, sector_lead, strategic_posture,
                        gkg_theme_count, hostility_confirmed
    """
    instrument = existing_instrument
    sector     = existing_sector

    for theme in themes:
        for prefix, instr in _GKG_THEME_TO_INSTRUMENT.items():
            if theme.startswith(prefix) and not instrument:
                instrument = instr
                break
        for prefix, sec in _GKG_THEME_TO_SECTOR.items():
            if theme.startswith(prefix) and not sector:
                sector = sec
                break

    # 톤 기반 strategic_posture 보정
    # V2Tone ≤ -5 → revisionist 신호 (CAMEO GoldsteinScale 기준과 동일 임계치)
    posture = "revisionist" if tone <= -5.0 else "status_quo"

    # 적대성 확인: 분쟁 테마 2개 이상 + 강한 부정 톤
    hostility_confirmed = len(themes) >= 2 and tone <= -3.0

    return {
        "instrument_of_power":  instrument or "informational",
        "sector_lead":          sector,
        "strategic_posture":    posture,
        "gkg_theme_count":      len(themes),
        "hostility_confirmed":  hostility_confirmed,
        "top_themes":           themes[:5],  # 최대 5개만 저장
    }


# ── 공개 인터페이스 ──────────────────────────────────────────────────────────
def map_gdelt_to_intelligence_tags(
    actor1_type_code: str,
    event_root_code: str,
    goldstein_scale: float,
    region_code: str | None,
    timestamp: datetime,
) -> IntelligenceMetadata:
    """GDELT 3개 CAMEO 필드 → IntelligenceMetadata (7대 축 전체).

    LLM 호출 없이 순수 파이썬 결정론적 매핑.
    CLAUDE.md §14-A Token-Zero Tagging Rule 준수.

    Args:
        actor1_type_code: GDELT Actor1Type1Code (예: "MIL", "GOV", "REB")
        event_root_code:  CAMEO EventRootCode 2자리 (예: "18", "19", "14")
        goldstein_scale:  GoldsteinScale float (-10 ~ +10)
        region_code:      자체 지역 코드 (예: "taiwan_strait"), None이면 미분류
        timestamp:        이벤트 발생 UTC 시각

    Returns:
        IntelligenceMetadata — 모든 7개 축이 채워진 태그 객체
    """
    instrument = _map_instrument(event_root_code)
    sector     = _map_sector(region_code, instrument)

    return IntelligenceMetadata(
        form_type="data_point",                          # 축 1: GDELT는 항상 실시간 데이터포인트
        geopol_region=region_code,                       # 축 2: region_for_point() 결과 그대로
        sector_lead=sector,                              # 축 3: region_code → sector
        temporal_era=_map_temporal_era(timestamp),       # 축 4: 타임스탬프 기반
        level_of_analysis=_map_level(actor1_type_code),  # 축 5: ActorType1Code → Waltz
        instrument_of_power=instrument,                  # 축 6: EventRootCode → DIME
        strategic_posture=_map_posture(goldstein_scale), # 축 7: GoldsteinScale → Snyder
    )
