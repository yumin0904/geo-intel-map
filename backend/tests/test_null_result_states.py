"""비유의 결과 3분할 그물 — B02 + B25.

구 코드의 상태 배정은 이 한 줄로 끝났다:

    if 선행성: VERIFIED / elif 상관: PARTIAL / **else: PENDING**

`else`가 셋을 삼켰다 —
  · p=0.8로 **명확히 기각된** 가설 (정직한 귀무는 발견이다)
  · 데이터가 없어 **못 잰** 가설
  · 검정력이 없어 **잴 수 없는 설계**였던 가설

"미검증"이라는 말이 정직한 기각을 '아직 안 해봤다'로 위장하고, 못 잰 것을 '관계 없다'로
바꿔치기한다. **후자가 B01의 정의였다.**
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.hypothesis_verifier import _classify_null_result
from services.statistical_power import achieved_power, can_reject, mde_f2, power_caveat


def _spec(**kw):
    base = dict(
        diagnosis=None, n_obs=0, best_lag=1, controlled=False, inference_caveat=""
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ── 검정력 계산 자체 ──────────────────────────────────────────────────────────

def test_power_matches_the_methodology_seat():
    """방법론석(B01위원회)이 계산한 값을 코드가 재현하는가.

    이 숫자가 틀리면 그 위에 세운 모든 상태 판정이 틀린다.
    """
    assert achieved_power(246, 1) == pytest.approx(0.182, abs=0.01)  # STATUS의 "검정력 0.18"
    assert achieved_power(1747, 1) == pytest.approx(0.80, abs=0.01)  # "1,747~2,857 필요표본"


def test_the_engine_cannot_actually_reject_anything():
    """이 엔진의 최대 창(411일)에서도 기각할 자격이 없다 — **그 사실 자체가 발견이다.**

    STATUS: "8/8 비유의를 '룰북이 틀렸다'로 읽지 마라 — 검정력 0.18."

    MDE(최소 탐지 가능 효과)는 목표 검정력에 따라 다르다. 숫자를 부풀리지 않고 둘 다 적는다:
      바닥선 50% 기준 → f² = 0.0094  (현실적 효과의 **2.1배**)
      관례적 80% 기준 → f² = 0.0192  (현실적 효과의 **4.3배**)
    어느 쪽이든 **잡을 수 있는 것은 현실에 없는 크기의 효과뿐이다.**
    """
    F2_REALISTIC = 0.0045
    assert achieved_power(411, 1) < 0.30
    assert not can_reject(411, 1), "411일 창에서 REJECTED를 주장할 수 있으면 안 된다"

    mde_floor = mde_f2(411, 1)  # 바닥선(50%) 기준 — can_reject가 쓰는 그 기준
    assert mde_floor is not None and mde_floor > F2_REALISTIC * 2

    mde_80 = mde_f2(411, 1, target_power=0.80)
    assert mde_80 is not None and mde_80 > F2_REALISTIC * 4


def test_n80_is_not_sufficient_power():
    """`granger_adapter.py`가 '80개+ → 통계력 충분'이라 적었던 지점 — 실제 9%다."""
    assert achieved_power(80, 1) < 0.10


# ── 상태 3분할 ───────────────────────────────────────────────────────────────

def test_d3_becomes_invalid_proxy():
    """질문이 틀렸다 — 데이터를 더 모아도 소용없다."""
    assert _classify_null_result(_spec(diagnosis="D3_BAD_PROXY"), None) == "INVALID_PROXY"


def test_d4_becomes_underpowered():
    """표본이 없었다 — **더 모으면 된다.** D3와 처방이 정반대라 이름도 달라야 한다."""
    assert _classify_null_result(_spec(diagnosis="D4_INSUFFICIENT"), 0.7) == "UNDERPOWERED"


def test_untested_stays_pending():
    """검정을 아예 안 했으면 PENDING — 이것만이 '아직 안 쟀다'의 정당한 의미다."""
    assert _classify_null_result(_spec(n_obs=500), None) == "PENDING"


def test_null_with_low_power_is_underpowered_not_rejected():
    """★ 핵심 — 못 잰 것을 '관계 없다'로 바꿔치기하지 않는다.

    n=411은 이 엔진이 실제로 가진 최대 창이다. 여기서 p=0.7이 나와도
    **REJECTED가 아니다** — 잡을 힘이 애초에 없었다.
    """
    s = _spec(n_obs=411, best_lag=1)
    assert _classify_null_result(s, 0.7) == "UNDERPOWERED"
    assert s.achieved_power is not None and s.achieved_power < 0.5
    assert "검정력 부족" in s.inference_caveat, "인용자에게 캐비엇이 반드시 붙어야 한다"


def test_null_with_adequate_power_is_an_honest_rejection():
    """음성 테스트 — 검정력이 있으면 REJECTED가 **나와야 한다.**

    이게 안 나오면 이 상태는 영원히 비어 있고, 그러면 상태를 만든 의미가 없다
    ("모든 것을 잡는 가드는 채점기가 아니라 채점 중단 스위치다").
    """
    s = _spec(n_obs=2000, best_lag=1)
    assert _classify_null_result(s, 0.7) == "REJECTED"
    assert not s.inference_caveat, "검정력이 충분하면 검정력 캐비엇은 붙지 않는다"


def test_power_caveat_is_silent_when_power_is_adequate():
    assert power_caveat(2000, 1) is None
    assert power_caveat(411, 1) is not None
