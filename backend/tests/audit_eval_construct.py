"""
tests/audit_eval_construct.py — eval 결과 전수 구성타당도·변수 감사 (2026-07-06)

목적(사용자 요청): 33케이스 eval 결과물에 변수 통제·구성타당도 문제가 있는지 전수 조사.
7호에서 드러난 결함(IV가 질문 대상을 측정 못함)이 다른 케이스에도 있는지 알고리즘으로 검출.

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/audit_eval_construct.py [결과.json]
기본 대상: tests/eval_results/latest.json

감사 항목 (각 가설 단위):
  1. IV_CONSTRUCT  — 케이스 쿼리의 국가 의도가 실제 검정 지역 표본에 <10%면 오염(7호형)
  2. PROXY_PAIR    — is_proxy_pair=True (화이트리스트 밖 대리변수쌍)
  3. NO_THEORY_SIG — 검정 유의(PARTIAL/VERIFIED)인데 theory_grounded=False (이론근거 없는 유의)
  4. LOW_ROUTING   — routing_confidence=LOW (방법 오선택 의심)
  5. NOT_DIFFERENCED — 검정 수행됐으나 1차 차분 미적용 (정상성 미보정 → 허위회귀 위험)
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.methods.iv_construct import (  # noqa: E402
    probe_event_iv, _named_countries, _MIN_TARGET_SHARE,
)

_CASES = Path(__file__).parent / "eval_cases.yaml"
_DEFAULT = Path(__file__).parent / "eval_results" / "latest.json"
_REGION_RE = re.compile(r"ACLED\s+([a-z_]+)")
_PROBE_START, _PROBE_END = date(2018, 1, 1), date(2026, 12, 31)


def _load_cases() -> dict[str, dict]:
    c = yaml.safe_load(_CASES.read_text())
    cases = c if isinstance(c, list) else c.get("cases", c)
    return {x["id"]: x for x in cases}


def audit(results_path: Path) -> dict:
    cases = _load_cases()
    data = json.loads(results_path.read_text())
    results = data.get("results", [])

    findings: list[tuple[str, str, str]] = []
    tested_total = 0
    probe_cache: dict[str, dict | None] = {}

    for r in results:
        cid = r.get("id", "?")
        query = cases.get(cid, {}).get("query", "")
        intent = _named_countries(query)  # 쿼리가 지목한 국가(의도)

        for h in r.get("hypothesis", []):
            h1 = h.get("h1", "")
            p = h.get("p_value")
            tested = p is not None
            if tested:
                tested_total += 1

            m = _REGION_RE.search(h1)
            region = m.group(1) if m else None

            # 1. IV 구성타당도 — 의도 국가가 실제 표본에 거의 없는가
            if region and intent and tested:
                if region not in probe_cache:
                    probe_cache[region] = probe_event_iv(region, _PROBE_START, _PROBE_END)
                probe = probe_cache[region]
                if probe and probe["n_events"] > 0:
                    share = sum(probe["country_dist"].get(c, 0) for c in intent) / probe["n_events"]
                    if share < _MIN_TARGET_SHARE:
                        top = max(probe["country_dist"], key=probe["country_dist"].get)
                        findings.append((cid, "IV_CONSTRUCT",
                            f"의도 {'·'.join(intent)} but 표본 {share:.0%} "
                            f"(region={region}, 최다={top} {probe['country_dist'][top]/probe['n_events']:.0%}) "
                            f"· p={p}"))

            # 2. 대리쌍 오류
            if h.get("is_proxy_pair"):
                findings.append((cid, "PROXY_PAIR", h1[:55]))

            # 3. 이론근거 없는 유의 검정
            if tested and h.get("status") in ("PARTIAL", "VERIFIED") and not h.get("theory_grounded"):
                findings.append((cid, "NO_THEORY_SIG", f"status={h['status']} p={p} · {h1[:40]}"))

            # 4. 방법 오선택 의심
            if h.get("routing_confidence") == "LOW":
                findings.append((cid, "LOW_ROUTING", f"{h.get('routing_method')} · {h1[:40]}"))

            # 5. 허위회귀 위험 — 유의(PARTIAL/VERIFIED)인데 1차 차분 미적용만 (비유의는 무해)
            if h.get("status") in ("PARTIAL", "VERIFIED") and h.get("differenced") is False:
                findings.append((cid, "SPURIOUS_RISK", f"status={h['status']} p={p} 차분X · {h1[:40]}"))

            # 6. 선언문인데 검정됨 (laundering 잔재 — '가설 없음'이 p값을 얻음)
            _decl = ("가설 없음" in h1 or "검증 가능한 정량 가설 없음" in h1)
            if tested and _decl:
                findings.append((cid, "DECLARATION_TESTED", f"p={p} status={h.get('status')} · {h1[:45]}"))

    by_cat: dict[str, list] = defaultdict(list)
    for cid, cat, note in findings:
        by_cat[cat].append((cid, note))
    return {"tested_total": tested_total, "by_cat": dict(by_cat),
            "n_cases": len(results), "timestamp": data.get("timestamp", "?")}


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT
    rep = audit(path)
    print(f"=== eval 구성타당도·변수 감사 ({rep['timestamp']}, {rep['n_cases']}케이스) ===")
    print(f"검정 수행된 가설: {rep['tested_total']}개\n")
    order = ["DECLARATION_TESTED", "IV_CONSTRUCT", "SPURIOUS_RISK", "NO_THEORY_SIG",
             "PROXY_PAIR", "LOW_ROUTING"]
    labels = {
        "DECLARATION_TESTED": "'가설 없음' 선언이 검정됨 (laundering 잔재 — 최우선)",
        "IV_CONSTRUCT": "IV 구성타당도 오염 (의도 국가가 표본에 <10%)",
        "SPURIOUS_RISK": "허위회귀 위험 (유의인데 차분 미적용)",
        "NO_THEORY_SIG": "이론근거 없는 유의 검정",
        "PROXY_PAIR": "대리변수쌍 오류 가능",
        "LOW_ROUTING": "방법 오선택 의심 (routing LOW)",
    }
    for cat in order:
        items = rep["by_cat"].get(cat, [])
        print(f"[{cat}] {labels[cat]} — {len(items)}건")
        for cid, note in items:
            print(f"    · {cid}: {note}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
