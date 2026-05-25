"""
news.py — 상단 뉴스 티커 API.

GET /api/news/ticker — importance >= 0.5 & confidence >= 0.5 최신 8건,
                       Gemini 티커 포맷(이모지 [지역] 요약)으로 번역 (3분 캐시)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from connectors.gemini_translator import translate_ticker_text, _is_quota_exhausted
from connectors.gdelt_connector import fetch_headline

router = APIRouter(prefix="/api/news", tags=["news"])
logger = logging.getLogger(__name__)

_TICKER_TTL            = timedelta(minutes=3)
_TICKER_TTL_SHORT      = timedelta(minutes=5)    # RPM 초과 시 재시도
_TICKER_TTL_QUOTA_DONE = timedelta(hours=1)      # 일일 할당량 소진 시
_ticker_cache: dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}


def _hours_ago_label(timestamp_str: str) -> str:
    """ISO timestamp -> 경과 시간 레이블 (분/시간/일/개월/년)."""
    try:
        ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        minutes = int(delta.total_seconds() / 60)
        if minutes < 1:
            return "방금 전"
        if minutes < 60:
            return f"{minutes}분 전"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}시간 전"
        days = hours // 24
        if days < 30:
            return f"{days}일 전"
        months = days // 30
        if months < 12:
            return f"{months}개월 전"
        return f"{days // 365}년 전"
    except Exception:
        return ""


def _has_korean(text: str) -> bool:
    """한글 음절(가-힣) 포함 여부."""
    return any("가" <= c <= "힣" for c in text)


async def _process_feature(props: dict, headline: str | None = None) -> dict | None:
    """단일 GeoJSON feature props + 실제 기사 헤드라인 → 티커 아이템 변환.

    headline이 있으면 실제 기사 헤드라인 기반 번역,
    없으면 GDELT 템플릿 title로 fallback.
    """
    source_url = props.get("source_url") or props.get("url") or ""
    # 실제 헤드라인 우선, 없으면 템플릿 title 사용
    source_text = (headline or props.get("title", "")).strip()
    if not source_text:
        return None

    # source_url 기준으로 캐싱 (같은 기사 재번역 방지)
    text_ko    = await translate_ticker_text(source_text, cache_key=source_url)
    time_label = _hours_ago_label(props.get("timestamp", ""))

    return {
        "text_ko":     text_ko,
        "time_label":  time_label,
        "url":         source_url,
        "is_fallback": not _has_korean(text_ko),
    }


@router.get("/ticker")
async def get_news_ticker():
    """상단 뉴스 티커용 GDELT 이벤트 목록.

    GDELT만 사용 (ACLED는 1년 전 데이터라 최신 티커 부적합).
    필터: confidence_score >= 0.8 (교차검증 완료) + importance_score >= 0.5
    최신 8건을 Gemini 티커 포맷으로 번역해 반환한다.
    fallback(429 등) 발생 시 30초 단축 TTL로 빠른 재시도.
    """
    now = datetime.now(timezone.utc)
    if _ticker_cache["data"] is not None and now < _ticker_cache["expires_at"]:
        return _ticker_cache["data"]

    from api.layers import _gdelt_cache

    # GDELT만 사용 (ACLED는 1년 전 데이터라 최신 티커 부적합)
    # 1순위: confidence >= 0.8 (RSS 교차검증 완료) + importance >= 0.5
    # 2순위: 8건 미만이면 confidence >= 0.5 (미검증) 로 보충
    _IMPORTANCE_MIN      = 0.5
    _CONFIDENCE_VERIFIED = 0.8
    _CONFIDENCE_ANY      = 0.5

    features = []
    if _gdelt_cache.get("geojson") is not None:
        features = _gdelt_cache["geojson"].get("features", [])

    def _passes(props: dict, conf_min: float) -> bool:
        return (
            float(props.get("importance_score", 0.0)) >= _IMPORTANCE_MIN
            and float(props.get("confidence_score", 0.0)) >= conf_min
        )

    # 1순위: 교차검증 완료
    candidates = [f["properties"] for f in features if _passes(f["properties"], _CONFIDENCE_VERIFIED)]

    # 2순위 보충: 8건 미만이면 미검증도 추가 (중복 제외)
    if len(candidates) < 8:
        verified_ids = {p.get("id") for p in candidates}
        for f in features:
            p = f["properties"]
            if p.get("id") not in verified_ids and _passes(p, _CONFIDENCE_ANY):
                candidates.append(p)
            if len(candidates) >= 8:
                break

    # 최신순 정렬 후 상위 8건
    candidates.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
    top8 = candidates[:8]

    if not top8:
        data = {"items": []}
        _ticker_cache["data"] = data
        # GDELT 캐시가 비어있거나 필터 통과 항목 없음 → 30초 뒤 재시도
        _ticker_cache["expires_at"] = now + timedelta(seconds=30)
        return data

    # Step 1: 기사 헤드라인 병렬 fetch (HTTP GET — Gemini 호출 아님, 병렬 OK)
    headline_results = await asyncio.gather(
        *[fetch_headline(p.get("source_url", "")) for p in top8],
        return_exceptions=True,
    )
    headlines = [
        h if isinstance(h, str) and h else None
        for h in headline_results
    ]
    fetched = sum(1 for h in headlines if h)
    logger.debug("[ticker] 헤드라인 fetch: %d/%d 성공", fetched, len(top8))

    # Step 2: 순차 번역 — Gemini 15 RPM 한도 준수 (캐시 히트 시 딜레이 없음)
    items: list[dict] = []
    had_fallback = False
    for i, (props, headline) in enumerate(zip(top8, headlines)):
        if i > 0:
            await asyncio.sleep(2.0)   # 요청 간 2초 간격 (free tier 15 RPM 방지)
        try:
            result = await _process_feature(props, headline)
            if result:
                if result.get("is_fallback"):
                    had_fallback = True
                # is_fallback 필드는 내부 신호용, 클라이언트에 노출 불필요
                items.append({k: v for k, v in result.items() if k != "is_fallback"})
        except Exception as e:
            logger.debug("[ticker] 번역 건너뜀: %s", e)

    data = {"items": items}
    _ticker_cache["data"] = data
    # TTL 결정: 할당량 소진 → 1시간, 일시 429 → 5분, 정상 → 3분
    if had_fallback and _is_quota_exhausted():
        ttl = _TICKER_TTL_QUOTA_DONE
    elif had_fallback:
        ttl = _TICKER_TTL_SHORT
    else:
        ttl = _TICKER_TTL
    _ticker_cache["expires_at"] = now + ttl
    logger.debug("[ticker] %d건 완료, fallback=%s, TTL=%s", len(items), had_fallback, ttl)
    return data
