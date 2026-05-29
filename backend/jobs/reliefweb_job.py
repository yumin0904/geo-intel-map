"""
reliefweb_job.py — ReliefWeb RSS 30분 수집 잡

APScheduler에서 호출되는 동기 래퍼.
수집된 이벤트는 캐시 갱신용으로만 사용 (DB 저장 없음 — 30분 TTL이 소멸 기준).
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def run_reliefweb_batch() -> None:
    """ReliefWeb RSS 병렬 수집 + 캐시 invalidation.

    캐시는 layers.py의 _reliefweb_cache에서 TTL로 자동 갱신되므로
    이 잡은 단순히 캐시를 만료시켜 다음 API 호출 시 fresh fetch를 유도한다.
    """
    from api.layers import _reliefweb_cache
    from datetime import datetime, timezone

    # 캐시 만료 → 다음 /api/layers/reliefweb 호출 시 자동 갱신
    _reliefweb_cache["expires_at"] = datetime(1970, 1, 1, tzinfo=timezone.utc)
    logger.info("[reliefweb_job] 캐시 만료 — 다음 요청 시 fresh fetch")
