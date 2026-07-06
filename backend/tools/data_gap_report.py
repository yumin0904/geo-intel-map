#!/usr/bin/env python3
"""
tools/data_gap_report.py — 데이터 수집 루프 1단계: eval 결과 → 데이터 갭 원장.

목표(사용자, 2026-07-06 "데이터 수집 반복 루프"): 무엇을 수집할지 주관이 아니라
엔진의 실제 폐기 사유에서 도출한다(CLAUDE.md "블라인드 적재 회피"). 구성타당도 게이트·
라우팅이 남긴 폐기 사유를 세 갈래로 분류한다:

  [데이터 갭]  construct_validity_fail — IV가 지목한 국가가 표본에 없음 → 수집으로 해결
  [방법 갭]    pending_typeB·pending_typeA_no_mapping — actor filter·9-A/9-B 미구현 → 코드로 해결
  [구조]       structural_arg·no_quantitative_hypothesis — 검정 대상 아님(정직한 폐기)

데이터 갭만 수집 큐가 된다. 방법 갭은 코드 백로그로 분리 표시(수집으로 못 고침).

실행: cd backend && PYTHONPATH=. python3 tools/data_gap_report.py [결과.json]
기본: tests/eval_results/latest.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[1] / "tests" / "eval_results" / "latest.json"

# 폐기 사유 분류
_DATA_GAP   = {"construct_validity_fail"}
_METHOD_GAP = {"pending_typeB", "pending_typeA_no_mapping", "pending_method_unimplemented"}
_STRUCTURAL = {"structural_arg", "no_quantitative_hypothesis"}

# 데이터 갭 국가 → 왜 ACLED로 안 잡히나 + 권장 소스 (수집 커넥터 대상).
# ACLED는 분쟁 이벤트 DB라 ① 폐쇄국가 내부 ② 정책·경제 조치를 구조적으로 못 잡는다.
_SOURCE_HINT: dict[str, str] = {
    "North Korea": "ACLED 폐쇄국가 미커버 → NTI 미사일 DB · 38North · CSIS Missile Threat · 한국 합참 발표",
    "China":       "ACLED는 분쟁만 — 中 정책·수출통제는 이벤트 아님 → 中 상무부 발표 · BIS 통제목록 · CSIS China Power 시계열",
    "United States": "ACLED 본토 이벤트 희소 → 연방관보(수출통제) · BIS Entity List · FRED 정책 지표",
    "Taiwan":      "대만해협 군사활동 → 국방부 ADIZ 로그 · OpenSky ADS-B(이미 일부)",
    "Iran":        "이란전 이벤트는 middle_east에 혼입 → 이란 특정 필터 + IAEA·OFAC 제재 시계열",
    "Russia":      "우크라이나전 외 러 정책 → OFAC 제재 · Kiel 지원 트래커(이미 일부)",
}


def report(path: Path) -> dict:
    data = json.loads(path.read_text())
    results = data.get("results", [])

    data_gap = Counter()      # 부족 국가 → 폐기 횟수
    data_gap_cases: dict[str, list] = {}
    method_gap = Counter()    # 방법 갭 라우팅 → 횟수
    structural = 0
    tested = 0
    n_hyp = 0

    for r in results:
        cid = r.get("id", "?")
        for h in r.get("hypothesis", []):
            n_hyp += 1
            rm = h.get("routing_method", "")
            if rm in _DATA_GAP:
                ivc = (h.get("method_result") or {}).get("iv_construct") or {}
                for c in ivc.get("named_countries", []):
                    data_gap[c] += 1
                    data_gap_cases.setdefault(c, []).append(cid)
            elif rm in _METHOD_GAP:
                method_gap[rm] += 1
            elif rm in _STRUCTURAL:
                structural += 1
            elif h.get("p_value") is not None:
                tested += 1

    return {
        "timestamp": data.get("timestamp", "?"), "n_hyp": n_hyp, "tested": tested,
        "data_gap": data_gap, "data_gap_cases": data_gap_cases,
        "method_gap": method_gap, "structural": structural,
    }


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT
    rep = report(path)
    print(f"=== 데이터 갭 원장 ({rep['timestamp']}) — 가설 {rep['n_hyp']}개 중 검정 {rep['tested']}개 ===\n")

    print("── [데이터 갭] 수집으로 해결 (게이트가 폐기: IV가 지목한 국가가 표본에 없음) ──")
    if not rep["data_gap"]:
        print("  없음")
    for country, n in rep["data_gap"].most_common():
        cases = ", ".join(sorted(set(rep["data_gap_cases"][country])))
        print(f"  ⚑ {n}회 ← {country}")
        print(f"      권장 소스: {_SOURCE_HINT.get(country, '(소스 매핑 미정 — 수동 조사)')}")
        print(f"      영향 케이스: {cases}")
    print()

    print("── [방법 갭] 코드로 해결 (수집으로 못 고침 — actor filter·9-A/9-B 미구현) ──")
    for rm, n in rep["method_gap"].most_common():
        print(f"  {n}회 · {rm}")
    print()

    print(f"── [구조] 검정 대상 아님(정직한 폐기): {rep['structural']}건 ──")
    print("\n수집 우선순위(데이터 갭 최다순):",
          " > ".join(f"{c}({n})" for c, n in rep["data_gap"].most_common()) or "없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
