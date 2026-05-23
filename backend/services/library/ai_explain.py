"""
services/library/ai_explain.py

이론 카드 → Gemini 1.5 Flash 추가 설명 생성 + SQLite 캐싱.

- GEMINI_API_KEY 없으면 fallback 메시지를 동일한 generator 형식으로 반환
- 동일 theory_id 재호출 시 cached=True → API 비용 0
- 스트리밍: Gemini alt=sse → httpx async stream → FastAPI StreamingResponse
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Iterator

import httpx

logger = logging.getLogger(__name__)

_DB_PATH  = Path(__file__).resolve().parents[2] / "db" / "ai_cache.db"
_GEMINI_MODEL = "gemini-1.5-flash"
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:streamGenerateContent?alt=sse&key={{key}}"
)

# .env에서 로드
_API_KEY: str | None = os.getenv("GEMINI_API_KEY")


# ── SQLite 캐시 ───────────────────────────────────────────────────────────────

@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_explain_cache (
                theory_id  TEXT PRIMARY KEY,
                content    TEXT NOT NULL,
                model      TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        con.commit()
        yield con
        con.commit()
    finally:
        con.close()


def _get_cache(theory_id: str) -> str | None:
    with _db() as con:
        row = con.execute(
            "SELECT content FROM ai_explain_cache WHERE theory_id = ?",
            (theory_id,),
        ).fetchone()
    return row["content"] if row else None


def _save_cache(theory_id: str, content: str) -> None:
    with _db() as con:
        con.execute(
            "INSERT OR REPLACE INTO ai_explain_cache (theory_id, content, model, created_at) VALUES (?,?,?,?)",
            (theory_id, content, _GEMINI_MODEL, datetime.utcnow().isoformat()),
        )


# ── SSE 이벤트 헬퍼 ───────────────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    """SSE 한 줄 포맷. 프론트엔드는 `data: <json>` 파싱."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── 프롬프트 ──────────────────────────────────────────────────────────────────

def _build_prompt(display_name: str, summary: str, sector_tag: str) -> str:
    return f"""당신은 국제정치학 전공 학부생을 가르치는 한국어 교수입니다.
아래 이론에 대해 학습자가 현실 세계와 연결할 수 있도록
**한국어로** 500자 내외로 설명해주세요.

이론명: {display_name}
섹터: {sector_tag}
한 줄 요약: {summary}

다음 두 가지를 중심으로 마크다운 형식으로 작성하세요:

## 추가 역사적 사례
(기존 교과서에 없는 덜 알려진 사례 2~3개)

## 2025~2026년 현재 지정학적 함의
(지금 이 이론이 어떤 사건에 적용되는지 구체적으로)

학술 전문용어는 처음 등장 시 괄호로 영문 병기해주세요.
"""


# ── 메인 스트리밍 generator ───────────────────────────────────────────────────

async def stream_ai_explain(
    theory_id: str,
    display_name: str,
    summary: str,
    sector_tag: str,
) -> AsyncGenerator[str, None]:
    """
    SSE 스트림을 yield하는 async generator.

    프론트엔드는 `data: {"text": "...", "done": false}` 를 누적 렌더링하고
    `data: {"done": true}` 를 받으면 완료 처리한다.
    """
    # 1) 캐시 히트
    cached = _get_cache(theory_id)
    if cached:
        logger.info("[ai_explain] cache hit: %s", theory_id)
        yield _sse({"text": cached, "done": False, "cached": True})
        yield _sse({"done": True, "cached": True})
        return

    # 2) API 키 없음 → graceful fallback
    if not _API_KEY:
        fallback = (
            "**GEMINI_API_KEY** 가 설정되지 않았습니다.\n\n"
            "`.env` 파일에 `GEMINI_API_KEY=your_key_here` 를 추가하면\n"
            "AI 추가 설명 기능이 활성화됩니다.\n\n"
            "[Google AI Studio에서 무료 키 발급](https://aistudio.google.com/app/apikey)"
        )
        yield _sse({"text": fallback, "done": False, "cached": False, "fallback": True})
        yield _sse({"done": True, "cached": False, "fallback": True})
        return

    # 3) Gemini 스트리밍
    prompt = _build_prompt(display_name, summary, sector_tag)
    url = _GEMINI_URL.format(key=_API_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 800,
        },
    }

    full_text = ""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    logger.error("[ai_explain] Gemini API error %d: %s", resp.status_code, err_body[:200])
                    yield _sse({"text": f"Gemini API 오류 ({resp.status_code}). 잠시 후 다시 시도해주세요.", "done": False})
                    yield _sse({"done": True})
                    return

                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    payload_str = raw_line[6:].strip()
                    if payload_str in ("[DONE]", ""):
                        continue
                    try:
                        chunk = json.loads(payload_str)
                        text = (
                            chunk.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        if text:
                            full_text += text
                            yield _sse({"text": text, "done": False, "cached": False})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        # 4) 캐시 저장
        if full_text:
            _save_cache(theory_id, full_text)

    except httpx.TimeoutException:
        yield _sse({"text": "\n\n⚠️ Gemini API 응답 시간 초과. 다시 시도해주세요.", "done": False})
    except Exception as exc:
        logger.exception("[ai_explain] 예외: %s", exc)
        yield _sse({"text": f"\n\n⚠️ 오류: {exc}", "done": False})

    yield _sse({"done": True, "cached": False})
