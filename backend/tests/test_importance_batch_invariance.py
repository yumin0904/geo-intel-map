"""importance_score 배치 불변성 그물 — B15.

**같은 이벤트는 배치 구성과 무관하게 같은 점수를 받아야 한다.**

구 코드는 배치 안에서 min/max로 recency를 정규화했다:

    rec_s = (t - ts_min) / (ts_max - ts_min)

그래서 **같은 이벤트가 무엇과 함께 조회됐느냐에 따라 다른 점수를 받았다**:
  · 배치의 가장 오래된 이벤트는 **어제 것이어도 rec=0.0**
  · 배치의 가장 최근 이벤트는 **5년 전 것이어도 rec=1.0**
  · 배치에 한 건뿐이면(ts_range=0) **아무리 오래돼도 rec=1.0**

그리고 이 점수는 프론트(`ConflictEventsLayer.js`)의 **줌별 마커 가시성**과 **등급 기호**를
정한다 — 즉 **어떤 이벤트가 지도에 보이느냐가 쿼리 구성에 좌우됐다.**
분모가 세계가 아니라 배치였다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from models.event import Event
from services.importance_scorer import score_events, score_gdelt_events

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def _ev(days_old: float, severity: int = 50, region: str = "hormuz") -> Event:
    return Event(
        id=f"e{days_old}-{severity}",
        timestamp=NOW - timedelta(days=days_old),
        source_type="conflict",
        source_id="test",
        location=(0.0, 0.0),
        region_code=region,
        severity=severity,
        title="t",
        description="d",
        payload={},
        theory_tags=[],
    )


def _score_of(events, target_id, **kw) -> float:
    out = score_events(events, frozenset(), ref_time=NOW, **kw)
    return next(e.importance_score for e in out if e.id == target_id)


def test_same_event_same_score_regardless_of_batch():
    """★ 핵심 불변식 — 이게 깨지면 지도의 가시성이 쿼리에 좌우된다."""
    target = _ev(10)

    alone = _score_of([target], target.id)
    with_older = _score_of([target, _ev(300)], target.id)
    with_newer = _score_of([target, _ev(0)], target.id)
    with_both = _score_of([target, _ev(300), _ev(0)], target.id)

    assert alone == with_older == with_newer == with_both, (
        f"배치 구성이 점수를 바꾼다: 단독={alone} · 더오래된것과={with_older} · "
        f"더최신것과={with_newer} · 둘다={with_both}"
    )


def test_a_single_ancient_event_is_not_maximally_recent():
    """음성 테스트 — 구 코드의 최악 사례.

    배치에 한 건뿐이면 `ts_range == 0` → `rec_s = 1.0`. **5년 전 이벤트가 최신도 만점.**
    """
    ancient = _ev(1825)  # 5년 전
    fresh = _ev(0)
    assert _score_of([ancient], ancient.id) < _score_of([fresh], fresh.id)


def test_older_is_never_more_recent_than_newer():
    """순서 불변식 — 나이가 많을수록 recency 기여가 작거나 같다."""
    evs = [_ev(d) for d in (0, 5, 30, 89, 91, 400)]
    out = score_events(evs, frozenset(), ref_time=NOW)
    by_age = sorted(out, key=lambda e: e.timestamp, reverse=True)  # 최신 → 오래된
    scores = [e.importance_score for e in by_age]
    assert scores == sorted(scores, reverse=True), f"단조성 위반: {scores}"


def test_beyond_the_window_recency_is_zero_not_negative():
    """창을 넘어서면 recency 기여는 0에서 멈춘다 — 음수로 점수를 깎지 않는다."""
    out = score_events([_ev(9999)], frozenset(), ref_time=NOW)
    brk = out[0].payload["_score_breakdown"]
    assert brk["recency"] == 0.0
    assert out[0].importance_score >= 0.0


def test_acled_lag_is_handled_by_the_horizon_not_by_the_batch():
    """ACLED는 event_date 랙이 365일이다 — `now` 기준이면 전건 rec=0.

    구 코드는 그 사실을 **배치 정규화로 감췄다**. 새 코드는 **호출자가 소스의 지평을
    넘기게** 한다: 지평은 세계의 성질이지 쿼리의 우연이 아니다.
    """
    acled_horizon = NOW - timedelta(days=365)  # ACLED 최신 event_date
    ev = Event(
        id="acled-1",
        timestamp=acled_horizon - timedelta(days=10),  # 지평에서 10일 전
        source_type="conflict",
        source_id="acled",
        location=(0.0, 0.0),
        region_code="hormuz",
        severity=50,
        title="t",
        description="d",
        payload={},
        theory_tags=[],
    )
    # 지평을 안 넘기면(now 기준) 랙 때문에 recency 0
    stale = score_events([ev], frozenset(), ref_time=NOW)[0]
    assert stale.payload["_score_breakdown"]["recency"] == 0.0

    # 지평을 넘기면 "ACLED 안에서 최근인가"가 제대로 잡힌다
    fresh = score_events([ev], frozenset(), ref_time=acled_horizon)[0]
    assert fresh.payload["_score_breakdown"]["recency"] > 0.0


# ── GDELT 경로 (recency가 점수의 40% — 피해가 더 컸다) ────────────────────────

def test_gdelt_batch_invariance():
    e = _ev(1)
    e.confidence_score = 0.5
    alone = score_gdelt_events([e], ref_time=NOW)[0].importance_score
    with_others = next(
        x.importance_score
        for x in score_gdelt_events([e, _ev(2), _ev(0)], ref_time=NOW)
        if x.id == e.id
    )
    assert alone == with_others


def test_gdelt_window_matches_the_ttl():
    """GDELT 감쇠 창(72h)은 §18 TTL의 핫 보관 창과 **일부러 같다.**

    다르면 importance가 무엇을 뜻하는지 아무도 설명할 수 없다 —
    이 점수의 용도가 "TTL 만료 전에 승격할 가치가 있나"이기 때문이다.
    """
    from services.importance_scorer import _GDELT_RECENCY_WINDOW_HOURS

    assert _GDELT_RECENCY_WINDOW_HOURS == 72.0
    at_ttl = score_gdelt_events([_ev(3.0)], ref_time=NOW)[0]  # 정확히 72h
    assert at_ttl.payload["_score_breakdown"]["recency"] == pytest.approx(0.0, abs=1e-6)
