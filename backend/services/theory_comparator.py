"""
경쟁 이론 비교 엔진 — Cycle 7-B (v7.1.0)

쿼리의 섹터·지역을 기반으로 관련 이론 2~3개를 선택하고,
각 이론의 예측 방향(falsifiable_prediction)을 실측 데이터와 비교하여
Gemini [경쟁설명] 섹션에 사용할 수치 편차 요약 컨텍스트를 생성한다.

Token-Zero 원칙: 이론 선택·데이터 조회·비교 포맷 모두 결정론적으로 처리.
Gemini는 이 컨텍스트를 바탕으로 우세 이론을 판정한다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LIB_DB   = Path(__file__).resolve().parent.parent / "db" / "library.db"
_MAIN_DB  = Path(__file__).resolve().parent.parent / "db" / "geomap.db"
_INTEL_DB = Path(__file__).resolve().parent.parent / "db" / "intel.db"


@contextmanager
def _db(path: Path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# ── 섹터·지역 → 이론 우선순위 매핑 ────────────────────────────────────────
# 각 섹터/지역에서 비교할 메인 이론 쌍 (기본 + 경쟁)
# theory_id 기준 (DB의 theory_id 컬럼)

_SECTOR_THEORY_PAIRS: dict[str, list[str]] = {
    "energy":      ["energy_weaponized_interdependence", "energy_resource_weaponization"],
    "maritime":    ["maritime_mahan_sea_power", "indo_pacific_a2ad_strategy"],
    "techno":      ["techno_digital_iron_curtain", "energy_weaponized_interdependence"],
    "indo_pacific":["indo_pacific_mearsheimer_offensive_realism", "indo_pacific_waltz_defensive_realism"],
    "gray_zone":   ["gray_zone_gray_zone_strategy", "gray_zone_hybrid_warfare"],
    "cyber":       ["cyber_libicki_cyber_deterrence", "techno_digital_iron_curtain"],
}

_REGION_THEORY_PAIRS: dict[str, list[str]] = {
    "taiwan_strait":    ["indo_pacific_mearsheimer_offensive_realism", "maritime_mahan_sea_power"],
    "hormuz":           ["energy_resource_weaponization", "energy_weaponized_interdependence"],
    "eastern_europe":   ["indo_pacific_waltz_defensive_realism", "gray_zone_hybrid_warfare"],
    "korean_peninsula": ["indo_pacific_alliance_theory", "indo_pacific_mearsheimer_offensive_realism"],
    "bab_el_mandeb":    ["energy_resource_weaponization", "gray_zone_gray_zone_strategy"],
    "south_china_sea":  ["maritime_mahan_sea_power", "indo_pacific_a2ad_strategy"],
    "east_china_sea":   ["maritime_mahan_sea_power", "indo_pacific_mearsheimer_offensive_realism"],
    "sahel":            ["gray_zone_gray_zone_strategy", "gray_zone_hybrid_warfare"],
}

# ── 이론 IV와 실측 데이터 소스 매핑 ────────────────────────────────────────
# theory_id → (데이터 소스 이름, 조회 함수)

def _get_sipri_milex_for_theories(actors: list[str]) -> dict[str, float]:
    """SIPRI 국방비(%GDP) 최신년도 조회 — 이론 IV 실측값으로 사용."""
    if not actors:
        return {}
    result = {}
    try:
        with _db(_INTEL_DB) as con:
            for iso3 in actors[:4]:
                row = con.execute(
                    "SELECT country_iso3, gdp_pct, year FROM sipri_milex "
                    "WHERE country_iso3=? ORDER BY year DESC LIMIT 1",
                    (iso3,),
                ).fetchone()
                if row:
                    result[iso3] = {"gdp_pct": row["gdp_pct"], "year": row["year"]}
    except Exception as e:
        logger.debug("[theory_cmp] sipri_milex 조회 실패: %s", e)
    return result


def _get_sipri_arms_hhi(actors: list[str]) -> dict:
    """SIPRI 무기 이전 집중도 계산 — Weaponized Interdependence IV proxy."""
    if not actors:
        return {}
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                "SELECT recipient, supplier, tiv_2023 FROM sipri_arms_transfers "
                "WHERE recipient IN ({}) OR supplier IN ({}) "
                "ORDER BY tiv_2023 DESC LIMIT 10".format(
                    ",".join("?" * len(actors)),
                    ",".join("?" * len(actors)),
                ),
                (*actors, *actors),
            ).fetchall()
        if not rows:
            return {}
        total = sum(r["tiv_2023"] for r in rows if r["tiv_2023"])
        dominant = rows[0]
        hhi_proxy = (dominant["tiv_2023"] / total * 100) if total > 0 else 0
        return {
            "dominant_supplier": dominant["supplier"],
            "dominant_recipient": dominant["recipient"],
            "dominant_tiv": dominant["tiv_2023"],
            "total_tiv": total,
            "hhi_proxy_pct": round(hhi_proxy, 1),
            "source": "SIPRI Arms Transfers 2023",
        }
    except Exception as e:
        logger.debug("[theory_cmp] sipri_arms_hhi 조회 실패: %s", e)
        return {}


def _get_eia_chokepoint(regions: list[str]) -> dict:
    """EIA 초크포인트 통과량 — Resource Weaponization IV proxy."""
    _REGION_TO_CHOKEPOINT = {
        "hormuz": "Strait of Hormuz",
        "bab_el_mandeb": "Bab el-Mandeb",
        "malacca": "Strait of Malacca",
        "suez": "Suez Canal",
        "south_china_sea": "South China Sea",
    }
    target = next(
        (_REGION_TO_CHOKEPOINT[r] for r in regions if r in _REGION_TO_CHOKEPOINT),
        None,
    )
    if not target:
        return {}
    try:
        with _db(_INTEL_DB) as con:
            row = con.execute(
                "SELECT chokepoint, flow_mbpd, year FROM eia_energy "
                "WHERE chokepoint=? ORDER BY year DESC LIMIT 1",
                (target,),
            ).fetchone()
        if row:
            return {
                "chokepoint": row["chokepoint"],
                "flow_mbpd": row["flow_mbpd"],
                "year": row["year"],
                "source": "EIA International Energy Statistics",
            }
    except Exception as e:
        logger.debug("[theory_cmp] eia_chokepoint 조회 실패: %s", e)
    return {}


def _get_fred_for_theories(regions: list[str]) -> dict:
    """FRED 유가·환율 최신값 + 변화율 — Resource Weaponization 실측 강화.

    무기화 이론의 핵심 예측은 '긴장 → 가격 상승'이므로, 유가의 최근 추세를
    실측값으로 제공해 예측 방향(상승)과 대조 가능하게 한다.
    """
    # 에너지 무기화가 의미있는 지역만
    _REGION_FRED = {
        "hormuz":         ["DCOILWTICO", "DCOILBRENTEU"],
        "bab_el_mandeb":  ["DCOILBRENTEU"],
        "eastern_europe": ["PNGASEUUSDM", "DCOILBRENTEU"],
        "taiwan_strait":  ["EXCHUS"],
        "korean_peninsula": ["KOREUS"],
        "east_china_sea": ["EXJPUS"],
    }
    series_ids: list[str] = []
    for r in regions:
        series_ids.extend(_REGION_FRED.get(r, []))
    if not series_ids:
        return {}
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            for sid in dict.fromkeys(series_ids):  # 중복 제거, 순서 유지
                rows = con.execute(
                    "SELECT series_name, date, value, unit FROM fred_indicators "
                    "WHERE series_id=? ORDER BY date DESC LIMIT 12",
                    (sid,),
                ).fetchall()
                if not rows:
                    continue
                latest = rows[0]
                oldest = rows[-1]
                pct = None
                if oldest["value"] and latest["value"]:
                    try:
                        pct = round((latest["value"] - oldest["value"]) / oldest["value"] * 100, 1)
                    except ZeroDivisionError:
                        pct = None
                result[sid] = {
                    "name": latest["series_name"],
                    "latest_value": latest["value"],
                    "latest_date": latest["date"],
                    "unit": latest["unit"],
                    "pct_change": pct,  # 최근 12개 데이터 구간 변화율
                }
    except Exception as e:
        logger.debug("[theory_cmp] fred 조회 실패: %s", e)
    return result


def _get_wbk_governance(actors: list[str]) -> dict:
    """World Bank WGI 거버넌스 지수 — Gray Zone 이론 취약국 실측값.

    Gray Zone 전략은 '거버넌스 공백을 비국가 행위자가 침투'하는 메커니즘이므로,
    정치안정성(PV)·법치(RL) 지수가 핵심 IV 실측값이다.
    """
    if not actors:
        return {}
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            for iso3 in actors[:4]:
                row = con.execute(
                    "SELECT iso3, country_name, year, pv_score, rl_score, ge_score, cc_score "
                    "FROM world_bank_wgi WHERE iso3=? ORDER BY year DESC LIMIT 1",
                    (iso3,),
                ).fetchone()
                if row:
                    result[iso3] = {
                        "country": row["country_name"],
                        "year": row["year"],
                        "pv": row["pv_score"],   # 정치안정성·폭력부재
                        "rl": row["rl_score"],   # 법치
                        "ge": row["ge_score"],   # 정부효과성
                        "cc": row["cc_score"],   # 부패통제
                    }
    except Exception as e:
        logger.debug("[theory_cmp] wbk 조회 실패: %s", e)
    return result


def _get_polity5(actors: list[str]) -> dict:
    """Polity5 정치체제 지수 — Waltz/Mearsheimer 행위자 분류 강화.

    V-DEM이 조직형태·부패 중심이라면, Polity5는 권위주의←→민주주의 연속 척도(-10~+10).
    Waltz 방어적 현실주의: 민주국가(+7~+10)는 현상유지 경향 → 반례 탐색.
    Mearsheimer 공격적 현실주의: 체제 무관하게 생존 추구 → 권위국가 군비 비교.
    """
    if not actors:
        return {}
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            for iso3 in actors[:5]:
                row = con.execute(
                    "SELECT iso3, polity_score, regime_type, year "
                    "FROM polity5 WHERE iso3=? ORDER BY year DESC LIMIT 1",
                    (iso3,),
                ).fetchone()
                if row:
                    result[iso3] = {
                        "polity": row["polity_score"],
                        "regime": row["regime_type"],
                        "year": row["year"],
                    }
    except Exception as e:
        logger.debug("[theory_cmp] polity5 조회 실패: %s", e)
    return result


def _get_hiik_conflict(regions: list[str]) -> dict:
    """HIIK 분쟁 강도 바로미터 — Gray Zone/Hybrid 이론 실측 강화.

    ACLED는 이벤트 건수, HIIK는 분쟁 **강도(1=분쟁~5=전쟁)** — 둘은 다른 차원.
    Gray Zone 이론 예측: 강도 1~3(비전통) 지속 → 실측과 비교해 우세/열세 판정.
    Hybrid Warfare 예측: 강도 3~4(위기~제한전) — 단순 ACLED 건수보다 정밀.
    """
    _REGION_MAP = {
        "sahel":          ["Mali", "Niger", "Burkina Faso", "Sahel"],
        "eastern_europe": ["Ukraine", "Russia"],
        "hormuz":         ["Iran"],
        "bab_el_mandeb":  ["Yemen"],
        "korean_peninsula": ["North Korea", "South Korea"],
        "east_china_sea": ["China", "Japan"],
        "middle_east":    ["Israel", "Lebanon", "Syria"],
    }
    regions_lower = [r.lower() for r in regions]
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            for region in regions:
                targets = _REGION_MAP.get(region, [])
                for target in targets:
                    rows = con.execute(
                        "SELECT conflict_name, intensity, year "
                        "FROM hiik_conflict WHERE region LIKE ? ORDER BY year DESC LIMIT 1",
                        (f"%{target}%",),
                    ).fetchall()
                    for row in rows:
                        key = f"{target}_{row['year']}"
                        result[key] = {
                            "conflict": row["conflict_name"],
                            "intensity": row["intensity"],
                            "year": row["year"],
                            "region": region,
                        }
    except Exception as e:
        logger.debug("[theory_cmp] hiik 조회 실패: %s", e)
    return result


def _get_itu_ict_for_theories(actors: list[str]) -> dict:
    """ITU ICT 발전 지수 — Libicki 사이버 억지 이론 실측 강화.

    Libicki 예측: ICT 역량 높은 국가(높은 IDI)는 귀속 능력이 높아 억지 성공률 ↑.
    실측: 해당 행위자의 IDI 점수로 예측 방향(↑)과 대조.
    주의: IDI는 사이버 '방어력' 직접 측정값이 아닌 인프라 보급 proxy.
    """
    if not actors:
        return {}
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            for iso3 in actors[:5]:
                row = con.execute(
                    "SELECT iso3, country_name, idi_score, global_rank, year "
                    "FROM itu_ict WHERE iso3=? ORDER BY year DESC LIMIT 1",
                    (iso3,),
                ).fetchone()
                if row:
                    result[iso3] = {
                        "country": row["country_name"],
                        "idi": row["idi_score"],
                        "rank": row["global_rank"],
                        "year": row["year"],
                    }
    except Exception as e:
        logger.debug("[theory_cmp] itu_ict 조회 실패: %s", e)
    return result


def _get_owid_military(actors: list[str], regions: list[str]) -> dict:
    """OWID 군비·핵탄두 시계열 — Mahan/A2AD 군사력 비교 강화.

    SIPRI milex는 GDP% 단일값, OWID는 실제 지출액·핵탄두 수량 시계열.
    Mahan 예측: 해군력(군비 지출) 증가 → SLOC 통제력 증가.
    A2AD 예측: 군비 집중도(반접근 거부 투자) → 지역 억지력 변화.
    """
    _REGION_ACTORS: dict[str, list[str]] = {
        "taiwan_strait":    ["CHN", "USA", "TWN"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
        "south_china_sea":  ["CHN", "USA"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "eastern_europe":   ["RUS", "UKR", "USA"],
        "hormuz":           ["IRN", "USA"],
        "bab_el_mandeb":    ["USA", "SAU"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS.get(r, []))
    if not iso3_set:
        return {}
    result: dict = {}
    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            # 군비 지출(USD bn)
            rows = con.execute(
                f"SELECT iso3, country, year, value, unit, dataset "
                f"FROM owid_data WHERE iso3 IN ({placeholders}) "
                f"AND dataset IN ('military_exp_gdp','nuclear_warheads') "
                f"ORDER BY iso3, dataset, year DESC",
                tuple(iso3_set),
            ).fetchall()
        for row in rows:
            iso3 = row["iso3"]
            ds = row["dataset"]
            if iso3 not in result:
                result[iso3] = {"country": row["country"]}
            if ds == "military_exp_gdp" and "milex_gdp" not in result[iso3]:
                result[iso3]["milex_gdp"] = row["value"]
                result[iso3]["milex_year"] = row["year"]
            elif ds == "nuclear_warheads" and "nukes" not in result[iso3]:
                result[iso3]["nukes"] = row["value"]
                result[iso3]["nukes_year"] = row["year"]
    except Exception as e:
        logger.debug("[theory_cmp] owid_military 조회 실패: %s", e)
    return result


def _get_acled_event_count(regions: list[str]) -> dict:
    """ACLED 분쟁 이벤트 수 — Gray Zone/A2AD IV proxy."""
    _REGION_COUNTRIES = {
        "taiwan_strait": ["Taiwan", "China"],
        "eastern_europe": ["Ukraine", "Russia"],
        "hormuz": ["Iran", "Yemen"],
        "korean_peninsula": ["North Korea", "South Korea"],
        "east_china_sea": ["Japan", "China"],
        "bab_el_mandeb": ["Yemen", "Ethiopia"],
        "sahel": ["Mali", "Niger", "Burkina Faso"],
    }
    target_countries = []
    for r in regions:
        target_countries.extend(_REGION_COUNTRIES.get(r, []))
    if not target_countries:
        return {}
    try:
        with _db(_INTEL_DB) as con:
            placeholders = ",".join("?" * len(target_countries))
            row = con.execute(
                f"SELECT COUNT(*) as cnt FROM event_archive "
                f"WHERE country IN ({placeholders}) "
                f"AND timestamp > datetime('now', '-24 months')",
                target_countries,
            ).fetchone()
        if row:
            return {
                "event_count_24m": row["cnt"],
                "countries": target_countries[:3],
                "source": "ACLED event_archive (24개월)",
            }
    except Exception as e:
        logger.debug("[theory_cmp] acled_count 조회 실패: %s", e)
    return {}


def _get_vdem_scores(actors: list[str]) -> dict:
    """V-DEM 민주주의 지수 — Waltz 국가 유형 분류 proxy."""
    if not actors:
        return {}
    result = {}
    try:
        with _db(_INTEL_DB) as con:
            for iso3 in actors[:4]:
                row = con.execute(
                    "SELECT country_iso3, v2x_libdem, regime_type, year FROM vdem_index "
                    "WHERE country_iso3=? ORDER BY year DESC LIMIT 1",
                    (iso3,),
                ).fetchone()
                if row:
                    result[iso3] = {
                        "libdem": row["v2x_libdem"],
                        "regime": row["regime_type"],
                        "year": row["year"],
                    }
    except Exception as e:
        logger.debug("[theory_cmp] vdem 조회 실패: %s", e)
    return result


def _get_semi_market_for_theories(sectors: list[str], regions: list[str]) -> dict:
    """반도체·기술 시장 핵심 수치 — techno/weaponized_interdependence 이론 실측값."""
    is_techno = "techno" in sectors or "cyber" in sectors or "taiwan_strait" in regions
    if not is_techno:
        return {}
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            # 파운드리 HHI 및 TSMC 점유율
            rows = con.execute(
                "SELECT metric, value, unit, year FROM semi_market_data "
                "WHERE category='foundry_share' ORDER BY year DESC"
            ).fetchall()
            for r in rows:
                if "HHI" in r["metric"]:
                    result["foundry_hhi"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}
                if "TSMC global" in r["metric"]:
                    result["tsmc_share"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}
                if "SMIC market share" in r["metric"]:
                    result["smic_share"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}

            # 중국 자급률 핵심 지표
            rows2 = con.execute(
                "SELECT metric, value, unit, year FROM semi_market_data "
                "WHERE category='china_self_sufficiency' ORDER BY year DESC"
            ).fetchall()
            for r in rows2:
                if "import dependency" in r["metric"]:
                    result["china_import_dep"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}
                if "node gap" in r["metric"]:
                    result["tsmc_smic_gap"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}
                if "yield rate" in r["metric"]:
                    result["smic_yield"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}

            # 선단 노드 집중도
            rows3 = con.execute(
                "SELECT metric, value, unit, year FROM semi_market_data "
                "WHERE category='advanced_nodes' ORDER BY year DESC"
            ).fetchall()
            for r in rows3:
                if "3nm" in r["metric"]:
                    result["node3nm_tsmc"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}

            # 핵심 광물 집중도 (gallium 대표값)
            rows4 = con.execute(
                "SELECT metric, value, unit, year FROM semi_market_data "
                "WHERE category='critical_mineral' AND metric LIKE '%gallium%' LIMIT 1"
            ).fetchall()
            if rows4:
                r = rows4[0]
                result["china_gallium"] = {"value": r["value"], "unit": r["unit"], "year": r["year"]}

    except Exception as e:
        logger.debug("[theory_cmp] semi_market 조회 실패: %s", e)
    return result


# ── 이론 프로파일 DB 조회 ────────────────────────────────────────────────────

def _fetch_theory_profiles(theory_ids: list[str]) -> list[dict]:
    """theory_id 목록으로 이론 프로파일 조회."""
    if not theory_ids:
        return []
    try:
        with _db(_LIB_DB) as con:
            placeholders = ",".join("?" * len(theory_ids))
            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag,
                       independent_var, dependent_var, conditions,
                       falsifiable_prediction, known_counterexample, rival_theories
                FROM theories
                WHERE theory_id IN ({placeholders})
                  AND independent_var IS NOT NULL
                """,
                theory_ids,
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.debug("[theory_cmp] 이론 프로파일 조회 실패: %s", e)
        return []


# ── 비교 컨텍스트 생성 ───────────────────────────────────────────────────────

def build_theory_comparison_context(
    sectors: list[str],
    regions: list[str],
    actors: list[str],
) -> str:
    """
    섹터·지역·행위자를 기반으로 관련 이론 2~3개를 선택하고
    실측 데이터와 대조한 비교 컨텍스트를 반환한다.

    반환된 텍스트는 intel_analyzer._build_context()에 삽입되어
    Gemini가 [경쟁설명] 섹션에서 수치 편차 비교를 수행하도록 안내한다.
    """
    # 1. 관련 이론 ID 수집 (섹터 우선, 지역 보완, 중복 제거)
    candidate_ids: list[str] = []
    seen: set[str] = set()
    for s in sectors:
        for tid in _SECTOR_THEORY_PAIRS.get(s, []):
            if tid not in seen:
                seen.add(tid)
                candidate_ids.append(tid)
    for r in regions:
        for tid in _REGION_THEORY_PAIRS.get(r, []):
            if tid not in seen:
                seen.add(tid)
                candidate_ids.append(tid)

    # 최대 3개로 제한
    target_ids = candidate_ids[:3]
    if not target_ids:
        return ""

    profiles = _fetch_theory_profiles(target_ids)
    if not profiles:
        return ""

    # 2. 이론별 실측값 조회
    milex   = _get_sipri_milex_for_theories(actors)
    arms    = _get_sipri_arms_hhi(actors)
    eia     = _get_eia_chokepoint(regions)
    acled   = _get_acled_event_count(regions)
    vdem    = _get_vdem_scores(actors)
    semi    = _get_semi_market_for_theories(sectors, regions)
    fred    = _get_fred_for_theories(regions)
    wbk     = _get_wbk_governance(actors)
    polity5 = _get_polity5(actors)
    hiik    = _get_hiik_conflict(regions)
    itu     = _get_itu_ict_for_theories(actors)
    owid    = _get_owid_military(actors, regions)

    # 3. 비교 텍스트 생성
    lines: list[str] = ["## 경쟁 이론 비교 프로파일 (예측값 vs 실측값)"]
    lines.append(
        "⚠️ [경쟁설명] 작성 지침: 아래 각 이론의 '반증 가능 예측'과 "
        "'실측 데이터'를 비교하여 어느 이론이 현재 상황을 더 잘 설명하는지 "
        "수치 편차와 함께 판정하라. 수사적 기각 금지 — 예측값 vs 실측값 형태로 작성.\n"
    )

    for p in profiles:
        lines.append(f"### 이론: {p.get('title', p['theory_id'])}")
        if p.get("independent_var"):
            lines.append(f"**독립변수(IV)**: {p['independent_var']}")
        if p.get("dependent_var"):
            lines.append(f"**종속변수(DV)**: {p['dependent_var']}")
        if p.get("falsifiable_prediction"):
            lines.append(f"**반증 가능 예측**: {p['falsifiable_prediction']}")

        # 이론별 실측값 연결
        empirical_lines: list[str] = []
        tid = p["theory_id"]

        if "mahan" in tid or "a2ad" in tid:
            if milex:
                milex_str = " | ".join(
                    f"{iso3}: {v.get('gdp_pct', '?')}% GDP ({v.get('year', '?')})"
                    for iso3, v in milex.items()
                )
                empirical_lines.append(f"실측 — SIPRI 국방비: {milex_str}")
            if acled:
                empirical_lines.append(
                    f"실측 — ACLED 분쟁 이벤트 24개월: {acled.get('event_count_24m', '?')}건 "
                    f"({', '.join(acled.get('countries', [])[:2])})"
                )
            # OWID 군비·핵탄두 — Mahan 해군력 투자 예측과 실측 수량 직접 비교
            if owid:
                parts = []
                for iso3, d in list(owid.items())[:4]:
                    entry = f"{d.get('country', iso3)}"
                    if d.get("milex_gdp") is not None:
                        entry += f" 군비 {d['milex_gdp']:.1f}% GDP ({d.get('milex_year','')})"
                    if d.get("nukes") is not None:
                        entry += f" 핵탄두 {int(d['nukes'])}기 ({d.get('nukes_year','')})"
                    parts.append(entry)
                if parts:
                    empirical_lines.append(f"실측 — OWID 군사력: {' | '.join(parts)}")

        if "weaponized_interdependence" in tid or "resource_weaponization" in tid:
            if eia:
                empirical_lines.append(
                    f"실측 — {eia.get('chokepoint', '?')}: "
                    f"{eia.get('flow_mbpd', '?')} Mbpd ({eia.get('year', '?')}, {eia.get('source', '')})"
                )
            if arms:
                empirical_lines.append(
                    f"실측 — 무기 공급 집중도: "
                    f"{arms.get('dominant_supplier', '?')}→{arms.get('dominant_recipient', '?')} "
                    f"TIV {arms.get('dominant_tiv', '?')} / 전체 {arms.get('total_tiv', '?')} "
                    f"(집중도 proxy {arms.get('hhi_proxy_pct', '?')}%)"
                )
            # FRED 유가·가스 가격 추세 — 무기화 예측('긴장→상승')과 직접 대조용
            if fred:
                for sid, d in fred.items():
                    pct = d.get("pct_change")
                    pct_str = f"{pct:+.1f}%" if pct is not None else "?"
                    empirical_lines.append(
                        f"실측 — {d['name']}: {d['latest_value']} {d.get('unit', '')} "
                        f"({d['latest_date']}, 최근 추세 {pct_str}) [FRED]"
                    )
            # techno 섹터: 반도체 공급망 집중도를 weaponized_interdependence의 핵심 IV로 추가
            if semi:
                if semi.get("foundry_hhi"):
                    empirical_lines.append(
                        f"실측 — 파운드리 HHI: {semi['foundry_hhi']['value']} "
                        f"({semi['foundry_hhi']['year']}, 기준 >2500=독과점) "
                        f"| TSMC: {semi.get('tsmc_share', {}).get('value', '?')}% "
                        f"| SMIC: {semi.get('smic_share', {}).get('value', '?')}%"
                    )
                if semi.get("china_import_dep"):
                    empirical_lines.append(
                        f"실측 — 중국 첨단 반도체 수입 의존도: {semi['china_import_dep']['value']}% "
                        f"({semi['china_import_dep']['year']}) — 비대칭 의존 수치"
                    )

        if "mearsheimer" in tid or "waltz" in tid:
            if milex:
                milex_str = " | ".join(
                    f"{iso3}: {v.get('gdp_pct', '?')}% GDP"
                    for iso3, v in milex.items()
                )
                empirical_lines.append(f"실측 — SIPRI 권력 proxy(국방비): {milex_str}")
            if vdem:
                vdem_str = " | ".join(
                    f"{iso3}: libdem={v.get('libdem', '?')} ({v.get('regime', '?')})"
                    for iso3, v in vdem.items()
                )
                empirical_lines.append(f"실측 — V-DEM 체제유형: {vdem_str}")
            # Polity5 — Waltz '민주평화론' 반증 또는 Mearsheimer '체제무관 생존경쟁' 검증
            if polity5:
                p5_str = " | ".join(
                    f"{iso3}: Polity {v.get('polity', '?')} ({v.get('regime', '?')}, {v.get('year', '?')})"
                    for iso3, v in polity5.items()
                )
                empirical_lines.append(
                    f"실측 — Polity5 체제점수(-10전제~+10민주): {p5_str} "
                    f"[Waltz 예측: +7이상=현상유지 / Mearsheimer 예측: 점수무관 군비경쟁]"
                )
            # OWID 군사력 — 권력 격차 수치화
            if owid:
                parts = []
                for iso3, d in list(owid.items())[:4]:
                    entry = f"{d.get('country', iso3)}"
                    if d.get("milex_gdp") is not None:
                        entry += f" {d['milex_gdp']:.1f}%GDP"
                    if d.get("nukes") is not None:
                        entry += f" 핵{int(d['nukes'])}기"
                    parts.append(entry)
                if parts:
                    empirical_lines.append(f"실측 — OWID 군사력 격차: {' | '.join(parts)}")

        if "alliance_theory" in tid:
            empirical_lines.append(
                "실측 — COW Alliance DB 및 alliance_graph.yaml의 pact_intensity 값 참조 (context §COW 동맹 섹션)"
            )

        if "gray_zone" in tid or "hybrid_warfare" in tid:
            if acled:
                empirical_lines.append(
                    f"실측 — ACLED 분쟁 이벤트 24개월: {acled.get('event_count_24m', '?')}건"
                )
            # WB WGI 거버넌스 — Gray Zone '거버넌스 공백 침투' 메커니즘의 핵심 IV
            if wbk:
                wbk_str = " | ".join(
                    f"{v['country']}: 정치안정 {v['pv']:+.2f}/법치 {v['rl']:+.2f} ({v['year']})"
                    for v in wbk.values() if v.get("pv") is not None
                )
                if wbk_str:
                    empirical_lines.append(
                        f"실측 — WB 거버넌스(WGI, -2.5~+2.5 척도): {wbk_str}"
                    )
            # HIIK 분쟁 강도 — Gray Zone 예측('강도 1~3 저강도 지속') vs 실측 비교
            if hiik:
                hiik_parts = []
                for key, d in list(hiik.items())[:3]:
                    intensity = d.get("intensity", "?")
                    label = {1:"분쟁",2:"비폭력위기",3:"폭력위기",4:"제한전쟁",5:"전쟁"}.get(intensity, str(intensity))
                    hiik_parts.append(
                        f"{d.get('conflict','?')} 강도{intensity}({label}, {d.get('year','')})"
                    )
                if hiik_parts:
                    empirical_lines.append(
                        f"실측 — HIIK 분쟁강도(1~5): {' | '.join(hiik_parts)} "
                        f"[Gray Zone 예측: 강도1~3 저강도 지속 / Hybrid 예측: 강도3~4 위기·제한전]"
                    )

        if "libicki" in tid or "digital_iron_curtain" in tid:
            empirical_lines.append(
                "실측 — CSIS Significant Cyber Incidents DB 참조 (context §CSIS 사이버 섹션)"
            )
            # ITU IDI — Libicki '귀속 능력 높을수록 억지 성공' 예측의 proxy
            if itu:
                itu_parts = []
                for iso3, d in list(itu.items())[:4]:
                    itu_parts.append(
                        f"{d.get('country', iso3)}: IDI {d.get('idi','?')} ({d.get('rank','?')}위, {d.get('year','')})"
                    )
                if itu_parts:
                    empirical_lines.append(
                        f"실측 — ITU ICT 발전지수(ICT 인프라 proxy, 사이버방어력 직접값 아님): "
                        f"{' | '.join(itu_parts)} "
                        f"[Libicki 예측: IDI↑ → 귀속능력↑ → 억지효과↑]"
                    )
            # digital_iron_curtain: 기술 분리 속도를 semi_market으로 수치화
            if semi:
                parts = []
                if semi.get("node3nm_tsmc"):
                    parts.append(f"3nm 이하 TSMC 독점 {semi['node3nm_tsmc']['value']}%")
                if semi.get("tsmc_smic_gap"):
                    parts.append(f"TSMC-SMIC 격차 {semi['tsmc_smic_gap']['value']}세대")
                if semi.get("china_gallium"):
                    parts.append(f"중국 갈륨 독점 {semi['china_gallium']['value']}%")
                if parts:
                    empirical_lines.append(f"실측 — 기술 분리 지표: {' | '.join(parts)}")

        if "techno_nationalism" in tid:
            if semi:
                if semi.get("china_import_dep"):
                    empirical_lines.append(
                        f"실측 — 중국 자립화 현황: 첨단 반도체 수입의존 {semi['china_import_dep']['value']}% "
                        f"| SMIC 7nm yield {semi.get('smic_yield', {}).get('value', '?')}% (TSMC 95%+ 대비)"
                    )

        if empirical_lines:
            lines.append("**실측 데이터**:")
            for el in empirical_lines:
                lines.append(f"  - {el}")

        if p.get("known_counterexample"):
            lines.append(f"**알려진 반례**: {p['known_counterexample']}")

        if p.get("rival_theories"):
            try:
                rivals = json.loads(p["rival_theories"])
                lines.append(f"**경쟁 이론**: {', '.join(rivals[:2])}")
            except Exception:
                pass
        lines.append("")

    # 4. 비교 지시문 추가
    if len(profiles) >= 2:
        t1 = profiles[0].get("title", profiles[0]["theory_id"])
        t2 = profiles[1].get("title", profiles[1]["theory_id"])
        lines.append(
            f"### 비교 판정 요청\n"
            f"위 실측 데이터를 근거로 '{t1}'과 '{t2}' 중 "
            f"어느 이론이 현재 상황을 더 잘 설명하는지 [경쟁설명] 섹션에서 "
            f"수치 편차와 함께 판정하라.\n"
            f"각 이론은 '예측:/실측:/판정:' 3줄, 마지막에 '▶ 종합 판정:'으로 "
            f"두 이론의 편차를 직접 비교해 우세 이론을 수치로 결론지어라."
        )

    return "\n".join(lines)
