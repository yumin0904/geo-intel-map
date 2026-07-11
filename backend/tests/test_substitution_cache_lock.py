"""
tests/test_substitution_cache_lock.py — 치환 잠금의 캐시 우회 회귀 (밤샘 사이클 3, 2026-07-12 새벽)

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/test_substitution_cache_lock.py

발단 실측(batch_20260713_cycle1/hormuz-iran-oil): H1(Type_A 정상)이 (hormuz, CL=F)
검정을 캐시에 심은 뒤, H2(Type_C 치환·is_substituted_target=True)가 캐시 HIT로
H1의 verification_status=VERIFIED·inference_grade까지 통째로 복사받고 **조기
return** — 함수 꼬리의 _lock_pending_if_substituted를 영영 안 거친다.
치환게이트위(2026-07-11)의 단독 Type_C 실증은 캐시 미스 경로만 검증해 이 구멍을
못 봤다: 우회는 동일쌍 선행 주자가 있을 때만 열린다(9-P-1 동일 검정 재사용 계열).

스텁 주입 단위 테스트 — _run_granger_for_spec이 로더·검정 함수를 파라미터로 받는
설계를 이용해 라이브 DB 무관하게 유의(p=0.001) 경로를 강제한다. (첫 판은 라이브
통합으로 썼다가 이벤트 분산=0으로 유의 경로가 안 밟혀 허무 통과 — 교훈 반영.)

불변식: is_substituted_target=True인 spec은 검정 수치(granger_p)는 보존하되
verification_status=PENDING·inference_grade=기술적 — 캐시 HIT 경로에서도 동일.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from services.hypothesis_extractor import HypothesisSpec  # noqa: E402
from services import hypothesis_verifier as hv  # noqa: E402


def _mk_series(n: int = 60) -> pd.Series:
    idx = pd.date_range("2024-01-07", periods=n, freq="W")
    return pd.Series(range(1, n + 1), index=idx, dtype=float)


def _load_event_series(region, start, end, country=None):
    return _mk_series()


async def _get_market_series(ticker, start, end):
    return _mk_series()


def _run_granger(ev, mkt):
    # (p_value, best_lag, n_obs, f_stat, meta) — 유의 경로 강제
    return (0.001, 2, 58, 9.9, {"differenced": True, "controlled": False})


def _spec(sub: bool) -> HypothesisSpec:
    s = HypothesisSpec(
        h1="호르무즈 이벤트가 증가할 때 지표가 유의하게 상승한다",
        h0="관계 없음",
        independent_var="호르무즈 이벤트 건수",
        dependent_var="WTI 유가" if not sub else "유조선 전쟁보험료 (치환 대상)",
        region_code="hormuz",
        ticker="CL=F",
        var_type="Type_A" if not sub else "Type_C",
    )
    s.is_substituted_target = sub
    return s


async def _run() -> list[str]:
    fails: list[str] = []
    start, end = date(2024, 1, 1), date(2025, 12, 31)

    # 캐시 오염 방지 — 전용 키 공간이 아니라 전역 캐시라 테스트 전 비운다
    try:
        hv._GRANGER_CACHE.clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass  # 캐시 구조 변경 시에도 테스트 본체는 유효 (미스→미스)

    s1 = await hv._run_granger_for_spec(
        _spec(sub=False), start, end,
        _load_event_series, _get_market_series, _run_granger,
    )
    if s1.verification_status == "PENDING":
        fails.append(f"전제 불성립 — 선행 주자 H1이 등급 미부여(PENDING): "
                     f"(p={s1.granger_p}, error={s1.error}) — 스텁 경로 확인 필요")

    s2 = await hv._run_granger_for_spec(
        _spec(sub=True), start, end,
        _load_event_series, _get_market_series, _run_granger,
        proxy_label="테스트 치환 (전쟁보험료 → CL=F)",
    )
    if s2.granger_p != s1.granger_p:
        fails.append(f"전제 불성립 — 캐시 공유 안 됨 (p1={s1.granger_p}, p2={s2.granger_p})")

    if s2.verification_status != "PENDING":
        fails.append(
            f"치환 잠금 우회 — H2 status={s2.verification_status} (기대 PENDING): "
            "캐시 조기 반환이 _lock_pending_if_substituted를 건너뜀"
        )
    if s2.inference_grade != "기술적":
        fails.append(f"치환 spec 등급 미잠금 — H2 grade={s2.inference_grade} (기대 기술적)")

    # 대조군: 정상 H1은 잠금의 영향권 밖
    if s1.is_substituted_target:
        fails.append("대조군 오염 — H1이 치환으로 마킹됨")
    return fails


def main() -> int:
    fails = asyncio.run(_run())
    if fails:
        print("❌ 치환 잠금 캐시 우회 회귀:")
        for f in fails:
            print("  -", f)
        return 1
    print("✅ 치환 잠금 캐시 경로 통과 (동일쌍 캐시 HIT에서도 PENDING·기술적 잠금 유지)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
