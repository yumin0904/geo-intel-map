"""
intelligence.py — 7대 축 다차원 태그 매트릭스 Pydantic 모델

CLAUDE.md §15 기준:
  form_type       : 지식 자산 유형 (GDELT 이벤트는 항상 data_point)
  geopol_region   : 지정학 지역 코드 (region_code와 동일값 사용)
  sector_lead     : 5대 섹터 중 주도 섹터
  temporal_era    : 사건이 속한 시대 배경
  level_of_analysis: Waltz 3수준 (systemic/state_domestic/non_state)
  instrument_of_power: DIME 프레임워크
  strategic_posture  : Snyder 동맹 딜레마 — 현상유지 vs 현상타파
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class IntelligenceMetadata(BaseModel):
    # 축 1: 지식 자산 유형 — 이벤트 데이터는 항상 data_point
    form_type: Literal["concept", "case_study", "norm", "data_point"] = "data_point"

    # 축 2: 지정학 지역 (regions.yaml 코드와 동일, None이면 미분류)
    geopol_region: str | None = None

    # 축 3: 5대 섹터 주도 분류
    sector_lead: Literal["maritime", "energy", "techno", "alliance", "gray_zone"] | None = None

    # 축 4: 시대 배경 — hot은 최근 7일 이내 이벤트
    temporal_era: Literal["cold_war", "post_cold", "us_china_rivalry", "hot"] = "us_china_rivalry"

    # 축 5: Waltz 분석 수준
    level_of_analysis: Literal["systemic", "state_domestic", "non_state"] = "state_domestic"

    # 축 6: DIME 권력 수단
    instrument_of_power: Literal["diplomatic", "informational", "military", "economic"] = "informational"

    # 축 7: Snyder 전략 태세 — GoldsteinScale ≤ -5 → revisionist
    strategic_posture: Literal["status_quo", "revisionist"] = "status_quo"
