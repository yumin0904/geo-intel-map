"""
cascade.py — Cascade(연쇄 분석) API 라우터.

엔진이 만든 CascadeLink와 관련 이벤트(trigger·response)를 반환한다.
프론트엔드는 이 응답으로 지도 위 trigger→response 점선 화살표를 그린다.

ACLED + yfinance 호출이 느리므로 1시간 캐시(CLAUDE.md 성능 원칙: 매번 재계산 금지).
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from services.cascade.engine import build_cascade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cascade", tags=["cascade"])

# Cascade 결과 1시간 캐시 — ACLED(분쟁) + yfinance(유가) 호출 비용이 크다.
_CASCADE_TTL = timedelta(hours=1)
_cache: dict = {
    "result":     None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}


@router.get("/links")
async def get_cascade_links():
    """활성 룰을 평가해 인과 링크 + 관련 이벤트를 반환한다.

    응답 구조: {"links": [...], "events": [...], "metadata": {...}}
    연관 이론: Resource Weaponization (호르무즈 긴장 → 유가)
    """
    now = datetime.now(timezone.utc)
    if _cache["result"] is not None and now < _cache["expires_at"]:
        return _cache["result"]

    result = await build_cascade()
    _cache["result"] = result
    _cache["expires_at"] = now + _CASCADE_TTL
    return result
