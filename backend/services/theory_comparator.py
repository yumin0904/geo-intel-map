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
_LIB_DB  = Path(__file__).resolve().parent.parent / "db" / "library.db"
_MAIN_DB = Path(__file__).resolve().parent.parent / "db" / "geomap.db"


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
        with _db(_MAIN_DB) as con:
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
        with _db(_MAIN_DB) as con:
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
        with _db(_MAIN_DB) as con:
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


def _get_acled_event_count(regions: list[str]) -> dict:
    """ACLED 분쟁 이벤트 수 — Gray Zone/A2AD IV proxy."""
    _REGION_COUNTRIES = {
        "taiwan_strait": ["Taiwan", "China"],
        "eastern_europe": ["Ukraine", "Russia"],
        "hormuz": ["Iran", "Yemen"],
        "korean_peninsula": ["North Korea", "South Korea"],
        "bab_el_mandeb": ["Yemen", "Ethiopia"],
        "sahel": ["Mali", "Niger", "Burkina Faso"],
    }
    target_countries = []
    for r in regions:
        target_countries.extend(_REGION_COUNTRIES.get(r, []))
    if not target_countries:
        return {}
    try:
        with _db(_MAIN_DB) as con:
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
        with _db(_MAIN_DB) as con:
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

        if "alliance_theory" in tid:
            empirical_lines.append(
                "실측 — COW Alliance DB 및 alliance_graph.yaml의 pact_intensity 값 참조 (context §COW 동맹 섹션)"
            )

        if "gray_zone" in tid or "hybrid_warfare" in tid:
            if acled:
                empirical_lines.append(
                    f"실측 — ACLED 분쟁 이벤트 24개월: {acled.get('event_count_24m', '?')}건"
                )

        if "libicki" in tid or "digital_iron_curtain" in tid:
            empirical_lines.append(
                "실측 — CSIS Significant Cyber Incidents DB 참조 (context §CSIS 사이버 섹션)"
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
            f"수치 편차와 함께 판정하라. "
            f"판정 형식: '예측: [이론 예측 방향] / 실측: [데이터 수치] / 편차: [차이] / 우세 이론: [이름]'"
        )

    return "\n".join(lines)
