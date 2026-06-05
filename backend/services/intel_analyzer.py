"""
services/intel_analyzer.py

멀티소스 병렬 검색 + 컨텍스트 조립 (Token-Zero).

소스:
  1.  LIKE 검색 — 한국어 키워드로 브리핑·이론 title/body 검색
  2.  섹터 필터 — 섹터별 최신 브리핑
  3.  event_archive 통계 — 지역별 집계
  4.  cascade_links — 지역 발화 실적 + 이론 텍스트
  5.  country_geopolitics.yaml — 행위자 국가 프로파일
  6.  SIPRI Military Expenditure — 국방비 %GDP
  7.  COW Alliances — 공식 동맹
  8.  Kiel Ukraine Support Tracker — 서방 지원액
  9.  EIA Energy — 초크포인트 통과량
  10. CSIS Cyber Incidents — APT 사건 선례
  11. SIPRI Arms Transfers — 무기 의존도·공급망 (Cycle 6-A)
  12. V-DEM Democracy Index — 행위자 체제 유형 정량화 (Cycle 6-A)
  13. COW Wars — 전쟁 선례 시계열 (Cycle 6-A)
  14. 외교부 LOD IFANS — 한반도·동아시아 한국 시각 발간자료 (Cycle 6-A)
  15. 경쟁 이론 비교 프로파일 — 이론 예측값 vs 실측값 편차 컨텍스트 (Cycle 7-B)
"""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import yaml
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from services.entity_parser import ParsedQuery
from services.theory_comparator import build_theory_comparison_context

logger = logging.getLogger(__name__)

_CONFIG   = Path(__file__).resolve().parent.parent / "config"
_INTEL_DB = Path(__file__).resolve().parent.parent / "db" / "intel.db"
_LIB_DB   = Path(__file__).resolve().parent.parent / "db" / "library.db"

# 브리핑 원문 1개당 최대 포함 글자 수 (토큰 절약)
_BODY_MAX_CHARS = 3000
# Gemini 컨텍스트 총 상한 (글자 기준 — 약 30,000 tokens)
_CONTEXT_MAX_CHARS = 20000


@contextmanager
def _db(path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# ── 1. LIKE 기반 한국어 키워드 검색 ─────────────────────────────────────────

def _extract_keywords(query: str) -> list[str]:
    """쿼리에서 유의미한 키워드 추출 (한국어 2자+ / 영어 3자+)."""
    ko = re.findall(r"[가-힣]{2,}", query)
    en = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", query)
          if w.lower() not in {"the", "and", "for", "with", "this", "that"}]
    return (ko + en)[:8]


def _search_library_like(query: str, regions: list[str],
                          sectors: list[str], limit: int = 10) -> list[dict]:
    """
    LIKE 기반 한국어·영어 혼합 검색.
    title + summary + body 전체에서 키워드 매칭.
    """
    keywords = _extract_keywords(query)

    # 지역 한국어 별칭도 검색 키워드에 추가
    _REGION_KO_SEARCH = {
        "ukraine": ["우크라이나", "러시아"], "taiwan_strait": ["대만", "양안"],
        "hormuz": ["호르무즈", "이란"], "bab_el_mandeb": ["홍해", "후티"],
        "south_china_sea": ["남중국해"], "korean_peninsula": ["한반도", "북한"],
        "middle_east": ["중동", "이스라엘"], "east_china_sea": ["동중국해"],
    }
    for r in regions:
        keywords.extend(_REGION_KO_SEARCH.get(r, []))
    keywords = list(dict.fromkeys(keywords))[:10]  # 중복 제거

    if not keywords:
        return []

    try:
        with _db(_LIB_DB) as con:
            # 키워드별 히트 수로 관련도 계산
            conditions = " OR ".join(
                f"(title LIKE ? OR summary LIKE ? OR body LIKE ?)"
                for _ in keywords
            )
            params = []
            for kw in keywords:
                pat = f"%{kw}%"
                params.extend([pat, pat, pat])
            params.append(limit)

            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary,
                       source_org, geopol_region, asset_type,
                       published_date, body,
                       independent_var, dependent_var, conditions,
                       falsifiable_prediction, known_counterexample, rival_theories
                FROM theories
                WHERE {conditions}
                ORDER BY published_date DESC NULLS LAST
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] LIKE 검색 실패: %s", e)
        return []


# ── 2. 섹터 필터 검색 ────────────────────────────────────────────────────────

def _search_library_by_sector(sectors: list[str], limit: int = 6) -> list[dict]:
    """섹터 필터로 최신 브리핑·이론 조회 (body 포함)."""
    if not sectors:
        return []
    placeholders = ",".join("?" * len(sectors))
    try:
        with _db(_LIB_DB) as con:
            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary,
                       source_org, geopol_region, asset_type,
                       published_date, body,
                       independent_var, dependent_var, conditions,
                       falsifiable_prediction, known_counterexample, rival_theories
                FROM theories
                WHERE sector_tag IN ({placeholders})
                ORDER BY published_date DESC NULLS LAST
                LIMIT ?
                """,
                (*sectors, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] sector 검색 실패: %s", e)
        return []


# ── 3. event_archive 통계 ────────────────────────────────────────────────────

_REGION_KO: dict[str, list[str]] = {
    "ukraine":          ["우크라이나"],
    "taiwan_strait":    ["대만", "대만해협"],
    "hormuz":           ["호르무즈"],
    "bab_el_mandeb":    ["바브엘만데브", "홍해"],
    "south_china_sea":  ["남중국해"],
    "korean_peninsula": ["한반도", "북한"],
    "malacca":          ["말라카"],
    "suez":             ["수에즈"],
    "middle_east":      ["중동"],
    "east_china_sea":   ["동중국해"],
}


def _get_event_stats(regions: list[str]) -> dict:
    if not regions:
        return {}
    placeholders = ",".join("?" * len(regions))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT region_code, source_type, COUNT(*) as cnt
                FROM event_archive
                WHERE region_code IN ({placeholders})
                GROUP BY region_code, source_type
                ORDER BY cnt DESC LIMIT 20
                """,
                tuple(regions),
            ).fetchall()
            sev_rows = con.execute(
                f"""
                SELECT region_code, ROUND(AVG(severity), 1) as avg_sev,
                       MAX(severity) as max_sev, COUNT(*) as total
                FROM event_archive
                WHERE region_code IN ({placeholders})
                GROUP BY region_code
                """,
                tuple(regions),
            ).fetchall()

        stats: dict = {}
        for r in rows:
            rc = r["region_code"]
            if rc not in stats:
                stats[rc] = {"event_types": {}}
            stats[rc]["event_types"][r["source_type"]] = r["cnt"]
        for r in sev_rows:
            rc = r["region_code"]
            if rc not in stats:
                stats[rc] = {"event_types": {}}
            stats[rc].update({
                "avg_severity": r["avg_sev"],
                "max_severity": r["max_sev"],
                "total_events":  r["total"],
            })
        return stats
    except Exception as e:
        logger.warning("[intel] event_stats 실패: %s", e)
        return {}


# ── 4. cascade_links + cascade_rules 이론 텍스트 ─────────────────────────────

def _get_cascade_context(regions: list[str]) -> dict:
    """cascade_links 발화 실적 + 관련 룰의 이론 텍스트."""
    result: dict = {"links": [], "rules": []}
    if not regions:
        return result

    # cascade_links 조회
    ko_keywords: list[str] = []
    for r in regions:
        ko_keywords.extend(_REGION_KO.get(r, [r]))
    try:
        with _db(_INTEL_DB) as con:
            conditions = " OR ".join(f"rule_name LIKE ?" for _ in ko_keywords)
            params     = [f"%{kw}%" for kw in ko_keywords] + [8]
            rows = con.execute(
                f"""
                SELECT rule_name, correlation_score, depth
                FROM cascade_links
                WHERE {conditions}
                ORDER BY correlation_score DESC LIMIT ?
                """,
                params,
            ).fetchall()
        result["links"] = [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] cascade_links 실패: %s", e)

    # cascade_rules.yaml에서 관련 룰 이론 텍스트 추출
    try:
        with open(_CONFIG / "cascade_rules.yaml", encoding="utf-8") as f:
            rules = yaml.safe_load(f) or []

        region_set = set(regions)
        for rule in rules:
            trigger = rule.get("trigger", {})
            rule_region = trigger.get("region", "")
            if rule_region in region_set or not region_set:
                theory = rule.get("theory", {})
                if theory:
                    result["rules"].append({
                        "name":       rule.get("name", rule.get("id", "")),
                        "framework":  theory.get("framework", ""),
                        "reference":  theory.get("reference", ""),
                        "learning":   theory.get("learning_note", ""),
                    })
    except Exception as e:
        logger.warning("[intel] cascade_rules 로드 실패: %s", e)

    return result


# ── 5. SIPRI 국방비 ──────────────────────────────────────────────────────────

def _get_sipri_data(actors: list[str], regions: list[str]) -> dict[str, list[dict]]:
    """SIPRI 국방비 — 행위자 국가의 최근 5년 추이."""
    # 지역 → 관련 국가 추가 매핑
    _REGION_ACTORS: dict[str, list[str]] = {
        "ukraine":          ["UKR", "RUS"],
        "taiwan_strait":    ["CHN", "USA", "TWN"],
        "hormuz":           ["IRN", "SAU", "USA", "ISR"],
        "bab_el_mandeb":    ["SAU", "USA"],
        "south_china_sea":  ["CHN", "USA", "VNM", "PHL"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "middle_east":      ["ISR", "IRN", "SAU", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS.get(r, []))

    if not iso3_set:
        return {}

    placeholders = ",".join("?" * len(iso3_set))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT iso3, country_name, year, gdp_pct, usd_mn_2022
                FROM sipri_milex
                WHERE iso3 IN ({placeholders})
                  AND year >= (SELECT MAX(year)-4 FROM sipri_milex)
                  AND gdp_pct IS NOT NULL
                ORDER BY iso3, year DESC
                """,
                tuple(iso3_set),
            ).fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            iso3 = r["iso3"]
            if iso3 not in result:
                result[iso3] = []
            result[iso3].append({
                "year":       r["year"],
                "gdp_pct":    r["gdp_pct"],
                "usd_mn":     r["usd_mn_2022"],
                "country":    r["country_name"],
            })
        return result
    except Exception as e:
        logger.warning("[intel] sipri_data 실패: %s", e)
        return {}


def _get_cow_alliances(actors: list[str], regions: list[str] | None = None) -> list[dict]:
    """COW 동맹 — 행위자 국가의 현재 활성 동맹 관계."""
    # SIPRI와 동일한 region → ISO3 확장 매핑 활용
    _REGION_ACTORS: dict[str, list[str]] = {
        "ukraine":          ["UKR", "RUS", "USA", "GBR", "DEU", "FRA", "POL"],
        "taiwan_strait":    ["CHN", "USA", "JPN", "KOR"],
        "hormuz":           ["IRN", "SAU", "USA", "GBR"],
        "bab_el_mandeb":    ["SAU", "USA"],
        "south_china_sea":  ["CHN", "USA", "PHL"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "middle_east":      ["ISR", "IRN", "SAU", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
    }
    iso3_set = set(actors)
    for r in (regions or []):
        iso3_set.update(_REGION_ACTORS.get(r, []))

    if not iso3_set:
        return []
    placeholders = ",".join("?" * len(iso3_set))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT iso3_a, iso3_b, name_a, name_b,
                       start_year, end_year, alliance_type
                FROM cow_alliances
                WHERE (iso3_a IN ({placeholders}) OR iso3_b IN ({placeholders}))
                  AND (end_year IS NULL OR end_year >= 2020)
                ORDER BY alliance_type, start_year
                """,
                (*iso3_set, *iso3_set),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] cow_alliances 실패: %s", e)
        return []


def _get_kiel_data(regions: list[str]) -> list[dict]:
    """Kiel Ukraine Support Tracker — 우크라이나 지역 쿼리 시만 반환."""
    ukraine_regions = {"ukraine", "eastern_europe", "bab_el_mandeb"}
    if not any(r in ukraine_regions for r in regions):
        return []
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                """
                SELECT donor_name, donor_iso3,
                       military_eur_bn, financial_eur_bn,
                       humanitarian_eur_bn, total_eur_bn, data_period
                FROM kiel_ukraine_support
                ORDER BY total_eur_bn DESC
                LIMIT 12
                """,
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] kiel_data 실패: %s", e)
        return []


# ── 6. EIA 에너지 통계 ───────────────────────────────────────────────────────

def _get_eia_data(actors: list[str], regions: list[str]) -> dict:
    """EIA 에너지 통계 — 행위자 국가 생산량 + 관련 초크포인트 통과량."""
    _REGION_CHOKEPOINTS: dict[str, list[str]] = {
        "hormuz":        ["HORMUZ", "IRN", "SAU", "IRQ", "ARE", "KWT", "QAT"],
        "malacca":       ["MALACCA", "SAU", "IRQ"],
        "bab_el_mandeb": ["BABELM", "SAU"],
        "suez":          ["SUEZ"],
        "taiwan_strait": ["MALACCA"],
        "south_china_sea": ["MALACCA"],
        "ukraine":       ["RUS", "NOR"],
        "korean_peninsula": ["RUS", "CHN"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_CHOKEPOINTS.get(r, []))

    if not iso3_set:
        return {}

    placeholders = ",".join("?" * len(iso3_set))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT iso3, country_name, crude_prod_mbpd,
                       natgas_prod_bcfd, oil_export_mbpd, data_year
                FROM eia_energy
                WHERE iso3 IN ({placeholders})
                ORDER BY crude_prod_mbpd DESC NULLS LAST
                """,
                tuple(iso3_set),
            ).fetchall()
        return {r["iso3"]: dict(r) for r in rows}
    except Exception as e:
        logger.warning("[intel] eia_data 실패: %s", e)
        return {}


def _get_csis_incidents(actors: list[str], regions: list[str],
                        sectors: list[str]) -> list[dict]:
    """CSIS 사이버 사건 — 행위자·지역·섹터 기반 필터링."""
    _REGION_COUNTRIES: dict[str, list[str]] = {
        "ukraine":          ["UKR", "RUS"],
        "taiwan_strait":    ["CHN", "USA", "TWN"],
        "hormuz":           ["IRN", "SAU", "USA"],
        "korean_peninsula": ["PRK", "KOR", "USA"],
        "middle_east":      ["IRN", "ISR", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
    }
    # cyber 또는 techno 섹터 포함 시 더 넓은 범위 조회
    is_cyber = "cyber" in sectors or "techno" in sectors

    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_COUNTRIES.get(r, []))

    try:
        with _db(_INTEL_DB) as con:
            if iso3_set:
                placeholders = ",".join("?" * len(iso3_set))
                rows = con.execute(
                    f"""
                    SELECT incident_id, incident_date, actor_iso3, actor_group,
                           victim_iso3, victim_sector, incident_type, title, description
                    FROM csis_cyber_incidents
                    WHERE actor_iso3 IN ({placeholders})
                       OR victim_iso3 IN ({placeholders})
                    ORDER BY incident_date DESC
                    LIMIT 10
                    """,
                    (*iso3_set, *iso3_set),
                ).fetchall()
            elif is_cyber:
                # cyber 섹터 쿼리지만 특정 행위자 없으면 최신 10건
                rows = con.execute(
                    """
                    SELECT incident_id, incident_date, actor_iso3, actor_group,
                           victim_iso3, victim_sector, incident_type, title, description
                    FROM csis_cyber_incidents
                    ORDER BY incident_date DESC LIMIT 10
                    """,
                ).fetchall()
            else:
                rows = []
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] csis_incidents 실패: %s", e)
        return []


# ── Cycle 6-A 신규 소스 ────────────────────────────────────────────────────

def _get_sipri_arms(actors: list[str], regions: list[str]) -> list[dict]:
    """SIPRI Arms Transfers — 행위자 관련 무기 공급망 조회.
    techno/cyber 섹터 전용 쿼리에는 미주입 (무관한 주장 유발 방지).
    """
    if not actors:
        return []
    try:
        placeholders = ",".join("?" * len(actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT supplier_iso3, supplier_name, recipient_iso3, recipient_name,
                           year, tiv_mn, weapon_category, notes
                    FROM sipri_arms_transfers
                    WHERE supplier_iso3 IN ({placeholders})
                       OR recipient_iso3 IN ({placeholders})
                    ORDER BY year DESC
                    LIMIT 10""",
                actors * 2,
            ).fetchall()
        return [
            {
                "supplier": r[1] or r[0], "recipient": r[3] or r[2],
                "year": r[4], "tiv_mn": r[5],
                "category": r[6], "notes": r[7],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] sipri_arms 실패: %s", e)
        return []


def _get_vdem(actors: list[str]) -> list[dict]:
    """V-DEM 민주주의 지수 — 행위자 체제 유형 정량화."""
    if not actors:
        return []
    try:
        placeholders = ",".join("?" * len(actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, v2x_libdem, v2x_regime,
                           v2x_polyarchy, v2x_corr, notes
                    FROM vdem_index
                    WHERE iso3 IN ({placeholders})
                    ORDER BY year DESC""",
                actors,
            ).fetchall()
        regime_labels = {0: "폐쇄권위주의", 1: "선거권위주의", 2: "선거민주주의", 3: "자유민주주의"}
        return [
            {
                "iso3": r[0], "country": r[1] or r[0], "year": r[2],
                "libdem": r[3], "regime_type": regime_labels.get(r[4], "미분류"),
                "polyarchy": r[5], "corruption": r[6], "notes": r[7],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] vdem 실패: %s", e)
        return []


def _get_cow_wars(regions: list[str], actors: list[str]) -> list[dict]:
    """COW Wars — 지역·행위자 관련 전쟁 선례 조회."""
    try:
        conditions: list[str] = []
        params: list = []
        if regions:
            ph = ",".join("?" * len(regions))
            conditions.append(f"relevance_tag IN ({ph})")
            params.extend(regions)
        if actors:
            actor_conds = [
                "(side_a_iso3 LIKE ? OR side_b_iso3 LIKE ?)"
                for _ in actors
            ]
            conditions.append("(" + " OR ".join(actor_conds) + ")")
            for a in actors:
                params.extend([f"%{a}%", f"%{a}%"])
        if not conditions:
            return []
        where = " OR ".join(conditions)
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT war_name, start_year, end_year,
                           side_a_iso3, side_b_iso3, region,
                           battle_deaths, outcome, relevance_tag
                    FROM cow_wars WHERE {where}
                    ORDER BY start_year DESC LIMIT 8""",
                params,
            ).fetchall()
        outcome_labels = {1: "A측 승", 2: "B측 승", 3: "협상 타결", 4: "정전", 5: "진행 중"}
        return [
            {
                "name": r[0],
                "period": f"{r[1]}~{r[2] or '진행중'}",
                "sides": f"{r[3]} vs {r[4]}",
                "region": r[5],
                "battle_deaths": r[6],
                "outcome": outcome_labels.get(r[7], "?"),
                "tag": r[8],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] cow_wars 실패: %s", e)
        return []


def _get_ifans_publications(actors: list[str], regions: list[str]) -> list[dict]:
    """외교부 LOD IFANS 발간자료 — 한반도·동아시아 한국 시각 컨텍스트."""
    try:
        from connectors.mofa_lod import fetch_ifans_publications
        return fetch_ifans_publications(actors, regions)
    except Exception as e:
        logger.warning("[intel] ifans_publications 실패: %s", e)
        return []


# ── 16. FRED 경제 시계열 (Cycle 7-D-1) ───────────────────────────────────────

_REGION_FRED_SERIES: dict[str, list[str]] = {
    "hormuz":           ["DCOILWTICO", "DCOILBRENTEU", "MHHNGSP"],
    "eastern_europe":   ["PNGASEUUSDM", "DCOILWTICO", "GOLDAMGBD228NLBM"],
    "korean_peninsula": ["KOREUS", "DCOILWTICO"],
    "taiwan_strait":    ["EXCHUS", "EXJPUS", "DCOILWTICO"],
    "indo_pacific":     ["EXJPUS", "EXCHUS", "USMC"],
    "energy":           ["DCOILWTICO", "DCOILBRENTEU", "PNGASEUUSDM", "MHHNGSP"],
    "gray_zone":        ["GOLDAMGBD228NLBM", "DCOILWTICO"],
}

def _get_fred_data(regions: list[str], sectors: list[str]) -> list[dict]:
    """FRED 경제 지표 시계열 — 지역·섹터 기반 스마트 라우팅."""
    series_ids: set[str] = set()
    for r in regions:
        series_ids.update(_REGION_FRED_SERIES.get(r, []))
    if "energy" in sectors:
        series_ids.update(_REGION_FRED_SERIES["energy"])
    if "gray_zone" in sectors:
        series_ids.update(_REGION_FRED_SERIES["gray_zone"])
    if not series_ids:
        series_ids = {"DCOILWTICO", "GOLDAMGBD228NLBM"}  # 기본값

    try:
        placeholders = ",".join("?" * len(series_ids))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT series_id, series_name, date, value, unit
                    FROM fred_indicators
                    WHERE series_id IN ({placeholders})
                    ORDER BY series_id, date DESC""",
                list(series_ids),
            ).fetchall()
        # 시리즈별로 최근 3개 값만 반환
        result: dict[str, list] = {}
        for r in rows:
            sid = r[0]
            if sid not in result:
                result[sid] = []
            if len(result[sid]) < 3:
                result[sid].append({
                    "series_id": sid, "series_name": r[1],
                    "date": r[2], "value": r[3], "unit": r[4],
                })
        return [item for items in result.values() for item in items]
    except Exception as e:
        logger.warning("[intel] fred_data 실패: %s", e)
        return []


# ── 17. World Bank WGI 거버넌스 지수 (Cycle 7-D-2) ──────────────────────────

def _get_world_bank_wgi(actors: list[str], regions: list[str]) -> list[dict]:
    """World Bank WGI — 행위자 국가 거버넌스 지수 (gray_zone·사헬·북극 공백 해소)."""
    _REGION_ACTORS_WB: dict[str, list[str]] = {
        "sahel":            ["MLI", "NER", "BFA", "ETH", "NGA"],
        "bab_el_mandeb":    ["ETH", "SOM", "YEM", "SAU"],
        "hormuz":           ["IRN", "SAU", "QAT", "ARE"],
        "eastern_europe":   ["UKR", "RUS", "BLR"],
        "korean_peninsula": ["PRK", "KOR"],
        "taiwan_strait":    ["CHN", "TWN", "USA"],
        "arctic":           ["RUS", "NOR", "USA", "CAN"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS_WB.get(r, []))
    if not iso3_set:
        return []

    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, pv_score, cc_score,
                           rl_score, ge_score, rq_score, va_score
                    FROM world_bank_wgi
                    WHERE iso3 IN ({placeholders})
                    ORDER BY iso3, year DESC""",
                list(iso3_set),
            ).fetchall()
        seen = set()
        result = []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                result.append({
                    "iso3": r[0], "country": r[1] or r[0], "year": r[2],
                    "political_stability": r[3], "corruption_control": r[4],
                    "rule_of_law": r[5], "gov_effectiveness": r[6],
                    "regulatory_quality": r[7], "voice_accountability": r[8],
                })
        return result
    except Exception as e:
        logger.warning("[intel] world_bank_wgi 실패: %s", e)
        return []


# ── 18. Polity5 정치체제 지수 (Cycle 7-D-4) ─────────────────────────────────

def _get_polity5(actors: list[str]) -> list[dict]:
    """Polity5 — 행위자 국가 체제 분류 강화 (V-DEM 보완)."""
    if not actors:
        return []
    try:
        placeholders = ",".join("?" * len(actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, polity_score, polity2_score, regime_type
                    FROM polity5
                    WHERE iso3 IN ({placeholders})
                    ORDER BY iso3, year DESC""",
                actors,
            ).fetchall()
        seen = set()
        result = []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                result.append({
                    "iso3": r[0], "country": r[1] or r[0], "year": r[2],
                    "polity_score": r[3], "polity2": r[4], "regime_type": r[5],
                })
        return result
    except Exception as e:
        logger.warning("[intel] polity5 실패: %s", e)
        return []


# ── 19. ITU ICT 개발 지수 (Cycle 7-D-5) ─────────────────────────────────────

def _get_itu_ict(actors: list[str], sectors: list[str]) -> list[dict]:
    """ITU ICT 개발 지수 — cyber/techno 섹터 국가별 역량 수치화."""
    if not actors and "cyber" not in sectors and "techno" not in sectors:
        return []
    target_actors = list(actors)
    # cyber/techno 쿼리면 핵심 행위자 자동 추가
    if "cyber" in sectors or "techno" in sectors:
        for iso3 in ["USA", "CHN", "RUS", "PRK", "IRN"]:
            if iso3 not in target_actors:
                target_actors.append(iso3)
    if not target_actors:
        return []
    try:
        placeholders = ",".join("?" * len(target_actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, idi_score, global_rank, cyber_tier
                    FROM itu_ict
                    WHERE iso3 IN ({placeholders})
                    ORDER BY idi_score DESC""",
                target_actors,
            ).fetchall()
        return [
            {"iso3": r[0], "country": r[1] or r[0], "year": r[2],
             "idi_score": r[3], "rank": r[4], "tier": r[5]}
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] itu_ict 실패: %s", e)
        return []


# ── 20. HIIK 분쟁 강도 바로미터 (Cycle 7-D-6) ──────────────────────────────

def _get_hiik_conflict(regions: list[str]) -> list[dict]:
    """HIIK — 지역별 최신 분쟁 강도 (ACLED 보완, 분쟁 수치화)."""
    if not regions:
        return []
    try:
        placeholders = ",".join("?" * len(regions))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT conflict_id, conflict_name, primary_country_iso3,
                           region, year, intensity, intensity_label, involved_actors
                    FROM hiik_conflict
                    WHERE region IN ({placeholders})
                    ORDER BY intensity DESC, year DESC
                    LIMIT 8""",
                regions,
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "country": r[2], "region": r[3],
             "year": r[4], "intensity": r[5], "label": r[6], "actors": r[7]}
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] hiik_conflict 실패: %s", e)
        return []


# ── 21. 반도체·기술 시장 데이터 (Cycle 7-D-7) ────────────────────────────────

def _get_semi_market(sectors: list[str], regions: list[str]) -> list[dict]:
    """SIA 반도체 시장 데이터 — techno/cyber 섹터 HHI·점유율 수치화."""
    if "techno" not in sectors and "cyber" not in sectors and "taiwan_strait" not in regions:
        return []
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                """SELECT category, metric, value, unit, year, source, region_hint, notes
                   FROM semi_market_data
                   ORDER BY category, year DESC
                   LIMIT 20""",
            ).fetchall()
        return [
            {"category": r[0], "metric": r[1], "value": r[2], "unit": r[3],
             "year": r[4], "source": r[5], "region_hint": r[6], "notes": r[7]}
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] semi_market 실패: %s", e)
        return []


# ── 22. Our World in Data 군사비·핵탄두 (Cycle 7-D-3) ──────────────────────

def _get_owid_data(actors: list[str], regions: list[str], sectors: list[str]) -> list[dict]:
    """OWID 군사비 %GDP·핵탄두 — indo_pacific 군사력 비교 수치화."""
    # 군사 비교가 의미있는 쿼리만: indo_pacific·maritime 섹터 또는 행위자 지정
    _REGION_ACTORS_MIL: dict[str, list[str]] = {
        "taiwan_strait":    ["CHN", "USA", "TWN", "JPN"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "south_china_sea":  ["CHN", "USA", "VNM", "PHL"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
        "eastern_europe":   ["RUS", "UKR", "USA"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS_MIL.get(r, []))
    # 군사 관련 섹터가 아니고 행위자도 없으면 스킵
    if not iso3_set and not ({"indo_pacific", "maritime"} & set(sectors)):
        return []
    if not iso3_set:
        iso3_set = {"USA", "CHN", "RUS"}  # 군사 섹터 기본 비교군

    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT dataset, iso3, country, year, value, unit
                    FROM owid_data
                    WHERE iso3 IN ({placeholders})
                    ORDER BY dataset, iso3, year DESC""",
                list(iso3_set),
            ).fetchall()
        # dataset+iso3별 최신값만
        seen = set()
        result = []
        for r in rows:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                result.append({
                    "dataset": r[0], "iso3": r[1], "country": r[2],
                    "year": r[3], "value": r[4], "unit": r[5],
                })
        return result
    except Exception as e:
        logger.warning("[intel] owid_data 실패: %s", e)
        return []


# ── 7. 국가 프로파일 ──────────────────────────────────────────────────────────

def _get_country_profiles(actors: list[str]) -> dict:
    if not actors:
        return {}
    try:
        with open(_CONFIG / "country_geopolitics.yaml", encoding="utf-8") as f:
            cg = yaml.safe_load(f)
        profiles = cg.get("profiles", {})
        return {iso3: profiles[iso3] for iso3 in actors if iso3 in profiles}
    except Exception as e:
        logger.warning("[intel] country_profiles 실패: %s", e)
        return {}


# ── 컨텍스트 조립 ─────────────────────────────────────────────────────────────

def _build_context(
    pq:               ParsedQuery,
    like_items:       list[dict],
    sector_items:     list[dict],
    event_stats:      dict,
    cascade_ctx:      dict,
    country_profiles: dict,
    sipri_data:       dict | None = None,
    cow_alliances:    list[dict] | None = None,
    kiel_data:        list[dict] | None = None,
    eia_data:         dict | None = None,
    csis_incidents:   list[dict] | None = None,
    sipri_arms:       list[dict] | None = None,
    vdem_data:        list[dict] | None = None,
    cow_wars:         list[dict] | None = None,
    ifans_pubs:       list[dict] | None = None,
    # Cycle 7-D 신규 소스
    fred_data:        list[dict] | None = None,
    wbk_data:         list[dict] | None = None,
    polity5_data:     list[dict] | None = None,
    itu_data:         list[dict] | None = None,
    hiik_data:        list[dict] | None = None,
    semi_data:        list[dict] | None = None,
    owid_data:        list[dict] | None = None,
) -> str:
    lines: list[str] = []
    total_chars = 0

    # ── 쿼리 요약 ──────────────────────────────────────────────────────────
    lines.append("## 분석 쿼리 요약")
    lines.append(f"- 지역: {', '.join(pq.regions) or '미지정'}")
    lines.append(f"- 행위자: {', '.join(pq.actors) or '미지정'}")
    lines.append(f"- 섹터: {', '.join(pq.sectors) or '전체'}")
    lines.append("")

    # ── 브리핑·이론 원문 (상위 3개 full body) ─────────────────────────────
    # LIKE 검색 결과 우선, 섹터 필터로 보완, 중복 제거
    seen_ids: set[str] = set()
    all_items: list[dict] = []
    for item in like_items + sector_items:
        tid = item.get("theory_id", "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            all_items.append(item)

    # body 있는 것 우선 정렬
    all_items.sort(key=lambda x: len(x.get("body") or ""), reverse=True)

    body_count = 0
    meta_items = []

    for item in all_items:
        body = (item.get("body") or "").strip()
        org  = f"[{item.get('source_org', '')}] " if item.get("source_org") else ""
        title = item.get("title", "")

        if body and body_count < 3 and total_chars < _CONTEXT_MAX_CHARS:
            # 원문 포함 (최대 3개, 각 3000자)
            truncated = body[:_BODY_MAX_CHARS]
            if len(body) > _BODY_MAX_CHARS:
                truncated += "\n...(이하 생략)"
            section = f"### {org}{title}\n{truncated}\n"
            lines.append(section)
            total_chars += len(section)
            body_count += 1
        else:
            # 원문 초과 시 제목+요약만
            meta_items.append(item)

    if body_count > 0:
        lines.insert(2, f"## 브리핑·이론 원문 ({body_count}개 전문 포함)\n")

    # 나머지는 제목+요약만
    if meta_items:
        lines.append("## 추가 관련 브리핑 (요약)")
        for item in meta_items[:5]:
            org   = f"[{item.get('source_org', '')}] " if item.get("source_org") else ""
            lines.append(f"- {org}{item.get('title', '')}")
            summary = (item.get("summary") or "")[:150]
            if summary:
                lines.append(f"  {summary}")
        lines.append("")

    # ── Phase 7 이론 프로파일 (예측변수·반례·경쟁이론) ────────────────────
    # asset_type=theory이면서 프로파일 필드가 있는 항목만 추출
    import json as _json
    theory_profiles = [
        item for item in all_items
        if item.get("asset_type") == "theory" and item.get("independent_var")
    ]
    if theory_profiles:
        lines.append("## 이론 프로파일 (예측 도구)")
        for tp in theory_profiles[:4]:
            lines.append(f"### {tp.get('title', tp.get('theory_id', ''))}")
            lines.append(f"- 독립변수: {tp['independent_var']}")
            lines.append(f"- 종속변수: {tp.get('dependent_var', '?')}")
            if tp.get("falsifiable_prediction"):
                lines.append(f"- 반증 가능 예측: {tp['falsifiable_prediction']}")
            if tp.get("known_counterexample"):
                lines.append(f"- 알려진 반례: {tp['known_counterexample']}")
            if tp.get("rival_theories"):
                try:
                    rivals = _json.loads(tp["rival_theories"])
                    lines.append(f"- 경쟁 이론: {', '.join(rivals)}")
                except Exception:
                    pass
        lines.append("")

    # ── Cascade 룰 이론 텍스트 ────────────────────────────────────────────
    cascade_rules = cascade_ctx.get("rules", [])
    if cascade_rules:
        lines.append("## Cascade 인과 룰 (이론 근거)")
        for rule in cascade_rules[:4]:
            lines.append(f"- **{rule['name']}**")
            if rule.get("framework"):
                lines.append(f"  이론: {rule['framework']} ({rule.get('reference', '')})")
            if rule.get("learning"):
                lines.append(f"  해석: {rule['learning']}")
        lines.append("")

    # ── Cascade 발화 실적 ─────────────────────────────────────────────────
    cascade_links = cascade_ctx.get("links", [])
    if cascade_links:
        lines.append("## Cascade 발화 실적 (실제 데이터)")
        for lnk in cascade_links[:5]:
            lines.append(
                f"- {lnk['rule_name']} "
                f"(상관계수 {lnk['correlation_score']}, {lnk.get('depth', 1)}단계)"
            )
        lines.append("")

    # ── 이벤트 통계 ───────────────────────────────────────────────────────
    if event_stats:
        lines.append("## ACLED 이벤트 통계")
        for region, stats in event_stats.items():
            total = stats.get("total_events", "?")
            avg_s = stats.get("avg_severity", "?")
            lines.append(f"- **{region}**: 총 {total}건, 평균 심각도 {avg_s}/100")
            top3 = sorted(stats.get("event_types", {}).items(), key=lambda x: -x[1])[:3]
            if top3:
                lines.append("  유형: " + " / ".join(f"{t}({n}건)" for t, n in top3))
        lines.append("")

    # ── 국가 프로파일 ─────────────────────────────────────────────────────
    if country_profiles:
        lines.append("## 행위자 국가 프로파일")
        for iso3, profile in country_profiles.items():
            posture  = profile.get("strategic_posture", "?")
            position = profile.get("strategic_position", "?")
            inst     = profile.get("instrument_of_power", "?")
            risks    = profile.get("key_risks", [])
            lines.append(f"- **{iso3}**: {position}")
            lines.append(f"  포지션={posture} | 주요수단={inst}")
            if risks:
                lines.append(f"  주요위험: {', '.join(str(r) for r in risks[:3])}")
        lines.append("")

    # ── SIPRI 국방비 (IA-Engine-B1) ───────────────────────────────────────────
    if sipri_data:
        lines.append("## 국방비 추이 (SIPRI 2023, % of GDP / USD billion)")
        for iso3, records in sipri_data.items():
            if not records:
                continue
            latest = records[0]
            name   = latest.get("country", iso3)
            gdp    = latest.get("gdp_pct")
            usd    = latest.get("usd_mn")
            year   = latest.get("year")
            trend  = " → ".join(
                f"{r['year']}:{r['gdp_pct']}%"
                for r in reversed(records) if r.get("gdp_pct")
            )
            usd_bn = f"${usd/1000:.1f}bn" if usd else ""
            lines.append(f"- **{name}** ({iso3}): {year}년 GDP {gdp}% {usd_bn}")
            if len(records) > 1:
                lines.append(f"  5년 추이: {trend}")
        lines.append("  출처: SIPRI Military Expenditure Database 2024")
        lines.append("")

    # ── COW 동맹 관계 (IA-Engine-B1) ─────────────────────────────────────────
    if cow_alliances:
        defense = [a for a in cow_alliances if a.get("alliance_type") == "defense"]
        others  = [a for a in cow_alliances if a.get("alliance_type") != "defense"]
        lines.append("## 공식 동맹 관계 (COW Formal Alliances v4.1)")
        if defense:
            lines.append("**방위조약 (Defense Pact)**")
            for a in defense[:10]:
                end_str = f"~{a['end_year']}" if a.get("end_year") else "~현재"
                lines.append(
                    f"- {a.get('name_a') or a['iso3_a']} ↔ "
                    f"{a.get('name_b') or a['iso3_b']} "
                    f"({a.get('start_year', '?')}{end_str})"
                )
        if others:
            types: dict[str, list[str]] = {}
            for a in others:
                t = a.get("alliance_type", "기타")
                types.setdefault(t, []).append(
                    f"{a.get('name_a') or a['iso3_a']}-{a.get('name_b') or a['iso3_b']}"
                )
            for t, pairs in types.items():
                lines.append(f"**{t}**: {', '.join(pairs[:5])}")
        lines.append("  출처: Correlates of War Formal Alliances v4.1")
        lines.append("")

    # ── Kiel Ukraine Support Tracker (IA-Engine-B1) ───────────────────────────
    if kiel_data:
        lines.append("## 우크라이나 지원 현황 (Kiel Ukraine Support Tracker 2024)")
        lines.append("단위: EUR 십억 (군사/재정/인도적/합계)")
        for d in kiel_data[:8]:
            mil  = d.get("military_eur_bn", 0) or 0
            fin  = d.get("financial_eur_bn", 0) or 0
            hum  = d.get("humanitarian_eur_bn", 0) or 0
            tot  = d.get("total_eur_bn", 0) or 0
            lines.append(
                f"- **{d['donor_name']}**: 군사 {mil:.1f} / 재정 {fin:.1f} / "
                f"인도적 {hum:.1f} / **합계 {tot:.1f}bn€**"
            )
        period = kiel_data[0].get("data_period", "") if kiel_data else ""
        lines.append(f"  기간: {period} | 출처: Kiel Institute Ukraine Support Tracker")
        lines.append("")


    # ── EIA 에너지 통계 (IA-Engine-B2) ──────────────────────────────────────
    if eia_data:
        lines.append("## 에너지 생산·수출 현황 (EIA International Energy Statistics 2023)")
        # 초크포인트 먼저 표시
        chokepoints = {k: v for k, v in eia_data.items() if len(k) > 3}
        producers   = {k: v for k, v in eia_data.items() if len(k) == 3}
        if chokepoints:
            lines.append("**전략 초크포인트 통과량 (백만 배럴/일)**")
            for key, d in chokepoints.items():
                lines.append(f"- {d['country_name']}: {d.get('crude_prod_mbpd', '?')} Mbpd")
        if producers:
            lines.append("**주요 산유국 생산량 / 수출량 (Mbpd)**")
            for iso3, d in producers.items():
                prod = d.get("crude_prod_mbpd", "?")
                exp  = d.get("oil_export_mbpd")
                gas  = d.get("natgas_prod_bcfd")
                row  = f"- **{d.get('country_name', iso3)}** ({iso3}): 원유 {prod}"
                if exp:
                    row += f" / 수출 {exp}"
                if gas:
                    row += f" / 천연가스 {gas} Bcfd"
                lines.append(row)
        lines.append("  출처: EIA International Energy Statistics 2024")
        lines.append("")

    # ── CSIS 사이버 사건 (IA-Engine-B2) ──────────────────────────────────────
    if csis_incidents:
        lines.append("## 주요 사이버 사건 (CSIS Significant Cyber Incidents DB)")
        for inc in csis_incidents[:6]:
            actor = inc.get("actor_group") or inc.get("actor_iso3") or "미귀속"
            victim = inc.get("victim_iso3", "?")
            sector = inc.get("victim_sector", "")
            itype  = inc.get("incident_type", "")
            date   = (inc.get("incident_date") or "")[:7]
            lines.append(
                f"- [{date}] **{inc.get('title', '')}**"
                f" | 행위자: {actor} → 피해: {victim}({sector}) | 유형: {itype}"
            )
            desc = (inc.get("description") or "")[:120]
            if desc:
                lines.append(f"  {desc}")
        lines.append("  출처: CSIS Strategic Technologies Program 2024")
        lines.append("")

    # ── SIPRI 무기 이전 (Cycle 6-A) ──────────────────────────────────────────
    if sipri_arms:
        lines.append("## 무기 공급망 (SIPRI Arms Transfers Database)")
        for arm in sipri_arms[:6]:
            lines.append(
                f"- {arm.get('year')} | {arm.get('supplier')} → {arm.get('recipient')}"
                f" | {arm.get('category', '')} | TIV {arm.get('tiv_mn', '?')}mn"
            )
            if arm.get("notes"):
                lines.append(f"  {arm['notes'][:100]}")
        lines.append("  출처: SIPRI Arms Transfers Database 2020-2024")
        lines.append("")

    # ── V-DEM 민주주의 지수 (Cycle 6-A) ─────────────────────────────────────
    if vdem_data:
        lines.append("## 행위자 체제 유형 (V-Dem Democracy Index v14)")
        for v in vdem_data:
            libdem = f"{v['libdem']:.2f}" if v.get("libdem") is not None else "?"
            corr   = f"{v['corruption']:.2f}" if v.get("corruption") is not None else "?"
            lines.append(
                f"- **{v.get('country')}** ({v.get('iso3')}, {v.get('year')}): "
                f"{v.get('regime_type')} | 자유민주주의 지수: {libdem} | 부패지수: {corr}"
            )
            if v.get("notes"):
                lines.append(f"  {v['notes'][:80]}")
        lines.append("  출처: V-Dem Institute, University of Gothenburg 2024")
        lines.append("")

    # ── COW 전쟁 선례 (Cycle 6-A) ───────────────────────────────────────────
    if cow_wars:
        lines.append("## 관련 전쟁 선례 (COW Inter-State/Intra-State Wars)")
        for w in cow_wars[:5]:
            deaths = f"{w['battle_deaths']:,}" if w.get("battle_deaths") else "미집계"
            lines.append(
                f"- **{w.get('name')}** ({w.get('period')}) | "
                f"{w.get('sides')} | 사망: {deaths} | 결과: {w.get('outcome')}"
            )
        lines.append("  출처: Correlates of War Project v4.0")
        lines.append("")

    # ── 외교부 IFANS 발간자료 (Cycle 6-A) ────────────────────────────────────
    if ifans_pubs:
        lines.append("## 한국 외교부 IFANS 발간자료 (국립외교원 학술 분석)")
        for pub in ifans_pubs[:4]:
            date = str(pub.get("date", ""))
            date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
            lines.append(f"- [{date_fmt}] **{pub.get('title', '')}**")
            abstract = (pub.get("abstract") or "")[:300]
            if abstract:
                lines.append(f"  {abstract}")
            lines.append(f"  출처: {pub.get('source', '외교부 IFANS')}")
        lines.append("")

    # ── FRED 경제 시계열 (Cycle 7-D-1) ───────────────────────────────────────
    if fred_data:
        lines.append("## 주요 경제 지표 시계열 (FRED — Federal Reserve Economic Data)")
        by_series: dict[str, list] = {}
        for d in fred_data:
            sid = d.get("series_id", "?")
            by_series.setdefault(sid, []).append(d)
        for sid, records in list(by_series.items())[:6]:
            name = records[0].get("series_name", sid)
            unit = records[0].get("unit", "")
            trend = " → ".join(
                f"{r['date'][:4]}:{r['value']}" for r in reversed(records) if r.get("value") is not None
            )
            lines.append(f"- **{name}** ({sid}): {trend} [{unit}]")
        lines.append("  출처: FRED St. Louis Federal Reserve (fred.stlouisfed.org)")
        lines.append("")

    # ── World Bank WGI 거버넌스 지수 (Cycle 7-D-2) ──────────────────────────
    if wbk_data:
        lines.append("## 국가 거버넌스 지수 (World Bank WGI 2022)")
        lines.append("점수 범위: -2.5(최하) ~ +2.5(최상)")
        for d in wbk_data[:8]:
            pv = f"{d['political_stability']:.2f}" if d.get("political_stability") is not None else "?"
            cc = f"{d['corruption_control']:.2f}" if d.get("corruption_control") is not None else "?"
            rl = f"{d['rule_of_law']:.2f}" if d.get("rule_of_law") is not None else "?"
            lines.append(
                f"- **{d['country']}** ({d['iso3']}): "
                f"정치안정={pv} | 부패통제={cc} | 법치={rl}"
            )
        lines.append("  출처: World Bank Worldwide Governance Indicators 2023")
        lines.append("")

    # ── Polity5 정치체제 지수 (Cycle 7-D-4) ─────────────────────────────────
    if polity5_data:
        lines.append("## 정치체제 지수 (Polity5 2022)")
        lines.append("점수: -10(완전권위) ~ +10(완전민주)")
        for d in polity5_data[:8]:
            score = d.get("polity_score")
            regime = d.get("regime_type", "?")
            lines.append(
                f"- **{d['country']}** ({d['iso3']}): {score}점 ({regime})"
            )
        lines.append("  출처: Center for Systemic Peace, Polity5 Dataset")
        lines.append("")

    # ── ITU ICT 개발 지수 (Cycle 7-D-5) ─────────────────────────────────────
    if itu_data:
        lines.append("## 사이버 역량 지수 (ITU ICT Development Index 2023)")
        lines.append("IDI 점수: 0-100 (인프라·이용·역량 종합)")
        for d in itu_data[:8]:
            score = d.get("idi_score")
            rank = d.get("rank")
            tier = d.get("tier", "?")
            lines.append(
                f"- **{d['country']}** ({d['iso3']}): IDI {score} (전세계 {rank}위, {tier}티어)"
            )
        lines.append("  출처: ITU ICT Development Index 2023")
        lines.append("")

    # ── HIIK 분쟁 강도 바로미터 (Cycle 7-D-6) ──────────────────────────────
    if hiik_data:
        lines.append("## 분쟁 강도 바로미터 (HIIK Conflict Barometer 2024)")
        lines.append("강도: 1=분쟁 / 2=비폭력위기 / 3=폭력위기 / 4=제한전 / 5=전쟁")
        for d in hiik_data[:6]:
            lines.append(
                f"- **{d['name']}** ({d['year']}): 강도 {d['intensity']} [{d['label']}]"
                f" | 행위자: {d.get('actors', '?')}"
            )
        lines.append("  출처: HIIK Heidelberg Institute for International Conflict Research")
        lines.append("")

    # ── 반도체·기술 시장 데이터 (Cycle 7-D-7) ────────────────────────────────
    if semi_data:
        lines.append("## 반도체·기술 시장 데이터 (SIA/TechInsights 2023-2024)")
        # 카테고리별 그룹핑
        by_cat: dict[str, list] = {}
        for d in semi_data:
            by_cat.setdefault(d.get("category", "misc"), []).append(d)
        for cat, items in list(by_cat.items())[:4]:
            lines.append(f"**{cat}**")
            for d in items[:4]:
                val_str = f"{d['value']}" if d.get("value") is not None else "?"
                unit_str = d.get("unit", "")
                lines.append(f"  - {d['metric']}: {val_str} {unit_str} ({d.get('year', '?')})")
                if d.get("notes"):
                    lines.append(f"    {d['notes'][:100]}")
        lines.append("  출처: SIA, TechInsights, USGS, ASML Annual Report")
        lines.append("")

    # ── OWID 군사비·핵탄두 (Cycle 7-D-3) ──────────────────────────────────────
    if owid_data:
        milex = [d for d in owid_data if d.get("dataset") == "military_exp_gdp"]
        nukes = [d for d in owid_data if d.get("dataset") == "nuclear_warheads"]
        lines.append("## 군사력 비교 (Our World in Data, SIPRI/FAS 원천)")
        if milex:
            lines.append("**국방비 (% of GDP, 최신연도)**")
            for d in sorted(milex, key=lambda x: -(x.get("value") or 0))[:8]:
                v = f"{d['value']:.2f}" if d.get("value") is not None else "?"
                lines.append(f"- {d['country']} ({d['iso3']}): {v}% ({d.get('year')})")
        if nukes:
            lines.append("**핵탄두 보유량 (최신연도)**")
            for d in sorted(nukes, key=lambda x: -(x.get("value") or 0))[:6]:
                v = int(d['value']) if d.get("value") is not None else "?"
                lines.append(f"- {d['country']} ({d['iso3']}): {v}기 ({d.get('year')})")
        lines.append("  출처: Our World in Data (ourworldindata.org)")
        lines.append("")

    return "\n".join(lines)


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

async def build_intel_context(pq: ParsedQuery) -> dict:
    loop = asyncio.get_event_loop()

    results = await asyncio.gather(
        loop.run_in_executor(None, _search_library_like,
                             pq.raw_query, pq.regions, pq.sectors),
        loop.run_in_executor(None, _search_library_by_sector, pq.sectors),
        loop.run_in_executor(None, _get_event_stats, pq.regions),
        loop.run_in_executor(None, _get_cascade_context, pq.regions),
        loop.run_in_executor(None, _get_country_profiles, pq.actors),
        loop.run_in_executor(None, _get_sipri_data, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_cow_alliances, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_kiel_data, pq.regions),
        loop.run_in_executor(None, _get_eia_data, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_csis_incidents, pq.actors, pq.regions, pq.sectors),
        # Cycle 6-A 신규 소스
        # Arms: techno/cyber 섹터 전용 쿼리에는 미주입 (무관한 주장 유발 방지)
        loop.run_in_executor(None, _get_sipri_arms,
                             pq.actors if not {"techno","cyber"}.issubset(set(pq.sectors or [])) and
                             not all(s in {"techno","cyber"} for s in (pq.sectors or [])) else [],
                             pq.regions),
        loop.run_in_executor(None, _get_vdem, pq.actors),
        loop.run_in_executor(None, _get_cow_wars, pq.regions, pq.actors),
        loop.run_in_executor(None, _get_ifans_publications, pq.actors, pq.regions),
        # Cycle 7-B: 경쟁 이론 비교 프로파일 (예측값 vs 실측값)
        loop.run_in_executor(None, build_theory_comparison_context,
                             pq.sectors, pq.regions, pq.actors),
        # Cycle 7-D: 신규 소스 6개
        loop.run_in_executor(None, _get_fred_data, pq.regions, pq.sectors),
        loop.run_in_executor(None, _get_world_bank_wgi, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_polity5, pq.actors),
        loop.run_in_executor(None, _get_itu_ict, pq.actors, pq.sectors),
        loop.run_in_executor(None, _get_hiik_conflict, pq.regions),
        loop.run_in_executor(None, _get_semi_market, pq.sectors, pq.regions),
        loop.run_in_executor(None, _get_owid_data, pq.actors, pq.regions, pq.sectors),
        return_exceptions=True,
    )

    def _safe(r, default):
        return r if not isinstance(r, Exception) else default

    like_items        = _safe(results[0], [])
    sector_items      = _safe(results[1], [])
    event_stats       = _safe(results[2], {})
    cascade_ctx       = _safe(results[3], {"links": [], "rules": []})
    country_profiles  = _safe(results[4], {})
    sipri_data        = _safe(results[5], {})
    cow_alliances     = _safe(results[6], [])
    kiel_data         = _safe(results[7], [])
    eia_data          = _safe(results[8], {})
    csis_incidents    = _safe(results[9], [])
    sipri_arms        = _safe(results[10], [])
    vdem_data         = _safe(results[11], [])
    cow_wars          = _safe(results[12], [])
    ifans_pubs        = _safe(results[13], [])
    theory_cmp_ctx    = _safe(results[14], "")
    fred_data         = _safe(results[15], [])
    wbk_data          = _safe(results[16], [])
    polity5_data      = _safe(results[17], [])
    itu_data          = _safe(results[18], [])
    hiik_data         = _safe(results[19], [])
    semi_data         = _safe(results[20], [])
    owid_data         = _safe(results[21], [])

    context_text = _build_context(
        pq, like_items, sector_items, event_stats, cascade_ctx, country_profiles,
        sipri_data, cow_alliances, kiel_data, eia_data, csis_incidents,
        sipri_arms, vdem_data, cow_wars, ifans_pubs,
        fred_data, wbk_data, polity5_data, itu_data, hiik_data, semi_data,
        owid_data,
    )
    # Cycle 7-B: 경쟁 이론 비교 컨텍스트 추가 (공백 없으면 스킵)
    if theory_cmp_ctx:
        context_text = context_text + "\n\n" + theory_cmp_ctx

    logger.debug(
        "[intel] 컨텍스트 조립 — LIKE=%d sector=%d SIPRI=%d COW=%d Kiel=%d "
        "EIA=%d CSIS=%d Arms=%d VDEM=%d Wars=%d IFANS=%d Theory=%d "
        "FRED=%d WBK=%d P5=%d ITU=%d HIIK=%d SEMI=%d 총%d자",
        len(like_items), len(sector_items),
        len(sipri_data), len(cow_alliances), len(kiel_data),
        len(eia_data), len(csis_incidents),
        len(sipri_arms), len(vdem_data), len(cow_wars), len(ifans_pubs),
        len(theory_cmp_ctx),
        len(fred_data), len(wbk_data), len(polity5_data),
        len(itu_data), len(hiik_data), len(semi_data),
        len(context_text),
    )

    return {
        "context_text": context_text,
        "source_counts": {
            "fts_items":           len(like_items),
            "sector_items":        len(sector_items),
            "event_stats_regions": len(event_stats),
            "cascade_links":       len(cascade_ctx.get("links", [])),
            "country_profiles":    len(country_profiles),
            "sipri_countries":     len(sipri_data),
            "cow_alliances":       len(cow_alliances),
            "kiel_donors":         len(kiel_data),
            "eia_entries":         len(eia_data),
            "csis_incidents":      len(csis_incidents),
            "sipri_arms":          len(sipri_arms),
            "vdem_entries":        len(vdem_data),
            "cow_wars":            len(cow_wars),
            "ifans_pubs":          len(ifans_pubs),
            "theory_cmp_chars":    len(theory_cmp_ctx),
            # Cycle 7-D 신규 정형 수치 소스 (L1-c — data_void_penalty 보정용)
            "fred":                len(fred_data),
            "wbk":                 len(wbk_data),
            "polity5":             len(polity5_data),
            "itu":                 len(itu_data),
            "hiik":                len(hiik_data),
            "semi":                len(semi_data),
            "owid":                len(owid_data),
        },
        "like_items":        like_items,
        "sector_items":      sector_items,
        "event_stats":       event_stats,
        "cascade_ctx":       cascade_ctx,
        "country_profiles":  country_profiles,
        "sipri_data":        sipri_data,
        "cow_alliances":     cow_alliances,
        "kiel_data":         kiel_data,
        "eia_data":          eia_data,
        "csis_incidents":    csis_incidents,
        "sipri_arms":        sipri_arms,
        "vdem_data":         vdem_data,
        "cow_wars":          cow_wars,
        "ifans_pubs":        ifans_pubs,
    }
