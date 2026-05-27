"""
news_cross_validator.py — GDELT Stage 2: RSS 뉴스 교차검증

GDELT Stage 1 통과 이벤트에 대해 주요 국제 뉴스 RSS 피드를 조회해
동일 사건이 2개 이상 매체에 언급되었는지 확인한다.

교차검증 결과:
  - 2개+ 매체 언급 → confidence_score 0.5 → 0.8
  - 미언급             → confidence_score 0.5 유지

CLAUDE.md Phase 3 기준:
  "뉴스 RSS/NewsAPI 교차 검증 (24h 내 2개 이상 매체)"
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from models.event import Event

logger = logging.getLogger(__name__)

# ── RSS 피드 목록 (무료·안정적인 국제 뉴스 피드) ──────────────────────────
_RSS_FEEDS: list[tuple[str, str]] = [
    ("Reuters",    "http://feeds.reuters.com/reuters/worldNews"),
    ("BBC",        "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("AP News",    "https://feeds.apnews.com/rss/apf-intlnews"),
]

_CROSS_VALIDATE_THRESHOLD = 2   # 2개 이상 매체 = 교차검증 통과
_CONFIRMED_CONFIDENCE     = 0.8  # 교차검증 성공 시 confidence_score

# 매체당 fetch 타임아웃 (초). 느린 피드는 건너뜀.
_FEED_TIMEOUT = 8


async def cross_validate(events: list[Event]) -> list[Event]:
    """
    Stage 1 통과 이벤트 목록에 대해 RSS 교차검증을 수행한다.

    1. 모든 RSS 피드를 병렬 fetch
    2. 각 이벤트의 지역·행위자 키워드가 몇 개 매체에 등장하는지 카운트
    3. threshold 이상 → confidence_score = 0.8

    Returns:
        confidence_score가 갱신된 Event 목록 (새 객체)
    """
    if not events:
        return events

    articles = await _fetch_all_feeds()
    if not articles:
        logger.warning("[CrossValidator] RSS 피드 fetch 실패 — confidence_score 유지")
        return events

    validated: list[Event] = []
    for evt in events:
        keywords = _extract_keywords(evt)
        hit_count = _count_source_hits(keywords, articles)

        if hit_count >= _CROSS_VALIDATE_THRESHOLD:
            # Pydantic model_copy로 불변성 유지 (confidence만 갱신)
            updated = evt.model_copy(update={"confidence_score": _CONFIRMED_CONFIDENCE})
            validated.append(updated)
            logger.debug(
                "[CrossValidator] 교차검증 통과 (%d매체): %s", hit_count, evt.title[:60]
            )
        else:
            validated.append(evt)

    confirmed = sum(1 for e in validated if e.confidence_score >= _CONFIRMED_CONFIDENCE)
    logger.info(
        "[CrossValidator] 교차검증 완료 — %d/%d 통과 (≥%d매체)",
        confirmed, len(validated), _CROSS_VALIDATE_THRESHOLD,
    )
    return validated


async def _fetch_all_feeds() -> list[dict]:
    """
    모든 RSS 피드를 병렬 fetch. 실패한 피드는 건너뜀.

    Returns:
        [{"source": str, "title": str, "description": str}, ...]
    """
    import asyncio

    async def _fetch_one(source: str, url: str) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=_FEED_TIMEOUT) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
            return _parse_rss(source, resp.text)
        except Exception as exc:
            logger.debug("[CrossValidator] %s 피드 실패: %s", source, exc)
            return []

    results = await asyncio.gather(
        *[_fetch_one(src, url) for src, url in _RSS_FEEDS]
    )
    flat = [art for feed in results for art in feed]
    logger.info("[CrossValidator] RSS 수집: %d개 기사", len(flat))
    return flat


def _parse_rss(source: str, xml_text: str) -> list[dict]:
    """RSS XML → 기사 목록 (title + description 텍스트)."""
    articles: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    # RSS 2.0: channel/item, Atom: feed/entry 모두 처리
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for item in items[:50]:  # 피드당 최대 50개
        title = _text(item, ["title", "atom:title"], ns)
        desc  = _text(item, ["description", "summary", "atom:summary"], ns)
        articles.append({
            "source":  source,
            "text":    f"{title} {desc}".lower(),
        })
    return articles


def _text(el: ET.Element, tags: list[str], ns: dict) -> str:
    """여러 태그 이름 중 첫 번째 텍스트를 반환한다."""
    for tag in tags:
        child = el.find(tag, ns)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _extract_keywords(evt: Event) -> list[str]:
    """
    이벤트에서 교차검증용 키워드를 추출한다.

    GeoJSON geo_name(국가/지역명)과 행위자명이 주 검색 키워드.
    payload가 없는 이벤트는 title에서 추출.
    """
    keywords: list[str] = []

    payload = evt.payload or {}
    geo_name = payload.get("geo_name", "")
    actor1   = payload.get("actor1", "")
    actor2   = payload.get("actor2", "")

    for word in [geo_name, actor1, actor2]:
        # 국가코드처럼 짧은 단어나 "Unknown" 제외
        if word and len(word) > 2 and word.lower() != "unknown":
            keywords.append(word.lower().split(",")[0].strip())

    # region_code 기반 보조 키워드
    region_kw = {
        "taiwan_strait":    "taiwan",
        "south_china_sea":  "south china sea",
        "bab_el_mandeb":    "red sea",
        "suez":             "suez",
        "hormuz":           "hormuz",
        "ukraine":          "ukraine",
        "middle_east":      "israel",
        "korean_peninsula": "korea",
    }
    if evt.region_code in region_kw:
        keywords.append(region_kw[evt.region_code])

    return list(dict.fromkeys(keywords))  # 중복 제거, 순서 유지


def _count_source_hits(keywords: list[str], articles: list[dict]) -> int:
    """키워드 중 하나라도 언급한 고유 뉴스 소스 수를 반환한다."""
    if not keywords:
        return 0

    hit_sources: set[str] = set()
    for art in articles:
        text = art["text"]
        if any(kw in text for kw in keywords):
            hit_sources.add(art["source"])

    return len(hit_sources)


async def fetch_rss_articles() -> list[dict]:
    """RSS 기사 목록을 일괄 fetch해 반환한다 (외부 모듈용 공개 인터페이스).

    verification_funnel 등에서 RSS 피드를 한 번만 fetch하고 여러 이벤트에 재사용할 때 호출.
    """
    return await _fetch_all_feeds()


def check_rss_match(evt: "Event", articles: list[dict]) -> bool:
    """이벤트 키워드가 기사 목록에서 2개 이상 매체 히트 여부를 반환한다."""
    keywords = _extract_keywords(evt)
    return _count_source_hits(keywords, articles) >= _CROSS_VALIDATE_THRESHOLD
