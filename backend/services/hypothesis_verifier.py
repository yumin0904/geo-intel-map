"""
services/hypothesis_verifier.py

HypothesisSpec 목록을 받아 Granger 검정을 실행하고
verification_status (PENDING / PARTIAL / VERIFIED)를 결정한다.

기준:
  p < 0.05  → VERIFIED  (통계적 유의)
  p < 0.15  → PARTIAL   (경향성 있음)
  그 외     → PENDING   (미검증)

데이터가 없거나 관측값 부족 시 PENDING 유지 + error 필드 기록.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from services.hypothesis_extractor import HypothesisSpec

logger = logging.getLogger(__name__)

# 분석 기간: 최근 18개월 (이벤트 데이터 충분성 확보)
_LOOKBACK_MONTHS = 18


def _get_date_range() -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_MONTHS * 30)
    return start, end


async def verify_hypotheses(specs: list[HypothesisSpec]) -> list[HypothesisSpec]:
    """
    각 HypothesisSpec에 대해 Granger 검정을 실행한다.
    region_code 또는 ticker가 없으면 PENDING 상태로 반환한다.
    """
    from services.cascade.correlation import (
        _load_event_series,
        _get_market_series,
        _run_granger,
    )

    start, end = _get_date_range()
    results: list[HypothesisSpec] = []

    for spec in specs:
        # 매핑 실패 시 검증 불가 — PENDING 유지
        if not spec.region_code or not spec.ticker:
            missing = []
            if not spec.region_code:
                missing.append("region")
            if not spec.ticker:
                missing.append("ticker")
            spec.error = f"매핑 실패: {', '.join(missing)} 미식별"
            logger.info("[hypothesis] PENDING (매핑 실패): %s", spec.h1[:60])
            results.append(spec)
            continue

        try:
            # 이벤트 시계열 (독립변수 X)
            event_series = _load_event_series(spec.region_code, start, end)
            if event_series is None or len(event_series) < 20:
                spec.error = f"이벤트 데이터 부족 ({len(event_series) if event_series is not None else 0}건)"
                results.append(spec)
                continue

            # 시장/지표 시계열 (종속변수 Y)
            market_series = await _get_market_series(spec.ticker, start, end)
            if market_series is None or len(market_series) < 20:
                spec.error = f"시장 데이터 부족 (ticker={spec.ticker})"
                results.append(spec)
                continue

            # Granger F-test
            p_value, best_lag, n_obs = _run_granger(event_series, market_series)
            spec.n_obs = n_obs

            if p_value is None:
                spec.error = "Granger 검정 실패 (관측값 부족 또는 분산=0)"
                results.append(spec)
                continue

            spec.granger_p = round(p_value, 4)
            spec.best_lag = best_lag

            # verification_status 결정
            if p_value < 0.05:
                spec.verification_status = "VERIFIED"
            elif p_value < 0.15:
                spec.verification_status = "PARTIAL"
            else:
                spec.verification_status = "PENDING"

            logger.info(
                "[hypothesis] %s | region=%s ticker=%s p=%.4f lag=%s → %s",
                spec.h1[:50], spec.region_code, spec.ticker,
                p_value, best_lag, spec.verification_status,
            )

        except Exception as exc:
            spec.error = str(exc)
            logger.warning("[hypothesis] 검정 오류: %s — %s", spec.h1[:50], exc)

        results.append(spec)

    return results
