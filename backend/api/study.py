"""
study.py — 학습 노트 API 라우터.

Study Mode에서 이벤트별 개인 메모를 SQLite에 저장·조회한다.
event_id (UUID) 기준 upsert. DB 파일: backend/db/study.db

엔드포인트:
  GET  /api/study/notes/{event_id}  — 노트 조회 (없으면 content='')
  PUT  /api/study/notes/{event_id}  — 노트 저장 (upsert)
"""
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/study", tags=["study"])

# db/ 디렉터리가 없을 때도 안전하게 생성
_DB_PATH = Path(__file__).parent.parent / "db" / "study.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    """study.db 연결 + notes 테이블 초기화 (없을 때만)."""
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            event_id   TEXT PRIMARY KEY,
            content    TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
    """)
    con.commit()
    return con


class NoteBody(BaseModel):
    content: str


@router.get("/notes/{event_id}")
async def get_note(event_id: str):
    """이벤트 노트 조회. 저장된 노트가 없으면 content='' 반환."""
    with _conn() as con:
        row = con.execute(
            "SELECT event_id, content, updated_at FROM notes WHERE event_id = ?",
            (event_id,),
        ).fetchone()
    if row:
        return dict(row)
    return {"event_id": event_id, "content": "", "updated_at": None}


@router.put("/notes/{event_id}")
async def upsert_note(event_id: str, body: NoteBody):
    """노트 저장. 없으면 INSERT, 있으면 UPDATE (SQLite upsert)."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO notes (event_id, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                content    = excluded.content,
                updated_at = excluded.updated_at
            """,
            (event_id, body.content, now),
        )
        con.commit()
    logger.info("[Study] note saved: event_id=%s len=%d", event_id, len(body.content))
    return {"event_id": event_id, "content": body.content, "updated_at": now}
