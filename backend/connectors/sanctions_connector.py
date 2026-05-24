"""
sanctions_connector.py — 제재 레짐 정적 데이터 로더 (Step 8)

backend/config/sanctions.yaml을 읽어 Event로 정규화한다.
정적 데이터이므로 신뢰도는 1.0 (공개된 UN SC·OFAC·EU 결의 기반).

학습 이론:
  - Weaponized Interdependence (Farrell & Newman 2019): 경제적 상호의존을
    강압 수단으로 전환하는 메커니즘 — 제재는 그 공식 제도적 표현
  - Economic Coercion (Drezner 2011): 제재 위협 vs 실제 적용의 전략적 논리
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import yaml

from models.event import Event

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).parent.parent / "config" / "sanctions.yaml"


def load_sanctions() -> list[Event]:
    """
    sanctions.yaml에서 제재 레짐을 읽어 Event 리스트로 반환한다.

    각 레짐은 source_type="sanction", confidence_score=1.0 (공개 결의 기반).
    좌표가 없거나 0,0이면 제외한다.
    """
    try:
        data = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[Sanctions] YAML 로드 실패: %s", exc)
        return []

    regimes: list[dict[str, Any]] = data.get("regimes", [])
    events: list[Event] = []

    for r in regimes:
        evt = _to_event(r)
        if evt:
            events.append(evt)

    logger.info("[Sanctions] 로드 완료: %d개 레짐", len(events))
    return events


def _to_event(r: dict[str, Any]) -> Event | None:
    """단일 제재 레짐 dict → Event 정규화."""
    lat = r.get("lat")
    lon = r.get("lon")
    if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
        return None

    regime_id = r.get("id", str(uuid.uuid4()))
    bodies = r.get("sanctioning_bodies", [])
    year = r.get("year_established", 2000)

    # 제재 발효 연도를 타임스탬프로 변환
    ts = datetime(year, 1, 1, tzinfo=timezone.utc)

    # 주요 제재 기구 기반 구분 색상 힌트 (프론트 SanctionsLayer가 사용)
    if "UN" in bodies:
        sanction_type = "multilateral_un"
    elif len(bodies) >= 3:
        sanction_type = "multilateral_western"
    else:
        sanction_type = "unilateral"

    title = f"[제재] {r.get('target_name', regime_id)}"

    return Event(
        id=str(uuid.uuid4()),
        timestamp=ts,
        source_type="sanction",
        source_id=f"sanctions_{regime_id}",
        location=(float(lat), float(lon)),
        region_code=r.get("region_code"),
        severity=int(r.get("severity", 50)),
        title=title,
        description=r.get("description", ""),
        payload={
            "regime_id":          regime_id,
            "target_country":     r.get("target_country"),
            "target_name":        r.get("target_name"),
            "sanctioning_bodies": bodies,
            "year_established":   year,
            "trigger":            r.get("trigger", ""),
            "sectors":            r.get("sectors", []),
            "sanction_type":      sanction_type,
            "data_source":        "sanctions.yaml",
        },
        theory_tags=r.get("theory_tags", ["economic_coercion"]),
        confidence_score=1.0,  # 공개 UN SC·OFAC·EU 결의 기반 — 완전 검증
    )
