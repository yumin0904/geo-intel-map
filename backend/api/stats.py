"""
stats.py — 상단 2단 바 집계 통계 API.

GET /api/stats/tension    — 섹터별 평균 긴장도 (5분 캐시)
GET /api/stats/pizza-index — BigMac 지수 기반 구매력 피자지수 (1시간 캐시)
GET /api/stats/markets    — WTI·금·반도체·원달러 시장 지표 (5분 캐시)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

from fastapi import APIRouter

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger(__name__)

# ── 캐시 ──────────────────────────────────────────────────────────────────────
_tension_cache: dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
_pizza_cache:   dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
_market_cache:  dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}

_TENSION_TTL = timedelta(minutes=5)
_PIZZA_TTL   = timedelta(hours=1)
_MARKET_TTL  = timedelta(minutes=5)

# ── 섹터-국가 매핑 ────────────────────────────────────────────────────────────
# CLAUDE.md 5대 섹터 기준, region_code 우선 → country 폴백 순으로 판단한다.

_REGION_SECTOR: dict[str, str] = {
    # 섹터 2: 에너지 지정학 (호르무즈·바브엘만데브·수에즈) + 섹터 1 일부
    "hormuz":         "중동",
    "bab_el_mandeb":  "중동",
    "suez":           "중동",
    # 섹터 4: 인도-태평양 군사 대치
    "taiwan_strait":  "인태",
    "south_china_sea": "인태",
    "malacca":        "인태",
    # 섹터 5: 회색지대 (우크라이나 전쟁)
    "ukraine":        "유럽",
}

_COUNTRY_SECTOR: dict[str, str] = {
    # 중동
    "iran": "중동", "iraq": "중동", "israel": "중동", "lebanon": "중동",
    "syria": "중동", "saudi arabia": "중동", "yemen": "중동", "jordan": "중동",
    "egypt": "중동", "turkey": "중동", "palestine": "중동", "oman": "중동",
    "qatar": "중동", "bahrain": "중동", "kuwait": "중동",
    # 인태
    "myanmar": "인태", "philippines": "인태", "vietnam": "인태", "taiwan": "인태",
    "south korea": "인태", "north korea": "인태", "japan": "인태", "china": "인태",
    "indonesia": "인태", "malaysia": "인태", "thailand": "인태",
    "cambodia": "인태", "india": "인태", "bangladesh": "인태", "pakistan": "인태",
    # 유럽
    "ukraine": "유럽", "russia": "유럽", "belarus": "유럽", "moldova": "유럽",
    "georgia": "유럽", "armenia": "유럽", "azerbaijan": "유럽",
    "serbia": "유럽", "kosovo": "유럽",
    # 아프리카
    "nigeria": "아프리카", "ethiopia": "아프리카", "somalia": "아프리카",
    "democratic republic of congo": "아프리카", "sudan": "아프리카",
    "mali": "아프리카", "burkina faso": "아프리카", "mozambique": "아프리카",
    "cameroon": "아프리카", "central african republic": "아프리카",
    "south sudan": "아프리카", "libya": "아프리카",
}

_SECTORS = ["중동", "인태", "유럽", "아프리카"]


def _feature_to_sector(props: dict) -> str | None:
    """GeoJSON feature props → 섹터명. region_code 우선, country 폴백."""
    rc = (props.get("region_code") or "").lower()
    for region_key, sector in _REGION_SECTOR.items():
        if region_key in rc:
            return sector

    country = (props.get("country") or "").lower()
    for country_key, sector in _COUNTRY_SECTOR.items():
        if country_key in country:
            return sector

    return None


def _severity_level(avg: float) -> str:
    """평균 severity → 색상 레벨 문자열."""
    if avg >= 80:
        return "critical"
    if avg >= 60:
        return "high"
    if avg >= 40:
        return "medium"
    return "low"


@router.get("/tension")
async def get_tension():
    """섹터별 평균 긴장도.

    캐시된 conflict GeoJSON에서 집계. 캐시가 비어있으면 0을 반환하고,
    다음 호출에서 자동으로 채워진다 (conflict 레이어 defaultVisible=true).
    """
    now = datetime.now(timezone.utc)
    if _tension_cache["data"] is not None and now < _tension_cache["expires_at"]:
        return _tension_cache["data"]

    # layers 모듈 캐시에서 직접 읽기 (순환 import 방지를 위한 지연 import)
    from api.layers import _conflict_cache, _gdelt_cache

    sector_severities: dict[str, list[float]] = {s: [] for s in _SECTORS}

    for cache in (_conflict_cache, _gdelt_cache):
        if cache.get("geojson") is None:
            continue
        for feat in cache["geojson"].get("features", []):
            props = feat.get("properties", {})
            severity = float(props.get("severity", 0))
            sector = _feature_to_sector(props)
            if sector and sector in sector_severities:
                sector_severities[sector].append(severity)

    result = []
    for sector in _SECTORS:
        severities = sector_severities[sector]
        avg = sum(severities) / len(severities) if severities else 0.0
        result.append({
            "sector":       sector,
            "avg_severity": round(avg, 1),
            "event_count":  len(severities),
            "level":        _severity_level(avg),
        })

    _tension_cache["data"] = result
    _tension_cache["expires_at"] = now + _TENSION_TTL
    return result


# ── 피자지수 ──────────────────────────────────────────────────────────────────
# 한국 빅맥 가격(고정) + 실시간 환율로 구매력 지수를 계산한다.
# 100 = 미국과 동등, < 100 = 한국 원화 저평가(달러 대비 저렴)
_BIGMAC_KRW = 6_300   # 한국 빅맥 가격 추정치 (2024 기준, 원)
_BIGMAC_USD = 5.58    # 미국 빅맥 가격 (USD, 2024 기준)


def _fetch_pizza_sync() -> dict:
    """KRW=X 환율 기반 피자지수 동기 계산."""
    try:
        fi = yf.Ticker("KRW=X").fast_info
        krw_per_usd = float(fi.last_price)
    except Exception as e:
        logger.warning("[pizza] KRW=X 조회 실패: %s", e)
        # 폴백: 1380 고정값 (대략적 2024 환율)
        krw_per_usd = 1380.0

    bigmac_usd_korea = _BIGMAC_KRW / krw_per_usd
    pizza_index = (bigmac_usd_korea / _BIGMAC_USD) * 100

    return {
        "index":       round(pizza_index, 1),
        "krw_per_usd": round(krw_per_usd, 2),
        "label":       f"🍕 {pizza_index:.1f}",
    }


@router.get("/pizza-index")
async def get_pizza_index():
    """BigMac 지수 기반 한국 구매력 피자지수.

    100 = 미국과 동등한 구매력, < 100 = 원화 저평가 (달러 기준 한국이 저렴).
    환율은 yfinance KRW=X 실시간 데이터 사용.
    """
    now = datetime.now(timezone.utc)
    if _pizza_cache["data"] is not None and now < _pizza_cache["expires_at"]:
        return _pizza_cache["data"]

    data = await asyncio.to_thread(_fetch_pizza_sync)
    _pizza_cache["data"] = data
    _pizza_cache["expires_at"] = now + _PIZZA_TTL
    return data


# ── 시장 지표 ────────────────────────────────────────────────────────────────
_MARKET_TICKERS = [
    {"ticker": "CL=F",  "name": "WTI",   "unit": "$",  "emoji": "⛽"},
    {"ticker": "GLD",   "name": "금",     "unit": "$",  "emoji": "🥇"},
    {"ticker": "SOXX",  "name": "반도체", "unit": "$",  "emoji": "💾"},
    {"ticker": "KRW=X", "name": "원/달러", "unit": "₩", "emoji": "💴"},
]


def _fetch_quote_sync(ticker: str) -> dict | None:
    """단일 티커 시세(현재가·전일대비%) 동기 조회."""
    try:
        fi = yf.Ticker(ticker).fast_info
        price = float(fi.last_price)
        prev  = float(fi.previous_close)
        if prev == 0:
            return None
        change_pct = (price - prev) / prev * 100
        return {
            "price":      round(price, 2),
            "change_pct": round(change_pct, 2),
            "direction":  "up" if change_pct >= 0 else "down",
        }
    except Exception as e:
        logger.warning("[markets] %s 조회 실패: %s", ticker, e)
        return None


@router.get("/markets")
async def get_markets():
    """WTI·금·반도체·원달러 시장 지표 반환 (4개 티커 병렬 조회)."""
    now = datetime.now(timezone.utc)
    if _market_cache["data"] is not None and now < _market_cache["expires_at"]:
        return _market_cache["data"]

    tasks = [
        asyncio.to_thread(_fetch_quote_sync, m["ticker"])
        for m in _MARKET_TICKERS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    items = []
    for meta, result in zip(_MARKET_TICKERS, results):
        if isinstance(result, Exception) or result is None:
            items.append({**meta, "price": None, "change_pct": None, "direction": None})
        else:
            items.append({**meta, **result})

    _market_cache["data"] = items
    _market_cache["expires_at"] = now + _MARKET_TTL
    return items
