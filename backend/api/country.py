"""
country.py — 국가 클릭 정보 패널 API

GET /api/country/{iso3}
    국가 기본정보 + FRED 거시지표(최근 30일) + 무역 의존도(WITS/Comtrade) + 제재 레짐 + 관련 이론
    캐시: 30분

정치외교학 이론 연결:
    - Farrell & Newman 'Weaponized Interdependence': 무역 의존도 수치화
    - Drezner 'Economic Coercion': 제재 레짐 목록
    - Waltz 3수준 분석: 국가 단위 분석 수준 표현
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter

router = APIRouter(prefix="/api/country", tags=["country"])
logger = logging.getLogger(__name__)

_ROOT           = Path(__file__).resolve().parent.parent
_INTEL_DB       = _ROOT / "db" / "intel.db"
_LIBRARY_DB     = _ROOT / "db" / "library.db"
_SANCTIONS_YAML = _ROOT / "config" / "sanctions.yaml"

_CACHE_TTL = timedelta(minutes=30)
_cache: dict[str, tuple[datetime, dict]] = {}

# ── HS 코드 한국어 이름 ──────────────────────────────────────────────────────
_HS_NAMES: dict[str, str] = {
    "8542": "반도체·집적회로",
    "27":   "에너지·광물연료",
    "26":   "광석·희토류",
}

# ── ISO3 → ISO2 (제재 yaml target_country 매칭용) ─────────────────────────
_ISO3_TO_ISO2: dict[str, str] = {
    "PRK": "KP", "CHN": "CN", "RUS": "RU", "IRN": "IR",
    "VEN": "VE", "BLR": "BY", "MMR": "MM", "SYR": "SY",
    "CUB": "CU", "SDN": "SD", "LBY": "LY", "SOM": "SO",
    "MLI": "ML", "HTI": "HT", "YEM": "YE", "USA": "US",
    "KOR": "KR", "TWN": "TW", "JPN": "JP", "DEU": "DE",
    "GBR": "GB", "FRA": "FR", "AUS": "AU", "IND": "IN",
    "BRA": "BR", "SAU": "SA", "TUR": "TR", "ISR": "IL",
    "UKR": "UA", "POL": "PL", "EGY": "EG", "IDN": "ID",
    "PAK": "PK", "IRQ": "IQ", "AFG": "AF", "ETH": "ET",
    "NGA": "NG", "ZAF": "ZA", "MEX": "MX", "ARE": "AE",
    "NLD": "NL",
    "KWT": "KW", "QAT": "QA", "OMN": "OM", "PHL": "PH",
    "VNM": "VN", "MYS": "MY", "SGP": "SG", "THA": "TH",
}

# ── FRED 지표 메타 ────────────────────────────────────────────────────────────
_FRED_LABELS: dict[str, dict] = {
    "wti":     {"label": "WTI 원유",      "unit": "USD/배럴"},
    "brent":   {"label": "브렌트유",      "unit": "USD/배럴"},
    "usd_krw": {"label": "원/달러 환율",  "unit": "KRW/USD"},
    "usd_twd": {"label": "대만달러/달러", "unit": "TWD/USD"},
    "vix":     {"label": "VIX 변동성",    "unit": "포인트"},
}

# ── 국가 정보 레지스트리 ──────────────────────────────────────────────────────
# fred_indicators: 해당 국가에 가장 관련성 높은 FRED 지표 순서
_COUNTRY_INFO: dict[str, dict] = {
    "KOR": {"name_ko": "한국",         "name_en": "South Korea",
            "region_code": "korean_peninsula",
            "fred_indicators": ["usd_krw", "wti", "vix"]},
    "PRK": {"name_ko": "북한",         "name_en": "North Korea",
            "region_code": "korean_peninsula",
            "fred_indicators": ["wti", "vix"]},
    "CHN": {"name_ko": "중국",         "name_en": "China",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    "TWN": {"name_ko": "대만",         "name_en": "Taiwan",
            "region_code": "taiwan_strait",
            "fred_indicators": ["usd_twd", "wti", "vix"]},
    "JPN": {"name_ko": "일본",         "name_en": "Japan",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    "RUS": {"name_ko": "러시아",       "name_en": "Russia",
            "region_code": "ukraine",
            "fred_indicators": ["brent", "wti", "vix"]},
    "UKR": {"name_ko": "우크라이나",   "name_en": "Ukraine",
            "region_code": "ukraine",
            "fred_indicators": ["brent", "wti", "vix"]},
    "IRN": {"name_ko": "이란",         "name_en": "Iran",
            "region_code": "hormuz",
            "fred_indicators": ["wti", "brent", "vix"]},
    "IRQ": {"name_ko": "이라크",       "name_en": "Iraq",
            "region_code": "hormuz",
            "fred_indicators": ["wti", "brent", "vix"]},
    "SAU": {"name_ko": "사우디아라비아","name_en": "Saudi Arabia",
            "region_code": "hormuz",
            "fred_indicators": ["wti", "brent", "vix"]},
    "ARE": {"name_ko": "아랍에미리트", "name_en": "UAE",
            "region_code": "hormuz",
            "fred_indicators": ["wti", "brent", "vix"]},
    "YEM": {"name_ko": "예멘",         "name_en": "Yemen",
            "region_code": "bab_el_mandeb",
            "fred_indicators": ["wti", "brent", "vix"]},
    "ISR": {"name_ko": "이스라엘",     "name_en": "Israel",
            "region_code": "middle_east",
            "fred_indicators": ["wti", "vix"]},
    "SYR": {"name_ko": "시리아",       "name_en": "Syria",
            "region_code": "middle_east",
            "fred_indicators": ["wti", "vix"]},
    "USA": {"name_ko": "미국",         "name_en": "United States",
            "region_code": None,
            "fred_indicators": ["wti", "vix"]},
    "GBR": {"name_ko": "영국",         "name_en": "United Kingdom",
            "region_code": None,
            "fred_indicators": ["brent", "vix"]},
    "DEU": {"name_ko": "독일",         "name_en": "Germany",
            "region_code": None,
            "fred_indicators": ["brent", "vix"]},
    "FRA": {"name_ko": "프랑스",       "name_en": "France",
            "region_code": None,
            "fred_indicators": ["brent", "vix"]},
    "IND": {"name_ko": "인도",         "name_en": "India",
            "region_code": None,
            "fred_indicators": ["wti", "brent", "vix"]},
    "VEN": {"name_ko": "베네수엘라",   "name_en": "Venezuela",
            "region_code": None,
            "fred_indicators": ["wti", "brent"]},
    "MMR": {"name_ko": "미얀마",       "name_en": "Myanmar",
            "region_code": None,
            "fred_indicators": ["wti", "vix"]},
    "BLR": {"name_ko": "벨라루스",     "name_en": "Belarus",
            "region_code": None,
            "fred_indicators": ["brent", "vix"]},
    "SOM": {"name_ko": "소말리아",     "name_en": "Somalia",
            "region_code": "bab_el_mandeb",
            "fred_indicators": ["wti", "vix"]},
    "MLI": {"name_ko": "말리",         "name_en": "Mali",
            "region_code": None,
            "fred_indicators": ["wti", "vix"]},
    "SDN": {"name_ko": "수단",         "name_en": "Sudan",
            "region_code": None,
            "fred_indicators": ["wti", "vix"]},
    "LBY": {"name_ko": "리비아",       "name_en": "Libya",
            "region_code": None,
            "fred_indicators": ["wti", "brent", "vix"]},
    "CUB": {"name_ko": "쿠바",         "name_en": "Cuba",
            "region_code": None,
            "fred_indicators": ["wti"]},
    "HTI": {"name_ko": "아이티",       "name_en": "Haiti",
            "region_code": None,
            "fred_indicators": ["wti"]},
    "PHL": {"name_ko": "필리핀",       "name_en": "Philippines",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    "VNM": {"name_ko": "베트남",       "name_en": "Vietnam",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    "IDN": {"name_ko": "인도네시아",   "name_en": "Indonesia",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    "MYS": {"name_ko": "말레이시아",   "name_en": "Malaysia",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    "SGP": {"name_ko": "싱가포르",     "name_en": "Singapore",
            "region_code": "south_china_sea",
            "fred_indicators": ["wti", "vix"]},
    # ── 확장 (2026-05-30): 5대 섹터 추가 커버리지 ─────────────────────────
    "AUS": {"name_ko": "호주",         "name_en": "Australia",
            "region_code": None,
            # AUKUS·QUAD 핵심 멤버, 철광석·LNG 수출로 Weaponized Interdependence 직접 노출
            "fred_indicators": ["wti", "brent", "vix"],
            "sector_tags": ["maritime", "indo_pacific"]},
    "TUR": {"name_ko": "튀르키예",     "name_en": "Turkey",
            "region_code": "middle_east",
            # NATO 회원국이면서 러시아 에너지 의존 — 동맹 딜레마(Snyder)의 생생한 사례
            "fred_indicators": ["brent", "wti", "vix"]},
    "QAT": {"name_ko": "카타르",       "name_en": "Qatar",
            "region_code": "hormuz",
            # 세계 최대 LNG 수출국 — 호르무즈 봉쇄 시 유럽·아시아 에너지 안보 직격
            "fred_indicators": ["wti", "brent", "vix"]},
    "NLD": {"name_ko": "네덜란드",     "name_en": "Netherlands",
            "region_code": None,
            # ASML: EUV 노광기 독점 → 반도체 공급망 병목점. 테크노내셔널리즘 핵심 사례
            "fred_indicators": ["brent", "vix"],
            "sector_tags": ["techno"]},
    "EGY": {"name_ko": "이집트",       "name_en": "Egypt",
            "region_code": "suez",
            # 수에즈 운하 운영국 — 홍해 위기 시 통행료·통과 허용 여부가 핵심 변수
            "fred_indicators": ["wti", "brent", "vix"]},
    "PAK": {"name_ko": "파키스탄",     "name_en": "Pakistan",
            "region_code": None,
            # SCO 회원국·핵보유국·중인 완충지대. 미중 경쟁 속 '전략적 모호성' 실습 사례
            "fred_indicators": ["wti", "vix"],
            "sector_tags": ["gray_zone", "indo_pacific"]},
    "POL": {"name_ko": "폴란드",       "name_en": "Poland",
            "region_code": "ukraine",
            # NATO 동방 진영 핵심, 우크라이나 접경 — 동맹 확산(Alliance Diffusion) 연루 위험
            "fred_indicators": ["brent", "vix"]},
    "ETH": {"name_ko": "에티오피아",   "name_en": "Ethiopia",
            "region_code": "bab_el_mandeb",
            # DB 81,707건 아프리카 최대 분쟁국 — 회색지대·비전통 안보의 교과서적 사례
            "fred_indicators": ["wti", "vix"]},
}


# ── DB 연결 헬퍼 ──────────────────────────────────────────────────────────────

def _open_intel() -> sqlite3.Connection | None:
    if not _INTEL_DB.exists():
        return None
    con = sqlite3.connect(_INTEL_DB)
    con.row_factory = sqlite3.Row
    return con


def _open_library() -> sqlite3.Connection | None:
    if not _LIBRARY_DB.exists():
        return None
    con = sqlite3.connect(_LIBRARY_DB)
    con.row_factory = sqlite3.Row
    return con


# ── 데이터 조회 함수 ──────────────────────────────────────────────────────────

def _query_macro(iso3: str) -> list[dict]:
    """FRED 거시지표 최근 30일 조회.

    historical_macro_indices 테이블에서 해당 국가에 연관된 지표를 가져온다.
    DB가 없거나 적재 전이면 빈 목록 반환.
    """
    info = _COUNTRY_INFO.get(iso3, {})
    indicators = info.get("fred_indicators") or ["wti", "vix"]

    con = _open_intel()
    if not con:
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    result: list[dict] = []
    try:
        for ind in indicators:
            rows = con.execute(
                """
                SELECT date, value
                FROM historical_macro_indices
                WHERE indicator = ? AND date >= ?
                ORDER BY date ASC
                """,
                (ind, cutoff),
            ).fetchall()

            if not rows:
                continue

            series = [{"date": r["date"], "value": r["value"]} for r in rows]
            latest = series[-1]
            meta   = _FRED_LABELS.get(ind, {"label": ind, "unit": ""})
            result.append({
                "indicator":    ind,
                "label":        meta["label"],
                "unit":         meta["unit"],
                "latest_date":  latest["date"],
                "latest_value": round(latest["value"], 4),
                "series":       series,
            })
    finally:
        con.close()

    return result


def _query_trade(iso3: str) -> dict:
    """최신 연도 HS 8542/27/26 기준 상위 5개 파트너 무역 의존도 조회.

    Weaponized Interdependence (Farrell & Newman 2019) 계량화 데이터.
    dependency_ratio: 양자 무역액 / 보고국 전체 무역액 (0~1).
    """
    con = _open_intel()
    if not con:
        return {}

    result: dict = {}
    try:
        row = con.execute(
            "SELECT MAX(period) FROM historical_trade_matrix WHERE reporter_iso = ?",
            (iso3,),
        ).fetchone()
        latest_period = row[0] if row and row[0] else None
        if not latest_period:
            return {}

        for hs in ("8542", "27", "26"):
            rows = con.execute(
                """
                SELECT partner_iso, trade_flow, trade_value_usd, dependency_ratio
                FROM historical_trade_matrix
                WHERE reporter_iso = ? AND hs_code = ? AND period = ?
                  AND partner_iso NOT IN ('WLD', '0', 'WORLD', '')
                ORDER BY trade_value_usd DESC
                LIMIT 5
                """,
                (iso3, hs, latest_period),
            ).fetchall()

            if not rows:
                continue

            result[hs] = {
                "hs_name": _HS_NAMES.get(hs, hs),
                "period":  latest_period,
                "partners": [
                    {
                        "iso3":            r["partner_iso"],
                        "flow":            r["trade_flow"],
                        "value_usd":       r["trade_value_usd"],
                        "dependency_ratio": r["dependency_ratio"],
                    }
                    for r in rows
                ],
            }
    finally:
        con.close()

    return result


def _query_sanctions(iso2: str | None) -> list[dict]:
    """sanctions.yaml에서 target_country == iso2 인 제재 레짐 목록 반환."""
    if not iso2 or not _SANCTIONS_YAML.exists():
        return []
    try:
        with open(_SANCTIONS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("[country] sanctions.yaml 로드 실패: %s", e)
        return []

    return [
        {
            "id":                r.get("id"),
            "target_name":       r.get("target_name"),
            "sanctioning_bodies": r.get("sanctioning_bodies", []),
            "year_established":  r.get("year_established"),
            "sectors":           r.get("sectors", []),
            "description":       r.get("description"),
            "severity":          r.get("severity"),
            "theory_tags":       r.get("theory_tags", []),
        }
        for r in data.get("regimes", [])
        if r.get("target_country") == iso2
    ]


def _query_theories(
    region_code: str | None,
    sector_tags: list[str] | None = None,
) -> list[dict]:
    """library.db에서 region_code 또는 sector_tag 매칭 이론 조회.

    1차: region_code로 매칭 (regions JSON / geopol_region)
    2차 폴백: sector_tags 리스트로 매칭 (region_code=None인 국가용)
    """
    con = _open_library()
    if not con:
        return []

    def _format(rows) -> list[dict]:
        return [
            {
                "id":         r["theory_id"],
                "title":      r["title"],
                "sector_tag": r["sector_tag"],
                "summary":    r["summary"],
                "use_case":   r["use_case"],
            }
            for r in rows
        ]

    try:
        if region_code:
            rows = con.execute(
                """
                SELECT theory_id, title, sector_tag, summary, use_case, geopol_region
                FROM theories
                WHERE regions LIKE ? OR geopol_region LIKE ?
                ORDER BY
                    CASE use_case WHEN 'case_study' THEN 0 WHEN 'norm' THEN 1 ELSE 2 END,
                    title ASC
                LIMIT 12
                """,
                (f"%{region_code}%", f"%{region_code}%"),
            ).fetchall()
            return _format(rows)

        # region_code 없는 국가 — sector_tags 폴백
        if sector_tags:
            placeholders = ",".join("?" * len(sector_tags))
            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary, use_case, geopol_region
                FROM theories
                WHERE sector_tag IN ({placeholders})
                ORDER BY
                    CASE use_case WHEN 'case_study' THEN 0 WHEN 'norm' THEN 1 ELSE 2 END,
                    title ASC
                LIMIT 8
                """,
                sector_tags,
            ).fetchall()
            return _format(rows)

        return []
    finally:
        con.close()


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_countries():
    """COUNTRY_META에 등록된 국가 목록 반환 (한국어 이름 오름차순).

    LayerPanel 국가 검색 드롭다운의 데이터 소스.
    추후 국가 추가는 _COUNTRY_INFO 딕셔너리만 수정하면 자동 반영된다.
    """
    return sorted(
        [
            {"iso3": iso3, "name_ko": v["name_ko"], "name_en": v["name_en"]}
            for iso3, v in _COUNTRY_INFO.items()
        ],
        key=lambda x: x["name_ko"],
    )


@router.get("/{iso3}")
async def get_country(iso3: str):
    """국가 기본정보 + 거시지표 + 무역의존도 + 제재 + 관련 이론."""
    iso3 = iso3.upper()

    cached = _cache.get(iso3)
    if cached and datetime.now(timezone.utc) < cached[0]:
        return {**cached[1], "cached": True}

    info       = _COUNTRY_INFO.get(iso3, {})
    iso2       = _ISO3_TO_ISO2.get(iso3)
    region     = info.get("region_code")

    payload = {
        "iso3":        iso3,
        "iso2":        iso2,
        "name_ko":     info.get("name_ko", iso3),
        "name_en":     info.get("name_en", iso3),
        "region_code": region,
        "macro":       _query_macro(iso3),
        "trade":       _query_trade(iso3),
        "sanctions":   _query_sanctions(iso2),
        "theories":    _query_theories(region, info.get("sector_tags")),
        "cached":      False,
    }

    _cache[iso3] = (datetime.now(timezone.utc) + _CACHE_TTL, payload)
    return payload
