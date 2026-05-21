"""
yfinance_adapter.py — 시장 지표(유가 등) 조회 어댑터.

Cascade 룰의 expected_response를 검증하는 데 사용한다.
예: 호르무즈 분쟁 이벤트(트리거) 발생 후 48시간 내 WTI 원유(CL=F)가
    1.5% 이상 올랐는가?

yfinance는 동기(블로킹) 라이브러리이므로 이 모듈의 함수도 sync로 둔다.
async 컨텍스트(엔진)에서는 asyncio.to_thread로 감싸 호출한다.
무료/저가 자원 원칙(CLAUDE.md)에 따라 yfinance(야후 파이낸스 무료)를 사용한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

logger = logging.getLogger(__name__)

# (ticker, start_date, end_date) → 가격 시계열(list[(date, close)]) 메모리 캐시.
# 과거 가격은 변하지 않으므로 영구 캐시해도 안전하다(앱 재시작 전까지).
_price_cache: dict[tuple[str, str, str], list[tuple[datetime, float]]] = {}


def _fetch_daily_closes(
    ticker: str, start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    """[start, end] 구간의 일별 종가를 (UTC datetime, close) 리스트로 반환한다.

    네트워크/데이터 실패 시 빈 리스트를 반환한다(에러는 로그로 남김).
    """
    key = (ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if key in _price_cache:
        return _price_cache[key]

    try:
        df = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
        )
    except Exception as e:
        logger.warning(f"[yfinance] {ticker} 조회 실패: {e}")
        return []

    if df.empty or "Close" not in df.columns:
        logger.warning(f"[yfinance] {ticker} 데이터 없음 ({key[1]}~{key[2]})")
        _price_cache[key] = []
        return []

    series: list[tuple[datetime, float]] = []
    for ts, close in df["Close"].items():
        # pandas Timestamp → UTC aware datetime
        dt = ts.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        series.append((dt, float(close)))

    series.sort(key=lambda x: x[0])
    _price_cache[key] = series
    return series


def evaluate_response(
    ticker: str,
    direction: str,
    trigger_time: datetime,
    window_hours: int,
    threshold_pct: float,
) -> dict | None:
    """트리거 시점 이후 윈도우 동안 가격이 기대 방향으로 임계치 이상 움직였는지 평가한다.

    baseline = 트리거 시각 당일 또는 직전 거래일 종가
    extreme  = 윈도우 내 종가의 최댓값(up) / 최솟값(down)
    pct      = (extreme - baseline) / baseline * 100

    Returns:
        평가 결과 dict(baseline/extreme/pct_change/matched 등) 또는 데이터 없으면 None.
    """
    # baseline 확보를 위해 트리거 5일 전부터, 윈도우 끝 + 하루까지 조회
    start = trigger_time - timedelta(days=5)
    end = trigger_time + timedelta(hours=window_hours) + timedelta(days=1)
    series = _fetch_daily_closes(ticker, start, end)
    if not series:
        return None

    # baseline: 트리거 시각 이하의 마지막 종가
    baseline = None
    for dt, close in series:
        if dt <= trigger_time:
            baseline = (dt, close)
        else:
            break
    if baseline is None:
        return None

    window_end = trigger_time + timedelta(hours=window_hours)
    # 윈도우 내(트리거 이후 ~ window_end) 종가들
    in_window = [(dt, c) for dt, c in series if trigger_time < dt <= window_end]
    if not in_window:
        return None

    base_dt, base_price = baseline
    if direction == "up":
        ext_dt, ext_price = max(in_window, key=lambda x: x[1])
    else:
        ext_dt, ext_price = min(in_window, key=lambda x: x[1])

    pct_change = (ext_price - base_price) / base_price * 100.0
    matched = (
        (direction == "up" and pct_change >= threshold_pct)
        or (direction == "down" and pct_change <= -threshold_pct)
    )

    return {
        "ticker": ticker,
        "direction": direction,
        "baseline_date": base_dt.isoformat(),
        "baseline_price": round(base_price, 2),
        "extreme_date": ext_dt.isoformat(),
        "extreme_price": round(ext_price, 2),
        "pct_change": round(pct_change, 2),
        "threshold_pct": threshold_pct,
        "matched": matched,
    }
