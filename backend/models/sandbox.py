"""
분석실(Sandbox Lab) 데이터 스키마.

사용자가 노드와 엣지로 직접 가설을 구성하는 인과 캔버스를 위한 모델.
지도 뷰의 Event/CascadeLink와 분리하여, '검증된 인과'와 '가설'을 구분한다.
"""
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


# 노드 타입: 사건(분쟁/군사) / 지표(시장) / 결과(정책·외교 반응)
SandboxNodeType = Literal["event", "indicator", "outcome"]

# 엣지 유형: 사용자가 주장하는 인과의 종류
SandboxEdgeKind = Literal["causes", "correlates", "blocks", "amplifies"]


class SandboxNode(BaseModel):
    """분석실 캔버스의 단일 노드.

    실제 Event를 참조할 수도 있고(event_ref), 사용자가 자유롭게 가정한
    가상의 노드일 수도 있다(event_ref=None).
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    canvas_id: str  # 어느 캔버스(가설)에 속하는지
    node_type: SandboxNodeType
    label: str  # 사용자가 붙인 한국어 이름 (예: "TSMC 주가 -3%")

    # 캔버스 상 좌표 (지도 좌표 아님 - 분석실 평면)
    x: float
    y: float

    # 실제 데이터 참조 (선택)
    event_ref: str | None = None  # Event.id 또는 ticker 심볼
    region_code: str | None = None  # 지도 Deep Link용
    theory_tags: list[str] = Field(default_factory=list)

    # 사용자 메모
    note: str = ""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("노드 라벨은 비어 있을 수 없습니다")
        return v.strip()


class SandboxEdge(BaseModel):
    """노드 간 인과 연결.

    correlation_score는 사용자가 주관적으로 부여(0-1).
    엔진이 통계 검증한 경우 verified=True로 표시.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    canvas_id: str
    source_node_id: str
    target_node_id: str
    kind: SandboxEdgeKind = "causes"

    # 사용자 가설 강도
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # sandbox_solver가 실제 cascade 데이터로 검증한 결과
    verified: bool = False
    verification_score: float | None = None  # 0-1, Granger or correlation
    verified_at: datetime | None = None

    # 어떤 cascade rule이 이 엣지를 뒷받침하는지 (있으면)
    supporting_rule_id: str | None = None

    note: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("source_node_id")
    @classmethod
    def no_self_loop(cls, v: str, info) -> str:
        # 같은 노드를 source/target으로 지정 방지
        target = info.data.get("target_node_id")
        if target and v == target:
            raise ValueError("source와 target은 같은 노드일 수 없습니다")
        return v


class SandboxCanvas(BaseModel):
    """하나의 가설 = 하나의 캔버스. 여러 노드와 엣지를 묶는 컨테이너."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    hypothesis: str = ""  # 사용자가 검증하려는 가설 한 문장
    sector_tag: str | None = None  # 5대 섹터 중 하나

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SandboxCanvasFull(BaseModel):
    """캔버스 + 소속 노드·엣지 일괄 조회용 응답 모델."""

    canvas: SandboxCanvas
    nodes: list[SandboxNode]
    edges: list[SandboxEdge]
