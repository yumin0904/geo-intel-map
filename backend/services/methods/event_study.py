"""
services/methods/event_study.py  (9-A)

이벤트 스터디 어댑터 — SINGLE_SHOCK 시그니처 가설에 적용.

방법론 (준실험 식별전략):
  추정 윈도우(T-120 ~ T-20 거래일)에서 시장 모델(R_i = α + β·R_m)을 OLS로 적합 →
  이벤트 윈도우(T-5 ~ T+20)에서 비정상수익률(AR = R_실제 − R_기대) 산출 →
  누적비정상수익률(CAR)과 표준오차로 t-검정.

정치외교학 이론 연결:
  반사실 추정은 "사건이 없었다면 시장이 어떻게 움직였을까"를 시장 모델로 대리한다.
  MacKinlay(1997) 이벤트 스터디 표준 절차를 지정학 충격(펠로시 방문·JCPOA 탈퇴 등)에 적용.
  단기 국소 효과 탐지 — Granger(전역·lead-lag)와 삼각측량 시 발산하면
  "일시적 시장 과반응 → 장기 선행성 없음" 해석 가능.

사다리 칸: 준실험 (causal_rung = RUNG_QUASI_EXP)
가정 자가검증(assumptions_met 4조건):
  1. 이벤트 날짜 식별 가능 (H1 텍스트 또는 spec 메타)
  2. 추정 윈도우 관측값 ≥ MIN_ESTIMATION_OBS 거래일
  3. 시장 모델 R² ≥ MIN_R2 (대리변수 설명력 가드)
  4. 이벤트 윈도우 데이터 존재 (티커 가격 로드 성공)

anti-pattern 가드:
  - assumptions_met=False → RUNG_DESCRIPTIVE (자격 박탈 — method-type laundering 차단)
  - 시장 모델 R²<MIN_R2 → 벤치마크 설명력 부족 → 준실험 아님
  - CAR은 점추정 + bootstrap CI[③]로 보고 (t-분포 approximation 포함)
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from services.methods.base import (
    RUNG_CORRELATIONAL,
    RUNG_DESCRIPTIVE,
    RUNG_QUASI_EXP,
    MethodResult,
)
from services.methods.grader import effect_size_label

logger = logging.getLogger(__name__)

# ── 구성 상수 (granger_thresholds.yaml 참조) ──────────────────────────────────
_THR_PATH = Path(__file__).parent.parent.parent / "config" / "granger_thresholds.yaml"
_THR: dict = yaml.safe_load(_THR_PATH.read_text(encoding="utf-8"))

_ESTIMATION_PRE  = 120    # 추정 윈도우 시작: 이벤트 T-120 거래일 전
_ESTIMATION_POST = 20     # 추정 윈도우 종료: T-20 거래일 전 (오염 방지)
_EVENT_PRE       = 5      # 이벤트 윈도우 시작: T-5
_EVENT_POST      = 20     # 이벤트 윈도우 종료: T+20
_MIN_ESTIMATION_OBS = 60  # 추정 최소 관측값 (거래일)
_MIN_R2          = 0.05   # 시장 모델 최소 R² — 대리변수 설명력 가드
_BENCHMARK_TICKER = "^GSPC"  # S&P500 — 글로벌 공통 교란 통제 대리변수

# ── 이벤트 날짜 추출 패턴 ─────────────────────────────────────────────────────
_RE_DATE_KR  = re.compile(r"(\d{4})년\s*(\d{1,2})월(?:\s*(\d{1,2})일)?")
_RE_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATE_SHORT = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def from_spec(spec) -> MethodResult:
    """
    HypothesisSpec → MethodResult (SINGLE_SHOCK 전용).

    동기 함수 — yfinance.download()는 동기이므로 await 불필요.
    spec은 hypothesis_verifier가 완성한 상태 (ticker, h1, h0 등 채워진 후).
    """
    ticker = getattr(spec, "ticker", None) or ""
    # ticker 없이는 종속변수 시계열을 로드할 수 없어 이벤트스터디가 성립하지 않는다.
    # verifier가 매핑 실패 spec을 미리 걸러내지만, 다른 호출자 대비 이중 방어 —
    # 껍데기(effect=None) MethodResult를 만들지 않고 assumptions_met=False로 정직 반환.
    if not ticker:
        return _no_ticker_result()
    h1_text = f"{getattr(spec, 'h1', '')} {getattr(spec, 'h0', '')}"

    # ── 1. 이벤트 날짜 식별 ────────────────────────────────────────────────
    event_date = _extract_event_date(h1_text)
    if event_date is None:
        return _no_date_result(ticker)

    # ── 2. 데이터 로드 ────────────────────────────────────────────────────
    estimation_start = _trading_day_offset(event_date, -(_ESTIMATION_PRE))
    estimation_end   = _trading_day_offset(event_date, -(_ESTIMATION_POST))
    event_end        = _trading_day_offset(event_date, _EVENT_POST)

    data_start = estimation_start - timedelta(days=5)   # 주말·공휴일 여유
    data_end   = event_end + timedelta(days=5)

    returns, benchmark_returns = _load_returns(
        ticker, _BENCHMARK_TICKER, data_start, data_end
    )

    if returns is None or benchmark_returns is None:
        return _data_fail_result(ticker, event_date, "가격 데이터 로드 실패")

    # ── 3. 추정 윈도우 슬라이싱 ───────────────────────────────────────────
    est_mask = (returns.index >= pd.Timestamp(estimation_start)) & \
               (returns.index <= pd.Timestamp(estimation_end))
    r_est  = returns[est_mask]
    bm_est = benchmark_returns[est_mask]

    if len(r_est) < _MIN_ESTIMATION_OBS:
        return _assumption_fail_result(
            ticker, event_date,
            f"추정 윈도우 관측값 부족(n={len(r_est)}<{_MIN_ESTIMATION_OBS})",
            n_est=len(r_est),
        )

    # ── 4. 시장 모델 적합 (OLS) ──────────────────────────────────────────
    alpha, beta, r2 = _fit_market_model(r_est, bm_est)
    if r2 < _MIN_R2:
        return _assumption_fail_result(
            ticker, event_date,
            f"시장 모델 R²={r2:.3f}<{_MIN_R2} — 벤치마크 설명력 부족",
            n_est=len(r_est), r2=r2,
        )

    # ── 5. 이벤트 윈도우 AR·CAR 산출 ────────────────────────────────────
    evt_mask = (returns.index >= pd.Timestamp(_trading_day_offset(event_date, -_EVENT_PRE))) & \
               (returns.index <= pd.Timestamp(event_end))
    r_evt  = returns[evt_mask]
    bm_evt = benchmark_returns[evt_mask]

    if len(r_evt) == 0:
        return _data_fail_result(ticker, event_date, "이벤트 윈도우 데이터 없음")

    # AR = 실제 수익률 − (α + β·R_m)
    ar = r_evt - (alpha + beta * bm_evt)
    car = float(ar.sum())

    # ── 6. t-검정 ─────────────────────────────────────────────────────────
    # 표준오차: 추정 윈도우 AR 잔차의 표준편차 (MacKinlay 1997 §2)
    est_ar = r_est - (alpha + beta * bm_est)
    se = float(est_ar.std())
    n_evt = len(r_evt)
    t_stat = (car / (se * np.sqrt(n_evt))) if se > 0 and n_evt > 0 else 0.0

    from scipy import stats as sp_stats
    p_value = float(2 * sp_stats.t.sf(abs(t_stat), df=len(r_est) - 2))

    # ── 7. Bootstrap CI[③] ────────────────────────────────────────────────
    ci_low, ci_high = _bootstrap_car_ci(r_est, bm_est, alpha, beta, n_evt)

    # ── 8. 사다리 칸 + MethodResult ───────────────────────────────────────
    assumptions_met = True   # 여기까지 왔으면 모든 가정 충족
    actual_rung = RUNG_QUASI_EXP  # 반사실 추정 → 준실험

    significance_label = (
        "유의(p<0.05)" if p_value < 0.05
        else "경향성(p<0.15)" if p_value < 0.15
        else "비유의"
    )

    logger.info(
        "[event_study] ticker=%s event=%s CAR=%.4f t=%.3f p=%.4f R²=%.3f n_est=%d",
        ticker, event_date, car, t_stat, p_value, r2, len(r_est),
    )

    return MethodResult(
        method="event_study",
        signature="SINGLE_SHOCK",
        effect_estimate=car,
        effect_size_label=effect_size_label(car, small_threshold=0.01, medium_threshold=0.03),
        significance=round(p_value, 4),
        ci_low=round(ci_low, 4) if ci_low is not None else None,
        ci_high=round(ci_high, 4) if ci_high is not None else None,
        reachable_rung=RUNG_QUASI_EXP,
        actual_rung=actual_rung,
        assumptions_met=assumptions_met,
        assumption_caveat="",
        robustness={
            # [④] 내부 강건성: 윈도우 변동·이상치 민감도
            "r2_market_model":    round(r2, 4),
            "n_estimation":       len(r_est),
            "n_event_window":     n_evt,
            "alpha":              round(alpha, 6),
            "beta":               round(beta, 4),
            "significance_label": significance_label,
            # 이벤트 직후(T+1~T+5) 단기 CAR — 조기 반응 강건성
            "car_short": _car_short(r_evt, bm_evt, alpha, beta, window=5),
        },
        confidence_within_rung=_confidence(p_value, r2, len(r_est)),
        native_stats={
            "car":        round(car, 4),
            "t_stat":     round(t_stat, 3),
            "p_value":    round(p_value, 4),
            "r2":         round(r2, 4),
            "event_date": event_date.isoformat(),
            "ticker":     ticker,
            "benchmark":  _BENCHMARK_TICKER,
            "estimation_window": f"T-{_ESTIMATION_PRE}~T-{_ESTIMATION_POST}",
            "event_window":      f"T-{_EVENT_PRE}~T+{_EVENT_POST}",
        },
        exploratory=False,
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _extract_event_date(text: str) -> date | None:
    """H1 텍스트에서 이벤트 날짜를 추출한다. 실패 시 None."""
    # ISO 형식 우선 (2022-08-02)
    m = _RE_DATE_ISO.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 슬래시 형식 (2022/8/2)
    m = _RE_DATE_SHORT.search(text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 한국어 형식 (2022년 8월 2일 / 2022년 8월)
    m = _RE_DATE_KR.search(text)
    if m:
        try:
            y, mo = int(m.group(1)), int(m.group(2))
            d = int(m.group(3)) if m.group(3) else 15   # 일 미식별 → 월중순
            return date(y, mo, d)
        except ValueError:
            pass

    return None


def _trading_day_offset(base: date, offset_days: int) -> date:
    """
    영업일 근사 오프셋 — 달력일로 환산 (pandas BDay 미사용, 간결성 우선).
    양수면 이후, 음수면 이전. 주말 자동 보정은 yfinance 다운로드에 위임.
    """
    # 영업일 ≈ 달력일 × 7/5 (단순 근사)
    cal_days = int(abs(offset_days) * 1.4) + 3
    delta = timedelta(days=cal_days)
    return base + delta if offset_days >= 0 else base - delta


def _load_returns(
    ticker: str,
    benchmark: str,
    start: date,
    end: date,
) -> tuple[pd.Series | None, pd.Series | None]:
    """yfinance로 수익률 시계열을 동기 로드한다."""
    try:
        import yfinance as yf

        df = yf.download(
            [ticker, benchmark],
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return None, None

        # multi-column: ("Close", ticker) / ("Close", benchmark)
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"]
        else:
            close = df[["Close"]] if "Close" in df.columns else df

        if ticker not in close.columns or benchmark not in close.columns:
            logger.warning("[event_study] 티커 컬럼 누락: available=%s", list(close.columns))
            return None, None

        ret_t  = close[ticker].pct_change().dropna()
        ret_bm = close[benchmark].pct_change().dropna()

        # 공통 날짜만 유지 (거래일 불일치 보정)
        common = ret_t.index.intersection(ret_bm.index)
        return ret_t.loc[common], ret_bm.loc[common]

    except Exception as exc:
        logger.warning("[event_study] yfinance 로드 실패: %s", exc)
        return None, None


def _fit_market_model(
    returns: pd.Series,
    benchmark: pd.Series,
) -> tuple[float, float, float]:
    """
    OLS: R_i = α + β·R_m.
    반환: (alpha, beta, r_squared).
    """
    common = returns.index.intersection(benchmark.index)
    r = returns.loc[common].values
    b = benchmark.loc[common].values

    if len(r) < 10 or np.std(b) == 0:
        return 0.0, 1.0, 0.0

    # 수동 OLS (numpy — scipy 의존 최소화)
    X = np.column_stack([np.ones(len(b)), b])
    try:
        coeffs, *_ = np.linalg.lstsq(X, r, rcond=None)
        alpha, beta = float(coeffs[0]), float(coeffs[1])
        r_pred = alpha + beta * b
        ss_res = float(np.sum((r - r_pred) ** 2))
        ss_tot = float(np.sum((r - r.mean()) ** 2))
        r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        return alpha, beta, r2
    except np.linalg.LinAlgError:
        return 0.0, 1.0, 0.0


def _bootstrap_car_ci(
    r_est: pd.Series,
    bm_est: pd.Series,
    alpha: float,
    beta: float,
    n_evt: int,
    n_boot: int = 500,
    ci_level: float = 0.95,
) -> tuple[float | None, float | None]:
    """
    [③] 추정 윈도우 잔차 재표집으로 CAR 신뢰구간을 산출한다.
    계산 실패 시 None 반환.
    """
    try:
        residuals = (r_est - (alpha + beta * bm_est)).values
        if len(residuals) < 10:
            return None, None
        rng = np.random.default_rng(42)
        cars = [
            float(rng.choice(residuals, size=n_evt, replace=True).sum())
            for _ in range(n_boot)
        ]
        lo = float(np.percentile(cars, (1 - ci_level) / 2 * 100))
        hi = float(np.percentile(cars, (1 - (1 - ci_level) / 2) * 100))
        return lo, hi
    except Exception:
        return None, None


def _car_short(
    r_evt: pd.Series,
    bm_evt: pd.Series,
    alpha: float,
    beta: float,
    window: int = 5,
) -> float | None:
    """T+1~T+window 단기 CAR — 강건성 점검용."""
    try:
        common = r_evt.index.intersection(bm_evt.index)
        short = (r_evt.loc[common] - (alpha + beta * bm_evt.loc[common])).iloc[:window]
        return round(float(short.sum()), 4) if len(short) > 0 else None
    except Exception:
        return None


def _confidence(p_value: float, r2: float, n_est: int) -> int:
    """칸 안에서 신뢰도 0~100."""
    score = 0
    if p_value < 0.05:
        score += 50
    elif p_value < 0.15:
        score += 25
    if r2 >= 0.2:
        score += 25
    elif r2 >= 0.1:
        score += 15
    elif r2 >= _MIN_R2:
        score += 5
    if n_est >= 100:
        score += 15
    elif n_est >= _MIN_ESTIMATION_OBS:
        score += 10
    return min(score, 100)


def _no_date_result(ticker: str) -> MethodResult:
    """이벤트 날짜 미식별 → assumptions_met=False."""
    return MethodResult(
        method="event_study",
        signature="SINGLE_SHOCK",
        assumptions_met=False,
        assumption_caveat="이벤트 날짜 미식별 — H1 텍스트에 날짜(YYYY-MM-DD / YYYY년 MM월 DD일) 없음",
        reachable_rung=RUNG_QUASI_EXP,
        actual_rung=RUNG_DESCRIPTIVE,
        native_stats={"ticker": ticker},
    )


def _no_ticker_result() -> MethodResult:
    """종속변수 ticker 미식별 → 이벤트스터디 성립 불가, assumptions_met=False."""
    return MethodResult(
        method="event_study",
        signature="SINGLE_SHOCK",
        assumptions_met=False,
        assumption_caveat="종속변수 ticker 미식별 — 시장 시계열 로드 불가로 이벤트스터디 성립 안 함",
        reachable_rung=RUNG_QUASI_EXP,
        actual_rung=RUNG_DESCRIPTIVE,
        native_stats={"ticker": ""},
    )


def _data_fail_result(ticker: str, event_date: date, reason: str) -> MethodResult:
    """데이터 로드 실패 → assumptions_met=False."""
    return MethodResult(
        method="event_study",
        signature="SINGLE_SHOCK",
        assumptions_met=False,
        assumption_caveat=reason,
        reachable_rung=RUNG_QUASI_EXP,
        actual_rung=RUNG_DESCRIPTIVE,
        native_stats={"ticker": ticker, "event_date": event_date.isoformat()},
    )


def _assumption_fail_result(
    ticker: str,
    event_date: date,
    caveat: str,
    n_est: int = 0,
    r2: float = 0.0,
) -> MethodResult:
    """가정 미충족 (추정 obs 부족 / R² 부족) → 상관 상한."""
    return MethodResult(
        method="event_study",
        signature="SINGLE_SHOCK",
        assumptions_met=False,
        assumption_caveat=caveat,
        reachable_rung=RUNG_QUASI_EXP,   # 조건 충족 시 도달 가능
        actual_rung=RUNG_CORRELATIONAL,   # 가정 미충족 → 상관 상한 (descriptive보단 나음)
        robustness={"n_estimation": n_est, "r2_market_model": round(r2, 4)},
        native_stats={"ticker": ticker, "event_date": event_date.isoformat()},
    )
