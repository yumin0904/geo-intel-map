"""
8단계 추론 프로세서.

각 stage_N 함수는 Event와 부가 컨텍스트를 받아
해당 단계의 분석 결과 dict를 반환한다.
실패 시 {"error": "..."} 포함 — 엔진이 partial report로 처리.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from services.region import region_for_point

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parents[2] / "config"
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

    return {
        "stage": 3,
        "name_ko": "역사적 비교",
        "analogues": top3,
        "total_candidates": len(scored),
    }


# ── Stage 4: 거시 변수 ───────────────────────────────────────────────────

async def stage4_macro_variables(sectors: list[str], region: str) -> dict:
    """관련 시장 지표(yfinance)를 조회한다. 실패 시 빈 목록 반환."""
    # 섹터·지역별 관련 티커
    ticker_map = {
        "energy": ["CL=F", "BNO", "NG=F"],      # WTI, Brent ETF, 천연가스
        "maritime": ["FRO", "BDRY", "ZIM"],      # 해운 관련
        "techno": ["TSM", "NVDA", "SOXX"],       # 반도체
        "indo_pacific": ["TSM", "KWEB"],         # 대만·중국 노출
        "gray_zone": ["GLD", "VIX"],             # 안전자산·변동성
    }
    region_tickers = {
        "hormuz": ["CL=F", "BNO"],
        "taiwan_strait": ["TSM", "KWEB"],
        "ukraine": ["NG=F", "WEAT"],
        "red_sea": ["FRO", "ZIM", "BNO"],
        "south_china_sea": ["TSM", "KWEB"],
    }

    tickers: set[str] = set()
    for s in sectors:
        tickers.update(ticker_map.get(s, []))
    tickers.update(region_tickers.get(region, []))

    if not tickers:
        tickers = {"CL=F", "GLD"}  # 기본 지표

    results = []
    try:
        import yfinance as yf  # 선택 의존성

        # 하루치 데이터로 충분 (전일 종가 vs 현재)
        tickers_str = " ".join(tickers)
        data = yf.download(tickers_str, period="5d", progress=False, auto_adjust=True)

        if hasattr(data.columns, "levels"):
            # 멀티인덱스 (복수 티커)
            close = data["Close"] if "Close" in data.columns.get_level_values(0) else data
        else:
            close = data["Close"] if "Close" in data.columns else data

        for ticker in tickers:
            try:
                series = close[ticker] if ticker in close.columns else None
                if series is None or series.dropna().empty:
                    continue
                latest = float(series.dropna().iloc[-1])
                prev   = float(series.dropna().iloc[-2]) if len(series.dropna()) >= 2 else latest
                pct_chg = (latest - prev) / prev * 100 if prev else 0.0
                results.append({
                    "ticker": ticker,
                    "price": round(latest, 2),
                    "change_pct": round(pct_chg, 2),
                    "direction": "up" if pct_chg > 0 else ("down" if pct_chg < 0 else "flat"),
                })
            except Exception:
                pass
    except ImportError:
        return {"stage": 4, "name_ko": "거시 변수", "error": "yfinance 미설치", "tickers": []}
    except Exception as e:
        logger.warning("[stage4] yfinance 오류: %s", e)
        return {"stage": 4, "name_ko": "거시 변수", "error": str(e), "tickers": []}

    return {
        "stage": 4,
        "name_ko": "거시 변수",
        "tickers": results,
        "note_ko": "전일 종가 기준 변화율. 실시간 아님.",
    }


# ── Stage 5: 명분과 의도 (Phase 4) ──────────────────────────────────────

def stage5_intent_placeholder() -> dict:
    """외교 성명 RSS + Gemini 분석 — Phase 4 구현 예정."""
    return {
        "stage": 5,
        "name_ko": "명분과 의도",
        "status": "phase4",
        "note_ko": "외교 성명 RSS 수집 + Gemini 분석. Phase 4에서 구현 예정.",
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

def stage8_alliance_spread(actors: list[str]) -> dict:
    """alliance_graph.yaml에서 관련 동맹 네트워크를 조회한다."""
    data = _load_yaml(_ALLIANCE_GRAPH_PATH)
    alliances = data.get("alliances", [])
    memberships = data.get("country_memberships", {})

    # 3자리 코드 매핑 (간단한 국가명 → 코드 변환)
    _NAME_TO_CODE = {
        "usa": "USA", "united states": "USA", "america": "USA",
        "russia": "RUS", "china": "CHN", "prc": "CHN",
        "japan": "JPN", "korea": "KOR", "south korea": "KOR",
        "iran": "IRN", "israel": "ISR", "ukraine": "UKR",
        "australia": "AUS", "india": "IND", "uk": "GBR", "britain": "GBR",
        "france": "FRA", "germany": "DEU", "turkey": "TUR",
        "north korea": "PRK", "dprk": "PRK",
    }

    actor_codes: set[str] = set()
    for actor in actors:
        if not actor:
            continue
        code = _NAME_TO_CODE.get(actor.lower())
        if code:
            actor_codes.add(code)
        elif len(actor) == 3 and actor.upper() in memberships:
            actor_codes.add(actor.upper())

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

    return {
        "stage": 8,
        "name_ko": "동맹 확산",
        "actor_codes_resolved": list(actor_codes),
        "relevant_alliances": relevant_alliances,
        "potentially_involved_countries": list(involved_countries - actor_codes),
        "note_ko": "조약 의무 발동 시 잠재적으로 관여할 수 있는 국가 목록.",
    }
