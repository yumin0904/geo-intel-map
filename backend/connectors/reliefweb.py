"""
reliefweb.py — UN OCHA ReliefWeb RSS 커넥터

ReliefWeb (https://reliefweb.int) 은 UN OCHA가 운영하는 인도주의·분쟁
보고서 허브다. 일반 업데이트 RSS 피드를 수집 후 국가·분쟁 키워드로 필터링.

수집 전략:
  - 국가별 피드는 봇 탐지로 차단됨
  - 일반 피드(https://reliefweb.int/updates/rss.xml) 수집 후
    5대 섹터 국가 키워드 필터로 지정학 관련 항목만 추출

신뢰도(confidence_score): 0.65 — UN 기관 출처 (GDELT 미검증 0.5보다 높음)

이론 연결: Gray Zone / Hybrid Warfare — 인도주의 위기와 분쟁의 경계 추적
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from models.event import Event

logger = logging.getLogger(__name__)

# ── 수집 피드 (봇 탐지 우회: 일반 피드 사용) ────────────────────────────────
_RSS_URLS = [
    "https://reliefweb.int/updates/rss.xml",
    # 재난·위기 특화 피드 (있는 경우)
]

# 브라우저처럼 보이는 헤더 — ReliefWeb WAF 우회
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
}

# 5대 섹터 핵심 국가·지역 → (region_code, lat, lon, sector)
# description 내 "Country: [국가명]" 텍스트와 매칭
_COUNTRY_MAP: dict[str, dict] = {
    "Ukraine":               {"region": "ukraine",           "lat": 50.4,  "lon": 30.5,  "sector": "gray_zone"},
    "Russia":                {"region": "ukraine",           "lat": 55.7,  "lon": 37.6,  "sector": "gray_zone"},
    "Yemen":                 {"region": "bab_el_mandeb",    "lat": 15.5,  "lon": 44.2,  "sector": "maritime"},
    "Somalia":               {"region": "bab_el_mandeb",    "lat":  2.0,  "lon": 45.3,  "sector": "gray_zone"},
    "Mali":                  {"region": "africa_sahel",     "lat": 12.6,  "lon":  -8.0, "sector": "gray_zone"},
    "Myanmar":               {"region": "south_china_sea",  "lat": 19.7,  "lon": 96.1,  "sector": "indo_pacific"},
    "Afghanistan":           {"region": "indo_pacific",     "lat": 34.5,  "lon": 69.2,  "sector": "indo_pacific"},
    "Iraq":                  {"region": "hormuz",           "lat": 33.3,  "lon": 44.4,  "sector": "energy"},
    "Syrian Arab Republic":  {"region": "middle_east",      "lat": 33.5,  "lon": 36.3,  "sector": "gray_zone"},
    "Syria":                 {"region": "middle_east",      "lat": 33.5,  "lon": 36.3,  "sector": "gray_zone"},
    "occupied Palestinian":  {"region": "middle_east",      "lat": 31.5,  "lon": 34.5,  "sector": "gray_zone"},
    "Palestine":             {"region": "middle_east",      "lat": 31.5,  "lon": 34.5,  "sector": "gray_zone"},
    "Gaza":                  {"region": "middle_east",      "lat": 31.4,  "lon": 34.4,  "sector": "gray_zone"},
    "Democratic Republic of the Congo": {"region": "africa_great_lakes", "lat": -4.3, "lon": 15.3, "sector": "gray_zone"},
    "Sudan":                 {"region": "bab_el_mandeb",    "lat": 15.5,  "lon": 32.5,  "sector": "gray_zone"},
    "South Sudan":           {"region": "bab_el_mandeb",    "lat":  4.8,  "lon": 31.6,  "sector": "gray_zone"},
    "Ethiopia":              {"region": "bab_el_mandeb",    "lat":  9.0,  "lon": 38.7,  "sector": "gray_zone"},
    "Lebanon":               {"region": "middle_east",      "lat": 33.8,  "lon": 35.5,  "sector": "gray_zone"},
    "Iran":                  {"region": "hormuz",           "lat": 35.7,  "lon": 51.4,  "sector": "energy"},
    "Israel":                {"region": "middle_east",      "lat": 31.8,  "lon": 35.2,  "sector": "gray_zone"},
    "Philippines":           {"region": "south_china_sea",  "lat": 14.6,  "lon": 121.0, "sector": "indo_pacific"},
    "Pakistan":              {"region": "indo_pacific",     "lat": 33.7,  "lon": 73.0,  "sector": "gray_zone"},
}

# 분쟁·안보 키워드 필터 (제목에 1개 이상 포함 시 통과)
_CONFLICT_KEYWORDS = {
    "attack", "attacks", "conflict", "military", "armed", "shelling",
    "ceasefire", "strike", "bombing", "offensive", "troops", "forces",
    "casualt", "killed", "fighting", "violence", "displaced", "siege",
    "artillery", "airstrike", "missile", "drone", "hostage",
    "evacuation", "humanitarian crisis", "clashes", "ambush",
    "rebel", "insurgent", "militia", "sanctions", "blockade",
    "situation report", "sitrep", "emergency", "crisis",
    "displacement", "detention", "arrests", "explosion",
}

_FETCH_TIMEOUT = 15.0


async def _fetch_rss(client: httpx.AsyncClient, url: str) -> str:
    """단일 URL fetch 후 텍스트 반환."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("[reliefweb] fetch 실패 %s: %s", url, e)
        return ""


def _parse_rss(text: str) -> list[Event]:
    """RSS XML 텍스트 파싱 → 5대 섹터 국가 필터 → Event 목록 반환."""
    if not text:
        return []

    items = re.findall(r"<item>(.*?)</item>", text, re.DOTALL)
    events: list[Event] = []

    for raw in items:
        title = _extract_tag(raw, "title")
        if not title:
            continue

        title_lower = title.lower()

        # 분쟁 키워드 필터
        if not any(kw in title_lower for kw in _CONFLICT_KEYWORDS):
            continue

        pub_str  = _extract_tag(raw, "pubDate")
        link     = _extract_tag(raw, "link") or ""
        desc_raw = _extract_tag(raw, "description") or ""
        desc_clean = html.unescape(desc_raw)

        # 국가명 추출
        country_m = re.search(r"Country: ([^<]+)<", desc_clean)
        country_str = country_m.group(1).strip() if country_m else ""

        # 5대 섹터 국가 매핑 확인
        geo = _match_country(country_str, title)
        if not geo:
            continue  # 관련 없는 지역 건너뜀

        # 날짜 파싱
        try:
            ts = parsedate_to_datetime(pub_str).astimezone(timezone.utc) if pub_str else datetime.now(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)

        severity = _estimate_severity(title_lower)

        event = Event(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, link or title)),
            timestamp=ts,
            source_type="reliefweb",
            source_id=link,
            location=(geo["lat"], geo["lon"]),
            region_code=geo["region"],
            severity=severity,
            title=title,
            description=f"[ReliefWeb/UN OCHA] {country_str or '?'}: {title}",
            theory_tags=_derive_theory_tags(title_lower, geo["sector"]),
            payload={
                "data_source":      "ReliefWeb",
                "country":          country_str,
                "sector":           geo["sector"],
                "source_url":       link,
                "confidence_score": 0.65,
            },
            confidence_score=0.65,
        )
        events.append(event)

    return events


def _match_country(country_str: str, title: str) -> dict | None:
    """country_str 또는 title에서 _COUNTRY_MAP 매칭 후 geo 정보 반환."""
    # 국가명 직접 매칭
    for name, geo in _COUNTRY_MAP.items():
        if name.lower() in country_str.lower():
            return geo
    # 제목에서 국가명 검색 (국가명 포함 리포트)
    title_lower = title.lower()
    for name, geo in _COUNTRY_MAP.items():
        if name.lower() in title_lower:
            return geo
    return None


def _extract_tag(text: str, tag: str) -> str:
    """CDATA 포함 태그 추출."""
    m = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(rf"<{tag}>([^<]*)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else ""


def _estimate_severity(title_lower: str) -> int:
    """제목 키워드 기반 severity 추정 (0-100)."""
    high = {"airstrike", "missile", "artillery", "offensive", "siege", "bombing", "killed", "shelling", "explosion"}
    mid  = {"conflict", "attack", "clashes", "armed", "violence", "casualt", "troops", "fighting"}
    if any(kw in title_lower for kw in high):
        return 65
    if any(kw in title_lower for kw in mid):
        return 45
    return 30


def _derive_theory_tags(title_lower: str, sector: str) -> list[str]:
    """섹터·키워드 기반 이론 태그 도출."""
    tags: list[str] = []
    if sector == "gray_zone":
        tags.append("gray_zone")
        if any(kw in title_lower for kw in ("rebel", "militia", "insurgent")):
            tags.append("hybrid_warfare")
    if sector == "maritime":
        tags.append("SLOC")
    if sector == "energy":
        tags.append("resource_weaponization")
    if sector == "indo_pacific":
        tags.append("A2AD")
    if "sanction" in title_lower:
        tags.append("economic_coercion")
    if "drone" in title_lower:
        tags.append("hybrid_warfare")
    return tags or [sector]


async def fetch_reliefweb_events() -> list[Event]:
    """ReliefWeb RSS 수집 후 5대 섹터 분쟁 이벤트 반환.

    호출 주기: 30분 (APScheduler, main.py).
    """
    async with httpx.AsyncClient(http2=False, headers=_HEADERS) as client:
        tasks = [_fetch_rss(client, url) for url in _RSS_URLS]
        texts = await asyncio.gather(*tasks, return_exceptions=True)

    events: list[Event] = []
    for text in texts:
        if isinstance(text, str):
            events.extend(_parse_rss(text))

    # UUID 기반 중복 제거
    seen: set[str] = set()
    deduped = [e for e in events if not (e.id in seen or seen.add(e.id))]  # type: ignore[func-returns-value]

    logger.info("[reliefweb] 수집 완료: %d건", len(deduped))
    return deduped
