"""P6 실험 ② — Claude judge 골드 양방향 비대칭 (개선위 게이트, 판례 20260710-engine-improvement-committee).

통과 기준: defect_gold 전건 cr ≤ 상한 AND exemplar_gold 전건 cr ≥ 하한 (서열 보존).
이해충돌 완화 반영: 루브릭 동결(eval_insight._JUDGE_RUBRIC 그대로) · 컨텍스트 차단
(claude -p 무상태 headless, 골드 라벨 비노출 맹검) · 반복 n=3 중앙값(노이즈 완충).
모델 2종 병행: 기본(fable)·sonnet(루틴 운영 후보) — CLI 모델 핀 불가 한계는 결과에 버전 기록.

실행: .venv/bin/python tests/claude_judge_gold.py [--n 3]
출력: tests/eval_results/claude_gold_YYYYMMDD_HHMM.json
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from eval_insight import _JUDGE_RUBRIC  # noqa: E402 — 루브릭 동결: v1 원본 재사용

BASE = Path(__file__).resolve().parent
GOLD = yaml.safe_load((BASE / "judge_gold.yaml").read_text())
FROZEN = json.loads((BASE / "eval_results" / "latest.json").read_text())
MODELS = ["fable", "sonnet"]
AXES = ("non_obviousness", "inference_honesty", "competing_rigor", "falsifiability")
_JSON = re.compile(r"\{[^{}]*\}")


def _text_for(case_id: str) -> str | None:
    for r in FROZEN["results"]:
        if r.get("id") == case_id and r.get("full_text"):
            return r["full_text"]
    return None


def _judge_once(model: str, text: str) -> dict | None:
    """claude -p 무상태 1회 채점 — 마지막 JSON 블록 파싱."""
    prompt = _JUDGE_RUBRIC + text[:14000]
    try:
        p = subprocess.run(
            ["claude", "--model", model, "-p", prompt],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return None
    m = _JSON.findall(p.stdout or "")
    for cand in reversed(m):
        try:
            d = json.loads(cand)
            if all(a in d for a in AXES):
                return {a: float(d[a]) for a in AXES}
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def main(n: int) -> None:
    cases = (
        [(cid, "defect", spec) for cid, spec in (GOLD.get("defect_gold") or {}).items()]
        + [(cid, "exemplar", spec) for cid, spec in (GOLD.get("exemplar_gold") or {}).items()]
    )
    out = {"timestamp": datetime.now().strftime("%Y%m%d_%H%M"), "n_per_case": n,
           "rubric": "v1(동결)", "models": {}}
    for model in MODELS:
        rows = []
        for cid, kind, spec in cases:
            text = _text_for(cid)
            if text is None:
                rows.append({"id": cid, "kind": kind, "error": "frozen text 없음"})
                continue
            scores = []
            for i in range(n):
                s = _judge_once(model, text)
                if s:
                    scores.append(s)
                time.sleep(2)
            crs = [s["competing_rigor"] for s in scores]
            med = statistics.median(crs) if crs else None
            bound = spec.get("cr_max") if kind == "defect" else spec.get("cr_min")
            ok = (med is not None and
                  (med <= bound if kind == "defect" else med >= bound))
            rows.append({"id": cid, "kind": kind, "bound": bound, "cr_runs": crs,
                         "cr_median": med, "pass": ok, "all_axes": scores})
            print(f"[{model}] {cid} ({kind}, 기준 {'≤' if kind=='defect' else '≥'}{bound}) "
                  f"cr={crs} → 중앙값 {med} {'✅' if ok else '❌'}")
        valid = [r for r in rows if "pass" in r]
        asym = all(r["pass"] for r in valid) and len(valid) == len(cases)
        out["models"][model] = {"cases": rows, "asymmetry_pass": asym}
        print(f"== {model}: 비대칭 게이트 {'통과 ✅' if asym else '불통과 ❌'}\n")

    dst = BASE / "eval_results" / f"claude_gold_{out['timestamp']}.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"저장: {dst.name}")


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 3
    main(n)
