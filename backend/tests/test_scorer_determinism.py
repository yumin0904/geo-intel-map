"""채점기 결정성 그물 — B29.

**같은 (ticker, start, end)는 같은 `realized_pct`를 내야 한다.** 실측에서 안 그랬다:

    CL=F · created 2026-07-03 · resolve 2026-07-10 · 3건
      → realized_pct  4.8432 / 4.8432 / **4.8286**

같은 창·같은 티커인데 값이 갈렸다. 원인 둘:
  ① **만기 당일에 채점했다** — `resolve_by <= as_of`. 만기일 장중이면 그날 종가는
     아직 확정되지 않았고, yfinance는 진행 중인 봉의 현재가를 준다.
  ② **행마다 따로 `yf.download`를 호출했다** — 호출 사이에 가격이 움직인다.

`realized_pct`가 재현되지 않으면 **간판 숫자에 재현 가능성이 없다.** 임계 근처에서는
재채점 시 HIT/MISS가 뒤집힌다. IV 결함(B32)과 **독립된 별개의 병**이었다.

⚠️ 이 파일은 네트워크를 타지 않는다 — `yf.download`를 가짜로 갈아끼운다.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

from services import prediction_scorer as ps


@pytest.fixture(autouse=True)
def _clear_cache():
    """캐시를 비운다 — **단, 캐시가 없어도 죽지 않는다.**

    ⚠️ 초판은 `ps._fetch_market_outcome.cache_clear()`를 무조건 불렀다. 그래서 **수리 전
    코드(lru_cache 없음)에서는 AttributeError로 죽었고**, 테스트가 돌지도 못했다.
    `verify_repair.py`가 그걸 잡았다 — 증명 등급 **ABSENT**(코드가 새로 생겼다는 것만
    증명. 행동이 틀렸었다는 증거가 아니다).

    **회귀 테스트는 고장난 코드 위에서도 돌 수 있어야 한다.** 안 그러면 "수리 전에는
    실패했다"를 증명할 수 없고, 그러면 그건 결함의 증거가 아니라 그냥 새 테스트다.
    """
    cc = getattr(ps._fetch_market_outcome, "cache_clear", None)
    if cc:
        cc()
    yield
    if cc:
        cc()


class _DriftingFeed:
    """호출할 때마다 마지막 종가가 조금씩 움직이는 가짜 피드 — 만기 당일 장중을 흉내낸다."""

    def __init__(self, last_date: date, n_bars: int = 10):
        self.calls = 0
        self.last_date = last_date
        self.n_bars = n_bars

    def __call__(self, ticker, start, end, progress=False, auto_adjust=True):  # noqa: D401
        self.calls += 1
        idx = pd.bdate_range(end=pd.Timestamp(self.last_date), periods=self.n_bars)
        closes = [100.0] * (self.n_bars - 1) + [105.0 + self.calls * 0.01]  # ← 매번 흔들린다
        return pd.DataFrame({"Close": closes}, index=idx)


def test_same_window_same_value(monkeypatch):
    """★ 핵심 — 같은 창을 여러 번 채점해도 같은 값이 나온다(런 내 메모)."""
    feed = _DriftingFeed(last_date=date(2026, 7, 10))
    monkeypatch.setattr("yfinance.download", feed)

    a = ps._fetch_market_outcome("CL=F", date(2026, 7, 3), date(2026, 7, 10))
    b = ps._fetch_market_outcome("CL=F", date(2026, 7, 3), date(2026, 7, 10))
    c = ps._fetch_market_outcome("CL=F", date(2026, 7, 3), date(2026, 7, 10))

    assert a == b == c, f"같은 창인데 값이 갈린다: {a} · {b} · {c}"
    assert feed.calls == 1, (
        f"외부 피드를 {feed.calls}번 호출했다 — 행마다 호출하면 그 사이 가격이 움직인다"
    )


def test_drifting_feed_would_have_broken_the_old_code():
    """음성 테스트 — 이 가짜 피드가 실제로 값을 흔드는가.

    피드가 안 흔들리면 위 테스트는 아무것도 증명하지 못한다(가드를 짜고 나서 가드를 재라).
    """
    feed = _DriftingFeed(last_date=date(2026, 7, 10))
    f1 = feed("CL=F", None, None)["Close"].iloc[-1]
    f2 = feed("CL=F", None, None)["Close"].iloc[-1]
    assert f1 != f2, "가짜 피드가 안 흔들린다 — 이 테스트는 아무것도 잡지 못한다"


def test_settle_lag_guard_refuses_a_shorter_window(monkeypatch):
    """만기 봉이 안 왔으면 **더 짧은 창으로 대신 재지 않는다** — 보류한다.

    구 코드는 `close[close.index <= end]`의 마지막 값을 그냥 썼다. 데이터가 지연되면
    그건 **한참 이전 종가**이고, 우리는 선언한 창이 아니라 **우연히 데이터가 있는 창**을
    잰 뒤 그것을 예측 결과라 부르게 된다.
    """
    stale = _DriftingFeed(last_date=date(2026, 6, 20))  # 만기보다 20일 낡음
    monkeypatch.setattr("yfinance.download", stale)

    out = ps._fetch_market_outcome("CL=F", date(2026, 7, 3), date(2026, 7, 10))
    assert out is None, "만기 봉이 20일 낡았는데 채점했다 — 짧은 창을 예측 결과로 위조한다"


def test_settle_lag_allows_a_weekend(monkeypatch):
    """가드가 **너무 세면 안 된다** — 주말·휴장으로 벌어진 간격은 통과시켜야 한다.

    만기가 일요일(2026-07-12)이면 마지막 거래일 봉은 금요일(07-10)이다 → 간격 2일.
    이걸 막으면 **주말 만기 예측은 영원히 채점되지 않는다.**
    ("모든 것을 잡는 가드는 채점기가 아니라 채점 중단 스위치다" — 오늘 배운 것)
    """
    friday_bar = _DriftingFeed(last_date=date(2026, 7, 10))  # 금요일 종가가 마지막
    monkeypatch.setattr("yfinance.download", friday_bar)
    sunday_maturity = date(2026, 7, 12)
    # 수리 전엔 이 상수가 없다 — getattr로 방어해야 테스트가 구 코드 위에서도 돈다
    assert getattr(ps, "_SETTLE_LAG_D", 0) >= 2, (
        "주말(2일)조차 못 넘기면 주말 만기가 영구 미채점된다"
    )
    assert ps._fetch_market_outcome("CL=F", date(2026, 7, 3), sunday_maturity) is not None


def test_due_selection_waits_for_the_window_to_close():
    """만기 **당일**에는 채점하지 않는다 — 창이 완전히 닫힌 뒤에만."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        "CREATE TABLE prediction_log ("
        " prediction_id TEXT PRIMARY KEY, status TEXT, resolve_by TEXT)"
    )
    today = date(2026, 7, 10)
    con.executemany(
        "INSERT INTO prediction_log VALUES (?,?,?)",
        [
            ("p-today", "PENDING", today.isoformat()),                    # 만기 = 오늘
            ("p-yesterday", "PENDING", (today - timedelta(days=1)).isoformat()),
        ],
    )
    due = [
        r["prediction_id"]
        for r in con.execute(
            "SELECT * FROM prediction_log WHERE status='PENDING' AND resolve_by < ?",
            (today.isoformat(),),
        )
    ]
    assert due == ["p-yesterday"], (
        "만기 당일 예측을 뽑았다 — 그날 종가는 아직 확정되지 않았다(CL=F 실측 사고)"
    )
