"""
gdelt_pipeline.py — GDELT 3-Stage Funnel 오케스트레이터

Stage 1 (gdelt_connector)  → 원시 필터링 (QuadClass·GoldsteinScale·NumMentions)
Stage 2 (news_cross_validator) → RSS 교차검증 (≥2매체 → confidence 0.8)
Stage 3 (이 모듈)          → 최종 confidence_score 확정 + GeoJSON 직렬화
Stage GKG (gdelt_gkg)      → 테마·톤 보강 (events와 source_url로 조인)

confidence_score 체계 (CLAUDE.md Phase 3):
  ACLED     = 1.0  (검증된 현장 데이터)
  교차검증   = 0.8  (GDELT + ≥2 RSS 매체 일치)
  GKG 보강   = 0.75 (단일 RSS + GKG 적대성 확인)
  미검증     = 0.5  (GDELT Stage 1만 통과)

프론트엔드에서 confidence < 0.8인 마커는 점선 테두리 + ⚠️ 뱃지 표시 예정.
"""
from __future__ import annotations

import asyncio
import logging

from connectors.gdelt_connector import (
    fetch_latest_gdelt,
    _actor_ko,
    _generate_description,
)
from connectors.gdelt_gkg import fetch_gkg_records, build_gkg_index
from models.event import Event
from services.verification_funnel import enrich_with_funnel
from utils.cameo_mapper import map_gkg_themes_to_tags

logger = logging.getLogger(__name__)


async def run_gdelt_pipeline() -> list[Event]:
    """
    3-Stage Funnel + GKG 보강 전체 실행.

    Returns:
        confidence_score가 확정된 Event 목록 (비어있을 수 있음)
    """
    # Stage 1 + GKG: 병렬 다운로드 (동일 15분 스냅샷)
    stage1_task = asyncio.create_task(fetch_latest_gdelt())
    gkg_task    = asyncio.create_task(fetch_gkg_records())

    stage1, gkg_records = await asyncio.gather(stage1_task, gkg_task, return_exceptions=True)

    # 예외 처리
    if isinstance(stage1, Exception):
        logger.warning("[Pipeline] Stage 1 실패: %s", stage1)
        stage1 = []
    if isinstance(gkg_records, Exception):
        logger.warning("[Pipeline] GKG 수집 실패: %s", gkg_records)
        gkg_records = []

    if not stage1:
        logger.info("[Pipeline] Stage 1 결과 없음 — 파이프라인 종료")
        return []

    logger.info("[Pipeline] Stage 1: %d건, GKG: %d건", len(stage1), len(gkg_records))

    # GKG 인덱스 빌드 (source_url → GkgRecord)
    gkg_index = build_gkg_index(gkg_records)

    # Stages 2-3: Verification Funnel
    stage2 = await enrich_with_funnel(stage1)

    # Stage GKG: source_url 조인으로 테마·톤 보강
    stage3: list[Event] = []
    for evt in stage2:
        source_url = evt.payload.get("source_url", "")
        gkg_rec    = gkg_index.get(source_url)

        # GKG 보강 적용
        if gkg_rec and gkg_rec.themes:
            gkg_tags = map_gkg_themes_to_tags(
                themes=gkg_rec.themes,
                tone=gkg_rec.tone,
                existing_instrument=evt.payload.get("intelligence_meta", {}).get("instrument_of_power"),
                existing_sector=evt.payload.get("intelligence_meta", {}).get("sector_lead"),
            )
            # payload에 GKG 데이터 추가
            updated_payload = {
                **evt.payload,
                "gkg_themes":           gkg_tags["top_themes"],
                "gkg_tone":             round(gkg_rec.tone, 2),
                "gkg_hostility":        gkg_tags["hostility_confirmed"],
                "gkg_theme_count":      gkg_tags["gkg_theme_count"],
            }
            # GKG 적대성 확인 시 미검증(0.5) 이벤트를 0.65로 상향
            new_conf = evt.confidence_score
            if gkg_tags["hostility_confirmed"] and evt.confidence_score < 0.7:
                new_conf = 0.65
                logger.debug("[GKG] %s → confidence 0.5→0.65 (적대성 확인)", evt.id[:8])

            evt = evt.model_copy(update={
                "payload":          updated_payload,
                "confidence_score": new_conf,
                "is_staging":       new_conf < 0.8,
            })

        # description 재생성: confidence 0.8 이상 승격 이벤트
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
            evt = evt.model_copy(update={"description": new_desc})

        stage3.append(evt)

    promoted = sum(1 for e in stage3 if not e.is_staging)
    staging  = len(stage3) - promoted
    gkg_hit  = sum(1 for e in stage3 if e.payload.get("gkg_themes"))
    logger.info(
        "[Pipeline] 완료 — 승격=%d, 버퍼=%d, GKG조인=%d, 합계=%d",
        promoted, staging, gkg_hit, len(stage3),
    )
    return stage3


def to_geojson(events: list[Event]) -> dict:
    """Event 목록 → GeoJSON FeatureCollection.

    is_staging=True인 이벤트는 제외 (대시보드 노출 차단, CLAUDE.md §16).
    confidence_score < 0.8인 Feature에는 unverified=True 프로퍼티 추가
    (프론트엔드 ⚠️ 뱃지·점선 테두리 렌더링용).
    """
    features = []
    for evt in events:
        if evt.is_staging:
            continue  # 검증 미달 자산은 대시보드에 노출하지 않음
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
                # GKG 보강 필드 (있는 경우만)
                "gkg_themes":    evt.payload.get("gkg_themes", []),
                "gkg_tone":      evt.payload.get("gkg_tone"),
                "gkg_hostility": evt.payload.get("gkg_hostility", False),
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}
