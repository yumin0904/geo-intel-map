"""
8단계 지정학 추론 엔진 오케스트레이터.

run_reasoning(event_dict, cascade_links) → ReasoningReport

동기 단계 (1·2·3·6·7·8): asyncio.gather 내 run_in_executor
비동기 단계 (4·5): 직접 await
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .stages import (
    stage1_event_facts,
    stage2_sector_classification,
    stage3_historical_comparison,
    stage4_macro_variables,
    stage5_justification_intent,
    stage6_institutional_constraints,
    stage7_temporal_cascade,
    stage8_alliance_spread,
)

logger = logging.getLogger(__name__)


class ReasoningEngine:
    """8단계 추론 엔진. 인스턴스 없이 run_reasoning()으로 직접 호출 가능."""

    async def analyze(
        self,
        event: dict,
        cascade_links: list[dict] | None = None,
    ) -> dict:
        return await _run_stages(event, cascade_links or [])


async def run_reasoning(
    event: dict,
    cascade_links: list[dict] | None = None,
) -> dict:
    """8단계 추론 실행 진입점."""
    return await _run_stages(event, cascade_links or [])


async def _run_stages(event: dict, cascade_links: list[dict]) -> dict:
    started = time.monotonic()
    props = event.get("properties", event)

    # ── Stage 1·2 (동기, 빠름) ────────────────────────────────────────────
    s1 = stage1_event_facts(event)
    s2 = stage2_sector_classification(event)

    sectors = s2.get("inferred_sectors", []) + s2.get("explicit_tags", [])
    actors  = [a for a in s1.get("actors", []) if a]
    region  = props.get("region_code", "")
    event_id = s1.get("event_id", "")

    # ── Stage 3·5·6·7·8 (동기 or 즉시 결과) ──────────────────────────────
    loop = asyncio.get_event_loop()

    # 동기 함수들은 executor에서 실행 (블로킹 YAML 파싱 방지)
    s3_fut = loop.run_in_executor(None, stage3_historical_comparison, event, sectors)
    s5_fut = loop.run_in_executor(None, stage5_justification_intent, event, actors)
    s6_fut = loop.run_in_executor(None, stage6_institutional_constraints, actors, sectors)
    s7_fut = loop.run_in_executor(None, stage7_temporal_cascade, event_id, cascade_links)
    s8_fut = loop.run_in_executor(None, stage8_alliance_spread, actors, region)

    # ── Stage 4 (비동기, yfinance HTTP) ─────────────────────────────────
    s4_fut = stage4_macro_variables(sectors, region)

    # 전체 병렬 실행
    results = await asyncio.gather(s3_fut, s4_fut, s5_fut, s6_fut, s7_fut, s8_fut, return_exceptions=True)
    s3, s4, s5, s6, s7, s8 = [
        r if not isinstance(r, Exception) else {"error": str(r)}
        for r in results
    ]

    elapsed = round(time.monotonic() - started, 3)
    logger.debug("[reasoning] 완료 %.3fs — event=%s", elapsed, event_id)

    return {
        "event_id": event_id,
        "elapsed_sec": elapsed,
        "stages": {
            "1_facts": s1,
            "2_sector": s2,
            "3_history": s3,
            "4_macro": s4,
            "5_intent": s5,
            "6_sanctions": s6,
            "7_cascade": s7,
            "8_alliance": s8,
        },
    }
