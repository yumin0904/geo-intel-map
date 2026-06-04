"""
services/hypothesis_verifier.py

HypothesisSpec 목록을 받아 Granger 검정을 실행하고
verification_status (PENDING / PARTIAL / VERIFIED)를 결정한다.

기준:
  p < 0.05  → VERIFIED  (통계적 유의)
  p < 0.15  → PARTIAL   (경향성 있음)
  그 외     → PENDING   (미검증)

v6.3.0 추가:
  [P3] Type A ticker 매핑 실패 → region 있으면 Type C 대리변수 경로로 자동 강등
  [P2] Type C PROXY_DATA_MAP — ACLED 이벤트 시계열 + 지역 기본 ticker로 Granger 실행

데이터가 없거나 관측값 부족 시 PENDING 유지 + error 필드 기록.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from services.hypothesis_extractor import HypothesisSpec

logger = logging.getLogger(__name__)

# [P2] 지역 기본 ticker — Type C 및 Type A 실패 시 대리 종속변수로 사용
# 각 지역의 지정학적 충격이 가장 직접 전이되는 금융 지표
_REGION_DEFAULT_TICKER: dict[str, str] = {
    "eastern_europe":    "CL=F",   # 러-우: WTI 유가 (에너지 무기화)
    "taiwan_strait":     "TSM",    # 대만: TSMC 주가 (반도체 공급망)
    "hormuz":            "CL=F",   # 호르무즈: WTI 유가 (초크포인트)
    "korean_peninsula":  "KRW=X",  # 한반도: 원/달러 환율
    "bab_el_mandeb":     "CL=F",   # 바브엘만데브: WTI 유가
    "suez":              "CL=F",   # 수에즈: WTI 유가
    "middle_east":       "GLD",    # 중동: 금 (안전자산 도피)
    "malacca":           "CL=F",   # 말라카: WTI 유가
    "sahel":             "GLD",    # 사헬: 금 (지역 불안 프록시)
}

# 분석 기간: 최근 18개월 (이벤트 데이터 충분성 확보)
_LOOKBACK_MONTHS = 18


def _get_date_range() -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_MONTHS * 30)
    return start, end


async def _run_granger_for_spec(
    spec: HypothesisSpec,
    start: date,
    end: date,
    load_event_series,
    get_market_series,
    run_granger,
    *,
    proxy_label: str | None = None,
) -> HypothesisSpec:
    """
    HypothesisSpec에 대해 Granger 검정을 실행한다.
    proxy_label: Type C 대리변수 사용 시 에러 필드에 기재.
    """
    try:
        event_series = load_event_series(spec.region_code, start, end)
        if event_series is None or len(event_series) < 20:
            spec.error = (
                f"이벤트 데이터 부족 ({len(event_series) if event_series is not None else 0}건)"
            )
            return spec

        market_series = await get_market_series(spec.ticker, start, end)
        if market_series is None or len(market_series) < 20:
            spec.error = f"시장 데이터 부족 (ticker={spec.ticker})"
            return spec

        p_value, best_lag, n_obs = run_granger(event_series, market_series)
        spec.n_obs = n_obs

        if p_value is None:
            spec.error = "Granger 검정 실패 (관측값 부족 또는 분산=0)"
            return spec

        spec.granger_p = round(p_value, 4)
        spec.best_lag  = best_lag

        if p_value < 0.05:
            spec.verification_status = "VERIFIED"
        elif p_value < 0.15:
            spec.verification_status = "PARTIAL"
        else:
            spec.verification_status = "PENDING"

        if proxy_label:
            spec.error = (
                f"[대리변수 사용] {proxy_label} → {spec.ticker} "
                f"(p={spec.granger_p}, lag={best_lag})"
            )

        logger.info(
            "[hypothesis] %s | region=%s ticker=%s p=%.4f lag=%s → %s%s",
            spec.h1[:50], spec.region_code, spec.ticker,
            p_value, best_lag, spec.verification_status,
            f" [{proxy_label}]" if proxy_label else "",
        )
    except Exception as exc:
        spec.error = str(exc)
        logger.warning("[hypothesis] 검정 오류: %s — %s", spec.h1[:50], exc)

    return spec


async def verify_hypotheses(specs: list[HypothesisSpec]) -> list[HypothesisSpec]:
    """
    각 HypothesisSpec에 대해 Granger 검정을 실행한다.

    v6.3.0 분기 로직:
      Type_C: ACLED 이벤트 시계열 + 지역 기본 ticker → Granger 실행 (P2)
      Type_A 실패: region 있으면 Type C 경로로 자동 강등 (P3)
      Type_B: PENDING + 안내 메시지 (변화 없음)
    """
    from services.cascade.correlation import (
        _load_event_series,
        _get_market_series,
        _run_granger,
    )

    start, end = _get_date_range()
    results: list[HypothesisSpec] = []

    for spec in specs:
        if spec.var_type == "Type_B":
            if not spec.region_code:
                spec.error = "Type B (행동 변수): region_code 미식별 → ACLED 검증 불가"
            else:
                spec.error = (
                    f"Type B (행동 변수): ACLED 이벤트 비교 필요 "
                    f"(region={spec.region_code}) "
                    f"→ actor_filter 기반 event study로 검증 가능 (다음 버전 구현 예정)"
                )
            logger.info("[hypothesis] Type_B PENDING: %s", spec.h1[:60])
            results.append(spec)
            continue

        if spec.var_type == "Type_C":
            # [P2] 대리변수 Granger: ACLED 이벤트 시계열 + 지역 기본 ticker
            default_ticker = _REGION_DEFAULT_TICKER.get(spec.region_code or "")
            if spec.region_code and default_ticker:
                spec.ticker = default_ticker
                proxy_label = (
                    f"ACLED {spec.region_code} 이벤트 건수"
                    f" → {default_ticker} (지역 기본 지표)"
                )
                spec = await _run_granger_for_spec(
                    spec, start, end,
                    _load_event_series, _get_market_series, _run_granger,
                    proxy_label=proxy_label,
                )
            else:
                proxy_str = ", ".join(spec.proxy_suggestions[:3]) if spec.proxy_suggestions else "대체 지표 필요"
                spec.error = f"Type C (추상 변수): region 미식별 → 권장 대리변수: {proxy_str}"
            logger.info("[hypothesis] Type_C %s: %s", spec.verification_status, spec.h1[:60])
            results.append(spec)
            continue

        # Type_A: 금융 ticker Granger 경로
        if not spec.region_code or not spec.ticker:
            # [P3] ticker 매핑 실패 → region 있으면 Type C 대리변수 경로로 자동 강등
            if spec.region_code:
                default_ticker = _REGION_DEFAULT_TICKER.get(spec.region_code)
                if default_ticker:
                    spec.var_type = "Type_C"
                    spec.ticker = default_ticker
                    proxy_label = (
                        f"Type A 강등 → ACLED {spec.region_code} + {default_ticker} 대리변수"
                    )
                    spec = await _run_granger_for_spec(
                        spec, start, end,
                        _load_event_series, _get_market_series, _run_granger,
                        proxy_label=proxy_label,
                    )
                    logger.info("[hypothesis] Type_A→C 자동강등 %s: %s", spec.verification_status, spec.h1[:60])
                    results.append(spec)
                    continue

            missing = []
            if not spec.region_code:
                missing.append("region")
            if not spec.ticker:
                missing.append("ticker")
            spec.error = f"Type A (금융 ticker): 매핑 실패 — {', '.join(missing)} 미식별"
            logger.info("[hypothesis] Type_A PENDING (매핑 실패): %s", spec.h1[:60])
            results.append(spec)
            continue

        # Type_A 정상 경로: region + ticker 모두 있음
        spec = await _run_granger_for_spec(
            spec, start, end,
            _load_event_series, _get_market_series, _run_granger,
        )
        results.append(spec)

    return results
