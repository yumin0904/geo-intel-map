"""
gdelt_pipeline.py — GDELT 3-Stage Funnel 오케스트레이터

Stage 1 (gdelt_connector)  → 원시 필터링 (QuadClass·GoldsteinScale·NumMentions)
Stage 2 (news_cross_validator) → RSS 교차검증 (≥2매체 → confidence 0.8)
Stage 3 (이 모듈)          → 최종 confidence_score 확정 + GeoJSON 직렬화

confidence_score 체계 (CLAUDE.md Phase 3):
  ACLED  = 1.0  (검증된 현장 데이터)
  교차검증 = 0.8  (GDELT + ≥2 RSS 매체 일치)
  미검증  = 0.5  (GDELT Stage 1만 통과)

프론트엔드에서 confidence < 0.8인 마커는 점선 테두리 + ⚠️ 뱃지 표시 예정.
"""
from __future__ import annotations

import logging

from connectors.gdelt_connector import (
    fetch_latest_gdelt,
    _actor_ko,
    _generate_description,
)
from connectors.news_cross_validator import cross_validate
from models.event import Event

logger = logging.getLogger(__name__)


async def run_gdelt_pipeline() -> list[Event]:
    """
    3-Stage Funnel 전체 실행.

    Returns:
        confidence_score가 확정된 Event 목록 (비어있을 수 있음)
    """
    # Stage 1: GDELT 다운로드 + 필터
    stage1 = await fetch_latest_gdelt()
    if not stage1:
        logger.info("[Pipeline] Stage 1 결과 없음 — 파이프라인 종료")
        return []

    logger.info("[Pipeline] Stage 1 완료: %d개 이벤트", len(stage1))

    # Stage 2: RSS 교차검증 (네트워크 실패 시 stage1 결과 그대로 반환)
    stage2 = await cross_validate(stage1)

    # Stage 3: confidence 변경된 이벤트의 description 재생성
    # cross_validate가 confidence 0.5→0.8로 올린 경우 "미검증" → "교차검증 완료" 반영
    stage3: list[Event] = []
    for evt in stage2:
        if evt.confidence_score >= 0.8:
            root_code = evt.payload.get("event_code", "")[:2]
            new_desc  = _generate_description(
                actor1=evt.payload.get("actor1", ""),
                actor2=evt.payload.get("actor2", ""),
                event_root_code=root_code,
                region_code=evt.region_code,
                geo_name=evt.payload.get("geo_name", ""),
                goldstein=evt.payload.get("goldstein_scale", 0.0),
                severity=evt.severity,
                confidence_score=evt.confidence_score,
            )
            stage3.append(evt.model_copy(update={"description": new_desc}))
        else:
            stage3.append(evt)

    confirmed  = sum(1 for e in stage3 if e.confidence_score >= 0.8)
    unverified = len(stage3) - confirmed
    logger.info(
        "[Pipeline] 완료 — 교차검증=%d, 미검증=%d, 합계=%d",
        confirmed, unverified, len(stage3),
    )
    return stage3


def to_geojson(events: list[Event]) -> dict:
    """
    Event 목록 → GeoJSON FeatureCollection.

    confidence_score < 0.8인 Feature에는 'unverified': True 프로퍼티 추가
    (프론트엔드 ⚠️ 뱃지·점선 테두리 렌더링용).
    """
    features = []
    for evt in events:
        lat, lon = evt.location
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(lon, 5), round(lat, 5)],
            },
            "properties": {
                "id":               evt.id,
                "source_id":        evt.source_id,
                "title":            evt.title,
                "description":      evt.description,
                "severity":         evt.severity,
                "source_type":      evt.source_type,
                "timestamp":        evt.timestamp.isoformat(),
                "region_code":      evt.region_code,
                "theory_tags":      evt.theory_tags,
                "confidence_score":  evt.confidence_score,
                "importance_score":  evt.importance_score,
                "unverified":        evt.confidence_score < 0.8,
                "data_source":      "GDELT",
                # payload 핵심 필드만 노출 (전체 덤프 금지)
                "quad_class":    evt.payload.get("quad_class"),
                "goldstein":     evt.payload.get("goldstein_scale"),
                "num_mentions":  evt.payload.get("num_mentions"),
                "source_url":    evt.payload.get("source_url", ""),
                "actor1":        evt.payload.get("actor1", ""),
                "actor2":        evt.payload.get("actor2", ""),
                "actor1_ko":     evt.payload.get("actor1_ko", ""),
                "actor2_ko":     evt.payload.get("actor2_ko", ""),
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}
