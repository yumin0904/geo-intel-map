#!/usr/bin/env python
"""
scripts/trace_query.py — 쿼리 1건의 파이프라인 전 단계 계측기 (드라이런).

왜: 엔진이 "어디서 침묵하는가"를 보려면 단계별 입력·출력·소요시간이 전부 찍혀야 한다.
    이 도구는 프로브 실행의 기반 하니스다.

사용:
    .venv/bin/python scripts/trace_query.py --query "..." [--provider nim] [--out DIR] [--full]

산출:
    exports/traces/<slug>.trace.json  +  사람이 읽는 요약 stdout

원칙:
  - 드라이런: DB에 절대 쓰지 않는다 (prediction_log INSERT는 build_prediction 덤프로 대체,
    log_predictions는 트립와이어로 봉인).
  - 기존 코드 무수정: 조달 함수는 monkeypatch 래퍼로 계측(원본 파일 불변).
  - 단계별 격리: 한 단계가 죽어도 나머지는 계속 찍힌다 (status=FAIL로 기록).
  - 침묵 명시: 발화하지 않은 소스는 status=SILENT로 기록한다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# ── .env 로드가 import보다 먼저여야 한다 ────────────────────────────────────
# api.intel_query 는 모듈 임포트 시점에 _LLM_PROVIDER/_NIM_MODEL 를 os.getenv로 굳힌다.
# load_dotenv 없이 임포트하면 gemini로 조용히 폴백된다(실측 확인됨).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

_ARGP = argparse.ArgumentParser(description="쿼리 1건 파이프라인 전수 트레이스 (드라이런)")
_ARGP.add_argument("--query", required=True)
_ARGP.add_argument("--provider", default=None,
                   help="LLM provider override (nim|gemini|ollama). 미지정 시 .env 기본값")
_ARGP.add_argument("--out", default=str(BACKEND / "exports" / "traces"))
_ARGP.add_argument("--full", action="store_true",
                   help="프롬프트·컨텍스트 전문을 트레이스에 저장 (기본: 길이만)")
_ARGP.add_argument("--no-llm", action="store_true",
                   help="LLM 호출 생략 (조달·조립·접지 단계만 계측)")
ARGS = _ARGP.parse_args()

if ARGS.provider:
    os.environ["LLM_PROVIDER"] = ARGS.provider.strip().lower()

# ── 여기서부터 엔진 임포트 (env 확정 후) ────────────────────────────────────
import httpx  # noqa: E402

from services import intel_analyzer as IA  # noqa: E402
from services import prediction_instrument as PI  # noqa: E402
from services.entity_parser import parse_query  # noqa: E402
import api.intel_query as IQ  # noqa: E402


# ── 드라이런 봉인: prediction_log INSERT 경로 차단 ───────────────────────────
_TRIPWIRE: list[str] = []


def _sealed_log_predictions(*_a, **_kw):  # pragma: no cover - 방어선
    _TRIPWIRE.append("log_predictions() 호출됨 — 드라이런 위반 (INSERT 차단됨)")
    return []


PI.log_predictions = _sealed_log_predictions


# ── 단계 기록기 ─────────────────────────────────────────────────────────────

class Trace:
    """단계별 입력·출력·소요시간 수집기. 예외는 삼키고 status=FAIL로 기록."""

    def __init__(self, query: str) -> None:
        self.data: dict = {
            "query": query,
            "provider": IQ._LLM_PROVIDER,
            "model": (IQ._NIM_MODEL if IQ._LLM_PROVIDER == "nim"
                      else IQ._OLLAMA_MODEL if IQ._LLM_PROVIDER == "ollama"
                      else IQ._GEMINI_MODEL),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "stages": {},
        }

    def run(self, name: str, fn, **meta):
        """fn()을 실행하고 (반환값, 소요시간)을 name 단계로 기록. 실패해도 계속 진행."""
        t0 = time.perf_counter()
        try:
            out = fn()
            ms = round((time.perf_counter() - t0) * 1000, 1)
            payload = out if isinstance(out, dict) else {"value": out}
            self.data["stages"][name] = {"status": "OK", "ms": ms, **meta, **payload}
            return out
        except Exception as e:  # noqa: BLE001
            ms = round((time.perf_counter() - t0) * 1000, 1)
            self.data["stages"][name] = {
                "status": "FAIL", "ms": ms, **meta,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-1500:],
            }
            return None

    def stage(self, name: str) -> dict:
        return self.data["stages"].get(name) or {}


# ── 단계 2: 조달 계측 — monkeypatch 래퍼 (원본 파일 무수정) ───────────────────
# build_intel_context 내부는 모듈 전역 이름으로 조달 함수를 부르므로, 모듈 속성을
# 래핑하면 원본 코드를 건드리지 않고 호출을 가로챌 수 있다.

# (트레이스 키, intel_analyzer 함수명, source_counts 키, _SOURCE_EMITTERS 키)
_PROCUREMENT: list[tuple[str, str, str | None, str | None]] = [
    ("library_like",    "_search_library_like",          "fts_items",           None),
    ("library_sector",  "_search_library_by_sector",     "sector_items",        None),
    ("acled_events",    "_get_event_stats",              "event_stats_regions", None),
    ("cascade",         "_get_cascade_context",          "cascade_links",       None),
    ("country_profile", "_get_country_profiles",         "country_profiles",    None),
    ("sipri_milex",     "_get_sipri_data",               "sipri_countries",     "sipri_milex"),
    ("cow_alliances",   "_get_cow_alliances",            "cow_alliances",       "cow_alliances"),
    ("kiel",            "_get_kiel_data",                "kiel_donors",         "kiel"),
    ("eia",             "_get_eia_data",                 "eia_entries",         "eia"),
    ("csis",            "_get_csis_incidents",           "csis_incidents",      "csis"),
    ("sipri_arms",      "_get_sipri_arms",               "sipri_arms",          "sipri_arms"),
    ("vdem",            "_get_vdem",                     "vdem_entries",        "vdem"),
    ("cow_wars",        "_get_cow_wars",                 "cow_wars",            "cow_wars"),
    ("ifans",           "_get_ifans_publications",       "ifans_pubs",          "ifans"),
    ("theory_compare",  "build_theory_comparison_context", "theory_cmp_chars",  None),
    ("fred",            "_get_fred_data",                "fred",                "fred"),
    ("worldbank_wgi",   "_get_world_bank_wgi",           "wbk",                 "wbk"),
    ("polity5",         "_get_polity5",                  "polity5",             "polity5"),
    ("itu_ict",         "_get_itu_ict",                  "itu",                 "itu"),
    ("hiik",            "_get_hiik_conflict",            "hiik",                "hiik"),
    ("semi_market",     "_get_semi_market",              "semi",                "semi"),
    ("owid",            "_get_owid_data",                "owid",                "owid"),
    ("trade_dep",       "_get_trade_dependency",         None,                  "trade"),
    ("press",           "_get_press_releases",           "press",               "press"),
    ("bp_provocations", "_get_bp_provocations",          "bp_provocations",     "bp"),
]

_PROC_LOG: dict[str, dict] = {}


def _n_records(v) -> int:
    if v is None:
        return 0
    if isinstance(v, str):
        return 1 if v.strip() else 0
    if isinstance(v, dict):
        return len(v)
    try:
        return len(v)
    except TypeError:
        return 1


def _install_procurement_probes() -> None:
    """25개 조달 함수를 타이밍 래퍼로 교체. 원본은 클로저에 보관."""
    for key, fname, _sc_key, _em_key in _PROCUREMENT:
        orig = getattr(IA, fname, None)
        if orig is None:
            _PROC_LOG[key] = {"status": "FAIL", "error": f"함수 없음: {fname}"}
            continue

        def _wrap(_orig=orig, _key=key, _fname=fname):
            def _probe(*a, **kw):
                t0 = time.perf_counter()
                try:
                    out = _orig(*a, **kw)
                    _PROC_LOG[_key] = {
                        "fn": _fname,
                        "ms": round((time.perf_counter() - t0) * 1000, 1),
                        "args": [str(x)[:80] for x in a],
                        "n_records": _n_records(out),
                        "status": "OK" if _n_records(out) else "SILENT",
                        "_raw": out,
                    }
                    return out
                except Exception as e:  # noqa: BLE001
                    _PROC_LOG[_key] = {
                        "fn": _fname,
                        "ms": round((time.perf_counter() - t0) * 1000, 1),
                        "args": [str(x)[:80] for x in a],
                        "n_records": 0,
                        "status": "FAIL",
                        "error": f"{type(e).__name__}: {e}",
                        "_raw": None,
                    }
                    raise
            return _probe

        setattr(IA, fname, _wrap())


def _finish_procurement(context_text: str) -> dict:
    """조달 로그 + 렌더 블록 길이(컨텍스트 실투입량) 계산."""
    out: dict = {}
    for key, fname, sc_key, em_key in _PROCUREMENT:
        rec = _PROC_LOG.get(key)
        if rec is None:
            # gather가 이 함수를 아예 부르지 않았다 (배선 누락)
            out[key] = {"fn": fname, "status": "NOT_CALLED", "n_records": 0,
                        "rendered_chars": 0, "in_context": False}
            continue
        raw = rec.pop("_raw", None)
        rendered = 0
        in_ctx = False
        if em_key and raw:
            try:
                block = IA._SOURCE_EMITTERS[em_key](raw)
                rendered = sum(len(l) + 1 for l in block)
                # 예산 초과로 잘린 블록은 컨텍스트에 없다 → 헤더 존재로 실투입 확인
                head = next((l for l in block if l.strip()), "")
                in_ctx = bool(head) and head[:60] in context_text
            except Exception as e:  # noqa: BLE001
                rec["render_error"] = f"{type(e).__name__}: {e}"
        elif raw:
            # 에미터가 없는 소스(라이브러리·ACLED·cascade·프로파일·이론비교)는
            # _build_context 본문이 직접 렌더 → 섹션 헤더로 실투입만 확인
            _HDR = {
                "acled_events":    "## ACLED 이벤트 통계",
                "cascade":         "## Cascade",
                "country_profile": "## 행위자 국가 프로파일",
                "theory_compare":  "## 경쟁 이론 비교 프로파일",
                "library_like":    "## 브리핑·이론 원문",
                "library_sector":  "## 추가 관련 브리핑",
            }
            h = _HDR.get(key, "")
            in_ctx = bool(h) and h in context_text
            if key == "theory_compare" and isinstance(raw, str):
                rendered = len(raw)
        rec["rendered_chars"] = rendered
        rec["in_context"] = in_ctx
        rec["source_counts_key"] = sc_key
        out[key] = rec
    return out


# ── 단계 3: 컨텍스트 조립 해부 ───────────────────────────────────────────────

def _dissect_context(ctx: str, intel: dict) -> dict:
    sections = []
    for m in re.finditer(r"^## .*$", ctx, re.M):
        sections.append({"header": m.group(0).strip(), "start": m.start()})
    for i, s in enumerate(sections):
        end = sections[i + 1]["start"] if i + 1 < len(sections) else len(ctx)
        s["chars"] = end - s["start"]
        s["order"] = i + 1
        s.pop("start")

    # 브리핑 전문(full body) 판정 — _build_context와 같은 규칙(_own_relevance ≥ _BRIEF_FULL_MIN
    # AND _own_rel_ts ≥ 2 AND 상위 3개)을 재현해 어느 브리핑이 전문 주입됐는지 식별
    seen, all_items = set(), []
    for item in (intel.get("like_items") or []) + (intel.get("sector_items") or []):
        tid = item.get("theory_id", "")
        if tid and tid not in seen:
            seen.add(tid)
            all_items.append(item)
    all_items.sort(key=lambda x: (x.get("_own_relevance", 0), len(x.get("body") or "")),
                   reverse=True)

    briefs, n_full = [], 0
    for it in all_items:
        rel = it.get("_own_relevance", 0)
        rel_ts = it.get("_own_rel_ts", 0)
        body = (it.get("body") or "").strip()
        full = bool(body and n_full < 3 and rel >= IA._BRIEF_FULL_MIN and rel_ts >= 2
                    and f"### " in ctx and (it.get("title", "") or "\x00") in ctx)
        if full:
            n_full += 1
        briefs.append({
            "title": it.get("title", ""),
            "source_org": it.get("source_org", ""),
            "own_relevance": rel,
            "own_rel_ts": rel_ts,
            "body_chars": len(body),
            "full_body_injected": full,
        })

    return {
        "context_chars": len(ctx),
        "data_layer_chars": (intel.get("grounding") or {}).get("data_context_chars", 0),
        "budget_max": IA._CONTEXT_MAX_CHARS,
        "budget_overflow": "[컨텍스트 예산 초과" in ctx,
        "n_sections": len(sections),
        "sections": sections,
        "n_briefings_total": len(all_items),
        "n_briefings_full_body": n_full,
        "briefings": briefs[:12],
    }


# ── 단계 6: LLM 생성 (provider별) ────────────────────────────────────────────

async def _generate(prompt: str) -> tuple[str, dict]:
    """provider에 맞는 생성기를 호출해 full_text를 반환. intel_query의 스트리머 재사용."""
    prov = IQ._LLM_PROVIDER
    t0 = time.perf_counter()
    text = ""
    if prov == "nim":
        async for chunk in IQ._nim_stream_text(prompt):
            text += chunk
    elif prov == "ollama":
        async for chunk in IQ._ollama_stream_text(prompt):
            text += chunk
    else:  # gemini — intel_query의 _stream_gemini은 후처리까지 묶여 있어 스트림만 재현
        body = {
            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
            "generationConfig": {"maxOutputTokens": 16384, "temperature": 0.7},
        }
        url = IQ._GEMINI_URL.format(key=IQ._GEMINI_KEY)
        async with httpx.AsyncClient(timeout=180) as cl:
            async with cl.stream("POST", url, json=body) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    text = f"⚠️ Gemini {resp.status_code}: {err[:200]!r}"
                else:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        try:
                            ch = json.loads(line[6:].strip())
                            for p in (ch.get("candidates", [{}])[0].get("content", {})
                                      .get("parts", [])):
                                if not p.get("thought"):
                                    text += p.get("text", "")
                        except Exception:  # noqa: BLE001, S112
                            continue
    ms = round((time.perf_counter() - t0) * 1000, 1)
    return text, {
        "provider": prov,
        "model": (IQ._NIM_MODEL if prov == "nim"
                  else IQ._OLLAMA_MODEL if prov == "ollama" else IQ._GEMINI_MODEL),
        "ms": ms,
        "response_chars": len(text),
        "empty": not text.strip(),
    }


# ── 메인 ────────────────────────────────────────────────────────────────────

def _spec_dump(s) -> dict:
    return {
        "h1": s.h1,
        "h0": s.h0,
        "independent_var": s.independent_var,
        "dependent_var": s.dependent_var,
        "control_vars": s.control_vars,
        "var_type": s.var_type,
        "region_code": s.region_code,
        "dependent_region": s.dependent_region,
        "ticker": s.ticker,
        "linear_testable": s.linear_testable,
        "testability_reason": s.testability_reason,
        "proxy_suggestions": s.proxy_suggestions,
        "is_proxy_pair": s.is_proxy_pair,
        "is_substituted_target": getattr(s, "is_substituted_target", False),
        "exploratory": getattr(s, "exploratory", False),
    }


async def main() -> None:
    tr = Trace(ARGS.query)

    # ── 1. 파싱 ──────────────────────────────────────────────────────────────
    pq = tr.run("1_parse", lambda: {
        "value": parse_query(ARGS.query),
    })
    pq = pq["value"] if isinstance(pq, dict) else pq
    if pq is None:
        print("치명: 파싱 실패 — 이후 단계 진행 불가")
        _write(tr)
        return
    st = tr.stage("1_parse")
    st.pop("value", None)
    st.update(pq.to_dict())
    st["keywords"] = IA._extract_keywords(pq.raw_query)

    # ── 2. 조달 24종 + 3. 조립 + 4. 접지 (build_intel_context 1회) ───────────
    _install_procurement_probes()
    intel = tr.run("2_procurement", lambda: {"_": None})  # 자리 확보 (아래에서 덮어씀)
    t0 = time.perf_counter()
    try:
        intel = await IA.build_intel_context(pq)
        ctx_ms = round((time.perf_counter() - t0) * 1000, 1)
        ctx_text = intel["context_text"]
        tr.data["stages"]["2_procurement"] = {
            "status": "OK", "ms": ctx_ms,
            "source_counts": intel.get("source_counts", {}),
            "sources": _finish_procurement(ctx_text),
        }
        tr.data["stages"]["3_context"] = {"status": "OK", "ms": 0,
                                          **_dissect_context(ctx_text, intel)}
        tr.data["stages"]["4_grounding"] = {"status": "OK", "ms": 0,
                                            **(intel.get("grounding") or {})}
    except Exception as e:  # noqa: BLE001
        tr.data["stages"]["2_procurement"] = {
            "status": "FAIL", "ms": round((time.perf_counter() - t0) * 1000, 1),
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc()[-1500:],
            "sources": _finish_procurement(""),
        }
        _write(tr)
        return

    if ARGS.full:
        tr.data["context_text"] = ctx_text

    # ── 5. 프롬프트 ──────────────────────────────────────────────────────────
    def _mk_prompt() -> dict:
        titles = [i.get("title", "") for i in
                  (intel.get("like_items", []) + intel.get("sector_items", []))[:5]]
        syn = ("### 참조 브리핑\n" + "\n".join(f"- {t}" for t in titles)) if titles else ""
        p = IQ._build_prompt(pq, ctx_text, syn)
        d = {"prompt_chars": len(p), "synthesis_chars": len(syn),
             "context_share": round(len(ctx_text) / len(p), 3) if p else 0,
             "_prompt": p}
        if ARGS.full:
            d["prompt_text"] = p
        return d

    pr = tr.run("5_prompt", _mk_prompt)
    prompt = (pr or {}).get("_prompt", "")
    tr.stage("5_prompt").pop("_prompt", None)

    if ARGS.no_llm or not prompt:
        tr.data["stages"]["6_llm"] = {"status": "SKIPPED", "reason": "--no-llm 또는 프롬프트 부재"}
        _write(tr)
        _print_summary(tr)
        return

    # ── 6. LLM 생성 ──────────────────────────────────────────────────────────
    full_text, gen_meta = "", {}
    try:
        full_text, gen_meta = await _generate(prompt)
        tr.data["stages"]["6_llm"] = {
            "status": "SILENT" if not full_text.strip() else "OK",
            **gen_meta, "response_text": full_text,
        }
    except Exception as e:  # noqa: BLE001
        tr.data["stages"]["6_llm"] = {"status": "FAIL", "error": f"{type(e).__name__}: {e}",
                                      "traceback": traceback.format_exc()[-1500:]}

    if not full_text.strip():
        _write(tr)
        _print_summary(tr)
        return

    # ── 7. 후처리 (lint + dv_gate) — _finalize와 동일 순서 ────────────────────
    def _post() -> dict:
        from services.deterministic_lint import lint as _lint, strip_scaffold as _strip
        from services.dv_gate import apply_gate as _dv
        t, n_strip = _strip(full_text)
        problems = _lint(t)
        m = re.search(r"<context>(.*?)</context>", prompt, re.S)
        t2, actions = _dv(t, m.group(1) if m else None)
        return {
            "scaffold_lines_stripped": n_strip,
            "lint_problems": problems,
            "lint_count": len(problems),
            "dv_gate_actions": actions,
            "dv_gate_count": len(actions),
            "text_delta_chars": len(t2) - len(full_text),
            "_text": t2,
        }

    po = tr.run("7_postprocess", _post)
    clean = (po or {}).get("_text", full_text)
    tr.stage("7_postprocess").pop("_text", None)

    # ── 8. 채점 ──────────────────────────────────────────────────────────────
    def _score() -> dict:
        from services.confidence_scorer import score_confidence, apply_data_void_penalty
        sc = intel.get("source_counts", {})
        r = score_confidence(clean, sc, intel.get("grounding"))
        r["inference_grade"] = "기술적"
        r["inference_caveat"] = "인과 검정 미수행 — 서술·이론 근거만(인과 아님)"
        _STRUCTURED = ("sipri_countries", "cow_alliances", "kiel_donors", "eia_entries",
                       "csis_incidents", "sipri_arms", "vdem_entries", "cow_wars",
                       "fred", "wbk", "polity5", "itu", "hiik", "semi", "owid")
        n_struct = sum(1 for k in _STRUCTURED if sc.get(k, 0) > 0)
        pen = apply_data_void_penalty(r["confidence"], sc.get("event_stats_regions", 0),
                                      sc.get("cascade_links", 0), n_struct)
        r["data_void_penalty_applied"] = pen != r["confidence"]
        r["confidence_before_penalty"] = r["confidence"]
        r["confidence"] = pen
        r["provisional"] = pen < 60 or r.get("grounding_flag") == "TOPIC_ABSENT"
        r["structured_sources"] = n_struct
        return r

    tr.run("8_score", _score)

    # ── 9. 가설 추출 ─────────────────────────────────────────────────────────
    def _extract() -> dict:
        from services.hypothesis_extractor import extract_hypotheses
        specs = extract_hypotheses(clean, default_regions=pq.regions)
        for s in specs:
            s.source_query = ARGS.query
            # [세탁 버그 수리 2026-07-13] 구판: `s.exploratory = (pq.mode != "verify")`
            # verify 모드는 쿼리에 "검증"·"근거"·"확인"이 있으면 켜지는 어투 판정이지
            # 가설 직접 입력이 아니다. 가설은 위 extract_hypotheses(clean)가 **LLM 출력
            # (=데이터를 보고 생성된 텍스트)**에서 뽑는다 — 구성상 전부 HARKing이다.
            # 추출기 기본값(exploratory=True)을 그대로 둔다. 확증은 사전등록 경로에서만.
        return {"n_hypotheses": len(specs),
                "hypotheses": [_spec_dump(s) for s in specs],
                "_specs": specs}

    ex = tr.run("9_hypothesis", _extract)
    specs = (ex or {}).get("_specs", []) or []
    tr.stage("9_hypothesis").pop("_specs", None)
    if not specs:
        tr.stage("9_hypothesis")["status"] = "SILENT"

    # ── 10. 방법 라우팅 (verify 전 사전 판정 — 라우터 직접 호출) ─────────────
    def _route() -> dict:
        from services.methods.router import (classify_signature, select_method_set,
                                             filter_implemented, unquantifiable_question_reason)
        rows = []
        for s in specs:
            sig = classify_signature(f"{s.source_query} {s.h1} {s.h0}",
                                     linear_testable=s.linear_testable)
            methods = select_method_set(sig)
            impl, stubs = filter_implemented(methods)
            rows.append({"h1": s.h1[:70], "data_signature": sig,
                         "method_set": methods, "implemented": impl, "stubs": stubs,
                         "unquantifiable_reason": unquantifiable_question_reason(
                             f"{s.source_query} {s.h1} {s.h0}")})
        return {"n_routed": len(rows), "routes": rows}

    tr.run("10_routing", _route)
    if not specs:
        tr.stage("10_routing")["status"] = "SILENT"

    # ── 11. 검정 (Granger·패널·이벤트스터디) ─────────────────────────────────
    if specs:
        t0 = time.perf_counter()
        try:
            from services.hypothesis_verifier import verify_hypotheses
            specs = await verify_hypotheses(specs)
            tr.data["stages"]["11_verify"] = {
                "status": "OK", "ms": round((time.perf_counter() - t0) * 1000, 1),
                "results": [{
                    "h1": s.h1[:70],
                    "verification_status": s.verification_status,
                    "inference_grade": s.inference_grade,
                    "inference_caveat": s.inference_caveat,
                    "routing_method": s.routing_method,
                    "routing_confidence": s.routing_confidence,
                    "routing_alternatives": s.routing_alternatives,
                    "data_signature": s.data_signature,
                    "granger_p": s.granger_p,
                    "granger_q": s.granger_q,
                    "f_statistic": s.f_statistic,
                    "best_lag": s.best_lag,
                    "n_obs": s.n_obs,
                    "differenced": s.differenced,
                    "controlled": s.controlled,
                    "control_name": s.control_name,
                    "theory_grounded": s.theory_grounded,
                    "partial_basis": s.partial_basis,
                    "is_substituted_target": getattr(s, "is_substituted_target", False),
                    "surface_summary": s.surface_summary,
                    "confidence_word": s.confidence_word,
                    "method_result": getattr(s, "method_result", {}),
                    "error": s.error,
                } for s in specs],
            }
        except Exception as e:  # noqa: BLE001
            tr.data["stages"]["11_verify"] = {
                "status": "FAIL", "ms": round((time.perf_counter() - t0) * 1000, 1),
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc()[-1500:]}
    else:
        tr.data["stages"]["11_verify"] = {"status": "SILENT", "reason": "가설 0건"}

    # ── 12. 예측 등재 (드라이런 — build_prediction만, INSERT 없음) ────────────
    def _predict() -> dict:
        from dataclasses import asdict
        rows, skipped = [], 0
        for s in specs:
            rec = PI.build_prediction(s, ARGS.query)
            if rec is None:
                skipped += 1
                continue
            rows.append(asdict(rec))
        return {"would_insert": len(rows), "skipped_declarations": skipped,
                "dry_run": True, "predictions": rows}

    tr.run("12_prediction_dryrun", _predict)
    if not specs:
        tr.stage("12_prediction_dryrun")["status"] = "SILENT"

    tr.data["tripwire"] = _TRIPWIRE
    _write(tr)
    _print_summary(tr)


def _slug(q: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", q).strip("-")
    return s[:60] or "query"


def _write(tr: Trace) -> None:
    out_dir = Path(ARGS.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_slug(ARGS.query)}.trace.json"
    path.write_text(json.dumps(tr.data, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    tr.data["_path"] = str(path)
    print(f"\n[trace] 저장: {path}")


# ── 사람이 읽는 요약 ────────────────────────────────────────────────────────

def _print_summary(tr: Trace) -> None:
    d = tr.data
    S = d["stages"]
    print("\n" + "=" * 78)
    print(f"TRACE  {d['query']}")
    print(f"provider={d['provider']}  model={d['model']}")
    print("=" * 78)

    p = S.get("1_parse", {})
    print(f"\n[1] 파싱 ({p.get('ms', 0)}ms)  mode={p.get('mode')} thinking={p.get('thinking')}")
    print(f"    regions={p.get('regions')}  actors={p.get('actors')}  sectors={p.get('sectors')}")
    print(f"    keywords={p.get('keywords')}")

    pc = S.get("2_procurement", {})
    srcs = pc.get("sources", {})
    fired = {k: v for k, v in srcs.items() if v.get("status") == "OK"}
    silent = [k for k, v in srcs.items() if v.get("status") == "SILENT"]
    failed = [k for k, v in srcs.items() if v.get("status") in ("FAIL", "NOT_CALLED")]
    print(f"\n[2] 조달 ({pc.get('ms', 0)}ms)  발화 {len(fired)}/{len(srcs)}")
    print(f"    {'source':16} {'n':>5} {'chars':>7} {'in_ctx':>7} {'ms':>7}")
    for k, v in sorted(srcs.items(), key=lambda x: -x[1].get("rendered_chars", 0)):
        if v.get("status") != "OK":
            continue
        print(f"    {k:16} {v.get('n_records', 0):>5} {v.get('rendered_chars', 0):>7} "
              f"{str(v.get('in_context')):>7} {v.get('ms', 0):>7}")
    print(f"    SILENT ({len(silent)}): {', '.join(silent) or '—'}")
    if failed:
        print(f"    FAIL/NOT_CALLED ({len(failed)}): {', '.join(failed)}")

    c = S.get("3_context", {})
    print(f"\n[3] 조립  총 {c.get('context_chars')}자 / 데이터층 {c.get('data_layer_chars')}자 "
          f"(예산 {c.get('budget_max')}, 초과절단={c.get('budget_overflow')})")
    for s in c.get("sections", [])[:14]:
        print(f"    {s['order']:>2}. {s['header'][:52]:52} {s['chars']:>6}자")
    print(f"    브리핑 {c.get('n_briefings_total')}편 중 전문주입 {c.get('n_briefings_full_body')}편")
    for b in c.get("briefings", [])[:6]:
        mark = "FULL" if b["full_body_injected"] else "요약"
        print(f"    [{mark}] rel={b['own_relevance']:>2} ts={b['own_rel_ts']} "
              f"{b['title'][:44]}")

    g = S.get("4_grounding", {})
    print(f"\n[4] 접지  flag={g.get('flag')}  ratio={g.get('grounded_ratio')}  "
          f"데이터층={g.get('data_context_chars')}자")
    print(f"    terms={g.get('terms')}")

    print(f"\n[5] 프롬프트  {S.get('5_prompt', {}).get('prompt_chars')}자 "
          f"(context 비중 {S.get('5_prompt', {}).get('context_share')})")

    l = S.get("6_llm", {})
    print(f"\n[6] LLM  {l.get('status')}  {l.get('response_chars', 0)}자  {l.get('ms', 0)}ms")
    if l.get("status") in ("SKIPPED", "FAIL", "SILENT"):
        print(f"\n[7~12] 미실행 (LLM {l.get('status')}) — 후처리·채점·가설·라우팅·검정·예측 없음")
        print(f"\n침묵 단계: {', '.join(k for k, v in S.items() if v.get('status') in ('SILENT', 'SKIPPED'))}")
        return

    pp = S.get("7_postprocess", {})
    print(f"\n[7] 후처리  스캐폴드제거={pp.get('scaffold_lines_stripped')}줄  "
          f"lint={pp.get('lint_count')}건  dv_gate={pp.get('dv_gate_count')}건")
    for x in (pp.get("lint_problems") or []):
        print(f"    [lint] {x.get('code')}: {str(x.get('detail'))[:60]}")
    for x in (pp.get("dv_gate_actions") or []):
        print(f"    [dv]   {x.get('code')}: {str(x.get('detail'))[:60]}")

    sc = S.get("8_score", {})
    print(f"\n[8] 채점  confidence={sc.get('confidence')} provisional={sc.get('provisional')} "
          f"legacy={sc.get('legacy_score')}")
    print(f"    breakdown={sc.get('breakdown')}")

    h = S.get("9_hypothesis", {})
    print(f"\n[9] 가설  {h.get('n_hypotheses', 0)}건 ({h.get('status')})")
    for x in (h.get("hypotheses") or []):
        print(f"    IV={x['independent_var'][:28]:28} DV={x['dependent_var'][:28]:28} "
              f"{x['var_type']} linear={x['linear_testable']} ticker={x['ticker']}")

    r = S.get("10_routing", {})
    print(f"\n[10] 라우팅 ({r.get('status')})")
    for x in (r.get("routes") or []):
        print(f"    sig={x['data_signature']:18} set={x['method_set']} stubs={x['stubs']}")

    v = S.get("11_verify", {})
    print(f"\n[11] 검정 ({v.get('status')}, {v.get('ms', 0)}ms)")
    for x in (v.get("results") or []):
        print(f"    {x['verification_status']:8} grade={x['inference_grade']:6} "
              f"p={x['granger_p']} n={x['n_obs']} route={x['routing_method']}")
        if x.get("error"):
            print(f"      error: {str(x['error'])[:70]}")

    pd_ = S.get("12_prediction_dryrun", {})
    print(f"\n[12] 예측 등재 (드라이런)  등재될 것 {pd_.get('would_insert', 0)}건 / "
          f"선언문 제외 {pd_.get('skipped_declarations', 0)}건")
    for x in (pd_.get("predictions") or []):
        print(f"    target={x['target']} kind={x['target_kind']} dir={x['direction']} "
              f"scorable={x['scorable']} resolve_by={x['resolve_by']}")

    silent_stages = [k for k, v in S.items() if v.get("status") in ("SILENT", "SKIPPED")]
    print(f"\n침묵 단계: {', '.join(silent_stages) or '없음'}")
    if d.get("tripwire"):
        print(f"⚠️ 드라이런 위반: {d['tripwire']}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
