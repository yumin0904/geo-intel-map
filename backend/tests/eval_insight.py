#!/usr/bin/env python3
"""
eval_insight.py — 인사이트 분석실 자동화 테스트

사용법:
  cd backend
  python tests/eval_insight.py                  # 전체 케이스 실행
  python tests/eval_insight.py --case ukraine   # 특정 케이스만
  python tests/eval_insight.py --summary        # 마지막 결과만 출력

출력:
  tests/eval_results/YYYYMMDD_HHMM.json  — 상세 결과
  tests/eval_results/latest.json         — 항상 최신 결과 (덮어쓰기)
  stdout: 터미널 요약 (Claude Code가 읽고 개선안 도출)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml

# ── 경로 설정 ─────────────────────────────────────────────────────────────
_ROOT    = Path(__file__).resolve().parents[1]  # backend/
_CASES   = Path(__file__).parent / "eval_cases.yaml"
_OUT_DIR = Path(__file__).parent / "eval_results"
_OUT_DIR.mkdir(exist_ok=True)

BASE_URL = "http://localhost:8000"

# ── 필수 섹션 기본값 (모드별) ─────────────────────────────────────────────
_DEFAULT_SECTIONS = {
    "insight": ["[관찰]", "[주장]", "[가설]", "[근거]",
                "[한계]", "[경쟁설명]", "[검증포인트]", "[문헌공백]"],
    "verify":  ["[단계 1]", "[단계 2]", "[단계 3]",
                "[단계 4]", "[단계 5]", "[단계 6]"],
    "presentation": ["[관찰]", "[주장]", "[가설]", "[근거]"],
}

# ── SSE 스트림 수집 ───────────────────────────────────────────────────────

def _collect_sse(query: str, mode: str, timeout: int = 120) -> dict:
    """백엔드 /api/intel/query SSE를 수집하고 이벤트별로 분류해 반환."""
    payload = {"query": query}
    # 모드 키워드를 쿼리에 자동 삽입 (entity_parser가 감지)
    if mode == "presentation":
        payload["query"] = query + " 발표 주제로 추천해줘"
    elif mode == "verify":
        payload["query"] = query + " 근거와 검증 포인트를 중심으로"

    result = {
        "full_text": "",
        "score_event": None,
        "hypothesis_events": [],
        "error": None,
        "elapsed": 0.0,
    }
    t0 = time.time()

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", f"{BASE_URL}/api/intel/query",
                               json=payload) as resp:
                if resp.status_code != 200:
                    result["error"] = f"HTTP {resp.status_code}"
                    return result

                for raw_line in resp.iter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    data_str = raw_line[6:].strip()
                    if data_str in ("[DONE]", ""):
                        continue
                    try:
                        ev = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    ev_type = ev.get("type", "")
                    if ev_type == "score":
                        result["score_event"] = ev
                    elif ev_type == "hypothesis":
                        result["hypothesis_events"].append(ev)
                    elif "text" in ev:
                        result["full_text"] += ev.get("text", "")

    except httpx.ConnectError:
        result["error"] = "서버 연결 실패 (localhost:8000 — 서버가 실행 중인지 확인)"
    except httpx.TimeoutException:
        result["error"] = "타임아웃"
    except Exception as e:
        result["error"] = str(e)

    result["elapsed"] = round(time.time() - t0, 1)

    # Gemini API 오류 메시지를 error로 분류 (FAIL이 아닌 SKIP 처리)
    ft = result["full_text"]
    if ft and ("⚠️ Gemini API 오류" in ft or "GEMINI_API_KEY가 설정되지 않았습니다" in ft):
        result["error"] = ft.strip()
        result["full_text"] = ""
    # 응답 시간 < 2초 & 텍스트 없음 → API 오류로 간주
    elif not ft and result["elapsed"] < 2.0 and not result.get("error"):
        result["error"] = "빈 응답 (API 오류 가능성)"

    return result


# ── 케이스 평가 ───────────────────────────────────────────────────────────

def _check_sections(text: str, required: list[str]) -> dict[str, bool]:
    """각 섹션 헤더의 존재 여부를 확인."""
    return {sec: (sec in text) for sec in required}


def _check_tags(text: str, tags: list[str]) -> dict[str, bool]:
    """기대 키워드의 포함 여부를 확인."""
    return {tag: (tag in text) for tag in tags}


def _check_rival_comparison(text: str) -> dict:
    """[경쟁설명] 섹션에서 7-B 수치 편차 비교 충족 여부 확인.

    두 수준으로 채점:
    - quantitative (엄격): '예측:' + '실측:' 레이블 모두 존재
    - comparative (완화): 이론명 2개+ + 수치(%) + 판정 키워드 존재
    """
    rival_section = ""
    m = re.search(r"\[경쟁설명\](.*?)(?=\[검증포인트\]|\[문헌공백\]|\Z)", text, re.DOTALL)
    if m:
        rival_section = m.group(1)

    # 엄격 기준
    has_prediction = bool(re.search(r"예측\s*:", rival_section))
    has_measured   = bool(re.search(r"실측\s*:", rival_section))
    has_verdict    = bool(re.search(r"(편차|우세|판정)\s*:", rival_section))

    # 완화 기준: 이론명 2개+ 비교 + 수치 + 기각/우세 표현
    theory_mentions = len(re.findall(
        r"(현실주의|자원무기화|무기화|억지|회색지대|하이브리드|해양력|동맹 이론|디지털 철|"
        r"Mahan|Waltz|Mearsheimer|Libicki|Farrell|Hirschman|Snyder|Hoffman|A2/AD)",
        rival_section, re.IGNORECASE
    ))
    has_numbers = bool(re.search(r"\d+[\.\d]*\s*(%|Mbpd|bn|억|조|건|회|달러|USD)", rival_section))
    has_rejection = bool(re.search(
        r"(기각|우세|열세|설명력|반례|한계|부분적|불충분|초과|미달|더 높|더 낮)", rival_section
    ))
    comparative = theory_mentions >= 2 and (has_numbers or has_rejection)

    quantitative = has_prediction and has_measured
    return {
        "has_prediction_label": has_prediction,
        "has_measured_label": has_measured,
        "has_verdict_label": has_verdict,
        "theory_mentions": theory_mentions,
        "has_numbers_in_rival": has_numbers,
        "quantitative_comparison": quantitative,
        "comparative_comparison": comparative,   # 완화 기준
    }


def _check_labels(text: str) -> dict[str, int]:
    """품질 레이블 카운트."""
    return {
        "UNVERIFIED": text.count("[UNVERIFIED]"),
        "SPECULATIVE": text.count("[SPECULATIVE]"),
        "PROVISIONAL": text.count("[PROVISIONAL]"),
        "TEMPORAL_REVERSAL": text.count("[TEMPORAL_REVERSAL]"),
        "HIGH_chain": text.count("HIGH"),
        "MEDIUM_chain": text.count("MEDIUM"),
        "LOW_chain": text.count("LOW"),
    }


def _check_h1(text: str, hyp_events: list | None = None) -> bool:
    """H1 가설 문장이 있는지 확인 — SSE 이벤트 우선, 텍스트 검색 fallback."""
    # SSE hypothesis 이벤트가 있으면 extractor가 H1을 찾은 것
    if hyp_events:
        return True
    # 텍스트에서 직접 H1 탐지 (insight: H1: / verify: **H1 (주장)**: )
    return bool(re.search(r"H1\s*[:：\s\*\(]", text))


def _score_completeness(section_results: dict) -> float:
    """섹션 충족률 0~1."""
    if not section_results:
        return 0.0
    return sum(section_results.values()) / len(section_results)


def evaluate_case(case: dict) -> dict:
    """단일 케이스 실행 및 평가."""
    name    = case["name"]
    cid     = case["id"]
    query   = case["query"]
    mode    = case.get("mode", "insight")
    expect  = case.get("expect", {})
    req_sec = expect.get("sections", _DEFAULT_SECTIONS.get(mode, _DEFAULT_SECTIONS["insight"]))
    exp_tags = expect.get("tags", [])
    exp_score = expect.get("min_score", 60)
    exp_h1    = expect.get("h1", False)

    print(f"\n{'='*60}")
    print(f"▶ [{cid}] {name}")
    print(f"  쿼리: {query[:60]}...")
    print(f"  실행 중...", end="", flush=True)

    sse = _collect_sse(query, mode)
    # 503 오류 시 최대 2회 재시도 (30초, 60초 간격)
    for wait in (30, 60):
        if not (sse.get("error") and "503" in str(sse.get("error", ""))):
            break
        print(f" 503 → {wait}초 후 재시도...", end="", flush=True)
        time.sleep(wait)
        sse = _collect_sse(query, mode)
    print(f" {sse['elapsed']}s")

    if sse["error"]:
        print(f"  ❌ 오류: {sse['error']}")
        return {"id": cid, "name": name, "error": sse["error"], "elapsed": sse["elapsed"]}

    text       = sse["full_text"]
    hyp_events = sse["hypothesis_events"]

    section_check = _check_sections(text, req_sec)
    tag_check     = _check_tags(text, exp_tags)
    labels        = _check_labels(text)
    has_h1        = _check_h1(text, hyp_events)
    rival_check   = _check_rival_comparison(text)

    score_ev   = sse["score_event"] or {}
    confidence = score_ev.get("confidence", 0)
    provisional = score_ev.get("provisional", True)
    # hypothesis 이벤트는 {"type":"hypothesis", "hypotheses":[{...},...]} 구조
    hyp_summary = []
    for ev in hyp_events:
        for h in ev.get("hypotheses", [ev]):  # hypotheses 키 없으면 이벤트 자체로 fallback
            hyp_summary.append({
                "h1": h.get("h1", ""),
                "status": h.get("verification_status", "PENDING"),
                "var_type": h.get("var_type", ""),
                "p_value": h.get("granger_p"),
            })

    completeness = _score_completeness(section_check)
    missing_sections = [s for s, ok in section_check.items() if not ok]
    missing_tags     = [t for t, ok in tag_check.items() if not ok]

    # 통과/실패 판정
    passed = (
        confidence >= exp_score
        and completeness >= 0.875   # 7/8 이상
        and (not exp_h1 or has_h1)
    )

    # 터미널 출력
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}  신뢰도: {confidence}/100  섹션: {int(completeness*100)}%")
    if missing_sections:
        print(f"  ⚠ 누락 섹션: {', '.join(missing_sections)}")
    if missing_tags:
        print(f"  ⚠ 누락 키워드: {', '.join(missing_tags)}")
    if labels["TEMPORAL_REVERSAL"]:
        print(f"  🔁 시간 역전 탐지: {labels['TEMPORAL_REVERSAL']}건")
    cmp_mark = "✅" if rival_check["quantitative_comparison"] else "⚠"
    print(f"  {cmp_mark} 경쟁이론 수치 비교: 예측{'✓' if rival_check['has_prediction_label'] else '✗'} 실측{'✓' if rival_check['has_measured_label'] else '✗'} 판정{'✓' if rival_check['has_verdict_label'] else '✗'}")
    if hyp_summary:
        for h in hyp_summary:
            mark = "🟢" if h["status"] == "VERIFIED" else "🟡" if h["status"] == "PARTIAL" else "⚪"
            print(f"  {mark} H1 [{h['status']}] type={h['var_type']} p={h['p_value']}")
    elif exp_h1:
        print(f"  ⚠ H1 가설 미추출 (기대: True)")

    return {
        "id": cid,
        "name": name,
        "mode": mode,
        "passed": passed,
        "elapsed": sse["elapsed"],
        "confidence": confidence,
        "provisional": provisional,
        "completeness_pct": round(completeness * 100),
        "missing_sections": missing_sections,
        "missing_tags": missing_tags,
        "has_h1": has_h1,
        "h1_expected": exp_h1,
        "hypothesis": hyp_summary,
        "labels": labels,
        "rival_check": rival_check,
        "full_text": text,  # 상세 분석용 (JSON에 포함)
        "expected_min_score": exp_score,
    }


# ── 종합 리포트 ───────────────────────────────────────────────────────────

def _print_summary(results: list[dict]) -> None:
    ok = [r for r in results if r.get("passed")]
    fail = [r for r in results if not r.get("passed") and not r.get("error")]
    err  = [r for r in results if r.get("error")]

    total = len(results)
    print(f"\n{'='*60}")
    print(f"📊 종합 결과: {len(ok)}/{total} PASS")
    print(f"  ✅ 통과: {len(ok)}  ❌ 실패: {len(fail)}  🔌 오류: {len(err)}")

    if fail:
        print("\n실패 케이스 요약:")
        for r in fail:
            issues = []
            if r["confidence"] < r["expected_min_score"]:
                issues.append(f"신뢰도 {r['confidence']}<{r['expected_min_score']}")
            if r["missing_sections"]:
                issues.append(f"누락 섹션 {r['missing_sections']}")
            if r["h1_expected"] and not r["has_h1"]:
                issues.append("H1 미추출")
            print(f"  [{r['id']}] {' / '.join(issues)}")

    avg_conf = sum(r.get("confidence", 0) for r in results if not r.get("error"))
    n_valid  = sum(1 for r in results if not r.get("error"))
    if n_valid:
        print(f"\n평균 신뢰도: {avg_conf // n_valid}/100")

    avg_elapsed = sum(r.get("elapsed", 0) for r in results) / max(len(results), 1)
    print(f"평균 응답 시간: {avg_elapsed:.1f}s")


def _diagnosis(results: list[dict]) -> str:
    """Claude Code용 진단 텍스트 생성."""
    lines = ["## 자동화 테스트 진단\n"]

    # 반복 실패 패턴
    all_missing = []
    for r in results:
        all_missing.extend(r.get("missing_sections", []))

    from collections import Counter
    sec_counts = Counter(all_missing)
    if sec_counts:
        lines.append("### 반복 누락 섹션 (빈도순)")
        for sec, cnt in sec_counts.most_common():
            lines.append(f"- `{sec}`: {cnt}/{len(results)} 케이스에서 누락")

    # 신뢰도 분포
    confs = [r.get("confidence", 0) for r in results if not r.get("error")]
    if confs:
        lines.append(f"\n### 신뢰도 분포")
        lines.append(f"- 최고: {max(confs)}, 최저: {min(confs)}, 평균: {sum(confs)//len(confs)}")
        lines.append(f"- 60 미만(PROVISIONAL): {sum(1 for c in confs if c < 60)}/{len(confs)}")

    # H1 추출 현황
    h1_needed = [r for r in results if r.get("h1_expected")]
    h1_ok = [r for r in h1_needed if r.get("has_h1")]
    if h1_needed:
        lines.append(f"\n### H1 가설 추출률")
        lines.append(f"- {len(h1_ok)}/{len(h1_needed)} 케이스에서 H1 추출 성공")
        for r in h1_needed:
            mark = "✅" if r.get("has_h1") else "❌"
            lines.append(f"  {mark} [{r['id']}]")

    # 경쟁이론 수치 비교 충족률 (Cycle 7-B)
    insight_results = [r for r in results if r.get("mode") == "insight" and not r.get("error")]
    if insight_results:
        n = len(insight_results)
        quantitative_cnt = sum(1 for r in insight_results if r.get("rival_check", {}).get("quantitative_comparison"))
        comparative_cnt  = sum(1 for r in insight_results if r.get("rival_check", {}).get("comparative_comparison"))
        lines.append(f"\n### 경쟁이론 수치 비교 충족률 (Cycle 7-B 평가)")
        lines.append(f"- [엄격] 예측+실측 레이블: {quantitative_cnt}/{n} ({round(quantitative_cnt/n*100)}%)")
        lines.append(f"- [완화] 이론 2개+수치+판정: {comparative_cnt}/{n} ({round(comparative_cnt/n*100)}%)")
        pred_cnt = sum(1 for r in insight_results if r.get("rival_check", {}).get("has_prediction_label"))
        meas_cnt = sum(1 for r in insight_results if r.get("rival_check", {}).get("has_measured_label"))
        lines.append(f"- '예측:' 레이블: {pred_cnt}/{n}")
        lines.append(f"- '실측:' 레이블: {meas_cnt}/{n}")
        status_strict = "✅ 달성" if quantitative_cnt/n*100 >= 50 else "❌ 미달"
        status_loose  = "✅ 달성" if comparative_cnt/n*100 >= 50 else "❌ 미달"
        lines.append(f"- 목표(50%+) 엄격: {status_strict} / 완화: {status_loose}")

    # Granger 검증 현황
    all_hyp = []
    for r in results:
        all_hyp.extend(r.get("hypothesis", []))
    if all_hyp:
        lines.append(f"\n### Granger 검증 현황 ({len(all_hyp)}개 가설)")
        from collections import Counter as C2
        status_dist = C2(h["status"] for h in all_hyp)
        for status, cnt in status_dist.most_common():
            lines.append(f"- {status}: {cnt}개")

    return "\n".join(lines)


# ── 메인 ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="인사이트 분석실 자동화 테스트")
    parser.add_argument("--case", help="특정 케이스 ID만 실행 (부분 매칭)")
    parser.add_argument("--summary", action="store_true", help="latest.json 요약만 출력")
    parser.add_argument("--no-save-text", action="store_true", help="결과 JSON에 full_text 제외")
    args = parser.parse_args()

    # --summary: 저장된 결과만 출력
    if args.summary:
        latest = _OUT_DIR / "latest.json"
        if not latest.exists():
            print("결과 없음. 먼저 테스트를 실행하세요.")
            sys.exit(1)
        data = json.loads(latest.read_text())
        _print_summary(data["results"])
        print("\n" + data.get("diagnosis", ""))
        return

    # 케이스 로드
    cases_data = yaml.safe_load(_CASES.read_text(encoding="utf-8"))
    cases = cases_data["cases"]
    if args.case:
        cases = [c for c in cases if args.case.lower() in c["id"].lower()]
        if not cases:
            print(f"케이스 '{args.case}' 없음. 사용 가능: {[c['id'] for c in cases_data['cases']]}")
            sys.exit(1)

    print(f"🧪 인사이트 분석실 테스트 — {len(cases)}개 케이스")
    print(f"📡 서버: {BASE_URL}")
    print(f"🕐 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for i, case in enumerate(cases):
        if i > 0:
            # Gemini 60 RPM 제한 대응 — 케이스 사이 5초 간격
            time.sleep(5)
        res = evaluate_case(case)
        if args.no_save_text:
            res.pop("full_text", None)
        results.append(res)

    _print_summary(results)

    # 진단 텍스트 생성 (Claude Code 분석용)
    diagnosis = _diagnosis(results)
    print("\n" + diagnosis)

    # JSON 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report = {
        "timestamp": timestamp,
        "server": BASE_URL,
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "results": results,
        "diagnosis": diagnosis,
    }

    out_path = _OUT_DIR / f"{timestamp}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (_OUT_DIR / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\n💾 저장: {out_path}")
    print(f"💾 최신: {_OUT_DIR / 'latest.json'}")

    # 실패 케이스가 있으면 종료 코드 1 (CI 대응)
    failed = sum(1 for r in results if not r.get("passed") and not r.get("error"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
