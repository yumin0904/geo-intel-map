"""
tests/test_method_result_invariant.py  (엔진 위원회 C-4 회귀 테스트, 2026-07-05)

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/test_method_result_invariant.py

배경: Method Router 루프(hypothesis_verifier)가 '검정을 실제로 수행하지 않은' spec
(Type_A 매핑 실패·방법 미구현·정량 가설 없음)에도 event_study 등 어댑터를 호출해,
ticker 없는 spec에 effect=None 껍데기 MethodResult를 기록하던 결함(2계층 분열).
소비자(export_insight → neoul 기사)가 이를 '검정 결과 있음'으로 오독했다.

불변식: 검정을 수행하지 않은 PENDING spec은 method_result에 실측 추정치를 담지 않는다
(skipped 마커만 남긴다). 정상 검정 spec은 종전대로 결과를 보존한다.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.hypothesis_extractor import HypothesisSpec  # noqa: E402
from services.hypothesis_verifier import verify_hypotheses  # noqa: E402
from services.methods.event_study import from_spec as event_study_from_spec  # noqa: E402


def _check_event_study_no_ticker() -> list[str]:
    """event_study 단위: ticker 없으면 껍데기(effect) 대신 assumptions_met=False."""
    fails = []
    spec = SimpleNamespace(ticker="", h1="2025년 12월 사건 이후 변화", h0="")
    mr = event_study_from_spec(spec)
    if mr.assumptions_met is not False:
        fails.append("event_study(ticker=''): assumptions_met가 False가 아님")
    if mr.effect_estimate is not None:
        fails.append(f"event_study(ticker=''): effect_estimate가 채워짐({mr.effect_estimate})")
    return fails


def _check_pending_spec_no_method_result() -> list[str]:
    """통합: Type_A 매핑 실패 spec → method_result에 실측 추정치 없음(skipped)."""
    fails = []
    # region_code·ticker 둘 다 없음 → Type_A 매핑 실패 경로 (검정 미수행)
    spec = HypothesisSpec(
        h1="북한의 미사일 도발이 증가할 때 한국 방위산업 지표가 유의하게 변화한다",
        h0="관계 없음",
        independent_var="북한 미사일 도발 빈도",
        dependent_var="한국 방위산업 지표",
        region_code=None,
        ticker=None,
        var_type="Type_A",
    )
    results = asyncio.run(verify_hypotheses([spec]))
    r = results[0]
    if r.verification_status != "PENDING":
        fails.append(f"매핑 실패 spec이 PENDING이 아님({r.verification_status})")
    mr = r.method_result or {}
    if not mr.get("skipped"):
        fails.append(f"PENDING spec의 method_result에 skipped 마커 없음: {mr}")
    # 껍데기 결과가 새어들지 않았는지 — all_results에 effect 담긴 항목 금지
    for item in mr.get("all_results", []):
        if item.get("effect_estimate") is not None:
            fails.append(f"PENDING spec에 effect_estimate 누출: {item}")
    return fails


def main() -> int:
    fails = _check_event_study_no_ticker() + _check_pending_spec_no_method_result()
    if fails:
        print("❌ method_result 불변식 위반:")
        for f in fails:
            print("  -", f)
        return 1
    print("✅ method_result 불변식 통과 (event_study 방어 + PENDING skip 마커)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
