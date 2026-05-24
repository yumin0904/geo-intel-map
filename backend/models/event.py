"""
event.py — 모든 레이어의 공통 Event Pydantic 모델
CLAUDE.md 3.1 데이터 모델 기준으로 구현.
레이어가 무엇이든(분쟁·시장·인프라·해군) 이 모델로 정규화된다.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Event(BaseModel):
    id: str                        # uuid4
    timestamp: datetime            # UTC
    source_type: str               # "conflict" | "market" | "infra" | "naval" | "cyber"
    source_id: str                 # 원본 소스의 식별자 (예: ACLED event_id_cnty)
    location: tuple[float, float]  # (lat, lon), 좌표 없으면 (0, 0) + region_code 사용
    region_code: str | None        # ISO 또는 자체 코드 (예: "taiwan_strait")
    severity: int                  # 0-100, 소스별 정규화된 심각도
    title: str
    description: str               # 500자 이하 요약
    payload: dict                  # 소스별 원본 필드 보존 (Cascade 분석용)
    theory_tags: list[str]         # ["A2AD", "gray_zone", "hybrid_warfare", ...]
    confidence_score: float = 1.0  # ACLED=1.0, 교차검증=0.8, GDELT 미검증=0.5
    importance_score: float = 0.0  # 복합 중요도 0-1 (severity·recency·cascade·반복·gdelt)
    cluster_count: int = 1         # 지역+7일+inter1 기준 통합된 원본 이벤트 수
