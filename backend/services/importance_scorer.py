"""
backend/services/importance_scorer.py

ACLED 이벤트 복합 중요도 점수 계산 + 지역-기간-행위자 기반 클러스터링.

importance_score 구성요소 (가중합 = 1.0):
  severity        × 0.3  severity / 100
  recency         × 0.3  오늘=1.0, 30일전=0.0 선형 감소
  cascade_hit     × 0.2  cascade_rules.yaml 트리거 지역이면 1.0
  repeat_region   × 0.1  동일 region 30일 내 반복 횟수 / 10 (상한 1.0)
  gdelt_confirmed × 0.1  GDELT가 같은 지역을 보도한 경우 1.0

클러스터링 기준:
  동일 region_code + 7일 이내 + 동일 inter1(행위자 유형)
  → 대표 1개(severity 최고값)로 통합, cluster_count에 원본 수 기록
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from models.event import Event

logger = logging.getLogger(__name__)

_CASCADE_RULES_PATH = Path(__file__).parent.parent / "config" / "cascade_rules.yaml"

# cascade_rules.yaml에서 trigger.region 목록을 읽어 캐싱
_CASCADE_TRIGGER_REGIONS: Optional[frozenset] = None


def _load_cascade_regions() -> frozenset:
    global _CASCADE_TRIGGER_REGIONS
    if _CASCADE_TRIGGER_REGIONS is not None:
        return _CASCADE_TRIGGER_REGIONS
    try:
        rules = yaml.safe_load(_CASCADE_RULES_PATH.read_text(encoding="utf-8")) or []
        regions = {
            r.get("trigger", {}).get("region")
            for r in rules
            if r.get("trigger", {}).get("region")
        }
        _CASCADE_TRIGGER_REGIONS = frozenset(regions)
        logger.debug("[importance] cascade trigger regions: %s", _CASCADE_TRIGGER_REGIONS)
    except Exception as exc:
        logger.warning("[importance] cascade_rules.yaml 읽기 실패: %s", exc)
        _CASCADE_TRIGGER_REGIONS = frozenset()
    return _CASCADE_TRIGGER_REGIONS


def score_events(
    events: list[Event],
    gdelt_regions: frozenset[str],
    ref_time: Optional[datetime] = None,
) -> list[Event]:
    """
    events 배열 전체를 받아 importance_score를 in-place로 채운 뒤 반환.

    Args:
        events:        ACLED connector에서 반환된 Event 리스트 (이미 클러스터링 완료)
        gdelt_regions: GDELT GeoJSON에서 추출한 region_code 집합
        ref_time:      미사용 (하위 호환 유지용으로만 존재)
    """
    if not events:
        return events

    cascade = _load_cascade_regions()

    # recency: 데이터셋 내 상대적 최신순 정규화
    # 절대 시간 기준(오늘 - 30일)은 시스템 시계와 데이터 날짜가 다르면 항상 0이 되므로,
    # 보유 데이터 내 min/max timestamp 기준으로 정규화한다.
    timestamps = [e.timestamp.timestamp() for e in events]
    ts_min = min(timestamps)
    ts_max = max(timestamps)
    ts_range = ts_max - ts_min  # 0이면 단일 이벤트 → 모두 1.0

    # repeat_region: 같은 region_code 등장 횟수 집계
    region_counts: dict[str, int] = {}
    for e in events:
        if e.region_code:
            region_counts[e.region_code] = region_counts.get(e.region_code, 0) + 1

    scored: list[Event] = []
    for e in events:
        sev_s   = e.severity / 100.0
        # 데이터 내 상대적 최신순: 가장 최근 = 1.0, 가장 오래된 = 0.0
        rec_s   = (e.timestamp.timestamp() - ts_min) / ts_range if ts_range > 0 else 1.0
        casc_s  = 1.0 if e.region_code in cascade        else 0.0
        rep_s   = min(1.0, region_counts.get(e.region_code, 0) / 10.0)
        gdelt_s = 1.0 if e.region_code in gdelt_regions  else 0.0

        score = (
            sev_s   * 0.3 +
            rec_s   * 0.3 +
            casc_s  * 0.2 +
            rep_s   * 0.1 +
            gdelt_s * 0.1
        )

        # Pydantic v2: model_copy로 불변 필드 업데이트
        scored.append(e.model_copy(update={
            "importance_score": round(min(1.0, score), 4),
            "payload": {
                **e.payload,
                "_score_breakdown": {
                    "severity":        round(sev_s   * 0.3, 4),
                    "recency":         round(rec_s   * 0.3, 4),
                    "cascade_hit":     round(casc_s  * 0.2, 4),
                    "repeat_region":   round(rep_s   * 0.1, 4),
                    "gdelt_confirmed": round(gdelt_s * 0.1, 4),
                },
            },
        }))

    return scored


def score_gdelt_events(events: list[Event]) -> list[Event]:
    """GDELT 이벤트 importance_score 계산.

    ACLED 스코어와 다른 가중치를 사용한다:
      severity        × 0.3  (Goldstein → 0-100 정규화된 값)
      recency         × 0.4  (GDELT는 15분 단위 실시간 → 최신성 가중치 높임)
      confidence_score × 0.3 (0.8=교차검증, 0.5=미검증)
      cascade_hit / repeat_region = 0  (GDELT는 region 매칭이 약함)

    recency도 ACLED와 동일하게 데이터셋 내 상대적 최신순 정규화.
    """
    if not events:
        return events

    timestamps = [e.timestamp.timestamp() for e in events]
    ts_min  = min(timestamps)
    ts_max  = max(timestamps)
    ts_range = ts_max - ts_min

    scored: list[Event] = []
    for e in events:
        sev_s  = e.severity / 100.0
        rec_s  = (e.timestamp.timestamp() - ts_min) / ts_range if ts_range > 0 else 1.0
        conf_s = e.confidence_score  # 0.8(교차검증) or 0.5(미검증)

        score = sev_s * 0.3 + rec_s * 0.4 + conf_s * 0.3

        scored.append(e.model_copy(update={
            "importance_score": round(min(1.0, score), 4),
            "payload": {
                **e.payload,
                "_score_breakdown": {
                    "severity":         round(sev_s  * 0.3, 4),
                    "recency":          round(rec_s  * 0.4, 4),
                    "confidence":       round(conf_s * 0.3, 4),
                },
            },
        }))

    return scored


def cluster_events(events: list[Event]) -> list[Event]:
    """
    동일 region_code + 7일 이내 + 동일 inter1 그룹을 대표 이벤트 1개로 통합.

    - 대표 이벤트: 그룹 내 severity 최고값
    - cluster_count: 통합된 원본 이벤트 수
    - 좌표 없는 이벤트(lat=lon=0)와 region_code=None은 클러스터링 제외(단독 유지)
    """
    _WINDOW_DAYS = 7

    # 클러스터 키: (region_code, inter1, week_bucket)
    # week_bucket = timestamp를 7일 단위로 내림 (epoch 기준 정수 나눔)
    clusters: dict[tuple, list[Event]] = {}
    unclustered: list[Event] = []

    for e in events:
        lat, lon = e.location
        inter1   = e.payload.get("inter1", 0)
        rc       = e.region_code

        if not rc or (lat == 0.0 and lon == 0.0):
            unclustered.append(e)
            continue

        epoch_days = int(e.timestamp.timestamp() / 86_400)
        bucket     = epoch_days // _WINDOW_DAYS

        key = (rc, inter1, bucket)
        clusters.setdefault(key, []).append(e)

    result: list[Event] = []
    for group in clusters.values():
        if len(group) == 1:
            result.append(group[0])
            continue

        # 대표: severity 최고값
        representative = max(group, key=lambda e: e.severity)
        result.append(representative.model_copy(update={
            "cluster_count": len(group),
        }))

    result.extend(unclustered)
    return result
