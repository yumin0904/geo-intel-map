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


def _nk_count(start=date(2018, 1, 1), end=date(2026, 12, 31)) -> int:
    p = probe_event_iv("korean_peninsula", start, end) or {}
    return p.get("country_dist", {}).get("North Korea", 0)


def _check_probe_and_assess() -> list[str]:
    """게이트는 '필터 후 절대량' 기준. 북한 데이터(CNS 미사일)가 ≥30이면 PASS+필터,
    없으면 FAIL. 데이터 없는 대상(이란)은 FAIL, 국가 미특정 IV는 None(게이트 미적용)."""
    fails = []
    probe = probe_event_iv("korean_peninsula", date(2018, 1, 1), date(2026, 12, 31))
    if not probe or probe["n_events"] == 0:
        return ["korean_peninsula probe 비어있음 — DB(event_archive) 확인 필요"]
    dist = probe["country_dist"]

    nk_n = dist.get("North Korea", 0)
    v = assess_construct("북한의 미사일 도발 빈도 증가", probe)
    if nk_n >= 30:  # CNS 미사일 적재됨 → 필터로 순수 검정 가능
        if v is None or not v.ok or v.filter_country != "North Korea":
            fails.append(f"북한 데이터 {nk_n}건인데 PASS+필터(North Korea) 아님: {v}")
    else:  # 데이터 없음 → 정직한 폐기
        if v is None or v.ok:
            fails.append(f"북한 데이터 부족({nk_n})인데 FAIL 아님: {v}")

    # 데이터 없는 대상(korean_peninsula에 이란 이벤트 거의 없음) → FAIL
    if dist.get("Iran", 0) < 30:
        vi = assess_construct("이란 핵 프로그램 활동 빈도", probe)
        if vi is None or vi.ok:
            fails.append(f"이란 데이터 부족인데 FAIL 아님: {vi}")

    # 국가 미특정 IV → None (게이트 미적용, 오탐 방지)
    v2 = assess_construct("ACLED korean_peninsula 지역의 월별 conflict 이벤트 건수", probe)
    if v2 is not None:
        fails.append(f"국가 미특정 IV가 게이트에 걸림(오탐): {v2}")
    return fails


def _check_integration() -> list[str]:
    """통합: 북한 IV spec → 데이터 있으면 A-1 필터로 검정, 없으면 폐기. 감사 메타 보존."""
    fails = []
    spec = HypothesisSpec(
        h1="북한의 미사일 도발이 증가할 때 원/달러 환율이 유의하게 상승한다",
        h0="관계 없음",
        independent_var="북한의 미사일 도발 빈도(ACLED korean_peninsula conflict 이벤트)",
        dependent_var="원/달러 환율",
        region_code="korean_peninsula",
        ticker="KRW=X",
        var_type="Type_A",
    )
    # 게이트/검정이 실제로 쓰는 기간(_get_date_range = 최근 _LOOKBACK_MONTHS)의 북한 건수로
    # 판정한다. 미사일은 창에 ~7건뿐이라 현 lookback에선 폐기가 정상.
    # ⚠️ 원인은 sparse가 아니라 stale: CNS 소스가 2024-11에서 멈춰 창의 최근 구간이 공백이다
    # (평가 위원회 2026-07-06). lookback 확대는 기각(granger_thresholds.yaml) — 이 분기를
    # 뒤집는 정직한 길은 CNS 최신화 또는 미사일 가설의 구조적 논증 라우팅이다.
    from services.hypothesis_verifier import _get_date_range
    gs, ge = _get_date_range()
    nk_n = _nk_count(gs, ge)
    r = asyncio.run(verify_hypotheses([spec]))[0]
    if not (r.method_result or {}).get("iv_construct"):
        fails.append(f"감사 메타(iv_construct) 미보존: {r.method_result}")

    if nk_n >= 30:  # 필터로 검정 — 폐기 아님, filter_country 적용
        if r.routing_method == "construct_validity_fail":
            fails.append(f"북한 데이터 {nk_n}건인데 construct_fail 폐기됨")
        if getattr(r, "_filter_country", None) != "North Korea":
            fails.append(f"A-1 필터 국가 미적용: {getattr(r, '_filter_country', None)}")
    else:  # 현 lookback에 데이터 부족 → 정직한 폐기
        if r.routing_method != "construct_validity_fail":
            fails.append(f"북한 데이터 부족({nk_n})인데 폐기 안 됨: {r.routing_method}")
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
