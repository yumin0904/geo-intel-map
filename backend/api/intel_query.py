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
from services.confidence_scorer import (
    score_output, apply_verification_cap,
    apply_data_void_penalty, validate_insight_completeness,
)
from services.hypothesis_extractor import extract_hypotheses
from services.hypothesis_verifier import verify_hypotheses

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
    """모드에 따라 Gemini에게 전달할 시스템+유저 프롬프트를 구성한다.

    §19-A 6단계 구조, §19-B 인사이트 카드 형식, §19-B-2 3대 강점,
    §19-C 금지 패턴, §19-D 신뢰도 산출 기준 적용.
    """

    # §19-A 원칙 + §19-B-2 강점 보존 지침 + §19-D 신뢰도 기준
    system_role = (
        "당신은 국제정치학 박사 과정을 지도하는 지정학 분석 전문가입니다.\n"
        "아래 데이터 컨텍스트를 바탕으로 분석하되, 컨텍스트에 없는 수치·사실은 반드시 [UNVERIFIED] 태그를 붙이세요.\n\n"

        "## 필수 분석 원칙 (§19-A)\n"
        "1. 현상 기술(관찰)에서 멈추지 말고 인과 검증 단계(가설·경쟁이론·데이터·고리강도)까지 진입하라.\n"
        "2. 수치 없는 인과 주장은 [UNVERIFIED] 필수. '시사한다' / '가능성이 높다' 로만 끝내는 것 금지.\n"
        "3. 연쇄 고리마다 강도를 평가하라: HIGH(>70%) / MEDIUM(40~70%) / LOW(<40%). "
        "MEDIUM 이하 고리를 포함한 연쇄 전체에 [SPECULATIVE] 레이블을 붙일 것.\n"
        "4. 경쟁 이론을 반드시 1~2개 나열하고 기각 근거를 제시하라. 단일 이론 수렴 금지.\n"
        "5. 결과를 즉시 의도로 귀속하지 말라('강경 정권 온존 = 미국 실패' 형태 금지).\n"
        "6. 기존 주류 문헌이 충분히 다루지 않은 공백(gap)을 탐지하라. 이미 알려진 사실 재서술은 인사이트가 아니다.\n"
        "7. 복수 도메인이 관여된 경우 '어떤 도메인이 어떤 경로로 어떤 도메인에 영향'을 명시적으로 서술하라.\n"
        "8. 이론 레이블마다 '이 이론으로 설명되지 않는 반례' 필드를 반드시 추가하라.\n"
        "9. [시간 역전 탐지] 각 인과 연결 고리에서 원인 이벤트와 결과 이벤트의 날짜를 확인하라. "
        "결과 이벤트가 원인 이벤트보다 이전에 발생한 경우, [TEMPORAL_REVERSAL] 태그를 붙이고 "
        "'A가 B를 유발'이 아닌 '공통 구조적 선행 조건' 또는 'B가 A의 선행 지표'로 재공식화하라.\n\n"

        "## 신뢰도 점수 (§19-D) — 절대 자체 산출 금지\n"
        "신뢰도 숫자 점수(N점/100)는 외부 시스템이 자동 산출한다. "
        "출력에 '신뢰도: N점/100' 형태를 절대 포함하지 말 것. "
        "대신 연쇄강도(HIGH/MEDIUM/LOW)와 데이터기반·이론근거(고/중/저)만 카드 헤더에 표기하라.\n\n"

        "모든 답변은 한국어로 작성."
    )

    # §19-B 인사이트 카드 형식 (insight·presentation 공통)
    # ※ 신뢰도 점수는 서버 역산(§19-D)으로만 산출 — 여기서 자체 점수 부여 금지
    _card_fmt = """\
각 인사이트는 아래 카드 형식으로 작성하라:

```
[헤드라인] 한 줄 요약 (비자명적 발견 — "A가 증가했다" 수준 금지)
데이터기반: 고/중/저  |  이론근거: 고/중/저  |  연쇄강도: HIGH/MEDIUM/LOW

[관찰]      측정 가능한 현상 (수치·날짜·사례 포함, 없으면 [UNVERIFIED])
[주장]      인과 주장 — 방향·강도·조건 명시
[가설]      H1: "X가 증가할 때 Y가 통계적으로 유의하게 변화한다 (통제변수 Z)" 형태로
[근거]      데이터 소스명 + 수치 (없으면 [UNVERIFIED])
[한계]      이 분석이 답하지 못하는 것
[경쟁설명]  대안 이론 A: 설명 / 반례: ~할 경우 설명력 하락
            대안 이론 B: 설명 / 기각 근거: ~
[검증포인트] 다음 세션에서 확인할 지표·소스
[문헌공백]  기존 연구가 이 패턴을 충분히 다루지 않는 이유
```
"""

    if pq.mode == "presentation":
        task = f"""## 요청
사용자가 다음 주제로 발표를 준비하고 있습니다: "{pq.raw_query}"

{_card_fmt}

### 발표 각도 추천 (3~5개)
각 각도마다 위 인사이트 카드 형식으로 작성하되, 카드 끝에 아래를 추가하라:
- **청중 훅**: 발표 시작 30초 안에 관심을 끌 역설적 질문
- **차별점**: 기존 발표에서 흔히 다루는 각도와 무엇이 다른가 (§19-B-2 문헌 공백 활용)

### 추천 슬라이드 구성 (가장 강력한 각도 1개 기준)
슬라이드 흐름을 5~7단계로 제시하고, 각 단계에 '이 슬라이드에서 청중이 가져가야 할 한 문장'을 포함하라."""

    elif pq.mode == "verify":
        task = f"""## 요청
사용자가 다음 주장을 검증하려 합니다: "{pq.raw_query}"

§19-A 6단계 구조로 분석하라:

### [단계 1] 관찰
주장과 관련된 측정 가능한 현상을 수치와 함께 서술하라. 수치 없으면 [UNVERIFIED].

### [단계 2] 변수 식별
- 독립변수(원인 후보):
- 종속변수(결과):
- 통제변수(제거해야 할 혼재 요인):

### [단계 3] 가설 공식화
- H1 (주장 지지): [반증 가능 형태 — "X가 증가할 때 Y가 유의하게 변화한다"]
- H0 (귀무 가설): [H1이 틀렸을 때 관찰될 패턴]

### [단계 4] 경쟁 이론
이 현상을 다르게 설명하는 이론 1~2개를 나열하고, 어느 것을 먼저 기각할지 근거를 제시하라.
각 이론마다: 설명 / 반례(이론의 설명력이 떨어지는 조건)

### [단계 5] 근거 평가
컨텍스트 데이터에서:
- 지지 증거 (소스 + 수치):
- 반증 증거 (소스 + 수치):
- 미검증 항목: [UNVERIFIED] 명시

### [단계 6] 연쇄 고리 강도 자기평가
각 인과 연결고리를 HIGH / MEDIUM / LOW로 평가하고,
MEDIUM 이하가 포함되면 전체 결론에 [SPECULATIVE] 레이블을 붙일 것.

### 최종 판정
- **결론**: 지지 / 반증 / 불확실
- **레이블**: [SPECULATIVE] / [PROVISIONAL] / 없음"""

    else:  # insight
        task = f"""## 요청
다음 질문에 대해 교차 분석 기반 인사이트를 제공하세요: "{pq.raw_query}"

{_card_fmt}

인사이트 카드를 **2~3개** 작성하라.
⚠️ "A → B를 시사한다" / "가능성이 높다" 로만 끝내는 것 금지. 연쇄 고리 강도까지 반드시 평가할 것.

### 도메인 교차 경로 (§19-B-2 ②)
복수 도메인이 관여된 경우, 아래 형식으로 도메인 간 인과 경로를 명시하라:
[도메인A → 도메인B] 경로 설명 + 전이 조건

### 문헌 공백 탐지 (§19-B-2 ③)
"기존 주류 문헌이 이 패턴을 충분히 다루지 않는 이유"와
"이 분석이 기여할 수 있는 학문적·정책적 공백"을 한 단락으로 서술하라."""

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
    source_counts: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Gemini 2.5 Flash SSE 스트리밍. thinking=True 시 thinkingBudget 8192."""

    if not _GEMINI_KEY:
        yield _sse({"text": "⚠️ GEMINI_API_KEY가 설정되지 않았습니다.", "done": False})
        yield _sse({"done": True})
        return

    url  = _GEMINI_URL.format(key=_GEMINI_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {"maxOutputTokens": 16384, "temperature": 0.7},
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

        # §19-D 신뢰도 점수 역산 — 스트리밍 완료 후 score 이벤트 전송
        if full_text:
            score_result = score_output(full_text)

            # [P0-B] 데이터 공백 패널티: ACLED·Cascade 없는 지역은 상한 제한
            if source_counts:
                penalized = apply_data_void_penalty(
                    score_result["confidence"],
                    source_counts.get("event_stats_regions", 0),
                    source_counts.get("cascade_links", 0),
                )
                if penalized != score_result["confidence"]:
                    logger.info(
                        "[intel] 데이터 공백 패널티 적용: %d → %d (events=%d cascade=%d)",
                        score_result["confidence"], penalized,
                        source_counts.get("event_stats_regions", 0),
                        source_counts.get("cascade_links", 0),
                    )
                    score_result["confidence"] = penalized
                    score_result["provisional"] = penalized < 60

            # IA-Engine-D: H1 가설 추출 → Granger 검증 → 신뢰도 캡 적용
            specs = extract_hypotheses(full_text)
            if specs:
                specs = await verify_hypotheses(specs)
                # 가장 낮은 검증 상태로 신뢰도 캡 결정
                status_order = {"PENDING": 0, "PARTIAL": 1, "VERIFIED": 2}
                worst = min(specs, key=lambda s: status_order.get(s.verification_status, 0))
                score_result["confidence"] = apply_verification_cap(
                    score_result["confidence"], worst.verification_status
                )
                score_result["provisional"] = score_result["confidence"] < 60
                # hypothesis 이벤트 전송
                yield _sse({
                    "type": "hypothesis",
                    "done": False,
                    "hypotheses": [
                        {
                            "h1": s.h1,
                            "h0": s.h0,
                            "independent_var": s.independent_var,
                            "dependent_var": s.dependent_var,
                            "control_vars": s.control_vars,
                            "region_code": s.region_code,
                            "ticker": s.ticker,
                            "var_type": s.var_type,
                            "proxy_suggestions": s.proxy_suggestions,
                            "verification_status": s.verification_status,
                            "granger_p": s.granger_p,
                            "best_lag": s.best_lag,
                            "n_obs": s.n_obs,
                            "error": s.error,
                        }
                        for s in specs
                    ],
                })

            yield _sse({"type": "score", "done": False, **score_result})

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

        async for chunk in _stream_gemini(prompt, pq.thinking, source_counts):
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
    query:            str
    mode:             str = "insight"
    regions:          list[str] = []
    sectors:          list[str] = []
    result_md:        str
    context_chars:    int = 0
    confidence_score: int | None = None


@router.post("/save")
def intel_save(req: SaveRequest):
    """분석 결과 저장. [P0-A] 저장 전 완결성 검사 통과 시만 허용."""
    # [P0-A] 인사이트 완결성 검사 — 섹션 누락·문장 미완성 시 거부
    ok, reason = validate_insight_completeness(req.result_md)
    if not ok:
        raise HTTPException(status_code=422, detail=f"인사이트 미완성: {reason}")

    title = req.query[:40].strip() + ("..." if len(req.query) > 40 else "")
    with _db() as con:
        cur = con.execute(
            """
            INSERT INTO intel_analyses
                (title, query, mode, regions, sectors, result_md,
                 context_chars, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                req.query,
                req.mode,
                json.dumps(req.regions, ensure_ascii=False),
                json.dumps(req.sectors, ensure_ascii=False),
                req.result_md,
                req.context_chars,
                req.confidence_score,
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
