"""
분석실(Sandbox Lab) CRUD API.

캔버스 단위로 가설을 저장/조회하며, 노드·엣지 변경은 캔버스 ID 하위에서 처리.
DB는 backend/db/sandbox.db (SQLite). 동시 편집은 단일 사용자 가정으로 lock 없음.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException, status

from models.sandbox import (
    SandboxCanvas,
    SandboxCanvasFull,
    SandboxEdge,
    SandboxNode,
)
from services.cascade.sandbox_solver import verify_sandbox_hypothesis

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

# DB 경로는 프로젝트 루트 기준 고정. 마이그레이션은 첫 호출 시 lazy 생성.
_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "sandbox.db"


# ---------- DB 헬퍼 (단일 파일 라우터에서 직접 관리) ----------

@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    """짧은 트랜잭션 단위 connection. 사용 후 자동 close."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        _ensure_schema(con)
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _ensure_schema(con: sqlite3.Connection) -> None:
    """첫 호출 시 테이블 생성. 이미 있으면 no-op."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS canvases (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            hypothesis TEXT DEFAULT '',
            sector_tag TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            canvas_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            FOREIGN KEY (canvas_id) REFERENCES canvases(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS edges (
            id TEXT PRIMARY KEY,
            canvas_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            FOREIGN KEY (canvas_id) REFERENCES canvases(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_canvas ON nodes(canvas_id);
        CREATE INDEX IF NOT EXISTS idx_edges_canvas ON edges(canvas_id);
        """
    )


def _row_to_canvas(row: sqlite3.Row) -> SandboxCanvas:
    return SandboxCanvas(
        id=row["id"],
        title=row["title"],
        hypothesis=row["hypothesis"],
        sector_tag=row["sector_tag"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------- 캔버스 CRUD ----------

@router.get("/canvases", response_model=list[SandboxCanvas])
def list_canvases() -> list[SandboxCanvas]:
    """사용자의 모든 가설 캔버스 목록 (최신 수정순)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM canvases ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_canvas(r) for r in rows]


@router.post(
    "/canvases",
    response_model=SandboxCanvas,
    status_code=status.HTTP_201_CREATED,
)
def create_canvas(canvas: SandboxCanvas) -> SandboxCanvas:
    """새 가설 캔버스 생성. id가 비어 오면 모델 default_factory가 생성."""
    with _conn() as con:
        con.execute(
            """
            INSERT INTO canvases (id, title, hypothesis, sector_tag, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                canvas.id,
                canvas.title,
                canvas.hypothesis,
                canvas.sector_tag,
                canvas.created_at.isoformat(),
                canvas.updated_at.isoformat(),
            ),
        )
    return canvas


@router.get("/canvases/{canvas_id}", response_model=SandboxCanvasFull)
def get_canvas_full(canvas_id: str) -> SandboxCanvasFull:
    """캔버스 + 노드 + 엣지 일괄 조회 (프론트 초기 렌더용 단일 호출)."""
    with _conn() as con:
        canvas_row = con.execute(
            "SELECT * FROM canvases WHERE id = ?", (canvas_id,)
        ).fetchone()
        if canvas_row is None:
            raise HTTPException(status_code=404, detail="캔버스를 찾을 수 없습니다")

        node_rows = con.execute(
            "SELECT payload FROM nodes WHERE canvas_id = ?", (canvas_id,)
        ).fetchall()
        edge_rows = con.execute(
            "SELECT payload FROM edges WHERE canvas_id = ?", (canvas_id,)
        ).fetchall()

    return SandboxCanvasFull(
        canvas=_row_to_canvas(canvas_row),
        nodes=[SandboxNode(**json.loads(r["payload"])) for r in node_rows],
        edges=[SandboxEdge(**json.loads(r["payload"])) for r in edge_rows],
    )


@router.delete("/canvases/{canvas_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_canvas(canvas_id: str) -> None:
    """캔버스 삭제. CASCADE로 노드·엣지 동시 삭제."""
    with _conn() as con:
        result = con.execute("DELETE FROM canvases WHERE id = ?", (canvas_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="캔버스를 찾을 수 없습니다")


# ---------- 노드 CRUD (캔버스 하위) ----------

@router.post(
    "/canvases/{canvas_id}/nodes",
    response_model=SandboxNode,
    status_code=status.HTTP_201_CREATED,
)
def upsert_node(canvas_id: str, node: SandboxNode) -> SandboxNode:
    """노드 생성 또는 업데이트 (id 충돌 시 REPLACE).

    프론트엔드 드래그 이동 시마다 호출되므로 idempotent 보장.
    """
    if node.canvas_id != canvas_id:
        raise HTTPException(
            status_code=400, detail="URL의 canvas_id와 본문의 canvas_id가 일치해야 합니다"
        )
    with _conn() as con:
        # 부모 캔버스 존재 확인 (FK이지만 명확한 404 메시지 위해)
        exists = con.execute(
            "SELECT 1 FROM canvases WHERE id = ?", (canvas_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="캔버스를 찾을 수 없습니다")

        con.execute(
            "INSERT OR REPLACE INTO nodes (id, canvas_id, payload) VALUES (?, ?, ?)",
            (node.id, canvas_id, node.model_dump_json()),
        )
        # 캔버스 갱신 타임스탬프
        con.execute(
            "UPDATE canvases SET updated_at = ? WHERE id = ?",
            (node.updated_at.isoformat(), canvas_id),
        )
    return node


@router.delete(
    "/canvases/{canvas_id}/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_node(canvas_id: str, node_id: str) -> None:
    """노드 삭제. 연결된 엣지도 동반 삭제 (orphan edge 방지)."""
    with _conn() as con:
        # 연결 엣지 먼저 제거
        edge_rows = con.execute(
            "SELECT id, payload FROM edges WHERE canvas_id = ?", (canvas_id,)
        ).fetchall()
        for er in edge_rows:
            edge = json.loads(er["payload"])
            if edge["source_node_id"] == node_id or edge["target_node_id"] == node_id:
                con.execute("DELETE FROM edges WHERE id = ?", (er["id"],))

        result = con.execute(
            "DELETE FROM nodes WHERE id = ? AND canvas_id = ?", (node_id, canvas_id)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="노드를 찾을 수 없습니다")


# ---------- 엣지 CRUD ----------

@router.post(
    "/canvases/{canvas_id}/edges",
    response_model=SandboxEdge,
    status_code=status.HTTP_201_CREATED,
)
def upsert_edge(canvas_id: str, edge: SandboxEdge) -> SandboxEdge:
    """엣지 생성/업데이트. verified 필드는 sandbox_solver만 수정해야 하지만,
    PoC 단계에서는 클라이언트 입력을 그대로 신뢰 (학습용 단일 사용자 가정)."""
    if edge.canvas_id != canvas_id:
        raise HTTPException(
            status_code=400, detail="URL의 canvas_id와 본문의 canvas_id가 일치해야 합니다"
        )
    with _conn() as con:
        # 양 끝 노드 존재 확인 (참조 무결성)
        for nid in (edge.source_node_id, edge.target_node_id):
            row = con.execute(
                "SELECT 1 FROM nodes WHERE id = ? AND canvas_id = ?", (nid, canvas_id)
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=400, detail=f"노드 {nid} 가 캔버스에 존재하지 않습니다"
                )

        con.execute(
            "INSERT OR REPLACE INTO edges (id, canvas_id, payload) VALUES (?, ?, ?)",
            (edge.id, canvas_id, edge.model_dump_json()),
        )
    return edge


@router.delete(
    "/canvases/{canvas_id}/edges/{edge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_edge(canvas_id: str, edge_id: str) -> None:
    """엣지 단건 삭제."""
    with _conn() as con:
        result = con.execute(
            "DELETE FROM edges WHERE id = ? AND canvas_id = ?", (edge_id, canvas_id)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="엣지를 찾을 수 없습니다")


# ---------- 가설 검증 ─────────────────────────────────────────────────


@router.post("/canvases/{canvas_id}/verify")
def verify_hypothesis(canvas_id: str, canvas_full: SandboxCanvasFull) -> dict:
    """
    사용자 캔버스 가설을 cascade_rules.yaml과 비교해 검증.

    요청: canvas_full (노드+엣지 포함)
    응답: 룰 매칭 점수, 추천 규칙, 개선 제안
    """
    if canvas_full.canvas.id != canvas_id:
        raise HTTPException(
            status_code=400, detail="URL의 canvas_id와 본문의 canvas_id가 일치해야 합니다"
        )

    try:
        result = verify_sandbox_hypothesis(canvas_full)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검증 실패: {str(e)}")

    top_match = None
    if result.rule_matches:
        m = result.rule_matches[0]
        top_match = {
            "rule_id": m.rule_id,
            "rule_name": m.rule_name,
            "match_score": round(m.match_score, 3),
            "theory_framework": m.theory_framework,
            "missing_nodes": m.missing_nodes,
        }

    return {
        "canvas_id": result.canvas_id,
        "total_score": round(result.total_score, 3),
        "num_matches": len(result.rule_matches),
        "confidence_level": result.confidence_level,
        "theory_tags_found": sorted(list(result.theory_tags_found)),
        "gaps": result.gaps,
        "top_match": top_match,
        "all_matches": [
            {
                "rule_id": m.rule_id,
                "rule_name": m.rule_name,
                "match_score": round(m.match_score, 3),
                "theory_framework": m.theory_framework,
            }
            for m in result.rule_matches
        ],
    }


# ---------- 튜토리얼 시드 ─────────────────────────────────────────────────────

# 고정 ID — 재시작해도 중복 삽입되지 않도록 INSERT OR IGNORE 사용
_TUTORIAL_CANVAS_ID = "tutorial-red-sea"

# Weaponized Interdependence 이론: 에너지 공급망 의존도가 정치적 레버리지로 전환되는 구조
_TUTORIAL_NODES = [
    {
        "id": "t-n1", "canvas_id": _TUTORIAL_CANVAS_ID,
        "node_type": "event",
        "label": "후티 공격 (바브엘만데브)",
        "x": 80.0, "y": 220.0,
        "region_code": "bab_el_mandeb",
        "theory_tags": ["gray_zone_hybrid_warfare", "maritime_chokepoint_sloc"],
        "note": "예멘 후티의 드론·미사일 공격으로 홍해 상선 운항 차질",
        "event_ref": None,
    },
    {
        "id": "t-n3", "canvas_id": _TUTORIAL_CANVAS_ID,
        "node_type": "indicator",
        "label": "홍해 운임 급등",
        "x": 300.0, "y": 100.0,
        "region_code": "bab_el_mandeb",
        "theory_tags": ["maritime_chokepoint_sloc"],
        "note": "수에즈 우회(희망봉) 강제 → 운항 거리 +7,000km → 운임 600% 급등",
        "event_ref": "ZIM",
    },
    {
        "id": "t-n2", "canvas_id": _TUTORIAL_CANVAS_ID,
        "node_type": "indicator",
        "label": "WTI 유가 상승",
        "x": 520.0, "y": 220.0,
        "region_code": "hormuz",
        "theory_tags": ["energy_resource_weaponization"],
        "note": "공급망 불안 심리 + 운송비 전가 → 원유 선물(CL=F) 상승",
        "event_ref": "CL=F",
    },
    {
        "id": "t-n4", "canvas_id": _TUTORIAL_CANVAS_ID,
        "node_type": "outcome",
        "label": "유럽 에너지 비용 상승",
        "x": 740.0, "y": 220.0,
        "region_code": "ukraine",
        "theory_tags": ["energy_weaponized_interdependence"],
        "note": "유럽은 러-우 전쟁 이후 중동 LNG 의존도 상승 → 이중 충격",
        "event_ref": None,
    },
]

# 1→3→2→4 인과 연결 (후티공격 → 운임 → 유가 → 에너지비용)
_TUTORIAL_EDGES = [
    {
        "id": "t-e1", "canvas_id": _TUTORIAL_CANVAS_ID,
        "source_node_id": "t-n1", "target_node_id": "t-n3",
        "kind": "causes", "confidence": 0.9,
        "verified": False, "verification_score": None, "verified_at": None,
        "supporting_rule_id": "bab_el_mandeb_tension_to_oil",
        "note": "초크포인트 공격 → 우회 강제 → 운임 급등",
    },
    {
        "id": "t-e2", "canvas_id": _TUTORIAL_CANVAS_ID,
        "source_node_id": "t-n3", "target_node_id": "t-n2",
        "kind": "causes", "confidence": 0.75,
        "verified": False, "verification_score": None, "verified_at": None,
        "supporting_rule_id": "suez_tension_to_shipping",
        "note": "해운 비용 상승 → 에너지 운송 원가 → 유가에 반영",
    },
    {
        "id": "t-e3", "canvas_id": _TUTORIAL_CANVAS_ID,
        "source_node_id": "t-n2", "target_node_id": "t-n4",
        "kind": "causes", "confidence": 0.8,
        "verified": False, "verification_score": None, "verified_at": None,
        "supporting_rule_id": None,
        "note": "Farrell & Newman — 상호의존 무기화: 에너지 의존국이 가격 충격을 그대로 흡수",
    },
]


def seed_tutorial_canvas() -> None:
    """
    앱 시작 시마다 튜토리얼 캔버스를 INSERT OR IGNORE로 삽입한다.
    이미 같은 ID가 있으면 무시되므로 중복 없음.

    Weaponized Interdependence(Farrell & Newman 2019) 이론을 실제 데이터로
    체험하도록 설계된 '홍해 긴장 → 유가 연쇄' 시나리오.
    """
    now = datetime.utcnow().isoformat()

    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO canvases (id, title, hypothesis, sector_tag, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (
                _TUTORIAL_CANVAS_ID,
                "🎓 튜토리얼: 홍해 긴장 → 유가 연쇄",
                "후티 공격이 홍해 운임을 올리고, 이것이 유가에 영향을 준다",
                "energy",
                now, now,
            ),
        )

        for node in _TUTORIAL_NODES:
            payload = {
                **node,
                "created_at": now,
                "updated_at": now,
            }
            con.execute(
                "INSERT OR IGNORE INTO nodes (id, canvas_id, payload) VALUES (?,?,?)",
                (node["id"], _TUTORIAL_CANVAS_ID, json.dumps(payload, ensure_ascii=False)),
            )

        for edge in _TUTORIAL_EDGES:
            payload = {**edge, "created_at": now}
            con.execute(
                "INSERT OR IGNORE INTO edges (id, canvas_id, payload) VALUES (?,?,?)",
                (edge["id"], _TUTORIAL_CANVAS_ID, json.dumps(payload, ensure_ascii=False)),
            )

    logger.info("[Sandbox] 튜토리얼 캔버스 시드 완료 (INSERT OR IGNORE): %s", _TUTORIAL_CANVAS_ID)
