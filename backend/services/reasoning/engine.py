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
from .chain_verifier import verify_chain
from .agents import ALL_AGENTS, synthesize

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


async def run_reasoning_with_agents(
    event: dict,
    cascade_links: list[dict] | None = None,
) -> dict:
    """
    8단계 추론 + 6대 섹터 에이전트 병렬 심화 분석.

    기존 run_reasoning()을 기반으로 관련 섹터 에이전트를 추가 실행한다.
    결과는 IA 탭의 Gemini SSE 컨텍스트 조립에 사용된다.
    """
    # 1) 기존 8단계 실행
    base = await _run_stages(event, cascade_links or [])

    # 2) 관련 섹터 에이전트만 필터링 후 병렬 실행
    loop = asyncio.get_event_loop()
    relevant = [a for a in ALL_AGENTS if a.is_relevant(base)]

    if not relevant:
        logger.debug("[agents] 관련 섹터 에이전트 없음 — base 결과만 반환")
        return {**base, "agent_insights": [], "synthesis": synthesize(base, [])}

    agent_futs = [
        loop.run_in_executor(None, agent.analyze, event, base)
        for agent in relevant
    ]
    raw_results = await asyncio.gather(*agent_futs, return_exceptions=True)

    agent_results = []
    for agent, result in zip(relevant, raw_results):
        if isinstance(result, Exception):
            logger.warning("[agents] %s 실패: %s", agent.sector, result)
        else:
            agent_results.append(result)

    # 3) 종합 에이전트
    synthesis = synthesize(base, agent_results)

    logger.debug(
        "[agents] 완료 — 활성 섹터: %s, 교차 인사이트: %d개, 위험등급: %d/3",
        synthesis["active_sectors"],
        len(synthesis["cross_insights"]),
        synthesis["risk_grade"],
    )

    return {
        **base,
        "agent_insights": agent_results,
        "synthesis": synthesis,
    }


async def _run_stages(event: dict, cascade_links: list[dict]) -> dict:
    started = time.monotonic()
    props = event.get("properties", event)

    # ── Stage 1·2 (동기, 빠름) ────────────────────────────────────────────
    s1 = stage1_event_facts(event)
    s2 = stage2_sector_classification(event)

    sectors  = s2.get("inferred_sectors", []) + s2.get("explicit_tags", [])
    actors   = [a for a in s1.get("actors", []) if a]
    # stage1이 geofence 역조회로 region_code를 보정하므로 props 직접 읽기보다 우선
    region   = s1.get("region_code") or props.get("region_code", "") or ""
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

    stages_dict = {
        "1_facts": s1,
        "2_sector": s2,
        "3_history": s3,
        "4_macro": s4,
        "5_intent": s5,
        "6_sanctions": s6,
        "7_cascade": s7,
        "8_alliance": s8,
    }

    # ── 자기검증 (P5-6): 8단계 결과 BFS 반증 루프 ────────────────────────
    try:
        chain_verification = await loop.run_in_executor(
            None, verify_chain, stages_dict, region
        )
    except Exception as e:
        logger.warning("[reasoning] chain_verifier 실패: %s", e)
        chain_verification = {"error": str(e)}

    elapsed = round(time.monotonic() - started, 3)
    logger.debug("[reasoning] 완료 %.3fs — event=%s confidence=%.2f",
                 elapsed, event_id,
                 chain_verification.get("chain_confidence", 0) if isinstance(chain_verification, dict) else 0)

    return {
        "event_id": event_id,
        "elapsed_sec": elapsed,
        "stages": stages_dict,
        "chain_verification": chain_verification,
    }
