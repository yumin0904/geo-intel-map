"""
news.py — 상단 뉴스 티커 API.

GET /api/news/ticker — 최신 GDELT 이벤트 최대 8건을 영문 헤드라인으로 반환.
포맷: [지역] 영문 헤드라인
Gemini 번역 없음. source_url에서 실제 헤드라인을 fetch하고,
실패 시 GDELT 템플릿 title로 fallback. 3분 캐시.
"""
from __future__ import annotations

import asyncio
import html as html_mod
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from connectors.gdelt_connector import fetch_headline

router = APIRouter(prefix="/api/news", tags=["news"])
logger = logging.getLogger(__name__)

_TICKER_TTL = timedelta(minutes=3)
_ticker_cache: dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}

# region_code → 한국어 지역명 (티커 [지역] 접두사)
_REGION_LABEL: dict[str, str] = {
    "ukraine":        "우크라이나",
    "hormuz":         "호르무즈",
    "taiwan_strait":  "대만해협",
    "red_sea":        "홍해",
    "south_china_sea":"남중국해",
    "bab_el_mandeb":  "바브엘만데브",
    "suez":           "수에즈",
    "malacca":        "말라카",
    "east_china_sea": "동중국해",
    "korean_peninsula":"한반도",
    "middle_east":    "중동",
    "persian_gulf":   "페르시아만",
    "balkans":        "발칸",
    "sahel":          "사헬",
    "myanmar":        "미얀마",
    "global":         "글로벌",
}


def _time_label(timestamp_str: str) -> str:
    """ISO timestamp → 경과 시간 레이블."""
    try:
        ts = datetime.fromisoformat(timestamp_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        minutes = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
        if minutes < 1:   return "방금 전"
        if minutes < 60:  return f"{minutes}분 전"
        hours = minutes // 60
        if hours < 24:    return f"{hours}시간 전"
        days = hours // 24
        if days < 30:     return f"{days}일 전"
        months = days // 30
        if months < 12:   return f"{months}개월 전"
        return f"{days // 365}년 전"
    except Exception:
        return ""


def _format_text(headline: str | None, props: dict) -> str:
    """[지역] 영문 헤드라인 조합.

    headline: source_url에서 fetch한 실제 기사 제목 (없으면 GDELT title)
    """
    # GDELT 템플릿 title은 "[GDELT] 지명: ..." 형태라 실제 헤드라인보다 노이즈 많음
    # 실제 헤드라인이 있으면 우선 사용
    raw_title  = props.get("title", "")
    text       = html_mod.unescape((headline or raw_title).strip())

    # "[GDELT] ..." 형태의 템플릿 title이면 headline fetch 실패 → 짧게 정리
    if text.startswith("[GDELT]"):
        # 콜론 뒤 행위자 설명만 남김 (예: "IRAN vs AFGHANISTAN (물리적 충돌)")
        parts = text.split(":", 1)
        text  = parts[1].strip() if len(parts) > 1 else text

    # [지역] 접두사
    region = props.get("region_code", "")
    label  = _REGION_LABEL.get(region, "")
    if label:
        text = f"[{label}] {text}"

    return text


@router.get("/ticker")
async def get_news_ticker():
    """상단 뉴스 티커용 GDELT 이벤트 목록 (영문 헤드라인).

    필터: importance_score >= 0.5
    1순위: confidence_score >= 0.8 (RSS 교차검증 완료)
    2순위: confidence_score >= 0.5 (미검증) 로 8건 보충
    source_url 기준 중복 제거 후 최신순 상위 8건.
    """
    now = datetime.now(timezone.utc)
    if _ticker_cache["data"] is not None and now < _ticker_cache["expires_at"]:
        return _ticker_cache["data"]

    from api.layers import _gdelt_cache

    features: list[dict] = []
    if _gdelt_cache.get("geojson") is not None:
        features = _gdelt_cache["geojson"].get("features", [])

    _IMP_MIN  = 0.5
    _CONF_HI  = 0.8
    _CONF_LO  = 0.5

    def _passes(p: dict, conf_min: float) -> bool:
        return (
            float(p.get("importance_score", 0.0)) >= _IMP_MIN
            and float(p.get("confidence_score", 0.0)) >= conf_min
        )

    # 1순위 — 교차검증 완료
    candidates = [f["properties"] for f in features if _passes(f["properties"], _CONF_HI)]

    # 2순위 — 보충
    if len(candidates) < 8:
        seen_ids = {p.get("id") for p in candidates}
        for f in features:
            p = f["properties"]
            if p.get("id") not in seen_ids and _passes(p, _CONF_LO):
                candidates.append(p)
            if len(candidates) >= 8:
                break

    # source_url 중복 제거
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for p in candidates:
        url = p.get("source_url") or ""
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        deduped.append(p)

    deduped.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
    top8 = deduped[:8]

    if not top8:
        data = {"items": []}
        _ticker_cache.update({"data": data, "expires_at": now + timedelta(seconds=30)})
        return data

    # 기사 헤드라인 병렬 fetch (Gemini 없음, HTTP GET만)
    headline_results = await asyncio.gather(
        *[fetch_headline(p.get("source_url", "")) for p in top8],
        return_exceptions=True,
    )

    items: list[dict] = []
    for props, hl_result in zip(top8, headline_results):
        headline = hl_result if isinstance(hl_result, str) and hl_result else None
        text     = _format_text(headline, props)
        if not text:
            continue
        items.append({
            "text":       text,
            "time_label": _time_label(props.get("timestamp", "")),
            "url":        props.get("source_url", ""),
        })

    logger.debug("[ticker] %d건 완료", len(items))

    data = {"items": items}
    _ticker_cache.update({"data": data, "expires_at": now + _TICKER_TTL})
    return data
