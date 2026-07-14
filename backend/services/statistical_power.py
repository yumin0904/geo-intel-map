"""통계적 검정력 — "못 쟀다"와 "관계 없다"를 가르는 계기 (B25).

## 왜 이 파일이 생겼나

엔진의 `verification_status`는 `PENDING / PARTIAL / VERIFIED` 셋뿐이었다. 그리고
`hypothesis_verifier`의 상태 배정은 이렇게 끝났다:

    if 선행성:   VERIFIED
    elif 상관:   PARTIAL
    else:        PENDING      ← 여기서 셋이 뭉개진다

`else`가 삼킨 것:
  · p=0.8로 **명확히 기각된** 가설 (정직한 귀무 — 발견이다)
  · 데이터가 없어 **못 잰** 가설
  · 검정력이 없어 **잴 수 없는 설계**였던 가설

셋 다 `PENDING(미검증)`이다. **"미검증"이라는 말이 정직한 기각을 '아직 안 해봤다'로
위장하고, 못 잰 것을 '관계 없다'로 바꿔치기한다.** 후자가 B01의 정의였다.

## 실측 — 이 엔진의 비유의는 정보가 아니다

현실적 효과크기(f² = 0.0045 = 지정학이 익일 수익률 분산의 **0.45%**를 설명)에서
Granger F검정의 달성 검정력:

    n_obs    lag=1
       40    0.070
       80    0.091   ← granger_adapter.py:133 주석이 "통계력 충분"이라 적은 지점
      246    0.182
      411    0.274   ← 현재 쓸 수 있는 최대 창(D2 재검정)
     1750    0.800   ← 80% 검정력에 실제로 필요한 표본 ≈ 6.9년

n=411에서 MDE는 f² = 0.0192 — **현실적 효과의 4배**다. 즉 **잡을 수 있는 것은
현실에 없는 크기의 효과뿐**이다.

> 8개 룰이 **전부 참이어도** 8/8 비유의가 나올 확률이 20%다(우도비 3.3 = 무증거).
> **비유의를 "룰북이 틀렸다"로 읽으면 안 된다 — 애초에 물어볼 수 없는 질문이었다.**

## 효과크기는 사전 선언한다

`f2_realistic`는 **결과를 보기 전에** 정해야 한다. 결과를 보고 고르면 그 자체가
forking path다("유의하니까 효과가 컸다고 하자"). 그래서 `granger_thresholds.yaml`에
상수로 박고 여기서 읽는다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from scipy.stats import f as f_dist
from scipy.stats import ncf

_CFG = Path(__file__).resolve().parent.parent / "config" / "granger_thresholds.yaml"


@lru_cache(maxsize=1)
def _thresholds() -> dict:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8"))


def achieved_power(
    n_obs: int,
    n_lags: int,
    f2: float | None = None,
    *,
    alpha: float | None = None,
    n_controls: int = 0,
) -> float:
    """Granger F검정의 **달성 검정력**.

    귀무가 거짓일 때(효과가 f2만큼 실재할 때) 그것을 잡아낼 확률.
    비중심 F분포로 계산한다 — 비중심 모수 λ = f² × n.

    Returns 0.0 ~ 1.0. 자유도가 없으면 0.0(못 잰다).
    """
    thr = _thresholds()
    f2 = thr["f2_realistic"] if f2 is None else f2
    alpha = thr["p_verified"] if alpha is None else alpha

    df1 = n_lags
    df2 = n_obs - n_lags - n_controls - 1
    if df1 <= 0 or df2 <= 0 or n_obs <= 0:
        return 0.0
    crit = f_dist.ppf(1 - alpha, df1, df2)
    return float(1 - ncf.cdf(crit, df1, df2, f2 * n_obs))


def mde_f2(
    n_obs: int,
    n_lags: int,
    *,
    alpha: float | None = None,
    target_power: float | None = None,
    n_controls: int = 0,
) -> float | None:
    """최소 탐지 가능 효과크기(MDE) — 이 표본으로 **잡을 수 있는 가장 작은 효과**.

    이 값이 현실적 효과크기보다 크면, 그 검정은 **현실에 없는 크기의 효과만 잡는다.**
    비유의가 나와도 그것은 "관계 없음"의 증거가 아니다.
    """
    thr = _thresholds()
    target = thr["power_floor_for_rejection"] if target_power is None else target_power

    lo, hi = 0.0, 5.0
    if achieved_power(n_obs, n_lags, hi, alpha=alpha, n_controls=n_controls) < target:
        return None  # 이 표본으로는 어떤 효과도 target 검정력으로 못 잡는다
    for _ in range(80):  # 이분 탐색
        mid = (lo + hi) / 2
        if achieved_power(n_obs, n_lags, mid, alpha=alpha, n_controls=n_controls) < target:
            lo = mid
        else:
            hi = mid
    return hi


def can_reject(n_obs: int, n_lags: int, *, n_controls: int = 0) -> bool:
    """이 검정은 **기각을 주장할 자격이 있는가.**

    달성 검정력이 바닥선 미만이면 비유의는 "관계 없음"이 아니라 "못 쟀음"이다.
    이 함수가 False면 `verification_status`는 REJECTED가 아니라 UNDERPOWERED여야 한다.
    """
    thr = _thresholds()
    return achieved_power(n_obs, n_lags, n_controls=n_controls) >= thr[
        "power_floor_for_rejection"
    ]


def power_caveat(n_obs: int, n_lags: int, *, n_controls: int = 0) -> str | None:
    """검정력이 부족할 때 **인용자에게 붙일 문장**. 충분하면 None.

    캐비엇은 `caveat_gate`가 준수를 강제한다("말했다"와 "지켜졌다"는 다르다).
    """
    thr = _thresholds()
    pw = achieved_power(n_obs, n_lags, n_controls=n_controls)
    if pw >= thr["power_floor_for_rejection"]:
        return None
    mde = mde_f2(n_obs, n_lags, n_controls=n_controls)
    mde_txt = f"f²≥{mde:.4f}" if mde is not None else "어떤 크기도"
    return (
        f"검정력 부족: n={n_obs}·lag={n_lags}에서 현실적 효과(f²={thr['f2_realistic']})를 "
        f"잡아낼 확률은 {pw:.1%}다(바닥선 {thr['power_floor_for_rejection']:.0%}). "
        f"이 표본이 잡을 수 있는 것은 {mde_txt} — 현실에 없는 크기다. "
        f"**비유의를 '관계 없음'으로 인용하지 말 것. 못 쟀다는 뜻이다.**"
    )
