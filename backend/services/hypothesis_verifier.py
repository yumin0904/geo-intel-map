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
    "east_china_sea":    "ITA",    # 동중국해(일본): 미 방산 ETF (이론근거 쌍·로컬 캐시)
    "bab_el_mandeb":     "CL=F",   # 바브엘만데브: WTI 유가
    "suez":              "CL=F",   # 수에즈: WTI 유가
    "middle_east":       "GLD",    # 중동: 금 (안전자산 도피)
    "malacca":           "CL=F",   # 말라카: WTI 유가
    "sahel":             "GLD",    # 사헬: 금 (지역 불안 프록시)
}

# [Cycle 6-B] 섹터 기본 ticker — 지역 미식별 시 섹터로 대리변수 선택
# 사이버·기술 섹터 H1은 지역 코드 없이 섹터만 식별되는 경우가 많음
_SECTOR_DEFAULT_TICKER: dict[str, str] = {
    "cyber":       "ITA",    # 사이버 공격 → 미 방산 ETF (APT 공격 → 방산투자 반응)
    "techno":      "SOXX",   # 기술 패권 → 반도체 ETF (공급망 충격 반응)
    "maritime":    "CL=F",   # 해양 → WTI 유가 (SLOC 차단 에너지 프리미엄)
    "energy":      "CL=F",   # 에너지 → WTI 유가
    "indo_pacific": "TSM",   # 인도-태평양 → TSMC (대만해협 긴장 프록시)
    "gray_zone":   "GLD",    # 회색지대 → 금 (불확실성 안전자산 도피)
}

# 분석 기간: 최근 18개월 (이벤트 데이터 충분성 확보)
_LOOKBACK_MONTHS = 24  # 18→24: 2년 데이터로 Granger 통계력 강화 (Korean p=0.048 VERIFIED 확인)

# ── 인과추론 사다리 (학술 정합성 재설계) ──────────────────────────────────────
# Granger는 '선행성(precedence)'까지만 주장 가능. 인과 아님.
_LADDER_DESCRIPTIVE = "기술적"   # 검정 불가/미실행 — 서술적 근거만
_LADDER_CORRELATIONAL = "상관"   # p<0.15 or 이론근거 약한 쌍 — 시사적
_LADDER_PRECEDENCE = "선행성"    # p<0.05 + 이론근거 — Granger 예측적 선행 (인과 아님)

_GRANGER_CAVEAT = (
    "Granger 선행성은 예측적 선행이지 구조적 인과가 아님 · 양변량 교란 미통제"
)
_GRANGER_CAVEAT_CONTROLLED = (
    "VIX(글로벌 위험) 통제 조건부 선행성 — 공통 교란 완화했으나 여전히 구조적 인과는 아님"
)
_WEAK_PAIR_CAVEAT = (
    "이론적 인과 메커니즘이 약한 대리쌍 — 허위상관 가능성, 상관 이상 주장 불가"
)

# [B4] 문헌상 전이(contagion/spillover) 메커니즘이 정립된 (지역A → 지역B) 쌍.
# 사건→사건 Granger에서 이 쌍만 '선행성' 칸 도달 가능 (방향 있음, A→B).
_THEORY_GROUNDED_CONTAGION: set[tuple[str, str]] = {
    ("middle_east", "hormuz"),       # 이란 핵심 분쟁 → 호르무즈 도발 (프록시 에스컬레이션)
    ("middle_east", "bab_el_mandeb"),# 중동 분쟁 → 후티 홍해 공격 (이란 축)
    ("hormuz", "bab_el_mandeb"),     # 호르무즈 긴장 → 홍해 (이란-후티 연계)
    ("eastern_europe", "middle_east"),# 러-우 → 중동 (강대국 관심 분산·자원 연계)
    ("sahel", "bab_el_mandeb"),      # 사헬 지하디스트 → 홍해 회랑 (지하드 확산)
    ("middle_east", "korean_peninsula"),  # 중동 위기 → 미 자산 분산 → 한반도 기회주의
}

# 문헌상 인과 메커니즘이 정립된 (region, ticker) 쌍 — correlation.py _VALIDATION_PAIRS 기반
# 이 화이트리스트 밖의 쌍(섹터 편의 proxy)은 유의해도 '상관' 칸으로 상한
_THEORY_GROUNDED_PAIRS: set[tuple[str, str]] = {
    ("ukraine", "ZW=F"), ("ukraine", "CL=F"),
    ("eastern_europe", "ZW=F"), ("eastern_europe", "CL=F"),
    ("bab_el_mandeb", "CL=F"),
    ("hormuz", "CL=F"),
    ("middle_east", "GLD"),
    ("korean_peninsula", "KRW=X"), ("north_korea", "KRW=X"),
    ("taiwan_strait", "TSM"), ("taiwan_strait", "SOXX"),
    ("east_china_sea", "ITA"), ("south_china_sea", "ITA"),
    ("malacca", "NG=F"), ("suez", "CL=F"),
    # AR-2: 신규 일별 시계열 매핑의 문헌상 인과쌍
    ("taiwan_strait", "TWD=X"),    # 대만해협 긴장 → 대만 달러 (지정학 리스크 프리미엄)
    ("eastern_europe", "BZ=F"), ("ukraine", "BZ=F"),  # 러-우 → Brent (에너지 무기화)
    ("hormuz", "BZ=F"), ("bab_el_mandeb", "BZ=F"),    # 초크포인트 → Brent (중동 벤치마크)
}


def _classify_inference_grade(
    p_value: float | None,
    theory_grounded: bool,
    controlled: bool = False,
) -> tuple[str, str]:
    """
    Granger p값 + 이론근거 + 교란통제 → 인과추론 사다리 등급 + 단서.

    핵심 원칙 (학술 정직성):
      - 어떤 결과도 '선행성'을 넘어 인과를 주장하지 않는다.
      - '선행성'은 이론근거 + 유의 + **통제변수 조건부(B3)** 3조건 충족 시에만.
      - 이론근거 없거나 교란 미통제면 유의해도 '상관'에서 상한 (허위상관 방어).
    """
    if p_value is None:
        return _LADDER_DESCRIPTIVE, "Granger 검정 미실행/불가 — 인과 추론 근거 없음"
    if p_value < 0.05:
        if theory_grounded and controlled:
            return _LADDER_PRECEDENCE, _GRANGER_CAVEAT_CONTROLLED
        if theory_grounded and not controlled:
            # 교란 미통제 → 선행성 주장 불가, 상관 상한
            return _LADDER_CORRELATIONAL, _GRANGER_CAVEAT + " · 교란 미통제로 선행성 주장 불가"
        return _LADDER_CORRELATIONAL, _WEAK_PAIR_CAVEAT  # A3: 근거 약하면 상한
    if p_value < 0.15:
        return _LADDER_CORRELATIONAL, _GRANGER_CAVEAT + " · 경향성 수준(p<0.15)"
    return _LADDER_DESCRIPTIVE, "Granger 비유의(p≥0.15) — 선행성 근거 없음"


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
    get_control_series=None,
    run_conditional_granger=None,
) -> HypothesisSpec:
    """
    HypothesisSpec에 대해 Granger 선행성 검정을 실행한다.

    [B3] 통제변수(VIX) 로드 가능 시 **조건부 Granger** 우선 — 공통 교란 완화.
         불가 시 양변량 fallback (교란 미통제 단서 유지).
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

        # [B3] 통제변수 로드 (실패 시 None → 양변량 fallback)
        control_series, control_name = (None, None)
        if get_control_series is not None:
            control_series, control_name = await get_control_series(start, end)

        # sparse 이벤트 시계열(주간 집계)과 일별 시장·통제 시계열 길이 불일치 보정
        is_weekly = bool(event_series.name and "weekly" in str(event_series.name))
        if is_weekly:
            market_series = market_series.resample("W").last()
            if control_series is not None:
                control_series = control_series.resample("W").last()

        # ── [B3] 조건부 Granger 우선, 불가 시 양변량 ──────────────────────
        if control_series is not None and run_conditional_granger is not None:
            p_value, best_lag, n_obs, f_stat, meta = run_conditional_granger(
                event_series, market_series, control_series
            )
            # 조건부 검정이 표본 부족 등으로 실패하면 양변량으로 재시도
            if p_value is None:
                p_value, best_lag, n_obs, f_stat, meta = run_granger(event_series, market_series)
        else:
            p_value, best_lag, n_obs, f_stat, meta = run_granger(event_series, market_series)

        spec.n_obs = n_obs
        spec.differenced = bool(meta.get("differenced")) if meta else False
        spec.controlled  = bool(meta.get("controlled")) if meta else False
        spec.control_name = control_name if spec.controlled else None

        if p_value is None:
            spec.error = "Granger 검정 실패 (관측값 부족 또는 분산=0)"
            spec.inference_grade  = _LADDER_DESCRIPTIVE
            spec.inference_caveat = "검정 불가 — 인과 추론 근거 없음"
            return spec

        spec.granger_p    = round(p_value, 4)
        spec.f_statistic  = f_stat
        spec.best_lag     = best_lag

        # ── 이론근거 판정 + 인과추론 사다리 등급 (통제 여부 반영) ──────────
        spec.theory_grounded = (spec.region_code or "", spec.ticker or "") in _THEORY_GROUNDED_PAIRS
        spec.inference_grade, spec.inference_caveat = _classify_inference_grade(
            p_value, spec.theory_grounded, spec.controlled
        )

        # verification_status: 하위 호환용 — 사다리에서 파생 (인과 단정 어휘 배제)
        if spec.inference_grade == _LADDER_PRECEDENCE:
            spec.verification_status = "VERIFIED"   # = '선행성 유의' (UI에서 사다리로 표기)
        elif spec.inference_grade == _LADDER_CORRELATIONAL:
            spec.verification_status = "PARTIAL"
        else:
            spec.verification_status = "PENDING"

        if proxy_label:
            spec.error = (
                f"[대리변수 사용] {proxy_label} → {spec.ticker} "
                f"(p={spec.granger_p}, F={f_stat}, lag={best_lag}, "
                f"diff={spec.differenced})"
            )

        logger.info(
            "[hypothesis] %s | region=%s ticker=%s p=%.4f lag=%s grounded=%s diff=%s → %s%s",
            spec.h1[:50], spec.region_code, spec.ticker,
            p_value, best_lag, spec.theory_grounded, spec.differenced,
            spec.inference_grade,
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
        _get_control_series,        # [B3] 통제변수 로더
        _run_conditional_granger,   # [B3] 조건부 Granger
    )

    start, end = _get_date_range()
    results: list[HypothesisSpec] = []

    # [B3] 통제변수는 쿼리당 1회만 로드해 재사용 (yfinance 호출 절약)
    _ctl_cache: dict = {}

    async def _cached_control(s: date, e: date):
        if "v" not in _ctl_cache:
            _ctl_cache["v"] = await _get_control_series(s, e)
        return _ctl_cache["v"]

    # [B4] 사건→사건 Granger 러너 (전이 가설) — 글로벌 분쟁 baseline 통제
    from services.cascade.correlation import (
        _load_global_conflict_series, _run_conditional_granger as _cond_g,
    )

    async def _run_event_to_event(spec: HypothesisSpec) -> HypothesisSpec:
        x = _load_event_series(spec.region_code, start, end)       # 독립 지역 A
        y = _load_event_series(spec.dependent_region, start, end)  # 종속 지역 B
        if x is None or y is None or len(x) < 30 or len(y) < 30:
            spec.error = (
                f"사건→사건 데이터 부족 (A={spec.region_code}:{len(x) if x is not None else 0} "
                f"B={spec.dependent_region}:{len(y) if y is not None else 0})"
            )
            spec.inference_grade = _LADDER_DESCRIPTIVE
            return spec
        z = _load_global_conflict_series(start, end, exclude=[spec.region_code, spec.dependent_region])
        p, lag, n, f, meta = _cond_g(x, y, z)
        spec.n_obs = n
        spec.differenced = bool(meta.get("differenced"))
        spec.controlled = bool(meta.get("controlled"))
        spec.control_name = "글로벌 분쟁 baseline" if spec.controlled else None
        if p is None:
            spec.error = "사건→사건 Granger 실패 (관측·분산 부족)"
            spec.inference_grade = _LADDER_DESCRIPTIVE
            return spec
        spec.granger_p = round(p, 4)
        spec.f_statistic = f
        spec.best_lag = lag
        spec.theory_grounded = (
            (spec.region_code or "", spec.dependent_region or "") in _THEORY_GROUNDED_CONTAGION
        )
        spec.inference_grade, spec.inference_caveat = _classify_inference_grade(
            p, spec.theory_grounded, spec.controlled
        )
        # 사건→사건 통제변수는 VIX가 아니라 글로벌 분쟁 baseline — 단서 라벨 교정
        if spec.controlled:
            spec.inference_caveat = spec.inference_caveat.replace(
                "VIX(글로벌 위험)", "글로벌 분쟁 baseline"
            )
        if spec.inference_grade == _LADDER_PRECEDENCE:
            spec.verification_status = "VERIFIED"
        elif spec.inference_grade == _LADDER_CORRELATIONAL:
            spec.verification_status = "PARTIAL"
        else:
            spec.verification_status = "PENDING"
        spec.error = (
            f"[사건→사건] {spec.region_code}→{spec.dependent_region} "
            f"(글로벌 분쟁 통제, p={spec.granger_p}, grounded={spec.theory_grounded})"
        )
        logger.info(
            "[hypothesis] 사건→사건 %s→%s p=%.4f grounded=%s → %s",
            spec.region_code, spec.dependent_region, p, spec.theory_grounded,
            spec.inference_grade,
        )
        return spec

    for spec in specs:
        # [B4] 사건→사건 전이 가설이 최우선 — 시장 경로 대신 지역B 이벤트로 검정
        if spec.dependent_region and spec.region_code:
            spec = await _run_event_to_event(spec)
            results.append(spec)
            continue

        if spec.var_type == "Type_B":
            if not spec.region_code:
                spec.error = "Type B (행동 변수): region_code 미식별 → ACLED 검증 불가"
                spec.inference_caveat = (
                    "검정 불가 — 종속변수가 '건수·빈도'(행동 변수)이나 집계 지역이 식별되지 않음. "
                    "검정하려면 H1에 지역(예: '동중국해 분쟁 건수')과 집계 출처(ACLED/CSIS)를 명시해야 함."
                )
            else:
                spec.error = (
                    f"Type B (행동 변수): ACLED 이벤트 비교 필요 "
                    f"(region={spec.region_code}) "
                    f"→ actor_filter 기반 event study로 검증 가능 (다음 버전 구현 예정)"
                )
                spec.inference_caveat = (
                    f"검정 불가 — 종속변수가 행동 변수(건수)로 {spec.region_code} ACLED 시계열은 있으나 "
                    f"actor_filter 기반 event study 미구현. 현재는 서술·이론 근거만 가능."
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
                    get_control_series=_cached_control,
                    run_conditional_granger=_run_conditional_granger,
                    proxy_label=proxy_label,
                )
            else:
                proxy_str = ", ".join(spec.proxy_suggestions[:3]) if spec.proxy_suggestions else "대체 지표 필요"
                spec.error = f"Type C (추상 변수): region 미식별 → 권장 대리변수: {proxy_str}"
                spec.inference_caveat = (
                    f"검정 불가 — 종속변수가 추상 지표(예: 의존도·취약성·생산비)로 직접 매핑 가능한 "
                    f"시계열·ticker 없음. 권장 대리변수: {proxy_str}. "
                    f"이 대리변수의 실측 시계열이 확보돼야 Granger 검정 가능."
                )
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
                        get_control_series=_cached_control,
                        run_conditional_granger=_run_conditional_granger,
                        proxy_label=proxy_label,
                    )
                    logger.info("[hypothesis] Type_A→C 자동강등 %s: %s", spec.verification_status, spec.h1[:60])
                    results.append(spec)
                    continue

            # [Cycle 6-B] 섹터 proxy 경로: region 미식별이지만 섹터 키워드로 ticker 결정
            sector_proxy = _get_sector_proxy(spec)
            if sector_proxy:
                proxy_ticker, proxy_label = sector_proxy
                spec.var_type = "Type_C"
                # [버그수정] 이미 정확히 추출된 ticker(예: 원/달러→KRW=X)는 보존.
                #   섹터 키워드(사이버 등)로 ITA 등 엉뚱한 ticker로 덮어쓰지 않음.
                region_fallback = False
                if not spec.ticker:
                    spec.ticker = proxy_ticker
                # region 없으면 event_archive 조회 불가 → 섹터 대표 지역 폴백(명시)
                if not spec.region_code:
                    spec.region_code = "middle_east"
                    region_fallback = True
                spec = await _run_granger_for_spec(
                    spec, start, end,
                    _load_event_series, _get_market_series, _run_granger,
                    get_control_series=_cached_control,
                    run_conditional_granger=_run_conditional_granger,
                    proxy_label=f"섹터 proxy: {proxy_label}",
                )
                # 지역을 추정 폴백한 경우 결과가 쿼리 지역과 다를 수 있음을 명시
                if region_fallback:
                    spec.inference_caveat = (
                        f"[지역 미식별 — {spec.region_code} 추정 폴백] " +
                        (spec.inference_caveat or "")
                    )
                logger.info("[hypothesis] 섹터proxy %s: %s", spec.verification_status, spec.h1[:60])
                results.append(spec)
                continue

            missing = []
            if not spec.region_code:
                missing.append("지역")
            if not spec.ticker:
                missing.append("시장 ticker")
            spec.error = f"Type A (금융 ticker): 매핑 실패 — {', '.join(missing)} 미식별"
            spec.inference_caveat = (
                f"검정 불가 — {', '.join(missing)}을(를) 식별하지 못해 시계열 매핑 실패. "
                f"종속변수를 환율·유가·주가·ETF 등 측정 가능한 시장 지표로 재정의하거나, "
                f"H1에 분석 지역을 명시하면 검정 가능."
            )
            logger.info("[hypothesis] Type_A PENDING (매핑 실패): %s", spec.h1[:60])
            results.append(spec)
            continue

        # Type_A 정상 경로: region + ticker 모두 있음
        spec = await _run_granger_for_spec(
            spec, start, end,
            _load_event_series, _get_market_series, _run_granger,
            get_control_series=_cached_control,
            run_conditional_granger=_run_conditional_granger,
        )
        results.append(spec)

    # ── [B2] 다중검정 보정 (Benjamini-Hochberg FDR) ──────────────────────────
    # 한 쿼리에서 여러 가설을 검정하면 우연 유의가 누적된다.
    # 같은 쿼리 범위 내 Granger p값을 FDR 보정 → '선행성' 등급 재판정.
    tested = [s for s in results if s.granger_p is not None]
    if len(tested) >= 2:
        try:
            from statsmodels.stats.multitest import multipletests
            pvals = [s.granger_p for s in tested]
            _, qvals, _, _ = multipletests(pvals, alpha=0.05, method="fdr_bh")
            for s, q in zip(tested, qvals):
                s.granger_q = round(float(q), 4)
                # FDR 미통과 시 '선행성' → '상관'으로 정직 강등
                if s.inference_grade == _LADDER_PRECEDENCE and q >= 0.05:
                    s.inference_grade = _LADDER_CORRELATIONAL
                    s.inference_caveat = (
                        f"{_GRANGER_CAVEAT} · 다중검정 FDR 미통과(q={s.granger_q})"
                    )
                    s.verification_status = "PARTIAL"
                    logger.info(
                        "[hypothesis] FDR 강등: %s (p=%.4f q=%.4f)",
                        s.h1[:40], s.granger_p, q,
                    )
        except Exception as exc:
            logger.warning("[hypothesis] FDR 보정 실패: %s", exc)

    return results


def _get_sector_proxy(spec: "HypothesisSpec") -> tuple[str, str] | None:
    """
    [Cycle 6-B] 지역 미식별 시 섹터로 대리변수 ticker를 선택한다.
    H1 텍스트에서 섹터 키워드를 탐지해 _SECTOR_DEFAULT_TICKER로 매핑.
    반환: (ticker, proxy_label) 또는 None
    """
    h1_lower = spec.h1.lower()
    # 우선순위: 구체적(specific) → 일반(general) 순서로 배치
    sector_keywords = {
        "cyber":        ["사이버", "cyber", "apt", "해킹", "악성코드", "랜섬웨어"],
        "indo_pacific": ["대만", "taiwan", "tsmc", "인도-태평양", "indo-pacific", "a2ad"],
        "techno":       ["반도체", "semiconductor", "soxx", "chip", "희토류", "공급망"],
        "energy":       ["유가", "원유", "에너지", "lng", "가스", "oil", "호르무즈"],
        "maritime":     ["해양", "해협", "sloc", "초크포인트", "chokepoint", "선박"],
        "gray_zone":    ["회색지대", "gray zone", "하이브리드", "프록시"],
    }
    for sector, keywords in sector_keywords.items():
        if any(kw in h1_lower for kw in keywords):
            ticker = _SECTOR_DEFAULT_TICKER.get(sector)
            if ticker:
                return ticker, f"{sector} 섹터 대리변수 → {ticker}"
    return None
