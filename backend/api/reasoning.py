"""
reasoning.py — 8단계 지정학 추론 API.

GET  /api/reasoning/{event_id}
  → 특정 이벤트의 8단계 추론 리포트 반환.
  → event_id는 ACLED·GDELT 이벤트 모두 수용.
  → 캐시: 10분 (동일 이벤트 반복 요청 방지)

POST /api/reasoning/batch
  → 복수 이벤트 ID를 받아 병렬 추론. 최대 5개.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.reasoning import run_reasoning

router = APIRouter(prefix="/api/reasoning", tags=["reasoning"])
logger = logging.getLogger(__name__)

# 10분 메모리 캐시 {event_id: (expires_at, report)}
_cache: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(minutes=10)


class BatchRequest(BaseModel):
    event_ids: list[str]


def _get_cached(event_id: str) -> dict | None:
    entry = _cache.get(event_id)
    if entry and datetime.now(timezone.utc) < entry[0]:
        return entry[1]
    return None


def _set_cached(event_id: str, report: dict) -> None:
    _cache[event_id] = (datetime.now(timezone.utc) + _CACHE_TTL, report)


async def _resolve_event(event_id: str) -> dict | None:
    """이벤트 ID로 원본 이벤트 dict를 조회한다.

    GDELT·ACLED 레이어 캐시에서 먼저 찾고, 캐시가 비어 있으면 레이어를 직접 fetch해 채운다.
    """
    from api.layers import _gdelt_cache, _conflict_cache, get_conflict_events, get_gdelt

    # 캐시가 비어 있으면 레이어 fetch로 채움 (서버 재시작 직후 등)
    if not _conflict_cache.get("geojson"):
        try:
            await get_conflict_events()
        except Exception:
            pass
    if not _gdelt_cache.get("geojson"):
        try:
            await get_gdelt()
        except Exception:
            pass

    # GDELT 레이어 캐시
    gdelt_geojson = _gdelt_cache.get("geojson") or {}
    for feat in gdelt_geojson.get("features", []):
        if feat.get("properties", {}).get("id") == event_id:
            return feat

    # ACLED 레이어 캐시
    conflict_geojson = _conflict_cache.get("geojson") or {}
    for feat in conflict_geojson.get("features", []):
        if feat.get("properties", {}).get("id") == event_id:
            return feat

    return None


async def _resolve_cascade_links(event_id: str) -> list[dict]:
    """cascade_links 테이블에서 관련 링크를 조회한다.

    DB 없거나 실패 시 빈 목록 반환.
    """
    try:
        from db.database import get_db_connection

        with get_db_connection() as conn:
            rows = conn.execute(
                """
                SELECT source_event_id, target_event_id, link_type,
                       correlation_score, time_delta_seconds
                FROM cascade_links
                WHERE source_event_id = ? OR target_event_id = ?
                LIMIT 20
                """,
                (event_id, event_id),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.debug("[reasoning] cascade_links 조회 실패: %s", e)
        return []


@router.get("/{event_id}")
async def get_reasoning_report(event_id: str, refresh: bool = Query(False)):
    """단일 이벤트의 8단계 추론 리포트."""
    if not refresh:
        cached = _get_cached(event_id)
        if cached:
            return {**cached, "cached": True}

    event = await _resolve_event(event_id)
    if event is None:
        # 이벤트를 찾지 못했을 때: 빈 shell로 추론 실행 (stage1이 부분 결과 반환)
        event = {"properties": {"id": event_id}, "geometry": {}}
        logger.warning("[reasoning] event_id 미발견, shell로 진행: %s", event_id)

    cascade_links = await _resolve_cascade_links(event_id)
    report = await run_reasoning(event, cascade_links)
    _set_cached(event_id, report)
    return report


@router.post("/batch")
async def batch_reasoning(req: BatchRequest):
    """최대 5개 이벤트의 병렬 추론."""
    ids = req.event_ids[:5]
    if not ids:
        raise HTTPException(status_code=400, detail="event_ids 필요")

    import asyncio
    results = await asyncio.gather(
        *[get_reasoning_report(eid) for eid in ids],
        return_exceptions=True,
    )
    return {
        "reports": [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]
    }
