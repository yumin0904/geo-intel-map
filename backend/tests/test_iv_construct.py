"""
tests/test_iv_construct.py  (IV 구성타당도 게이트 회귀 — 2026-07-05)

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/test_iv_construct.py

목표(geo-os/docs/ENGINE_CONSTRUCT_VALIDITY.md): IV가 질문 대상을 실제로 측정하는지 검사.
7호 케이스("북한 도발" ↔ korean_peninsula 표본 South Korea 98%·North Korea 0건)가
검정 미수행(construct_validity_fail)으로 폐기되는지, 국가 미특정 IV는 오탐 없이 통과하는지.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.hypothesis_extractor import HypothesisSpec  # noqa: E402
from services.hypothesis_verifier import verify_hypotheses  # noqa: E402
from services.methods.iv_construct import (  # noqa: E402
    probe_event_iv, assess_construct, _named_countries,
)


def _check_keyword_matching() -> list[str]:
    """별칭 부분매칭 오염 방지 — 'korean_peninsula'가 South Korea로 걸리면 안 된다."""
    fails = []
    if "South Korea" in _named_countries("korean_peninsula 지역의 conflict 이벤트"):
        fails.append("'korean_peninsula'가 South Korea로 오매칭(부분문자열 오염)")
    if _named_countries("북한의 미사일 도발 빈도") != ["North Korea"]:
        fails.append(f"'북한' 매칭 오류: {_named_countries('북한의 미사일 도발 빈도')}")
    # 국가 특정 없는 IV는 빈 목록
    if _named_countries("호르무즈 해협 통행 방해 빈도"):
        fails.append("국가 미특정 IV에서 국가가 잡힘")
    return fails


def _check_probe_and_assess() -> list[str]:
    """7호 케이스: korean_peninsula 표본에 북한이 거의 없음 → FAIL, 국가 미특정 → None."""
    fails = []
    probe = probe_event_iv("korean_peninsula", date(2018, 1, 1), date(2026, 12, 31))
    if not probe or probe["n_events"] == 0:
        return ["korean_peninsula probe 비어있음 — DB(event_archive) 확인 필요"]
    nk_share = probe["country_dist"].get("North Korea", 0) / probe["n_events"]
    if nk_share >= 0.10:
        fails.append(f"실측 전제 붕괴 — 북한 이벤트 share={nk_share:.2%}(≥10%). 데이터 변동 확인")

    v = assess_construct("북한의 미사일 도발 빈도 증가", probe)
    if v is None or v.ok:
        fails.append(f"북한 IV가 구성타당도 FAIL이 아님: {v}")

    v2 = assess_construct("ACLED korean_peninsula 지역의 월별 conflict 이벤트 건수", probe)
    if v2 is not None:
        fails.append(f"국가 미특정 IV가 게이트에 걸림(오탐): {v2}")
    return fails


def _check_integration() -> list[str]:
    """통합: 북한 IV spec → verify_hypotheses가 검정 미수행 + 감사 메타 보존."""
    fails = []
    # 실제 7호 경로: 이벤트(korean_peninsula)를 IV로, 시장지표(KRW=X)를 DV로 쓰는 Type_A.
    # (Type_B는 별개로 이미 actor_filter 미구현 PENDING 처리 — 검정 안 함.)
    spec = HypothesisSpec(
        h1="북한의 미사일 도발이 증가할 때 원/달러 환율이 유의하게 상승한다",
        h0="관계 없음",
        independent_var="북한의 미사일 도발 빈도(ACLED korean_peninsula conflict 이벤트)",
        dependent_var="원/달러 환율",
        region_code="korean_peninsula",
        ticker="KRW=X",
        var_type="Type_A",
    )
    r = asyncio.run(verify_hypotheses([spec]))[0]
    if r.routing_method != "construct_validity_fail":
        fails.append(f"routing_method가 construct_validity_fail 아님: {r.routing_method}")
    if r.granger_p is not None:
        fails.append(f"검정이 수행됨(granger_p={r.granger_p}) — 게이트 미작동")
    mr = r.method_result or {}
    if not mr.get("iv_construct"):
        fails.append(f"감사 메타(iv_construct) 미보존: {mr}")
    return fails


def main() -> int:
    fails = _check_keyword_matching() + _check_probe_and_assess() + _check_integration()
    if fails:
        print("❌ IV 구성타당도 게이트 위반:")
        for f in fails:
            print("  -", f)
        return 1
    print("✅ IV 구성타당도 게이트 통과 (7호 케이스 검정 미수행 + 오탐 0 + 감사 메타 보존)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
