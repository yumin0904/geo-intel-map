"""
test_coverage_gate.py — B01 수집 커버리지 게이트 회귀 그물 (2026-07-14).

무엇을 막는가
─────────────
`reindex(idx, fill_value=0.0)`가 **"수집이 없던 날"과 "사건이 0건인 날"을 같은 0으로**
만들었다. 실측(2026-07-14, 24개월 창 731일): 전역 이벤트가 1건이라도 있는 날은 399일뿐이고
332일(45.4%)이 수집 공백이었다. 그중 2025-08~2026-03은 **8개월 통짜 구멍**이다.
그 공백이 전부 "전쟁 없음"으로 Granger에 투입됐고, 현존 VERIFIED 3건이 그 위에 서 있었다.

지켜야 할 두 불변식
──────────────────
  ① 수집 공백은 NaN이다 (0이 아니다).  0을 쓰면 "사건이 없었다"는 거짓 관측이 생긴다.
  ② 공백이 임계를 넘으면 **던진다**.   0건 반환은 "관계 없음"과 "못 쟀음"을 같게 만든다.

FIRMS 사고(2026-07-13)와 정확히 같은 병이다 — stale을 sparse로 오진하는 것.
원문: geo-os/ARCHITECTURE.html B01 · journal/2026-07-13.md
"""
import numpy as np
import pandas as pd
import pytest

from services.cascade.correlation import InsufficientCoverageError, apply_coverage


def _idx(start: str, days: int) -> pd.DatetimeIndex:
    return pd.date_range(start, periods=days, freq="D")


def _covered(idx: pd.DatetimeIndex, days: int) -> frozenset[str]:
    """앞에서부터 days일만 수집된 것으로 친다."""
    return frozenset(d.strftime("%Y-%m-%d") for d in idx[:days])


def test_collected_day_without_event_is_a_real_zero():
    """★ 불변식 ①-a — 수집된 날에 이 지역 사건이 없으면 그것은 **진짜 0**이다.

    이걸 NaN으로 만들면 표본이 통째로 날아간다. 0과 결측을 가르는 것이 요점이지,
    전부 결측으로 미는 것이 요점이 아니다.
    """
    idx = _idx("2026-01-01", 10)
    raw = pd.Series([5.0], index=pd.to_datetime(["2026-01-03"]))  # 3일에만 사건
    out = apply_coverage(raw, idx, _covered(idx, 10), "t")

    assert out.isna().sum() == 0          # 전부 수집된 날 → 결측 없음
    assert out.loc["2026-01-03"] == 5.0
    assert out.loc["2026-01-01"] == 0.0   # 사건이 없었을 뿐, 잰 날이다


def test_uncollected_day_is_nan_not_zero():
    """★ 불변식 ① — 수집이 없던 날은 NaN이다. 여기에 0을 쓰는 것이 위조였다."""
    idx = _idx("2026-01-01", 10)
    raw = pd.Series([5.0], index=pd.to_datetime(["2026-01-02"]))
    out = apply_coverage(raw, idx, _covered(idx, 8), "t", max_missing_share=0.5)

    assert out.isna().sum() == 2                  # 마지막 2일 = 수집 공백
    assert bool(np.isnan(out.iloc[-1]))
    assert out.iloc[-1] != 0.0 or np.isnan(out.iloc[-1])
    assert out.loc["2026-01-01"] == 0.0           # 수집된 무사건 날은 여전히 0


def test_missing_over_threshold_raises_instead_of_returning_zeros():
    """★ 불변식 ② — 공백이 임계를 넘으면 조용히 0을 채우지 않고 **던진다**.

    이 한 줄이 없으면 사고가 그대로 재현된다: 8개월 구멍이 "전쟁 없음"으로 검정에 들어가고,
    엔진은 그 위에서 p값을 뱉으며 "관계 없음"이라 보고한다. 그건 관계 없음이 아니라
    측정 불가다.
    """
    idx = _idx("2026-01-01", 100)
    raw = pd.Series([5.0], index=pd.to_datetime(["2026-01-02"]))
    with pytest.raises(InsufficientCoverageError, match="수집 공백"):
        apply_coverage(raw, idx, _covered(idx, 50), "t", max_missing_share=0.30)  # 50% 공백


def test_threshold_boundary_is_inclusive():
    """임계 '초과'만 던진다 — 정확히 임계값이면 통과(경계 동작 고정)."""
    idx = _idx("2026-01-01", 10)
    raw = pd.Series([1.0], index=pd.to_datetime(["2026-01-01"]))
    out = apply_coverage(raw, idx, _covered(idx, 7), "t", max_missing_share=0.30)  # 정확히 30%
    assert out.isna().sum() == 3


def test_the_actual_incident_8month_hole():
    """실제 사고 재현 — 2025-08~2026-03 8개월 공백이 낀 24개월 창은 검정되면 안 된다.

    구 동작: 이 창이 그대로 Granger에 들어갔고 공백은 severity 0으로 채워졌다.
    새 동작: 던진다.
    """
    idx = _idx("2025-06-01", 400)                      # 2025-06 ~ 2026-07
    covered_days = [d for d in idx if not (pd.Timestamp("2025-08-01") <= d <= pd.Timestamp("2026-03-31"))]
    covered = frozenset(d.strftime("%Y-%m-%d") for d in covered_days)
    raw = pd.Series([10.0] * len(covered_days), index=pd.DatetimeIndex(covered_days))

    hole = 400 - len(covered_days)
    assert hole > 200, "8개월 구멍이 재현돼야 한다"

    with pytest.raises(InsufficientCoverageError):
        apply_coverage(raw, idx, covered, "korean_peninsula")


def test_nan_days_drop_out_of_granger_join():
    """NaN은 하류에서 저절로 정직해진다 — concat().dropna()가 그 날을 검정에서 뺀다.

    0이었다면 빠지지 않고 '사건 없는 날'로 검정에 참여한다. 그 차이가 이 수리의 전부다.
    """
    idx = _idx("2026-01-01", 10)
    raw = pd.Series([5.0], index=pd.to_datetime(["2026-01-02"]))
    x = apply_coverage(raw, idx, _covered(idx, 8), "t", max_missing_share=0.5)
    y = pd.Series(np.arange(10.0), index=idx, name="Y")

    combined = pd.concat([y, x.rename("X")], axis=1).dropna()
    assert len(combined) == 8      # 수집된 8일만 검정에 들어간다 (10일이 아니다)


def test_all_nan_week_stays_nan_on_weekly_resample():
    """주간 전환에서도 위조가 되살아나면 안 된다.

    pandas의 sum()은 기본적으로 NaN을 0으로 센다 — 통째로 결측인 주가 '사건 0건인 주'로
    부활한다. min_count=1이 그것을 막는다(_load_event_series의 sparse 스위치가 이걸 쓴다).
    """
    idx = _idx("2026-01-05", 14)   # 월요일 시작, 2주
    s = pd.Series([np.nan] * 14, index=idx)
    s.iloc[0] = 3.0                # 첫 주에만 관측 1건

    naive  = s.resample("W").sum()               # 구 동작
    honest = s.resample("W").sum(min_count=1)    # 수리 후

    assert naive.iloc[-1] == 0.0                 # 둘째 주가 "0건"으로 부활한다
    assert bool(np.isnan(honest.iloc[-1]))       # 결측으로 남는다
