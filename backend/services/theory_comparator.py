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

from services import arithmetic_layer as A

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

# [8-C-2] 선택 풀 확장 — 라이브러리 51개 중 비교 등판 이론을 11→확대.
#   핵심 원칙: 한 쌍 안에 '서로 다른 앵커 metric'을 가진 이론을 배치 →
#   같은 숫자 인용 회피, 실측값이 우열을 판정하게 만든다(차별화 쌍).
#   예) 현실주의(milex_gap) vs 자유주의 상호의존(trade_hhi) vs 민주평화(polity).
_SECTOR_THEORY_PAIRS: dict[str, list[str]] = {
    "energy":      ["energy_weaponized_interdependence", "energy_resource_weaponization", "energy_energy_security_theory"],
    "maritime":    ["maritime_mahan_sea_power", "indo_pacific_a2ad_strategy", "maritime_chokepoint_sloc"],
    "techno":      ["techno_digital_iron_curtain", "energy_weaponized_interdependence", "techno_critical_minerals_security"],
    "indo_pacific":["indo_pacific_mearsheimer_offensive_realism", "indo_pacific_liberal_institutionalism", "indo_pacific_democratic_peace_theory"],
    "gray_zone":   ["gray_zone_gray_zone_strategy", "gray_zone_hybrid_warfare", "gray_zone_escalation_theory"],
    "cyber":       ["cyber_libicki_cyber_deterrence", "techno_digital_iron_curtain"],
}

_REGION_THEORY_PAIRS: dict[str, list[str]] = {
    "taiwan_strait":    ["indo_pacific_mearsheimer_offensive_realism", "indo_pacific_liberal_institutionalism", "indo_pacific_democratic_peace_theory"],
    "hormuz":           ["energy_resource_weaponization", "energy_weaponized_interdependence"],
    "eastern_europe":   ["indo_pacific_waltz_defensive_realism", "gray_zone_hybrid_warfare", "indo_burden_sharing_theory"],
    "korean_peninsula": ["indo_pacific_alliance_theory", "indo_pacific_mearsheimer_offensive_realism", "indo_burden_sharing_theory"],
    "bab_el_mandeb":    ["energy_resource_weaponization", "gray_zone_gray_zone_strategy"],
    "south_china_sea":  ["maritime_mahan_sea_power", "indo_pacific_a2ad_strategy", "maritime_chokepoint_sloc"],
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
                    "SELECT iso3, gdp_pct, year FROM sipri_milex "
                    "WHERE iso3=? ORDER BY year DESC LIMIT 1",
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
        hhi_proxy = A.share_of(dominant["tiv_2023"], total) or 0
        return {
            "dominant_supplier": dominant["supplier"],
            "dominant_recipient": dominant["recipient"],
            "dominant_tiv": dominant["tiv_2023"],
            "total_tiv": total,
            "hhi_proxy_pct": hhi_proxy,
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
                pct = A.pct_change(oldest["value"], latest["value"])
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
    # DB schema: region 컬럼 = region_code ("hormuz", "middle_east" 등)
    # 이전 버그: WHERE region LIKE '%Iran%' → region='hormuz'라 항상 빈 결과
    # 수정: region=? 로 직접 매핑 (country명이 아닌 region_code 기준)
    result: dict = {}
    try:
        with _db(_INTEL_DB) as con:
            for region in regions:
                rows = con.execute(
                    "SELECT conflict_name, intensity, year "
                    "FROM hiik_conflict WHERE region=? ORDER BY intensity DESC, year DESC LIMIT 3",
                    (region,),
                ).fetchall()
                for row in rows:
                    key = f"{region}_{row[2]}_{row[0][:12]}"
                    result[key] = {
                        "conflict": row[0],
                        "intensity": row[1],
                        "year": row[2],
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


# ── UN Comtrade 무역 의존도 HHI (AR-1b) ─────────────────────────────────────
# Weaponized Interdependence IV 직접 수치화: 공급망 집중도 → HHI proxy.
# dependency_ratio 0.1+ 쌍을 수집해 주요 공급자 집중도를 계산.

_HS_LABEL_TC = {"8542": "반도체", "27": "에너지", "26": "희토류·광물"}

# 지역 → 무역쌍 핵심 행위자
_REGION_TRADE_ACTORS_TC: dict[str, list[str]] = {
    "taiwan_strait":    ["TWN", "CHN", "USA", "JPN", "KOR"],
    "korean_peninsula": ["KOR", "PRK", "CHN", "USA", "JPN"],
    "hormuz":           ["IRN", "SAU", "ARE", "CHN", "USA"],
    "eastern_europe":   ["RUS", "DEU", "NLD", "UKR"],
    "south_china_sea":  ["CHN", "USA", "VNM", "PHL"],
    "east_china_sea":   ["CHN", "JPN", "USA", "KOR"],
    "bab_el_mandeb":    ["SAU", "ARE", "CHN", "IND"],
    "indo_pacific":     ["CHN", "USA", "JPN", "KOR", "IND"],
}


def _get_trade_hhi(actors: list[str], regions: list[str]) -> dict:
    """
    UN Comtrade → 공급망 HHI proxy 계산 (Weaponized Interdependence IV).

    반환 구조:
        {hs_code: {"hhi_proxy": float, "top_pair": str, "top_ratio": float,
                   "label": str, "period": str}}
    """
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_TRADE_ACTORS_TC.get(r, []))
    if not iso3_set:
        return {}

    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT hs_code, reporter_iso, partner_iso, trade_flow,
                       dependency_ratio, period
                FROM historical_trade_matrix
                WHERE reporter_iso IN ({placeholders})
                  AND partner_iso  IN ({placeholders})
                  AND partner_iso  != 'WLD'
                  AND dependency_ratio >= 0.1
                ORDER BY hs_code, dependency_ratio DESC
                """,
                (*list(iso3_set), *list(iso3_set)),
            ).fetchall()

        # HS 코드별 최고 의존도 쌍 + HHI proxy (상위 3쌍 제곱합)
        from collections import defaultdict
        by_hs: dict[str, list] = defaultdict(list)
        for r in rows:
            by_hs[r["hs_code"]].append(r)

        result: dict[str, dict] = {}
        for hs, items in by_hs.items():
            top = items[0]
            # HHI proxy = 상위 3쌍의 dependency_ratio² 합산 (arithmetic_layer 통일)
            hhi_val = A.hhi([i["dependency_ratio"] for i in items[:3]], scale_0_1=True) or 0
            result[hs] = {
                "hhi_proxy": hhi_val,
                "top_pair": f"{top['reporter_iso']} {('수입' if top['trade_flow']=='M' else '수출')}←{top['partner_iso']}",
                "top_ratio": round(top["dependency_ratio"] * 100, 1),
                "label": _HS_LABEL_TC.get(hs, hs),
                "period": top["period"],
            }
        return result
    except Exception as e:
        logger.debug("[theory_cmp] trade_hhi 조회 실패: %s", e)
        return {}


# ── DV 방향 추출 헬퍼 ────────────────────────────────────────────────────────

def _extract_dv_direction(fp: str, dv: str) -> str:
    """
    falsifiable_prediction 텍스트에서 DV 예측 방향을 한 줄로 추출한다.

    판정 시 "DV 예측 방향 vs DV 실측 방향" 비교를 Gemini에게 명시적으로 안내하기 위함.
    단순 키워드 매칭으로 방향만 추출 — 복잡한 파싱 불필요.
    """
    if not fp and not dv:
        return ""
    text = (fp + " " + dv).lower()
    # 증가/상승 방향
    up_keys = ["증가", "상승", "높아", "올라", "증대", "확대", "강화", "커진"]
    down_keys = ["감소", "하락", "낮아", "떨어", "축소", "약화", "줄어"]
    stable_keys = ["억제", "안정", "유지", "방지", "억", "낮은"]
    up_count   = sum(1 for k in up_keys   if k in text)
    down_count = sum(1 for k in down_keys if k in text)
    stbl_count = sum(1 for k in stable_keys if k in text)
    # DV 키워드 (종속변수 표현) — 무엇이 변하는지
    dv_short = (dv or "").split("(")[0].strip()[:30] if dv else "DV"
    if up_count > down_count and up_count > stbl_count:
        return f"[{dv_short}] ▲ 증가/상승 예측"
    if down_count > up_count and down_count >= stbl_count:
        return f"[{dv_short}] ▼ 감소/하락 예측"
    if stbl_count > 0:
        return f"[{dv_short}] ↔ 억제/안정 예측"
    return f"[{dv_short}] 방향: 반증 가능 예측 텍스트 참조"


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


# ── [8-C] 경쟁이론 정량 앵커 ──────────────────────────────────────────────────
# 각 이론이 '적용 가능'하려면 실측 IV가 넘어야 할 임계값(학술 표준 기준).
# direction "+": 실측>임계일수록 전제 성립 / "-": 실측<임계일수록 성립.
# ⚠️ 임계는 표준 기준만 사용(자의적 임계 금지 — 정직성). DV 직접측정이 아닌
#    IV 전제조건 충족도이므로 '전제 충족/미충족'으로만 판정(이론 입증 아님).

_THEORY_ANCHORS: dict[str, dict] = {
    "energy_weaponized_interdependence": {
        "metric": "trade_hhi", "threshold": 2500, "direction": "+", "unit": "",
        "anchor_label": "공급망 HHI 독과점 임계(美 DOJ 2500)",
        "interpret": "초과 → 비대칭 의존 구조 성립, Farrell&Newman 레버리지 예측 적용 가능",
    },
    "energy_resource_weaponization": {
        "metric": "eia_flow_mbpd", "threshold": 15.0, "direction": "+", "unit": "Mbpd",
        "anchor_label": "초크포인트 통과량 임계(글로벌 원유 약 15%≈15Mbpd)",
        "interpret": "초과 → 차단 시 글로벌 충격 큼, 자원무기화 지렛대 성립",
    },
    "maritime_mahan_sea_power": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "해군력(국방비%GDP) 우위 격차",
        "interpret": "양(+) → SLOC 통제 우위, Mahan 예측 부합",
    },
    "indo_pacific_a2ad_strategy": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "군사력(국방비%GDP) 격차",
        "interpret": "격차 클수록 반접근 거부 투자 여력 — A2AD 부합",
    },
    "indo_pacific_mearsheimer_offensive_realism": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "권력(국방비%GDP) 격차",
        "interpret": "격차 클수록 패권 추구 압력 — Mearsheimer 부합",
    },
    "indo_pacific_waltz_defensive_realism": {
        "metric": "polity_min", "threshold": 6, "direction": "+", "unit": "점",
        "anchor_label": "민주 임계(Polity +6, 민주평화론 경계)",
        "interpret": "행위자 모두 +6↑ → 현상유지 경향(Waltz), 미만이면 반례",
    },
    "gray_zone_gray_zone_strategy": {
        "metric": "wgi_pv_min", "threshold": 0.0, "direction": "-", "unit": "",
        "anchor_label": "정치안정 WGI 중립선(0)",
        "interpret": "음(-) → 거버넌스 공백, 회색지대 침투 전제 성립",
    },
    "gray_zone_hybrid_warfare": {
        "metric": "hiik_max", "threshold": 3, "direction": "+", "unit": "강도",
        "anchor_label": "HIIK 폭력위기 임계(3)",
        "interpret": "3↑ → 하이브리드전 활성, Hoffman 예측 부합",
    },
    "cyber_libicki_cyber_deterrence": {
        "metric": "itu_idi_min", "threshold": 70, "direction": "+", "unit": "IDI",
        "anchor_label": "ITU IDI 고역량 임계(70, 간접 proxy)",
        "interpret": "70↑ → 귀속·대응 역량 추정, Libicki 억지 성립 (※ IDI는 간접 proxy, 방어력 직접값 아님)",
    },
    "techno_digital_iron_curtain": {
        "metric": "semi_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "TSMC↔SMIC 점유율 격차",
        "interpret": "격차 클수록 기술 분리·종속 심화 — 디지털 철의장막 부합",
    },

    # ── [8-C-2] 확장 앵커 — 기존 실측 metric에 정직 매핑 (DV 직접측정 아님, IV 전제조건) ──
    # 차별화 핵심: 같은 사안에 서로 다른 metric을 쓰는 이론을 한 쌍으로 → 실측값이 우열 판정.
    "indo_pacific_democratic_peace_theory": {
        "metric": "polity_min", "threshold": 6, "direction": "+", "unit": "점",
        "anchor_label": "민주 임계(Polity +6, 민주평화론 경계)",
        "interpret": "양국 모두 +6↑ → 민주평화 억제 예측 성립 / 미만이면 이 이론 적용 불가(현실주의 영역)",
    },
    "indo_pacific_liberal_institutionalism": {
        "metric": "trade_hhi", "threshold": 2500, "direction": "+", "unit": "",
        "anchor_label": "무역 상호의존 집중도(HHI, 의존 강도 proxy)",
        "interpret": "의존 높을수록 자유주의는 분쟁 억제 예측 — 단 비대칭이면 무기화로 역전(Farrell&Newman과 정면 경쟁점)",
    },
    "indo_burden_sharing_theory": {
        "metric": "milex_min", "threshold": 2.0, "direction": "-", "unit": "%",
        "anchor_label": "동맹 최저 방위비(NATO 2% GDP 가이드라인)",
        "interpret": "최저 동맹이 2% 미만 → 무임승차 징후, Olson-Zeckhauser 예측 부합 / 2%↑면 반례",
    },
    "indo_pacific_conventional_deterrence": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "재래식 전력 격차(국방비%GDP)",
        "interpret": "방어자 우위(+)일수록 침략 억지 성립 — Mearsheimer 재래식 억지 부합",
    },
    "indo_pacific_coercive_diplomacy": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "강압자 군사 우위(국방비%GDP 격차)",
        "interpret": "군사 우위(+)일수록 위협 신뢰성↑ — Schelling 강압외교 전제 성립",
    },
    "indo_pacific_hegemonic_stability_theory": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "패권국 능력 우위(국방비%GDP 격차)",
        "interpret": "패권국 압도적 우위(+)일수록 질서 안정 공급 가능 — Kindleberger 부합",
    },
    "indo_pacific_power_transition_theory": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "패권-도전국 능력 격차(국방비%GDP, 추월 근접 proxy)",
        "interpret": "격차 축소(0 접근)일수록 추월 임박 → 분쟁 위험↑ — Organski 세력전이 부합",
    },
    "indo_pacific_security_dilemma": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "군비 비대칭(국방비%GDP 격차)",
        "interpret": "격차 존재 → 상호 군비 증강 악순환 가능 — Jervis 안보딜레마 전제",
    },
    "indo_pacific_offshore_balancing": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "역내 도전국 능력(국방비%GDP 격차)",
        "interpret": "역내 패권 도전 강할수록 역외균형자 개입 필요 — Mearsheimer&Walt 부합",
    },
    "maritime_corbett_sea_control": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "해군력 우위(국방비%GDP 격차, 함대 보존 proxy)",
        "interpret": "우위(+)일수록 제한적 제해권 확보 가능 — Corbett 부합",
    },
    "maritime_command_of_the_commons": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "공유지 지배력(국방비%GDP 격차 proxy)",
        "interpret": "압도적 우위(+)일수록 해·공·우주 공유지 지배 — Posen 부합",
    },
    "maritime_chokepoint_sloc": {
        "metric": "eia_flow_mbpd", "threshold": 15.0, "direction": "+", "unit": "Mbpd",
        "anchor_label": "초크포인트 통과량 임계(글로벌 원유 약 15%≈15Mbpd)",
        "interpret": "통과량 클수록 SLOC 취약성·차단 충격 큼 — 초크포인트 통제 가치 성립",
    },
    "gray_zone_escalation_theory": {
        "metric": "hiik_max", "threshold": 3, "direction": "+", "unit": "강도",
        "anchor_label": "HIIK 분쟁 강도(에스컬레이션 단계 proxy)",
        "interpret": "강도 3↑ → 사다리 상단 진입, 에스컬레이션 동역학 활성 — Kahn 부합",
    },
    "gray_zone_proxy_war_theory": {
        "metric": "hiik_max", "threshold": 3, "direction": "+", "unit": "강도",
        "anchor_label": "HIIK 분쟁 강도(대리전 활성 proxy)",
        "interpret": "강도 3↑ → 후원국 개입 대리전 격화 — Mumford 부합",
    },
    "gray_zone_salami_slicing": {
        "metric": "hiik_max", "threshold": 3, "direction": "-", "unit": "강도",
        "anchor_label": "HIIK 분쟁 강도(살라미는 임계 이하 유지가 특징)",
        "interpret": "강도 3 미만 유지 → 임계 회피 점진 잠식 성립 — Mastro/Fravel 부합 / 3↑면 노골화로 이론 이탈",
    },
    "energy_energy_security_theory": {
        "metric": "trade_hhi", "threshold": 2500, "direction": "+", "unit": "",
        "anchor_label": "에너지 공급원 집중도(HHI 독과점 임계 2500)",
        "interpret": "집중도 초과 → 공급 충격 취약, 에너지 안보 위협 성립 — Yergin 부합",
    },
    "techno_critical_minerals_security": {
        "metric": "trade_hhi", "threshold": 2500, "direction": "+", "unit": "",
        "anchor_label": "핵심 광물 공급 집중도(HHI 독과점 임계 2500)",
        "interpret": "집중도 초과 → 광물 무기화 지렛대 성립 — Overland 부합",
    },
    "techno_ai_strategic_competition": {
        "metric": "semi_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "AI 칩 역량 격차(TSMC↔SMIC proxy)",
        "interpret": "칩 역량 격차 클수록 AI 우위 누적 — NSCAI 예측 부합 (단 알고리즘 효율로 역전 가능)",
    },
    "techno_semiconductor_supply_chain": {
        "metric": "semi_gap_pp", "threshold": 0.0, "direction": "+", "unit": "%p",
        "anchor_label": "파운드리 생산 집중(TSMC↔SMIC 격차)",
        "interpret": "격차 클수록 공급망 단일 의존 심화 — 반도체 공급망 취약성 성립",
    },
    "techno_globalism": {
        "metric": "trade_hhi", "threshold": 2500, "direction": "-", "unit": "",
        "anchor_label": "기술 공급망 통합도(HHI 낮을수록 통합)",
        "interpret": "HHI 낮음(분산) → 글로벌 통합·시장 자정 예측 성립 / 높으면 분절화로 이론 이탈 — Rosecrance",
    },
}


def _collect_anchor_metrics(milex, trade_hhi, eia, wbk, polity5, hiik, itu, semi) -> dict:
    """실측 dict들에서 앵커 metric 단일 수치를 추출 (Token-Zero, 모두 결정론적)."""
    m: dict[str, float] = {}
    if trade_hhi:
        vals = [d.get("hhi_proxy") for d in trade_hhi.values() if d.get("hhi_proxy") is not None]
        if vals:
            m["trade_hhi"] = max(vals)   # 가장 집중된 품목
    if eia and eia.get("flow_mbpd") is not None:
        m["eia_flow_mbpd"] = eia["flow_mbpd"]
    mvals = [v.get("gdp_pct") for v in (milex or {}).values() if v.get("gdp_pct") is not None]
    if len(mvals) >= 2:
        m["milex_gap_pp"] = A.pct_point_gap(max(mvals), min(mvals))
    if mvals:
        m["milex_min"] = min(mvals)    # 동맹 최저 방위비 — 무임승차(burden sharing) 판정용
    pv = [v.get("polity") for v in (polity5 or {}).values() if v.get("polity") is not None]
    if pv:
        m["polity_min"] = min(pv)      # Waltz: '모두' 민주 임계 넘어야 → 최저값
    wv = [v.get("pv") for v in (wbk or {}).values() if v.get("pv") is not None]
    if wv:
        m["wgi_pv_min"] = min(wv)      # 최저 정치안정 = 거버넌스 공백
    iv = [d.get("intensity") for d in (hiik or {}).values() if d.get("intensity") is not None]
    if iv:
        m["hiik_max"] = max(iv)        # 최고 분쟁 강도
    idi = [v.get("idi") for v in (itu or {}).values() if v.get("idi") is not None]
    if idi:
        m["itu_idi_min"] = min(idi)    # 관련 행위자 중 최저 역량
    if semi:
        g = A.pct_point_gap(
            semi.get("tsmc_share", {}).get("value"),
            semi.get("smic_share", {}).get("value"),
        )
        if g is not None:
            m["semi_gap_pp"] = g
    return m


def _anchor_verdict(theory_id: str, metrics: dict):
    """이론 앵커 임계 vs 실측 편차 → (판정 라인, gap, 충족여부, 단위). 실측 없으면 None.
    IV 전제조건 충족도 (DV 직접측정 아님 — 라벨에 명시, 억지 판정 금지)."""
    anchor = _THEORY_ANCHORS.get(theory_id)
    if not anchor:
        return None
    val = metrics.get(anchor["metric"])
    if val is None:
        return None   # 실측 없으면 판정 생략 (빈칸 억지 채우기 금지)
    gap = A.delta(val, anchor["threshold"])
    if gap is None:
        return None
    met = (gap > 0) if anchor["direction"] == "+" else (gap < 0)
    verdict = "전제 충족" if met else "전제 미충족"
    line = (
        f"앵커(IV 전제조건) — {anchor['anchor_label']}: 실측 {val}{anchor['unit']} vs "
        f"임계 {anchor['threshold']}{anchor['unit']} (편차 {A.fmt_signed(gap, anchor['unit'])}, 사전계산) "
        f"→ {verdict}: {anchor['interpret']}"
    )
    return line, gap, met, anchor["unit"]


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
    # 1. 관련 이론 ID 수집 — 지역(region) 우선, 섹터 보완, 중복 제거.
    #    지역 매핑이 섹터 매핑보다 구체적이므로 지역을 먼저 채워 슬롯 선점.
    #    예: taiwan_strait 쿼리에서 maritime 섹터가 A2/AD·SLOC을 먼저 채워
    #    자유주의·현실주의 이론이 잘리는 버그 방지.
    candidate_ids: list[str] = []
    seen: set[str] = set()
    for r in regions:
        for tid in _REGION_THEORY_PAIRS.get(r, []):
            if tid not in seen:
                seen.add(tid)
                candidate_ids.append(tid)
    for s in sectors:
        for tid in _SECTOR_THEORY_PAIRS.get(s, []):
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
    milex      = _get_sipri_milex_for_theories(actors)
    arms       = _get_sipri_arms_hhi(actors)
    eia        = _get_eia_chokepoint(regions)
    acled      = _get_acled_event_count(regions)
    vdem       = _get_vdem_scores(actors)
    semi       = _get_semi_market_for_theories(sectors, regions)
    fred       = _get_fred_for_theories(regions)
    wbk        = _get_wbk_governance(actors)
    polity5    = _get_polity5(actors)
    hiik       = _get_hiik_conflict(regions)
    itu        = _get_itu_ict_for_theories(actors)
    owid       = _get_owid_military(actors, regions)
    trade_hhi  = _get_trade_hhi(actors, regions)  # AR-1b: Comtrade 의존도 HHI

    # [8-C] 정량 앵커 metric 1회 추출 (이론별 전제조건 충족 판정용)
    anchor_metrics = _collect_anchor_metrics(milex, trade_hhi, eia, wbk, polity5, hiik, itu, semi)
    anchor_summary: list[tuple] = []   # (이론명, 충족여부, 편차, 단위) — 편차 비교(사실) 병치용

    # 3. 비교 텍스트 생성
    lines: list[str] = ["## 경쟁 이론 비교 프로파일 (예측값 vs 실측값)"]
    lines.append(
        "⚠️ [경쟁설명] 판정 지침 — 2단계 구조:\n"
        "  ① IV 전제조건: 아래 '앵커 종합'의 충족/미충족 + 편차를 '판정:' 줄에 반드시 인용한다.\n"
        "  ② DV 방향 비교: **실측 데이터에 종속변수(DV)의 관측값·방향이 존재할 때만** 수행한다.\n"
        "     - DV 실측 있음 → '예측 부호 ▲/▼ vs DV 실측 방향·값'을 비교해 우세/열세 결론.\n"
        "       형식: 판정: 우세 — DV 예측 '분쟁건수 증가' vs DV 실측 '1170건(+trend)' → 방향 일치\n"
        "     - DV 실측 없음 → '실측: [UNVERIFIED] DV 정량값 부재'로 명시하고,\n"
        "       판정은 ①의 IV 전제충족도까지만 내린다. '전제 충족(DV 미검증)'으로 표기하라.\n"
        "  ⚠️ DV 실측이 없는데 방향 일치를 '추정'으로 적는 것은 환각 — 금지.\n"
        "     정직한 '[UNVERIFIED] DV 부재' 표기가 추정 판정보다 높은 평가를 받는다.\n"
    )

    for p in profiles:
        lines.append(f"### 이론: {p.get('title', p['theory_id'])}")
        if p.get("independent_var"):
            lines.append(f"**독립변수(IV)**: {p['independent_var']}")
        if p.get("dependent_var"):
            lines.append(f"**종속변수(DV)**: {p['dependent_var']}")
        # DV 예측 방향 부호를 fp 줄 끝에 인라인 병합 — 독립 라벨로 두면 Gemini가 예측: 줄에 복붙함
        _dv_dir = _extract_dv_direction(p.get("falsifiable_prediction", ""), p.get("dependent_var", ""))
        fp_text = p.get("falsifiable_prediction", "")
        if fp_text:
            # 부호 토큰(▲/▼/↔)만 괄호로 덧붙여 출력 오염 방지
            _dir_token = ""
            if _dv_dir:
                for token in ("▲", "▼", "↔"):
                    if token in _dv_dir:
                        _dir_token = f" (예측 부호: {token})"
                        break
            lines.append(f"**반증 가능 예측**: {fp_text}{_dir_token}")

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
                # 행위자가 2개 이상이면 GDP% 격차 사전계산 주입
                vals = [(iso3, v.get("gdp_pct")) for iso3, v in milex.items() if v.get("gdp_pct") is not None]
                if len(vals) >= 2:
                    vals.sort(key=lambda x: -x[1])
                    gap = A.pct_point_gap(vals[0][1], vals[-1][1])
                    empirical_lines.append(
                        f"실측 — SIPRI 국방비 격차: {vals[0][0]} {vals[0][1]}% ↔ "
                        f"{vals[-1][0]} {vals[-1][1]}% (격차 {A.fmt_signed(gap, '%p')}, 사전계산)"
                    )
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
                    pct_str = A.fmt_signed(d.get("pct_change"), "%")
                    empirical_lines.append(
                        f"실측 — {d['name']}: {d['latest_value']} {d.get('unit', '')} "
                        f"({d['latest_date']}, 최근 추세 {pct_str}, 사전계산) [FRED]"
                    )
            # techno 섹터: 반도체 공급망 집중도를 weaponized_interdependence의 핵심 IV로 추가
            if semi:
                if semi.get("foundry_hhi"):
                    tsmc_val = semi.get('tsmc_share', {}).get('value')
                    smic_val = semi.get('smic_share', {}).get('value')
                    ts_gap   = A.pct_point_gap(tsmc_val, smic_val)
                    empirical_lines.append(
                        f"실측 — 파운드리 HHI: {semi['foundry_hhi']['value']} "
                        f"({semi['foundry_hhi']['year']}, 기준 >2500=독과점) "
                        f"| TSMC: {tsmc_val or '?'}% | SMIC: {smic_val or '?'}%"
                        + (f" (TSMC↔SMIC 격차 {A.fmt_signed(ts_gap, '%p')}, 사전계산)" if ts_gap is not None else "")
                    )
                if semi.get("china_import_dep"):
                    empirical_lines.append(
                        f"실측 — 중국 첨단 반도체 수입 의존도: {semi['china_import_dep']['value']}% "
                        f"({semi['china_import_dep']['year']}) — 비대칭 의존 수치"
                    )
            # AR-1b: Comtrade 무역 의존도 HHI — Weaponized Interdependence IV 직접 측정값
            # HHI proxy: 상위 3쌍 dependency_ratio² 합산 × 10000 (>2500=독과점)
            if trade_hhi:
                for hs, data in trade_hhi.items():
                    hhi_val = data.get("hhi_proxy", 0)
                    concentration = A.concentration_label(hhi_val)
                    empirical_lines.append(
                        f"실측 — {data['label']}(HS {hs}) 공급망 HHI: {hhi_val:.0f} ({concentration}, 사전계산, "
                        f"최고의존쌍 {data['top_pair']} {data['top_ratio']}%, {data['period']}) "
                        f"[UN Comtrade]"
                    )

        if "mearsheimer" in tid or "waltz" in tid:
            if milex:
                milex_str = " | ".join(
                    f"{iso3}: {v.get('gdp_pct', '?')}% GDP"
                    for iso3, v in milex.items()
                )
                empirical_lines.append(f"실측 — SIPRI 권력 proxy(국방비): {milex_str}")
                vals = [(iso3, v.get("gdp_pct")) for iso3, v in milex.items() if v.get("gdp_pct") is not None]
                if len(vals) >= 2:
                    vals.sort(key=lambda x: -x[1])
                    gap = A.pct_point_gap(vals[0][1], vals[-1][1])
                    empirical_lines.append(
                        f"실측 — 권력 격차(국방비): {vals[0][0]} {vals[0][1]}% ↔ "
                        f"{vals[-1][0]} {vals[-1][1]}% (격차 {A.fmt_signed(gap, '%p')}, 사전계산)"
                    )
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
                # TSMC vs SMIC 점유율 격차 사전계산
                tsmc_v = semi.get("tsmc_share", {}).get("value")
                smic_v = semi.get("smic_share", {}).get("value")
                ts_gap = A.pct_point_gap(tsmc_v, smic_v)
                if ts_gap is not None:
                    parts.append(f"TSMC↔SMIC 점유율 격차 {A.fmt_signed(ts_gap, '%p')} (사전계산)")
                if parts:
                    empirical_lines.append(f"실측 — 기술 분리 지표: {' | '.join(parts)}")

        if "techno_nationalism" in tid:
            if semi:
                if semi.get("china_import_dep"):
                    empirical_lines.append(
                        f"실측 — 중국 자립화 현황: 첨단 반도체 수입의존 {semi['china_import_dep']['value']}% "
                        f"| SMIC 7nm yield {semi.get('smic_yield', {}).get('value', '?')}% (TSMC 95%+ 대비)"
                    )

        # [8-C] 정량 앵커 판정 추가 (실측 IV vs 임계 편차 — 결정론적)
        av = _anchor_verdict(tid, anchor_metrics)
        if av:
            empirical_lines.append(av[0])
            anchor_summary.append((p.get("title", tid), av[2], av[1], av[3]))

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

    # 4. 비교 지시문 추가 — 쌍을 하드코딩하지 않고 목록 전체를 제시하여
    #    Gemini가 쿼리 주제에 맞는 이론을 직접 선택하도록 한다.
    if len(profiles) >= 2:
        theory_list = " / ".join(
            f"'{p.get('title', p['theory_id'])}'" for p in profiles
        )
        lines.append(
            f"### 비교 증거 요청\n"
            f"위 이론 목록 [{theory_list}] 중 **사용자 쿼리 주제에 가장 직접 대응하는 2개**를 선택하여 "
            f"[경쟁설명] 섹션에서 각 이론의 예측 대비 실측 편차를 수치로 제시하라.\n"
            f"(예: 쿼리가 '자유주의 vs 현실주의'라면 자유주의 계열 1개 + 현실주의 계열 1개 선택)\n"
            f"각 이론은 '예측:/실측:/판정:' 3줄을 쓰되, '판정:'은 그 이론 단독의 예측-실측 편차(방향 일치/불일치)만 적는다. "
            f"마지막은 '▶ 편차 비교 (사실):'로 두 이론의 편차를 수치로 **병치만** 하고(우열 단정 금지), "
            f"이어 '▶ 당신의 판단 (연구자 몫):'으로 우세 이론 판정은 연구자에게 넘긴다 — "
            f"AI는 우열을 결론짓지 말고 판단 쟁점(숨은 가정·범위조건·metric 상이)만 1~2개 제시하라.\n"
            f"[9-Q 해석 주체] 최종 해석(어느 이론이 우세한가)은 연구자 본인의 몫이다. AI는 증거를 구조화하는 조수까지만."
        )

    # [8-C] 앵커 종합 (사전계산) — 각 이론 전제 충족 여부 결정론적 비교.
    #   ※ metric 스케일이 이론마다 달라(HHI 수천 vs Polity 한자리) 편차 '크기'
    #     직접 비교는 무의미·환각 위험 → '충족/미충족' 여부로만 비교 (정직성).
    if len(anchor_summary) >= 2:
        parts = [
            f"{name} {'전제충족' if met else '전제미충족'}(편차 {A.fmt_signed(gap, unit)})"
            for name, met, gap, unit in anchor_summary
        ]
        lines.append(
            "▶ 앵커 종합 (사전계산, IV 전제조건 충족도): " + " | ".join(parts) + "\n"
            "  ⚠️ 이 앵커는 IV 전제조건 충족 여부만 판정 — DV 직접 입증 아님.\n"
            "  [경쟁설명] '▶ 편차 비교 (사실):' 줄에 두 단계를 사실로만 제시하라(우열 결론 금지):\n"
            "    ① IV 전제조건: 이 앵커 충족 여부 인용 (필수)\n"
            "    ② DV 방향 비교: DV 실측값이 context에 있으면 수행, 없으면 '[UNVERIFIED] DV 부재'로 종결\n"
            "  → 어느 이론이 우세한지의 판정은 '▶ 당신의 판단 (연구자 몫)'에서 연구자에게 넘긴다."
        )

    return "\n".join(lines)
