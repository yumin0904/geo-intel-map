"""
tests/test_query_first_routing.py  (9-Q 쿼리-우선 라우팅 회귀 테스트)

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/test_query_first_routing.py

배경(방법론 검토 2026-07-01): 방법은 '질문의 논리 형태'에서 선택돼야 하는데, 기존 파이프라인은
LLM이 만든 정량 H1·ticker에서 linear_testable을 계산 → 조작화가 방법 선택을 오염시켰다
(순서 역전). "마한 vs 미어샤이머" 같은 이론 판별 질문(관측적 동등성으로 공변검정 부적합)이
Granger로 탈선하던 결함. 이 테스트는 라우팅 결정을 '날것의 쿼리'에서 직접 검증한다
(조작화된 입력이 아니라 — 검토가 지적한 8/8 구조테스트의 맹점 보완).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.methods.router import (  # noqa: E402
    classify_signature,
    unquantifiable_question_reason,
)

_CASES_YAML = Path(__file__).parent / "eval_cases.yaml"

# 질문의 논리 형태상 UNQUANTIFIABLE로 직행해야 하는 케이스 (공변검정 부적합)
_ADJUDICATION_IDS = {
    "russia_china_arctic_control",   # 회색지대 이론과 하이브리드 전쟁 이론으로 비교
    "pla_taiwan_a2ad",               # 마한 해양력 이론과 미어샤이머 공격적 현실주의로 비교
    "mearsheimer_vs_liberal_taiwan", # 현실주의와 자유주의 이론 중 어느 쪽이 더 설명력
}
_INTERPRETIVE_IDS = {
    "china_cyber_us",                # 방어 역량 '공백'(측정불가 gap)
    "salt_typhoon_cyber_deterrence", # 억지에 '실패한 이유'(귀속/attribution)
    "india_indo_pacific_balancing",  # 동맹 딜레마를 '어떻게 회피하는지'(메커니즘)
}
_ADJUDICATION_IDS |= _INTERPRETIVE_IDS  # 통합 목표 집합
# 위험한 함정: 두 '변수'(무역의존도 vs 군사력격차)를 수치로 비교 → 정량(CROSS_SECTION) 유지
_MUST_NOT_FLAG_IDS = {"taiwan_liberal_vs_realist"}


def _load_cases() -> list[dict]:
    d = yaml.safe_load(_CASES_YAML.read_text())
    return d if isinstance(d, list) else d.get("cases", d)


def main() -> int:
    cases = _load_cases()
    fails: list[str] = []

    for c in cases:
        cid, q = c["id"], c["query"]
        flagged = bool(unquantifiable_question_reason(q))
        # 최악조건 시뮬: LLM이 정량 H1을 만들고 ticker까지 붙였다고 가정
        sig = classify_signature(q, linear_testable=True, has_paired_timeseries=True)

        if cid in _ADJUDICATION_IDS:
            if not (flagged and sig == "UNQUANTIFIABLE"):
                fails.append(f"[MISS] {cid}: flagged={flagged} sig={sig} (기대 UNQUANTIFIABLE)")
        if cid in _MUST_NOT_FLAG_IDS:
            if flagged or sig == "UNQUANTIFIABLE":
                fails.append(f"[FALSE_POS] {cid}: 정량 케이스가 판별형으로 오분류 (sig={sig})")

    # 오탐 전수 점검: 판별로 잡혔는데 기대 시그니처가 UNQUANTIFIABLE이 아닌 케이스
    for c in cases:
        if unquantifiable_question_reason(c["query"]):
            exp = c.get("expected_signature", "")
            if exp and exp != "UNQUANTIFIABLE":
                fails.append(f"[FALSE_POS] {c['id']}: expected={exp}인데 판별형으로 잡힘")

    print("=== 판별형으로 잡힌 쿼리 (→UNQUANTIFIABLE) ===")
    for c in cases:
        if unquantifiable_question_reason(c["query"]):
            print(f"  {c['id']}  (expected={c.get('expected_signature', '—')})")

    if fails:
        print("\n❌ FAIL")
        for f in fails:
            print("  " + f)
        return 1
    print(f"\n✅ PASS — 목표 {len(_ADJUDICATION_IDS)}건 적중, 오탐 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
