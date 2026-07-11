"""P6 실험③ 목적 전환 — prod-deepseek × claude-gold 크로스워크 (계측위 2026-07-11).

원목적(교체 후보 수렴타당도)은 실험② 불통과로 소멸 — 재조준: 프로덕션 judge(deepseek
직영)가 "형식 완비 + 수치 무효" 결함 골드 3건을 통과시키는지 교차해, 수치맹이 judge
모델 불문 구조적(→ 결정론 검사로만 커버 가능)인지 확증/반증한다.

규약은 claude_judge_gold.py 상속: 루브릭 v1 동결·골드 라벨 비노출 맹검·n=3 중앙값·
frozen text(latest.json) 동일 사용. 판례: geo-os [[20260711-instrumentation-committee]]

실행: .venv/bin/python tests/deepseek_judge_gold.py [--n 3]
출력: tests/eval_results/deepseek_gold_YYYYMMDD_HHMM.json
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from eval_insight import _JUDGE_RUBRIC, _judge_quality  # noqa: E402 — 루브릭 v1 동결 재사용

BASE = Path(__file__).resolve().parent
GOLD = yaml.safe_load((BASE / "judge_gold.yaml").read_text())
FROZEN = json.loads((BASE / "eval_results" / "latest.json").read_text())


def _text_for(case_id: str) -> str | None:
    for r in FROZEN["results"]:
        if r.get("id") == case_id and r.get("full_text"):
            return r["full_text"]
    return None


def main(n: int) -> None:
    cases = (
        [(cid, "defect", spec) for cid, spec in (GOLD.get("defect_gold") or {}).items()]
        + [(cid, "exemplar", spec) for cid, spec in (GOLD.get("exemplar_gold") or {}).items()]
    )
    rows = []
    for cid, kind, spec in cases:
        text = _text_for(cid)
        if text is None:
            rows.append({"id": cid, "kind": kind, "error": "frozen text 없음"})
            continue
        scores = []
        for _ in range(n):
            s = _judge_quality(text, rubric_text=_JUDGE_RUBRIC)
            if s:
                scores.append(s)
        if not scores:
            rows.append({"id": cid, "kind": kind, "error": "judge 응답 없음"})
            continue
        crs = [float(s["competing_rigor"]) for s in scores]
        med = statistics.median(crs)
        bound = spec.get("cr_max") if kind == "defect" else spec.get("cr_min")
        ok = (med <= bound) if kind == "defect" else (med >= bound)
        rows.append({"id": cid, "kind": kind, "cr_scores": crs, "cr_median": med,
                     "bound": bound, "pass": bool(ok),
                     "sd": round(statistics.stdev(crs), 3) if len(crs) > 1 else 0.0,
                     "all_axes": scores})
        print(f"{cid} [{kind}] cr={crs} med={med} bound={bound} {'PASS' if ok else 'FAIL'}")
    out = {"timestamp": datetime.now().strftime("%Y%m%d_%H%M"), "n_per_case": n,
           "rubric": "v1(동결)", "judge": "deepseek 직영(prod)", "results": rows}
    dest = BASE / "eval_results" / f"deepseek_gold_{out['timestamp']}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"→ {dest}")


if __name__ == "__main__":
    n = 3
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    main(n)
