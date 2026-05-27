"""
stats.py — 상단 2단 바 집계 통계 API.

GET /api/stats/tension    — 섹터별 긴장도 (ACLED 30일 × 0.7 + GDELT 24h × 0.3)
GET /api/stats/markets    — WTI·금·반도체·원달러 시장 지표 (5분 캐시)

피자지수는 프론트엔드(TopBarView.js)에서 tension 응답의 pizza_weight로 계산한다.
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
# ACLED 30일 평균: 자주 안 바뀜 → 1시간 캐시
# GDELT 실시간: 5분마다 새 데이터 → 5분 캐시
# 최종 혼합 결과: 5분 캐시
_acled_tension_cache: dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
_gdelt_tension_cache: dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
_tension_cache:       dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
_market_cache:        dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}

_ACLED_TTL  = timedelta(hours=1)
_GDELT_TTL  = timedelta(minutes=5)
_TENSION_TTL = timedelta(minutes=5)
_MARKET_TTL  = timedelta(minutes=5)

# ── 섹터-지역 매핑 ────────────────────────────────────────────────────────────
_REGION_SECTOR: dict[str, str] = {
    "bab_el_mandeb":   "중동",
    "hormuz":          "중동",
    "middle_east":     "중동",
    "suez":            "중동",
    "taiwan_strait":   "인태",
    "south_china_sea": "인태",
    "malacca":         "인태",
    "ukraine":         "유럽",
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

# 피자지수 가중치 — 지정학적 중요도 반영 (중동·인태 비중 높게)
_PIZZA_WEIGHTS: dict[str, float] = {
    "중동":    0.4,
    "인태":    0.3,
    "유럽":    0.2,
    "아프리카": 0.1,
}


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


def _parse_ts(ts_str: str) -> datetime | None:
    """ISO 타임스탬프 문자열 → UTC datetime. 실패 시 None."""
    try:
        ts = datetime.fromisoformat(ts_str)
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _severity_level(avg: float) -> str:
    """평균 severity → 색상 레벨 문자열."""
    if avg >= 80: return "critical"
    if avg >= 60: return "high"
    if avg >= 40: return "medium"
    return "low"


def _calc_acled_tensions(now: datetime) -> dict[str, list[float]]:
    """_conflict_cache에서 최근 30일 ACLED 이벤트 severity 수집."""
    from api.layers import _conflict_cache

    cutoff = now - timedelta(days=30)
    sevs: dict[str, list[float]] = {s: [] for s in _SECTORS}

    if _conflict_cache.get("geojson") is None:
        return sevs

    for feat in _conflict_cache["geojson"].get("features", []):
        props = feat.get("properties", {})
        ts = _parse_ts(props.get("timestamp") or props.get("event_date") or "")
        if ts and ts < cutoff:
            continue
        sector = _feature_to_sector(props)
        if sector:
            sevs[sector].append(float(props.get("severity", 0)))

    return sevs


def _calc_gdelt_tensions(now: datetime) -> dict[str, list[float]]:
    """_gdelt_cache에서 최근 24시간 + confidence≥0.8 이벤트 severity 수집."""
    from api.layers import _gdelt_cache

    cutoff = now - timedelta(hours=24)
    sevs: dict[str, list[float]] = {s: [] for s in _SECTORS}

    if _gdelt_cache.get("geojson") is None:
        return sevs

    for feat in _gdelt_cache["geojson"].get("features", []):
        props = feat.get("properties", {})
        if float(props.get("confidence_score", 0)) < 0.8:
            continue
        ts = _parse_ts(props.get("timestamp") or "")
        if ts and ts < cutoff:
            continue
        sector = _feature_to_sector(props)
        if sector:
            sevs[sector].append(float(props.get("severity", 0)))

    return sevs


@router.get("/tension")
async def get_tension():
    """섹터별 긴장도 (ACLED 30일 베이스라인 × 0.7 + GDELT 24h 실시간 × 0.3).

    응답에 pizza_weight 포함 → 프론트엔드가 가중 평균으로 피자지수 산출.
    """
    now = datetime.now(timezone.utc)
    if _tension_cache["data"] is not None and now < _tension_cache["expires_at"]:
        return _tension_cache["data"]

    # ACLED 서브캐시 (1시간)
    if _acled_tension_cache["data"] is None or now >= _acled_tension_cache["expires_at"]:
        _acled_tension_cache["data"] = _calc_acled_tensions(now)
        _acled_tension_cache["expires_at"] = now + _ACLED_TTL
        logger.debug("[tension] ACLED 서브캐시 갱신")

    # GDELT 서브캐시 (5분)
    if _gdelt_tension_cache["data"] is None or now >= _gdelt_tension_cache["expires_at"]:
        _gdelt_tension_cache["data"] = _calc_gdelt_tensions(now)
        _gdelt_tension_cache["expires_at"] = now + _GDELT_TTL
        logger.debug("[tension] GDELT 서브캐시 갱신")

    acled_sevs = _acled_tension_cache["data"]
    gdelt_sevs = _gdelt_tension_cache["data"]

    result = []
    for sector in _SECTORS:
        al = acled_sevs.get(sector, [])
        gl = gdelt_sevs.get(sector, [])
        acled_avg = sum(al) / len(al) if al else 0.0
        gdelt_avg = sum(gl) / len(gl) if gl else 0.0

        # 두 소스가 모두 있으면 혼합, 하나만 있으면 그 값 사용
        if al and gl:
            blended = acled_avg * 0.7 + gdelt_avg * 0.3
        elif al:
            blended = acled_avg
        elif gl:
            blended = gdelt_avg
        else:
            blended = 0.0

        result.append({
            "sector":       sector,
            "avg_severity": round(blended, 1),
            "event_count":  len(al) + len(gl),
            "level":        _severity_level(blended),
            "pizza_weight": _PIZZA_WEIGHTS[sector],
            # 디버그 breakdown
            "acled_avg":    round(acled_avg, 1),
            "gdelt_avg":    round(gdelt_avg, 1),
            "acled_count":  len(al),
            "gdelt_count":  len(gl),
        })
        logger.debug("[tension] %s: ACLED %.1f(%d) × 0.7 + GDELT %.1f(%d) × 0.3 = %.1f",
                     sector, acled_avg, len(al), gdelt_avg, len(gl), blended)

    _tension_cache["data"] = result
    _tension_cache["expires_at"] = now + _TENSION_TTL
    return result


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
