"""
외교부 LOD (Linked Open Data) SPARQL 커넥터

엔드포인트: https://opendata.mofa.go.kr/lod/sparql
온톨로지:   https://opendata.mofa.go.kr/lod/ontologyModel.do

데이터셋:
  - mofapub:  IFANS(국립외교원) 발간자료 4,174건 — 한반도·동아시아 한국 시각 학술 분석
  - mofabrief: 외교부 대변인 브리핑 191건 (2022~2023)

쿼리 경로 2종:
  경로 1 — ISO2 국가코드 → 해당 국가 관련 발간자료
  경로 2 — DBpedia 이벤트 URI → 관련 발간자료 (owl:sameAs 브릿지)
            예: dbpedia:Houthi_insurgency → 후티 반란 관련 IFANS 발간자료
"""

import logging
from functools import lru_cache
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

_SPARQL_URL = "https://opendata.mofa.go.kr/lod/sparql"

# region_code → DBpedia 이벤트 URI 매핑 (SPARQL 경로 2용)
# owl:sameAs 검증 완료 (2026-06-05)
_REGION_DBPEDIA_EVENTS: dict[str, list[str]] = {
    "hormuz": [
        "http://dbpedia.org/resource/Abqaiq%E2%80%93Khurais_attack",
        "http://dbpedia.org/resource/Houthi_insurgency",
    ],
    "eastern_europe": [
        "http://dbpedia.org/resource/2022_Russian_invasion_of_Ukraine",
    ],
    "korean_peninsula": [
        "http://dbpedia.org/resource/Korean_War",
        "http://dbpedia.org/resource/Blue_House_raid",
    ],
    "bab_el_mandeb": [
        "http://dbpedia.org/resource/Houthi_insurgency",
    ],
    "middle_east": [
        "http://dbpedia.org/resource/Houthi_insurgency",
        "http://dbpedia.org/resource/Iran%E2%80%93Contra_affair",
    ],
    "taiwan_strait": [],  # DBpedia 이벤트 매핑 없음 — 경로 1(ISO2)만 사용
    "sahel": [],
    "arctic": [],
}

# actor ISO2 → ISO3 매핑 (mofapub relatedCountry는 ISO2 URI 사용)
_ISO2_TO_ISO3: dict[str, str] = {
    "USA": "US", "RUS": "RU", "CHN": "CN", "PRK": "KP", "KOR": "KR",
    "JPN": "JP", "IRN": "IR", "IRQ": "IQ", "ISR": "IL", "SAU": "SA",
    "UKR": "UA", "GBR": "GB", "DEU": "DE", "FRA": "FR", "IND": "IN",
    "PAK": "PK", "TUR": "TR", "EGY": "EG", "ARE": "AE", "QAT": "QA",
}


def _sparql_query(query: str, timeout: float = 10.0) -> list[dict]:
    """SPARQL 쿼리 실행 → bindings 반환."""
    try:
        params = urlencode({"query": query, "format": "json"})
        url = f"{_SPARQL_URL}?{params}"
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("bindings", [])
    except Exception as e:
        logger.warning("[mofa_lod] SPARQL 실패: %s", e)
        return []


def _val(binding: dict, key: str, default: str = "") -> str:
    v = binding.get(key, {}).get("value", default)
    # xsd:integer 타입 리터럴 정리: "20231026"^^xsd:integer → "20231026"
    if v and "^^" in v:
        v = v.split("^^")[0].strip('"')
    return v


# ── 경로 1: ISO2 국가코드 기반 발간자료 조회 ─────────────────────────────────

def _pub_by_iso2(iso2: str, limit: int = 5) -> list[dict]:
    """특정 국가(ISO2) 관련 IFANS 발간자료 조회."""
    country_uri = f"http://opendata.mofa.go.kr/core/resource/Country/{iso2}"
    query = f"""
SELECT ?label ?date ?abstract WHERE {{
  ?s a <http://opendata.mofa.go.kr/mofapub/Publication> .
  ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
  ?s <http://opendata.mofa.go.kr/mofapub/pubDate> ?date .
  ?s <http://purl.org/ontology/bibo/abstract> ?abstract .
  ?s <http://opendata.mofa.go.kr/mofadocu/relatedCountry> <{country_uri}> .
}} ORDER BY DESC(?date) LIMIT {limit}
"""
    rows = _sparql_query(query)
    return [
        {
            "title":    _val(r, "label"),
            "date":     _val(r, "date"),
            "abstract": _val(r, "abstract")[:800],
            "source":   f"외교부 IFANS 발간자료 (relatedCountry={iso2})",
        }
        for r in rows
    ]


# ── 경로 2: DBpedia 이벤트 URI 기반 발간자료 조회 ────────────────────────────

def _pub_by_dbpedia_event(dbpedia_uri: str, limit: int = 3) -> list[dict]:
    """DBpedia 이벤트 URI → owl:sameAs → relatedEvent → 발간자료."""
    query = f"""
SELECT ?label ?date ?abstract WHERE {{
  ?event <http://www.w3.org/2002/07/owl#sameAs> <{dbpedia_uri}> .
  ?s <http://opendata.mofa.go.kr/core/relatedEvent> ?event .
  ?s a <http://opendata.mofa.go.kr/mofapub/Publication> .
  ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
  ?s <http://opendata.mofa.go.kr/mofapub/pubDate> ?date .
  ?s <http://purl.org/ontology/bibo/abstract> ?abstract .
}} ORDER BY DESC(?date) LIMIT {limit}
"""
    rows = _sparql_query(query)
    event_name = dbpedia_uri.split("/")[-1].replace("%E2%80%93", "-")
    return [
        {
            "title":    _val(r, "label"),
            "date":     _val(r, "date"),
            "abstract": _val(r, "abstract")[:800],
            "source":   f"외교부 IFANS 발간자료 (이벤트={event_name})",
        }
        for r in rows
    ]


# ── 공개 인터페이스 ─────────────────────────────────────────────────────────

def fetch_ifans_publications(
    actors: list[str],
    regions: list[str],
    limit_per_source: int = 3,
) -> list[dict]:
    """
    intel_analyzer용 IFANS 발간자료 조회.
    경로 1(ISO2)과 경로 2(DBpedia 이벤트) 결과를 합산, 중복 제거.
    """
    results: list[dict] = []
    seen_titles: set[str] = set()

    # 경로 2 — region → DBpedia 이벤트 URI
    for region in regions:
        for dbpedia_uri in _REGION_DBPEDIA_EVENTS.get(region, []):
            for pub in _pub_by_dbpedia_event(dbpedia_uri, limit=limit_per_source):
                if pub["title"] not in seen_titles:
                    seen_titles.add(pub["title"])
                    results.append(pub)

    # 경로 1 — actor ISO3 → ISO2 → Country URI
    for iso3 in actors:
        iso2 = _ISO2_TO_ISO3.get(iso3)
        if not iso2:
            continue
        for pub in _pub_by_iso2(iso2, limit=limit_per_source):
            if pub["title"] not in seen_titles:
                seen_titles.add(pub["title"])
                results.append(pub)

    logger.debug("[mofa_lod] IFANS 발간자료 %d건 조회 (actors=%s regions=%s)",
                 len(results), actors, regions)
    return results[:10]  # 최대 10건으로 제한
