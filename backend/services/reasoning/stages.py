"""
8단계 추론 프로세서.

각 stage_N 함수는 Event와 부가 컨텍스트를 받아
해당 단계의 분석 결과 dict를 반환한다.
실패 시 {"error": "..."} 포함 — 엔진이 partial report로 처리.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from services.region import region_for_point

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parents[2] / "config"

# ── 공통: Actor 문자열 → ISO3 변환 ─────────────────────────────────────────
# Stage 5·8 공통 사용. ACLED 패턴 예: "Military Forces of Russia (2000-)"
_ACTOR_NAME_TO_CODE: dict[str, str] = {
    "usa": "USA", "united states": "USA", "the united states": "USA",
    "united states of america": "USA",
    "russia": "RUS", "russian federation": "RUS",
    "china": "CHN", "people's republic of china": "CHN", "prc": "CHN",
    "japan": "JPN", "south korea": "KOR", "republic of korea": "KOR",
    "north korea": "PRK", "dprk": "PRK", "democratic people's republic of korea": "PRK",
    "taiwan": "TWN",
    "iran": "IRN", "islamic republic of iran": "IRN",
    "israel": "ISR", "state of israel": "ISR",
    "saudi arabia": "SAU", "ksa": "SAU",
    "yemen": "YEM", "houthi": "YEM",
    "iraq": "IRQ", "syria": "SYR", "lebanon": "LBN",
    "turkey": "TUR", "turkiye": "TUR",
    "uae": "ARE", "united arab emirates": "ARE",
    "qatar": "QAT", "kuwait": "KWT", "bahrain": "BHR", "oman": "OMN",
    "ukraine": "UKR", "uk": "GBR", "united kingdom": "GBR", "britain": "GBR",
    "france": "FRA", "germany": "DEU", "poland": "POL",
    "nato": "USA",
    "india": "IND", "australia": "AUS",
    "philippines": "PHL", "the philippines": "PHL",
    "indonesia": "IDN", "malaysia": "MYS", "vietnam": "VNM",
    "singapore": "SGP", "thailand": "THA",
    "ethiopia": "ETH", "somalia": "SOM", "sudan": "SDN",
    "libya": "LBY", "mali": "MLI", "niger": "NER",
    "nigeria": "NGA", "kenya": "KEN",
    "armenia": "ARM", "azerbaijan": "AZE", "georgia": "GEO",
}
_OF_PAT    = re.compile(r'(?:Military|Police|Government|Naval|Air)\s+Forces?\s+of\s+([A-Za-z ]+?)(?:\s*\(|$)', re.I)
_GOV_PAT   = re.compile(r'Government\s+of\s+([A-Za-z ]+?)(?:\s*\(|$)', re.I)
_PAREN_PAT = re.compile(r'\(([A-Za-z ]+?)\)\s*$')


def _actor_to_iso3(actor: str) -> str | None:
    """ACLED actor 문자열 → ISO3 코드. Stage 5·8 공통 사용."""
    s = actor.strip()
    # 직접 ISO3
    if len(s) == 3 and s.isupper():
        return s if s in _ACTOR_NAME_TO_CODE.values() else None
    # "Forces of [Country]" / "Government of [Country]"
    for pat in (_OF_PAT, _GOV_PAT):
        m = pat.search(s)
        if m:
            code = _ACTOR_NAME_TO_CODE.get(m.group(1).strip().lower())
            if code:
                return code
    # 끝 괄호 "Protesters (Yemen)"
    m = _PAREN_PAT.search(s)
    if m:
        code = _ACTOR_NAME_TO_CODE.get(m.group(1).strip().lower())
        if code:
            return code
    # 전체 문자열 직접 매핑
    return _ACTOR_NAME_TO_CODE.get(s.lower())
_INTEL_DB = Path(__file__).resolve().parents[2] / "db" / "intel.db"
_LIBRARY_DB = Path(__file__).resolve().parents[2] / "db" / "library.db"
_CASE_STUDIES_PATH  = _CONFIG / "case_studies.yaml"
_ALLIANCE_GRAPH_PATH = _CONFIG / "alliance_graph.yaml"
_THEORY_LIBRARY_PATH = _CONFIG / "theory_library.yaml"
_SANCTIONS_PATH     = _CONFIG / "sanctions.yaml"

# ── YAML 로더 (파일당 한 번만 파싱) ──────────────────────────────────────

def _load_yaml(path: Path) -> dict | list:
    """YAML 파일 로드. 파싱 실패 시 빈 dict 반환."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("[reasoning] YAML 로드 실패 %s: %s", path.name, e)
        return {}


# ── 로컬 DB 헬퍼 ─────────────────────────────────────────────────────────

# 섹터·지역 → FRED 지표명 매핑 (yfinance 티커 대체)
_SECTOR_INDICATORS: dict[str, list[str]] = {
    "energy":       ["wti", "brent"],
    "maritime":     ["wti", "brent"],
    "techno":       ["usd_twd"],
    "indo_pacific": ["usd_twd", "usd_krw"],
    "gray_zone":    ["vix"],  # gold은 yfinance fallback
}
_REGION_INDICATORS: dict[str, list[str]] = {
    "hormuz":           ["wti", "brent"],
    "taiwan_strait":    ["usd_twd", "usd_krw"],
    "ukraine":          ["wti", "brent"],
    "red_sea":          ["wti", "brent"],
    "south_china_sea":  ["usd_twd"],
    "korean_peninsula": ["usd_krw"],
}
_INDICATOR_LABEL: dict[str, str] = {
    "wti":     "WTI 원유 (달러/배럴)",
    "brent":   "브렌트유 (달러/배럴)",
    "usd_krw": "원달러 환율 (KRW/USD)",
    "usd_twd": "대만달러 환율 (TWD/USD)",
    "vix":     "VIX 변동성 지수",
    "gold":    "금 현물 (달러/온스)",  # yfinance fallback
}

# HS 코드 레이블 (Stage 8 무역 의존도 표시용)
_HS_LABEL: dict[str, str] = {
    "27":   "에너지(HS27)",
    "8542": "반도체(HS8542)",
    "26":   "희토류(HS26)",
}


def _query_macro_indicators(indicators: set[str]) -> list[dict]:
    """historical_macro_indices에서 최신 2건을 조회해 변화율을 반환한다."""
    if not _INTEL_DB.exists():
        return []
    results = []
    try:
        with sqlite3.connect(_INTEL_DB) as con:
            for indicator in sorted(indicators):
                rows = con.execute(
                    """
                    SELECT indicator, date, value FROM historical_macro_indices
                    WHERE indicator = ?
                    ORDER BY date DESC LIMIT 2
                    """,
                    (indicator,),
                ).fetchall()
                if not rows:
                    continue
                latest = rows[0][2]
                prev = rows[1][2] if len(rows) >= 2 else latest
                pct = (latest - prev) / prev * 100 if prev else 0.0
                results.append({
                    "indicator": indicator,
                    "label":     _INDICATOR_LABEL.get(indicator, indicator),
                    "date":      rows[0][1],
                    "value":     round(latest, 4),
                    "change_pct": round(pct, 2),
                    "direction": "up" if pct > 0.01 else ("down" if pct < -0.01 else "flat"),
                    "source": "FRED",
                })
    except Exception as e:
        logger.warning("[stage4] 로컬 DB 조회 오류: %s", e)
    return results


def _query_trade_dependency(actor_codes: set[str]) -> list[dict]:
    """historical_trade_matrix에서 actor 간 무역 의존도를 조회한다.

    Farrell & Newman Weaponized Interdependence 이론 계량화:
    dependency_ratio = 양자 무역액 / 보고국 세계 전체 무역액
    """
    if not _INTEL_DB.exists() or not actor_codes:
        return []
    results = []
    codes = sorted(actor_codes)
    try:
        with sqlite3.connect(_INTEL_DB) as con:
            for reporter in codes:
                for partner in codes:
                    if reporter == partner:
                        continue
                    rows = con.execute(
                        """
                        SELECT hs_code, trade_flow, trade_value_usd,
                               dependency_ratio, period
                        FROM historical_trade_matrix
                        WHERE reporter_iso = ? AND partner_iso = ?
                          AND dependency_ratio IS NOT NULL
                          AND partner_iso NOT IN ('WLD','0','WORLD')
                        ORDER BY period DESC, hs_code
                        LIMIT 9
                        """,
                        (reporter, partner),
                    ).fetchall()
                    if not rows:
                        continue
                    results.append({
                        "reporter": reporter,
                        "partner":  partner,
                        "items": [
                            {
                                "hs_code":   r[0],
                                "hs_label":  _HS_LABEL.get(r[0], r[0]),
                                "flow":      "수입" if r[1] == "M" else "수출",
                                "value_usd": r[2],
                                "dependency_ratio": round(r[3], 4),
                                "period":    r[4],
                            }
                            for r in rows
                        ],
                    })
    except Exception as e:
        logger.warning("[stage8] 무역 의존도 조회 오류: %s", e)
    return results


# ── Stage 1: 사건 팩트 ───────────────────────────────────────────────────

def stage1_event_facts(event: dict) -> dict:
    """이벤트 원본 데이터에서 핵심 팩트를 추출한다."""
    props = event.get("properties", event)  # GeoJSON feature 또는 raw dict
    payload = props.get("payload", {}) or {}

    # ACLED: payload 내 actor1/actor2, GDELT: properties 최상위 actor1/actor2
    actor1 = (
        props.get("actor1") or props.get("actor1_ko")
        or payload.get("actor1") or payload.get("Actor1Name", "")
    )
    actor2 = (
        props.get("actor2") or props.get("actor2_ko")
        or payload.get("actor2") or payload.get("Actor2Name", "")
    )

    # region_code가 없으면 좌표 기반 geofence 역조회 (대부분의 ACLED 이벤트가 해당)
    region_code = props.get("region_code", "") or ""
    if not region_code:
        coords = event.get("geometry", {}).get("coordinates", [])
        if len(coords) >= 2:
            # GeoJSON은 [lon, lat] 순서
            derived = region_for_point(float(coords[1]), float(coords[0]))
            region_code = derived or ""

    return {
        "stage": 1,
        "name_ko": "사건 팩트",
        "event_id": props.get("id", ""),
        "title": props.get("title", ""),
        "timestamp": props.get("timestamp", ""),
        "location": event.get("geometry", {}).get("coordinates", []),
        "source_type": props.get("source_type", ""),
        "region_code": region_code,
        "severity": props.get("severity", 0),
        "importance_score": props.get("importance_score", 0.0),
        "confidence_score": props.get("confidence_score", 1.0),
        "actors": [a for a in [actor1, actor2] if a],
        "fatalities": payload.get("fatalities", 0),
        "source_url": props.get("source_url", ""),
        "description": props.get("description", ""),
    }


# ── Stage 2: 섹터 분류 ───────────────────────────────────────────────────

def stage2_sector_classification(event: dict) -> dict:
    """theory_library.yaml의 sector_tag 기준으로 섹터를 분류한다."""
    props = event.get("properties", event)
    theory_tags = props.get("theory_tags", [])
    payload = props.get("payload", {}) or {}

    raw = _load_yaml(_THEORY_LIBRARY_PATH)
    # theory_library.yaml은 리스트 형태
    items: list[dict] = raw if isinstance(raw, list) else raw.get("items", [])

    matched_theories = []
    for item in items:
        # sector_tag (단수) 또는 sector_tags (복수) 모두 지원
        tags = item.get("sector_tags") or ([item["sector_tag"]] if item.get("sector_tag") else [])
        if any(t in tags for t in theory_tags):
            matched_theories.append({
                "name": item.get("theory_id", item.get("display_name", "")),
                "name_ko": item.get("display_name", ""),
                "sector": item.get("sector_tag", ""),
                "one_liner": item.get("one_liner_ko", ""),
            })

    # 직접 섹터 추론 (theory_tags 없을 경우 키워드 기반)
    inferred_sectors: list[str] = []
    title_lower = (props.get("title", "") + props.get("description", "")).lower()
    sector_keywords = {
        "maritime": ["ship", "vessel", "naval", "maritime", "strait", "sea", "port"],
        "energy": ["oil", "gas", "pipeline", "energy", "fuel", "lng"],
        "techno": ["cyber", "semiconductor", "chip", "5g", "satellite", "drone"],
        "indo_pacific": ["taiwan", "south china sea", "korea", "japan", "pla", "indo-pacific"],
        "gray_zone": ["hybrid", "sanction", "covert", "irregular", "militia", "proxy"],
    }
    for sector, kws in sector_keywords.items():
        if any(kw in title_lower for kw in kws):
            inferred_sectors.append(sector)

    return {
        "stage": 2,
        "name_ko": "섹터 분류",
        "explicit_tags": theory_tags,
        "matched_theories": matched_theories[:3],
        "inferred_sectors": inferred_sectors,
        "primary_sector": theory_tags[0] if theory_tags else (inferred_sectors[0] if inferred_sectors else "unknown"),
    }


# ── Stage 3: 역사적 비교 ─────────────────────────────────────────────────

def stage3_historical_comparison(event: dict, sectors: list[str]) -> dict:
    """case_studies.yaml에서 현재 이벤트와 유사한 역사 사례를 찾는다."""
    props = event.get("properties", event)
    title_desc = (props.get("title", "") + " " + props.get("description", "")).lower()

    # theory_tags도 섹터 매칭에 활용 (GDELT는 sector 대신 theory_tags 사용)
    theory_tags = props.get("theory_tags", [])
    all_tags = set(sectors) | set(theory_tags)

    # theory_tag → sector 변환 맵 (GDELT theory_tags → case_studies sector_tags)
    _TAG_TO_SECTOR = {
        "conventional_warfare": ["indo_pacific", "gray_zone", "maritime"],
        "resource_weaponization": ["energy", "maritime"],
        "weaponized_interdependence": ["techno", "energy"],
        "gray_zone": ["gray_zone"],
        "hybrid_warfare": ["gray_zone"],
        "a2ad": ["indo_pacific"],
        "maritime_strategy": ["maritime"],
    }
    expanded_sectors: set[str] = set(sectors)
    for tag in all_tags:
        expanded_sectors.update(_TAG_TO_SECTOR.get(tag, []))

    data = _load_yaml(_CASE_STUDIES_PATH)
    cases = data.get("cases", [])

    scored: list[tuple[int, dict]] = []
    for case in cases:
        score = 0
        # 섹터 태그 매칭 (확장 섹터 포함)
        for tag in case.get("sector_tags", []):
            if tag in expanded_sectors:
                score += 3

        # 키워드 매칭
        for kw in case.get("trigger_keywords", []):
            if kw.lower() in title_desc:
                score += 2

        # 지역 매칭
        region = props.get("region_code", "")
        if region and case.get("region") == region:
            score += 2

        if score > 0:
            scored.append((score, case))

    # 점수 내림차순, 최대 3개
    scored.sort(key=lambda x: x[0], reverse=True)
    top3 = [
        {
            "id": c["id"],
            "title_ko": c["title_ko"],
            "date": c["date"],
            "region": c.get("region", ""),
            "outcome_summary_ko": c["outcome_summary_ko"].strip(),
            "lessons_ko": c.get("lessons_ko", ""),
            "theory_ref": c.get("theory_ref", ""),
            "match_score": s,
        }
        for s, c in scored[:3]
    ]

    # ── 브리핑 FTS 검색 (library.db) ─────────────────────────────────────
    briefing_refs: list[dict] = []
    if _LIBRARY_DB.exists():
        try:
            con = sqlite3.connect(_LIBRARY_DB)
            # 이벤트 title+description에서 핵심 토큰 추출 (FTS5 쿼리)
            tokens = [t for t in title_desc.split() if len(t) >= 3][:6]
            if tokens:
                fts_query = " OR ".join(tokens)
                rows = con.execute(
                    """
                    SELECT t.theory_id, t.title, t.summary,
                           t.source_org, t.published_date, t.source_url,
                           t.geopol_region, t.sector_tag
                    FROM theories t
                    JOIN theories_fts f ON t.rowid = f.rowid
                    WHERE theories_fts MATCH ?
                      AND t.use_case = 'briefing'
                    ORDER BY rank
                    LIMIT 3
                    """,
                    (fts_query,),
                ).fetchall()
                for row in rows:
                    briefing_refs.append({
                        "theory_id":     row[0],
                        "title":         row[1],
                        "summary":       row[2],
                        "source_org":    row[3],
                        "published_date":row[4],
                        "source_url":    row[5] or "",
                        "geopol_region": row[6],
                        "sector_tag":    row[7],
                    })
            con.close()
        except Exception as exc:
            logger.warning("[stage3] briefing FTS 실패: %s", exc)

    return {
        "stage": 3,
        "name_ko": "역사적 비교",
        "analogues": top3,
        "total_candidates": len(scored),
        "briefing_refs": briefing_refs,
    }


# ── Stage 4: 거시 변수 ───────────────────────────────────────────────────

async def stage4_macro_variables(sectors: list[str], region: str) -> dict:
    """FRED 베이스라인 DB에서 거시 지표를 조회한다.

    DB 미적재 시 yfinance 실시간 호출로 fallback.
    baseline_bulk_ingest.py --fred 로 사전 적재 필요.
    """
    indicators: set[str] = set()
    for s in sectors:
        indicators.update(_SECTOR_INDICATORS.get(s, []))
    indicators.update(_REGION_INDICATORS.get(region, []))
    if not indicators:
        indicators = {"wti", "gold"}

    # 1순위: 로컬 FRED DB 쿼리
    results = _query_macro_indicators(indicators)
    if results:
        return {
            "stage": 4,
            "name_ko": "거시 변수",
            "indicators": results,
            "source": "FRED 베이스라인 DB",
            "note_ko": "FRED 베이스라인 기준 전일 대비 변화율.",
        }

    # fallback: yfinance (DB 미적재 상태)
    _INDICATOR_TO_TICKER = {
        "wti": "CL=F", "gold": "GLD", "vix": "^VIX",
        "usd_krw": "KRW=X", "usd_twd": "TWD=X",
    }
    tickers = {_INDICATOR_TO_TICKER[i] for i in indicators if i in _INDICATOR_TO_TICKER}
    if not tickers:
        return {"stage": 4, "name_ko": "거시 변수", "indicators": [], "note_ko": "FRED DB 미적재. baseline_bulk_ingest.py --fred 실행 필요."}

    fallback_results = []
    try:
        import yfinance as yf
        tickers_str = " ".join(tickers)
        data = yf.download(tickers_str, period="5d", progress=False, auto_adjust=True)
        close = data["Close"] if hasattr(data.columns, "levels") or "Close" in data.columns else data
        for ticker in tickers:
            try:
                series = close[ticker] if ticker in close.columns else None
                if series is None or series.dropna().empty:
                    continue
                latest = float(series.dropna().iloc[-1])
                prev = float(series.dropna().iloc[-2]) if len(series.dropna()) >= 2 else latest
                pct = (latest - prev) / prev * 100 if prev else 0.0
                fallback_results.append({
                    "indicator": ticker,
                    "label": ticker,
                    "date": "",
                    "value": round(latest, 4),
                    "change_pct": round(pct, 2),
                    "direction": "up" if pct > 0.01 else ("down" if pct < -0.01 else "flat"),
                    "source": "yfinance(fallback)",
                })
            except Exception:
                pass
    except ImportError:
        pass
    except Exception as e:
        logger.warning("[stage4] yfinance fallback 오류: %s", e)

    return {
        "stage": 4,
        "name_ko": "거시 변수",
        "indicators": fallback_results,
        "source": "yfinance(fallback)",
        "note_ko": "FRED DB 미적재. yfinance 실시간 fallback. baseline_bulk_ingest.py --fred 실행 권장.",
    }


# ── Stage 5: 명분과 의도 ─────────────────────────────────────────────────

# GKG 테마 접두사 → 의도 신호 매핑 (Token-Zero, LLM 호출 없음)
_THEME_INTENT_MAP: dict[str, str] = {
    "WA_": "aggression",          # Weaponized Aggression
    "CRISISLEX_CRISISLEXREC":  "aggression",
    "MILITARY": "aggression",
    "TERROR": "aggression",
    "CONFLICT": "aggression",
    "SANCTION": "coercion",       # 경제 강압
    "ECON_COERCION": "coercion",
    "BLOCKADE": "coercion",
    "EMBARGO": "coercion",
    "CYBER": "coercion",          # 사이버 강압 (비물리적)
    "DIPLOMACY": "negotiation",   # 외교 협상
    "PEACE": "negotiation",
    "TREATY": "negotiation",
    "CEASEFIRE": "negotiation",
    "DETERRENCE": "deterrence",   # 억제 신호
    "MILITARY_EXERCISE": "deterrence",
    "NUCLEAR": "deterrence",
    "ALLIANCE": "deterrence",
}

# Goldstein 급 → 행동 강도 레이블
def _tone_label(tone: float) -> str:
    """GKG 톤 값 → 한국어 레이블."""
    if tone <= -7.0:
        return "극단적 적대"
    if tone <= -4.0:
        return "강한 적대"
    if tone <= -1.5:
        return "경미한 적대"
    if tone <= 1.5:
        return "중립"
    return "우호적"


def _resolve_actor_posture(actors: list[str]) -> list[dict]:
    """country_geopolitics.yaml에서 각 actor의 posture·권력수단을 조회한다.

    raw actor 이름(ACLED 패턴 포함)을 ISO3로 변환 후 조회.
    # Snyder 동맹 딜레마: revisionist 국가가 적대 행동 → 확전 의도 가능성 높음
    """
    data = _load_yaml(Path(__file__).resolve().parents[2] / "config" / "country_geopolitics.yaml")
    profiles = data.get("profiles", {})
    result = []
    seen: set[str] = set()
    for actor in actors:
        # ISO3 직접 또는 ACLED 패턴 변환
        iso3 = actor if (len(actor) == 3 and actor.isupper()) else (_actor_to_iso3(actor) or "")
        if not iso3 or iso3 in seen:
            continue
        seen.add(iso3)
        if iso3 in profiles:
            p = profiles[iso3]
            result.append({
                "iso3": iso3,
                "strategic_posture": p.get("strategic_posture", "unknown"),
                "instrument_of_power": p.get("instrument_of_power", "unknown"),
            })
    return result


def _infer_intent_from_themes(themes: list[str]) -> tuple[str, list[str]]:
    """GKG 테마 목록 → 의도 레이블 + 근거 테마 반환.

    우선순위: aggression > coercion > deterrence > negotiation > ambiguous
    """
    counts: dict[str, int] = {}
    matched: list[str] = []
    for theme in themes:
        theme_upper = theme.upper()
        for prefix, intent in _THEME_INTENT_MAP.items():
            if theme_upper.startswith(prefix):
                counts[intent] = counts.get(intent, 0) + 1
                matched.append(theme)
                break

    if not counts:
        return "ambiguous", []

    # 우선순위 순으로 판정
    for label in ("aggression", "coercion", "deterrence", "negotiation"):
        if counts.get(label, 0) > 0:
            return label, matched
    return "ambiguous", matched


_INTENT_LABEL_KO = {
    "aggression": "공세적 행동",
    "coercion": "강압·제재",
    "deterrence": "억제·경고",
    "negotiation": "외교·협상",
    "ambiguous": "불명확",
}

_INTENT_THEORY_MAP = {
    "aggression": ("공격적 현실주의", "Mearsheimer (2001) — 수정주의 강대국은 현상변경을 목표로 군사력 투사"),
    "coercion":   ("무기화된 상호의존", "Farrell & Newman (2019) — 경제·기술 네트워크를 지렛대로 강압"),
    "deterrence": ("확장억제 이론", "Schelling (1966) — 억제는 행동보다 신호 신뢰성에 달림"),
    "negotiation":("자유주의 제도주의", "Keohane (1984) — 반복 게임 속 협력 유인"),
    "ambiguous":  ("회색지대 전략", "Hoffman (2007) — 의도 모호성은 전략적 자산"),
}


def stage5_justification_intent(event: dict, actors: list[str]) -> dict:
    """GKG 톤·테마 + actor posture 결합으로 명분·의도를 분석한다.

    # 이론: Snyder 동맹 딜레마 × Farrell & Newman Weaponized Interdependence
    # revisionist 행위자 + 적대 톤 + 공세 테마 → 에스컬레이션 위험 신호
    """
    props = event.get("properties", event)
    payload = props.get("payload", {})
    if isinstance(payload, str):
        import json as _json
        try:
            payload = _json.loads(payload)
        except Exception:
            payload = {}

    # ── GKG 필드 추출 ────────────────────────────────────────────────────
    # GeoJSON properties는 **e.payload 스프레드로 평탄화됨 → props에서 직접 우선 읽기
    gkg_tone: float = float(props.get("gkg_tone") or payload.get("gkg_tone") or 0.0)
    gkg_themes: list[str] = props.get("gkg_themes") or payload.get("gkg_themes") or []
    gkg_hostility: bool = bool(props.get("gkg_hostility") or payload.get("gkg_hostility") or False)

    # ACLED 이벤트는 GKG 없음 → event_type 기반 fallback 추정
    source_type = props.get("source_type", "")
    # event_type도 props에 직접 있을 수 있음 (스프레드 구조)
    event_type = str(props.get("event_type") or payload.get("event_type") or "")
    if not gkg_themes and source_type == "conflict":
        if any(k in event_type.lower() for k in ("explosion", "battle", "attack", "armed")):
            gkg_themes = ["MILITARY", "CONFLICT"]
            gkg_tone = gkg_tone or -5.0   # 기본 적대 톤
        elif "protest" in event_type.lower():
            gkg_themes = ["DIPLOMACY"]    # 시위 = 비군사적 의사 표현
            gkg_tone = gkg_tone or -1.0

    # ── 의도 추론 ────────────────────────────────────────────────────────
    intent_label, matched_themes = _infer_intent_from_themes(gkg_themes)
    tone_label = _tone_label(gkg_tone)

    # GKG 적대성 확인 플래그가 있으면 negotiation을 aggression으로 상향
    if gkg_hostility and intent_label == "negotiation":
        intent_label = "aggression"

    # ── Actor posture 조회 ───────────────────────────────────────────────
    actor_postures = _resolve_actor_posture(actors)
    revisionist_actors = [p["iso3"] for p in actor_postures if p["strategic_posture"] == "revisionist"]

    # ── 에스컬레이션 위험 판정 ────────────────────────────────────────────
    # Snyder: revisionist + 공세 의도 + 강한 적대 톤 = 연루 위험
    escalation_risk = (
        intent_label in ("aggression", "coercion")
        and gkg_tone <= -4.0
        and bool(revisionist_actors)
    )

    theory_name, theory_ref = _INTENT_THEORY_MAP.get(intent_label, ("", ""))

    return {
        "stage": 5,
        "name_ko": "명분과 의도",
        "intent_label": intent_label,
        "intent_label_ko": _INTENT_LABEL_KO[intent_label],
        "tone": round(gkg_tone, 2),
        "tone_label_ko": tone_label,
        "gkg_hostility_confirmed": gkg_hostility,
        "matched_themes": matched_themes[:5],  # 최대 5개 노출
        "actor_postures": actor_postures,
        "revisionist_actors": revisionist_actors,
        "escalation_risk": escalation_risk,
        "theory_name": theory_name,
        "theory_ref": theory_ref,
        "has_gkg": bool(gkg_themes),
        "source_note": "GKG 직접 조인" if payload.get("gkg_tone") is not None else "ACLED fallback 추정",
    }


# ── Stage 6: 제도적 저항 ─────────────────────────────────────────────────

def stage6_institutional_constraints(actors: list[str], sectors: list[str]) -> dict:
    """관련 제재 레짐을 sanctions.yaml에서 조회한다.

    sanctions.yaml 구조: target_country(2자리 ISO), sectors(도메인), theory_tags.
    actor 이름 → ISO 2자리 코드 매핑으로 조회.
    """
    data = _load_yaml(_SANCTIONS_PATH)
    regimes = data.get("regimes", [])

    # 국가명·3자리 코드 → sanctions용 2자리 ISO 코드
    _TO_ISO2 = {
        "IRAN": "IR", "IRN": "IR", "Iran": "IR",
        "RUSSIA": "RU", "RUS": "RU", "Russia": "RU",
        "CHINA": "CN", "CHN": "CN", "China": "CN",
        "NORTH KOREA": "KP", "PRK": "KP", "DPRK": "KP",
        "MYANMAR": "MM", "BELARUS": "BY", "VENEZUELA": "VE",
        "SYRIA": "SY", "SYR": "SY",
        "ISRAEL": "IL", "ISR": "IL",
        "UKRAINE": "UA", "UKR": "UA",
    }

    actor_iso2: set[str] = set()
    for actor in actors:
        code = _TO_ISO2.get(actor.upper()) or _TO_ISO2.get(actor)
        if code:
            actor_iso2.add(code)
        elif len(actor) == 2:
            actor_iso2.add(actor.upper())

    matched: list[dict] = []
    for regime in regimes:
        target = (regime.get("target_country") or "").upper()
        if target not in actor_iso2:
            continue
        matched.append({
            "id": regime.get("id", ""),
            "name": regime.get("target_name", regime.get("id", "")),
            "issuer": ", ".join(regime.get("sanctioning_bodies", [])),
            "target_country": regime.get("target_country", ""),
            "sectors": regime.get("sectors", []),
            "year": regime.get("year_established", ""),
            "description": regime.get("description", ""),
        })

    return {
        "stage": 6,
        "name_ko": "제도적 저항",
        "active_sanctions": matched,
        "un_security_council_note": "UN 안보리 상임이사국 거부권 현황은 별도 확인 필요.",
    }


# ── Stage 7: 시간적 추이 ─────────────────────────────────────────────────

def stage7_temporal_cascade(event_id: str, cascade_links: list[dict]) -> dict:
    """기존 cascade 링크에서 이 이벤트의 인과 체인을 추출한다."""
    # cascade_links는 api/events.py 또는 cascade DB에서 전달받는다
    related = [
        lk for lk in cascade_links
        if lk.get("source_event_id") == event_id or lk.get("target_event_id") == event_id
    ]

    chains = []
    for lk in related[:5]:
        chains.append({
            "source_id": lk.get("source_event_id"),
            "target_id": lk.get("target_event_id"),
            "link_type": lk.get("link_type"),
            "correlation_score": lk.get("correlation_score"),
            "time_delta_hours": round(lk.get("time_delta_seconds", 0) / 3600, 1),
            "depth": lk.get("depth", 1),
        })

    return {
        "stage": 7,
        "name_ko": "시간적 추이",
        "cascade_chain": chains,
        "chain_depth": len(chains),
        "note_ko": "Cascade 링크 기반 인과 체인. 최대 depth=4.",
    }


# ── Stage 8: 동맹 확산 ───────────────────────────────────────────────────

def stage8_alliance_spread(actors: list[str], region_code: str = "") -> dict:
    """alliance_graph.yaml에서 관련 동맹 네트워크를 조회한다.

    actor 문자열에서 국가 코드를 추출하는 방법 (우선순위 순):
    1) 직접 ISO3 코드 (예: CHN, USA)
    2) "Military/Police/Government Forces of [Country]" 패턴 정규식 추출
    3) "Protesters ([Country])" 등 괄호 내 국가명 추출
    4) 전체 문자열을 국가명으로 직접 매핑
    5) region_code → 관여 국가 fallback (예: hormuz → IRN)
    """
    data = _load_yaml(_ALLIANCE_GRAPH_PATH)
    alliances = data.get("alliances", [])
    memberships = data.get("country_memberships", {})

    # 모듈 레벨 _ACTOR_NAME_TO_CODE / _actor_to_iso3 재사용
    _NAME_TO_CODE = _ACTOR_NAME_TO_CODE

    # region_code → 핵심 관여 국가 fallback
    _REGION_ACTORS: dict[str, list[str]] = {
        "taiwan_strait":    ["TWN", "CHN", "USA"],
        "south_china_sea":  ["CHN", "PHL", "VNM", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
        "korean_peninsula": ["KOR", "PRK", "USA", "CHN"],
        "north_korea":      ["PRK", "KOR", "USA"],
        "hormuz":           ["IRN", "USA", "SAU"],
        "bab_el_mandeb":    ["YEM", "USA"],
        "suez":             ["EGY", "USA"],
        "eastern_europe":   ["UKR", "RUS", "USA"],
        "ukraine":          ["UKR", "RUS"],
        "middle_east":      ["ISR", "IRN", "USA"],
        "persian_gulf":     ["IRN", "SAU", "USA"],
    }

    # 모듈 레벨 _actor_to_iso3 재사용 (memberships 추가 체크)
    def _extract_country(actor: str) -> str | None:
        s = actor.strip()
        if len(s) == 3 and s.isupper() and s in memberships:
            return s
        return _actor_to_iso3(actor)

    actor_codes: set[str] = set()
    for actor in actors:
        if not actor:
            continue
        code = _extract_country(actor)
        if code:
            actor_codes.add(code)

    # 5) region_code fallback: actor에서 코드를 못 찾으면 지역 기반 국가 추가
    if not actor_codes and region_code:
        for rc_key, rc_codes in _REGION_ACTORS.items():
            if rc_key in region_code:
                actor_codes.update(rc_codes)
                break

    relevant_alliances: list[dict] = []
    involved_countries: set[str] = set()

    for code in actor_codes:
        for alliance_id in memberships.get(code, []):
            alliance = next((a for a in alliances if a["id"] == alliance_id), None)
            if alliance and alliance_id not in [a["id"] for a in relevant_alliances]:
                relevant_alliances.append({
                    "id": alliance["id"],
                    "name": alliance["name"],
                    "name_ko": alliance["name_ko"],
                    "type": alliance["type"],
                    "members": alliance["members"],
                    "notes_ko": alliance.get("notes_ko", ""),
                })
                involved_countries.update(alliance["members"])

    # 무역 의존도 조회 (Weaponized Interdependence 계량화)
    trade_deps = _query_trade_dependency(actor_codes)

    return {
        "stage": 8,
        "name_ko": "동맹 확산",
        "actor_codes_resolved": list(actor_codes),
        "relevant_alliances": relevant_alliances,
        "potentially_involved_countries": list(involved_countries - actor_codes),
        "trade_dependencies": trade_deps,
        "note_ko": "조약 의무 발동 시 잠재적으로 관여할 수 있는 국가 목록. 무역 의존도는 Farrell & Newman(2019) Weaponized Interdependence 지표.",
    }
