"""
api/intel_query.py

POST /api/intel/query  — 인사이트 분석실 SSE 엔드포인트.

흐름:
  1. ParsedQuery 구성 (entity_parser)
  2. 멀티소스 컨텍스트 조립 (intel_analyzer)
  3. P5-7 에이전트 synthesis context 병합 (선택적)
  4. Gemini 2.5 Flash SSE 스트리밍
     - fast 모드: thinkingConfig 생략 (모델 자율)
     - deep 모드: thinkingBudget=8192, 503 시 fast로 자동 fallback
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import AsyncGenerator, Iterator

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_INTEL_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(_INTEL_DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

from services.entity_parser import parse_query, ParsedQuery
from services.intel_analyzer import build_intel_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intel", tags=["intel"])

_GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
_GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:streamGenerateContent?alt=sse&key={{key}}"
)

# ── 요청 스키마 ───────────────────────────────────────────────────────────

class IntelQueryRequest(BaseModel):
    query: str
    # 프론트에서 섹터·지역을 직접 지정하면 parser 결과를 override
    sector_override: list[str] = []
    region_override: list[str] = []


# ── 모드별 Gemini 프롬프트 ────────────────────────────────────────────────

def _build_prompt(pq: ParsedQuery, context_text: str, synthesis_ctx: str) -> str:
    """모드에 따라 Gemini에게 전달할 시스템+유저 프롬프트를 구성한다."""

    system_role = (
        "당신은 국제정치학 석사 과정 학생을 지도하는 지정학 분석 전문가입니다. "
        "아래 데이터 컨텍스트를 바탕으로 분석하되, 컨텍스트에 없는 사실은 창작하지 마세요. "
        "모든 답변은 한국어로 작성하고, 이론적 근거를 반드시 포함하세요."
    )

    if pq.mode == "presentation":
        task = f"""## 요청
사용자가 다음 주제로 발표를 준비하고 있습니다: "{pq.raw_query}"

아래 형식으로 답변하세요:

### 발표 각도 추천 (3~5개)
각 각도마다:
- **각도 제목**: (청중의 관심을 끌 수 있는 구체적 제목)
- **핵심 주장**: (한 문장)
- **근거**: (컨텍스트에서 가져온 구체적 데이터·사례)
- **이론 연결**: (관련 국제정치학 이론 + 학자)
- **차별점**: (기존 발표와 다른 새로운 인사이트)

### 추천 슬라이드 구성 (가장 강력한 각도 1개 기준)
슬라이드 흐름을 5~7단계로 제시하세요."""

    elif pq.mode == "verify":
        task = f"""## 요청
사용자가 다음 주장을 검증하려 합니다: "{pq.raw_query}"

아래 형식으로 답변하세요:

### 검증 결과
- **판정**: 지지 / 반증 / 불확실 (하나 선택)
- **신뢰도**: 0~100점

### 지지 근거
컨텍스트에서 이 주장을 뒷받침하는 증거를 나열하세요.

### 반증 근거
컨텍스트에서 이 주장에 반하는 증거를 나열하세요.

### 이론적 해석
관련 국제정치학 이론으로 판정을 설명하세요."""

    else:  # insight
        task = f"""## 요청
다음 질문에 대해 교차 분석 기반 인사이트를 제공하세요: "{pq.raw_query}"

아래 형식으로 답변하세요:

### 핵심 인사이트 (3개)
각 인사이트마다:
- **인사이트**: (비자명적 발견 — 누구나 아는 사실 제외)
- **근거**: (컨텍스트 데이터)
- **이론 연결**: (국제정치학 이론)

### 주목할 패턴
데이터에서 드러나는 숨겨진 연결고리나 역설적 상황을 서술하세요.

### 다음 관찰 포인트
이 분석을 심화하려면 어떤 지표·이벤트를 추적해야 하는지 제안하세요."""

    return f"""{system_role}

<context>
{context_text}

{synthesis_ctx}
</context>

{task}"""


# ── Gemini SSE 스트리밍 ───────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_gemini(
    prompt: str,
    thinking: bool,
) -> AsyncGenerator[str, None]:
    """Gemini 2.5 Flash SSE 스트리밍. thinking=True 시 thinkingBudget 8192."""

    if not _GEMINI_KEY:
        yield _sse({"text": "⚠️ GEMINI_API_KEY가 설정되지 않았습니다.", "done": False})
        yield _sse({"done": True})
        return

    url  = _GEMINI_URL.format(key=_GEMINI_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {"maxOutputTokens": 8192, "temperature": 0.7},
    }
    if thinking:
        # 1024로 제한: 8192는 출력 시작까지 15~20초 지연 발생
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 1024}

    async def _do_stream(request_body: dict) -> AsyncGenerator[str, None]:
        full_text = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, json=request_body) as resp:
                    if resp.status_code == 503 and thinking:
                        # thinking 모드 503 → fast 모드로 자동 fallback
                        logger.warning("[intel] Gemini 503 — thinking 비활성화 후 재시도")
                        yield _sse({"text": "", "done": False, "fallback": True,
                                    "note": "thinking 모드 일시 불가 → 일반 모드로 전환"})
                        fallback_body = {k: v for k, v in request_body.items()}
                        fallback_body["generationConfig"] = {
                            k: v for k, v in request_body["generationConfig"].items()
                            if k != "thinkingConfig"
                        }
                        async for chunk in _do_stream(fallback_body):
                            yield chunk
                        return

                    if resp.status_code != 200:
                        err = await resp.aread()
                        logger.error("[intel] Gemini %d: %s", resp.status_code, err[:200])
                        yield _sse({"text": f"⚠️ Gemini API 오류 ({resp.status_code})", "done": False})
                        yield _sse({"done": True})
                        return

                    async for raw_line in resp.aiter_lines():
                        if not raw_line.startswith("data: "):
                            continue
                        payload_str = raw_line[6:].strip()
                        if payload_str in ("[DONE]", ""):
                            continue
                        try:
                            chunk    = json.loads(payload_str)
                            parts    = (chunk.get("candidates", [{}])[0]
                                        .get("content", {})
                                        .get("parts", []))
                            for part in parts:
                                # thought=True 파트는 사용자에게 노출하지 않음
                                if part.get("thought"):
                                    continue
                                text = part.get("text", "")
                                if text:
                                    full_text += text
                                    yield _sse({"text": text, "done": False})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

        except httpx.TimeoutException:
            yield _sse({"text": "\n\n⚠️ 응답 시간 초과. 다시 시도해주세요.", "done": False})
        except Exception as e:
            logger.exception("[intel] 스트리밍 예외: %s", e)
            yield _sse({"text": f"\n\n⚠️ 오류: {e}", "done": False})

        yield _sse({"done": True})

    async for chunk in _do_stream(body):
        yield chunk


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@router.post("/query")
async def intel_query(req: IntelQueryRequest):
    """
    인사이트 분석실 메인 SSE 엔드포인트.

    응답: text/event-stream
    청크 형식: data: {"text": "...", "done": false}
    완료 형식: data: {"done": true, "meta": {...}}
    """
    # ── 1. 엔티티 파싱 ────────────────────────────────────────────────────
    pq = parse_query(req.query)
    if req.sector_override:
        pq.sectors = req.sector_override
    if req.region_override:
        pq.regions = req.region_override

    logger.info(
        "[intel] 쿼리 수신 mode=%s thinking=%s regions=%s sectors=%s",
        pq.mode, pq.thinking, pq.regions, pq.sectors,
    )

    # ── 2. 멀티소스 컨텍스트 조립 ─────────────────────────────────────────
    intel_ctx  = await build_intel_context(pq)
    context_text = intel_ctx["context_text"]
    source_counts = intel_ctx["source_counts"]

    # ── 3. synthesis context 조립 ─────────────────────────────────────────
    synthesis_ctx = ""
    briefing_titles = [
        i.get("title", "") for i in
        (intel_ctx.get("like_items", []) + intel_ctx.get("sector_items", []))[:5]
    ]
    if briefing_titles:
        synthesis_ctx = "### 참조 브리핑\n" + "\n".join(
            f"- {t}" for t in briefing_titles
        )

    # ── 4. 프롬프트 구성 → Gemini SSE ────────────────────────────────────
    prompt = _build_prompt(pq, context_text, synthesis_ctx)

    async def event_stream() -> AsyncGenerator[str, None]:
        # 메타 정보 먼저 전송 (프론트 소스 표시용)
        yield _sse({
            "type":  "meta",
            "mode":  pq.mode,
            "thinking": pq.thinking,
            "regions": pq.regions,
            "actors":  pq.actors,
            "sectors": pq.sectors,
            "source_counts": source_counts,
            "done":  False,
        })

        async for chunk in _stream_gemini(prompt, pq.thinking):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── 저장 / 조회 / 삭제 ────────────────────────────────────────────────────────

class SaveRequest(BaseModel):
    query:        str
    mode:         str = "insight"
    regions:      list[str] = []
    sectors:      list[str] = []
    result_md:    str
    context_chars: int = 0


@router.post("/save")
def intel_save(req: SaveRequest):
    """분석 결과 저장."""
    title = req.query[:40].strip() + ("..." if len(req.query) > 40 else "")
    with _db() as con:
        cur = con.execute(
            """
            INSERT INTO intel_analyses
                (title, query, mode, regions, sectors, result_md, context_chars)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                req.query,
                req.mode,
                json.dumps(req.regions, ensure_ascii=False),
                json.dumps(req.sectors, ensure_ascii=False),
                req.result_md,
                req.context_chars,
            ),
        )
    return {"id": cur.lastrowid, "title": title}


@router.get("/history")
def intel_history(limit: int = 30):
    """저장된 분석 목록 반환 (result_md 제외 — 목록 표시용)."""
    with _db() as con:
        rows = con.execute(
            """
            SELECT id, title, query, mode, regions, sectors,
                   context_chars, created_at
            FROM intel_analyses
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            **dict(r),
            "regions": json.loads(r["regions"] or "[]"),
            "sectors": json.loads(r["sectors"] or "[]"),
        }
        for r in rows
    ]


@router.get("/history/{analysis_id}")
def intel_history_detail(analysis_id: int):
    """저장된 분석 상세 (result_md 포함)."""
    with _db() as con:
        row = con.execute(
            "SELECT * FROM intel_analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    d = dict(row)
    d["regions"] = json.loads(d.get("regions") or "[]")
    d["sectors"] = json.loads(d.get("sectors") or "[]")
    return d


@router.delete("/history/{analysis_id}")
def intel_history_delete(analysis_id: int):
    """저장된 분석 삭제."""
    with _db() as con:
        con.execute("DELETE FROM intel_analyses WHERE id = ?", (analysis_id,))
    return {"deleted": analysis_id}
