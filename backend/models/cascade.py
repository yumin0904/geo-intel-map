"""
cascade.py — Cascade(연쇄 분석)용 Pydantic 모델.

CLAUDE.md 3.2 Rule Book + 3.1 CascadeLink 기준.
룰은 YAML로 관리되고, 이 모델로 검증·정규화된다.
코드 수정 없이 cascade_rules.yaml에 룰만 추가하면 새 인과관계가 등록된다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RuleTrigger(BaseModel):
    """룰의 발동 조건 — 어떤 이벤트가 들어오면 cascade를 검사할지."""
    source_type: str          # "conflict" | "naval_activity" | ...
    region: str               # regions.yaml의 region_code (예: "hormuz")
    severity_min: int = 0     # 이 값 이상일 때만 트리거로 인정


class RuleResponse(BaseModel):
    """트리거 후 기대되는 반응 — 시장 지표 등의 예상 변동."""
    source_type: str          # 보통 "market"
    ticker: str               # yfinance 티커 (예: "CL=F" 원유선물)
    direction: Literal["up", "down"]
    window_hours: int         # 트리거 시점 이후 관찰 윈도우
    threshold_pct: float      # 이 %p 이상 움직여야 인과관계로 인정


class RuleTheory(BaseModel):
    """학습용 이론 메타데이터 — 비전공자 학습 도구이므로 룰마다 필수."""
    framework: str
    reference: str
    learning_note: str = ""


class CascadeRule(BaseModel):
    """cascade_rules.yaml의 룰 1개를 표현한다."""
    id: str
    name: str
    trigger: RuleTrigger
    expected_response: RuleResponse
    theory: RuleTheory


class CascadeLink(BaseModel):
    """엔진이 trigger 이벤트와 response 이벤트를 연결해 만든 인과 링크.

    CLAUDE.md 3.1 데이터 모델 기준. 시각화 레이어(지도 점선 화살표,
    타임라인, Cytoscape 그래프)가 이 구조를 소비한다.
    """
    id: str
    source_event_id: str            # 트리거가 된 이벤트 id
    target_event_id: str            # 반응(시장 변동) 이벤트 id
    time_delta_seconds: int
    correlation_score: float        # 0-1, Phase 2 초기엔 규칙 충족도 기반 단순값
    link_type: Literal["rule", "statistical", "manual"] = "rule"
    rule_id: str | None = None
    evidence: dict                  # 근거: 지역 매칭, 관찰된 변동률 등
    theory_ref: str | None = None   # 관련 이론 한 줄 (학습 노트)
