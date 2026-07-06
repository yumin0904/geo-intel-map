#!/usr/bin/env python3
"""
scripts/export_insight.py — 헤드리스 인사이트 분석 → 구조화 export (엔진→퍼블리싱 출구).

왜 필요한가: HypothesisSpec의 구조화 필드(verification_status·inference_grade·
exploratory·method_result)는 SSE 스트림에만 존재하고, /api/intel/save 시점에는
마크다운(result_md)으로만 남아 소실된다. 이 스크립트는 서버 없이 분석 1회를 돌려
그 구조화 페이로드를 shared/schemas/insight.schema.json v0.1 형태로 동결한다.
소비자: geo-os/tools/insight_to_draft.py (→ neoul article 스캐폴드).

사용법:
    cd backend
    .venv/bin/python scripts/export_insight.py --query "..." --id <kebab-slug> \
        [--regions r1,r2] [--sectors s1,s2] [--save] [--out DIR]

기본 출력: <repo>/exports/insights/<id>.insight.json (git 커밋 대상 — 기사 근거 감사추적)
--save: 완결성 검사 통과 시 intel_analyses에도 저장 (엔진 UI 히스토리 연동).

경계 (geo-os Scheduler 경계 규칙): 이 스크립트 실행은 geo-intel-map 내부 소관이다.
geo-os는 산출된 insight.json만 소비하고 이 스크립트를 직접 호출하지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent
_DEFAULT_OUT = _REPO / "exports" / "insights"
_INTEL_DB = _BACKEND / "db" / "intel.db"
_VERSION = json.loads((_BACKEND / "config" / "version.json").read_text())["version"]


def _parse_sse(chunk: str) -> list[dict]:
    """_sse()가 만든 'data: {...}\\n\\n' 문자열 → 이벤트 dict 목록."""
    events = []
    for line in chunk.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                continue
    return events


async def run_analysis(query: str, regions: list[str], sectors: list[str]) -> dict:
    """분석 1회 실행 — intel_query 엔드포인트와 동일 경로, HTTP만 생략."""
    # 지연 import: main()이 LLM_PROVIDER 환경변수를 확정한 *뒤*에 모듈을 읽어야 한다
    # (intel_query가 import 시점에 provider·키를 고정하기 때문)
    from api.intel_query import _build_prompt, _stream_gemini
    from services.entity_parser import parse_query
    from services.intel_analyzer import build_intel_context

    pq = parse_query(query)
    if sectors:
        pq.sectors = sectors
    if regions:
        pq.regions = regions

    intel_ctx = await build_intel_context(pq)

    # 참조 브리핑 — 엔드포인트의 synthesis_ctx 조립과 동일 (상위 5)
    briefing_titles = [
        i.get("title", "") for i in
        (intel_ctx.get("like_items", []) + intel_ctx.get("sector_items", []))[:5]
    ]
    synthesis_ctx = ""
    if briefing_titles:
        synthesis_ctx = "### 참조 브리핑\n" + "\n".join(f"- {t}" for t in briefing_titles)

    prompt = _build_prompt(pq, intel_ctx["context_text"], synthesis_ctx)

    result_md = ""
    hypotheses: list[dict] = []
    score: dict = {}
    async for chunk in _stream_gemini(
        prompt, pq.thinking, intel_ctx["source_counts"],
        default_regions=pq.regions, source_query=query, mode=pq.mode,
    ):
        for ev in _parse_sse(chunk):
            if ev.get("type") == "hypothesis":
                hypotheses = ev.get("hypotheses", [])
            elif ev.get("type") == "score":
                score = {k: v for k, v in ev.items() if k not in ("type", "done")}
            elif ev.get("text"):
                result_md += ev["text"]
                # 진행 표시 — 긴 스트림에서 살아있음을 보여준다 (내용은 파일로만)
                print(".", end="", flush=True)
    print()

    return {
        "pq": pq, "result_md": result_md, "hypotheses": hypotheses,
        "score": score, "briefing_refs": briefing_titles,
        "source_counts": intel_ctx["source_counts"],
    }


def save_to_history(query: str, run: dict, score: dict) -> int:
    """intel_analyses INSERT — /api/intel/save와 동일 형태 (제목 규칙 포함)."""
    title = query[:40].strip() + ("..." if len(query) > 40 else "")
    con = sqlite3.connect(_INTEL_DB)
    try:
        cur = con.execute(
            """
            INSERT INTO intel_analyses
                (title, query, mode, regions, sectors, result_md,
                 context_chars, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title, query, run["pq"].mode,
                json.dumps(run["pq"].regions, ensure_ascii=False),
                json.dumps(run["pq"].sectors, ensure_ascii=False),
                run["result_md"], 0, score.get("confidence"),
            ),
        )
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", required=True)
    ap.add_argument("--id", required=True, help="export 식별자 (kebab-case)")
    ap.add_argument("--regions", default="", help="쉼표 구분 지역 override")
    ap.add_argument("--sectors", default="", help="쉼표 구분 섹터 override")
    ap.add_argument("--save", action="store_true",
                    help="완결성 통과 시 intel_analyses에도 저장")
    ap.add_argument("--out", default=str(_DEFAULT_OUT), help="출력 디렉토리")
    ap.add_argument("--provider", choices=["gemini", "ollama", "nim"], default="gemini",
                    help="LLM provider — nim(NVIDIA 무료·OpenAI 호환·70b급)이 Gemini 503·"
                         "Ollama 저품질을 대체. 발행용은 nim 또는 gemini 권장(.env 설정보다 우선)")
    args = ap.parse_args()

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.id):
        raise SystemExit(f"--id는 kebab-case: {args.id}")

    # provider 확정 → .env 로드 순서: 먼저 넣은 환경변수가 이긴다(load_dotenv는
    # 기존 env를 덮지 않음). .env LLM_PROVIDER=ollama(개발용)를 실행 시점에만 오버라이드.
    import os
    from dotenv import load_dotenv
    os.environ["LLM_PROVIDER"] = args.provider
    load_dotenv(_BACKEND / ".env")

    from services.confidence_scorer import validate_insight_completeness

    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    sectors = [s.strip() for s in args.sectors.split(",") if s.strip()]

    run = asyncio.run(run_analysis(args.query, regions, sectors))
    result_md = run["result_md"]

    if not result_md or result_md.lstrip().startswith("⚠️"):
        print(f"❌ 분석 실패 — 엔진 응답: {result_md[:200]}")
        return 1

    ok, reason = validate_insight_completeness(result_md)
    score = run["score"]
    exploratory = run["pq"].mode != "verify"  # _finalize와 동일 판정

    analysis_id = None
    if args.save:
        if not ok:
            print(f"⚠️ 완결성 실패 — intel_analyses 저장 생략: {reason}")
        else:
            analysis_id = save_to_history(args.query, run, score)

    export = {
        "schema_version": "0.1",
        "id": args.id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_version": _VERSION,
        "query": args.query,
        "mode": run["pq"].mode,
        "exploratory": exploratory,
        "regions": run["pq"].regions,
        "sectors": run["pq"].sectors,
        "briefing_refs": [t for t in run["briefing_refs"] if t],
        "source_counts": run["source_counts"],
        "completeness": {"ok": ok, **({"reason": reason} if not ok else {})},
        "confidence": {
            "score": int(score.get("confidence", 0)),
            "provisional": bool(score.get("provisional", False)),
            "inference_grade": score.get("inference_grade", "기술적"),
            "inference_caveat": score.get("inference_caveat", ""),
        },
        "result_md": result_md,
        "hypotheses": run["hypotheses"],
        "intel_analysis_id": analysis_id,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.id}.insight.json"
    out.write_text(json.dumps(export, ensure_ascii=False, indent=2) + "\n")

    statuses = [h["detail"].get("verification_status", "?") for h in export["hypotheses"]]
    print(f"✅ {out}")
    print(f"   engine v{_VERSION} · mode={export['mode']} "
          f"({'탐색적' if exploratory else '확증'}) · 완결성 {'PASS' if ok else 'FAIL: ' + reason}")
    print(f"   confidence {export['confidence']['score']} · "
          f"추론등급 {export['confidence']['inference_grade']} · "
          f"가설 {len(statuses)}건 {statuses}")
    if analysis_id:
        print(f"   intel_analyses id={analysis_id} 저장됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
