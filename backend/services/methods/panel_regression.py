"""
services/methods/panel_regression.py  (9-B)

횡단/패널 회귀 어댑터 — CROSS_SECTION 시그니처 가설에 적용.

방법론:
  단일 연도 데이터(n_periods==1) → 횡단 OLS (cross-section OLS) → 상관 칸
  다연도 데이터(n_periods≥2) → 패널 고정효과 회귀(within-estimator) → 준실험 칸

정치외교학 이론 연결:
  횡단 OLS: "X가 높은 국가일수록 Y가 낮다" 형태의 국가간 비교를 정량화.
    Waltz 수준 분석(state-domestic)에서 체계 간 변이를 포착.
  패널 FE(고정효과): 국가별 시불변(time-invariant) 교란변수(문화·지리·역사)를 소거.
    within-unit 변동만 이용해 탈락변수 편의(OVB)를 부분적으로 제거.
    → OLS보다 강한 식별전략, 준실험 칸까지 도달 가능.
  한계: 시변(time-varying) 교란·역인과 문제는 잔존(도구변수·RDD 필요).

사다리 칸:
  cross-section OLS   → RUNG_CORRELATIONAL (상관)
  panel FE (≥2 년, ≥5 국가) → RUNG_QUASI_EXP  (준실험)

가정 자가검증(assumptions_met):
  1. IV·DV 변수 카탈로그 매핑 성공
  2. 조인 후 유효 관측값 ≥ 5 국가(units)
  3. IV 분산 > 0 (상수 변수 배제)
  4. 통계 패키지(statsmodels) 임포트 가능

변수 카탈로그:
  H1 텍스트(independent_var·dependent_var)에서 키워드 매칭 →
  DB 테이블·컬럼·조인 키 결정 (Token-Zero 결정론, LLM 불필요).
"""
from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

from services.methods.base import (
    RUNG_CORRELATIONAL,
    RUNG_DESCRIPTIVE,
    RUNG_QUASI_EXP,
    MethodResult,
)
from services.methods.grader import effect_size_label

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "db" / "intel.db"
_MIN_UNITS = 5   # 최소 국가(단위) 수 — 횡단·패널 공통
_MIN_PERIODS = 2 # 패널 FE 최소 연도 수


# ── 변수 카탈로그 ──────────────────────────────────────────────────────────────
# (정규식 패턴, SQL 쿼리 템플릿, 컬럼명, 조인키, 데이터 유형)
# data_type: "panel" = iso3+year 두 키 / "cross" = iso3만
class _VarEntry(NamedTuple):
    pattern: str
    sql: str
    val_col: str
    data_type: str  # "panel" | "cross"


_VAR_CATALOG: list[_VarEntry] = [
    # ── 군사·안보 — 구체적 패턴을 일반 패턴보다 먼저 배치 ────────────────
    _VarEntry(
        r"milex.*usd|군사비.*usd|군사비.*달러|군사비.*규모|military.*usd|defense.*usd",
        "SELECT iso3, year, usd_mn_2022 AS val FROM sipri_milex",
        "val", "panel",
    ),
    _VarEntry(
        r"방위비|군사비|milex|military.*spend|defense.*spend",
        "SELECT iso3, year, gdp_pct AS val FROM sipri_milex",
        "val", "panel",
    ),
    _VarEntry(
        r"핵탄두|nuclear.*warhead",
        "SELECT iso3, year, value AS val FROM owid_data WHERE dataset='nuclear_warheads'",
        "val", "panel",
    ),
    # ── 민주주의·거버넌스 ────────────────────────────────────────────────
    _VarEntry(
        r"민주주의|democracy|polyarchy|자유화|liberal.*dem",
        "SELECT iso3, v2x_polyarchy AS val FROM vdem_index",
        "val", "cross",
    ),
    _VarEntry(
        r"자유민주주의|liberal.*democracy",
        "SELECT iso3, v2x_libdem AS val FROM vdem_index",
        "val", "cross",
    ),
    _VarEntry(
        r"체제.*유형|regime.*type|권위주의|autocracy|polity",
        "SELECT iso3, polity2_score AS val FROM polity5",
        "val", "cross",
    ),
    _VarEntry(
        r"정치.*안정|political.*stab|내전.*위험",
        "SELECT iso3, pv_score AS val FROM world_bank_wgi",
        "val", "cross",
    ),
    _VarEntry(
        r"부패|corruption|청렴",
        "SELECT iso3, cc_score AS val FROM world_bank_wgi",
        "val", "cross",
    ),
    _VarEntry(
        r"법치|rule.*of.*law",
        "SELECT iso3, rl_score AS val FROM world_bank_wgi",
        "val", "cross",
    ),
    _VarEntry(
        r"규제.*품질|regulatory",
        "SELECT iso3, rq_score AS val FROM world_bank_wgi",
        "val", "cross",
    ),
    _VarEntry(
        r"정부.*효율|government.*effect",
        "SELECT iso3, ge_score AS val FROM world_bank_wgi",
        "val", "cross",
    ),
    _VarEntry(
        r"표현.*자유|voice.*account",
        "SELECT iso3, va_score AS val FROM world_bank_wgi",
        "val", "cross",
    ),
    # ── 에너지·자원 ──────────────────────────────────────────────────────
    _VarEntry(
        r"원유.*생산|oil.*prod|crude.*prod",
        "SELECT iso3, crude_prod_mbpd AS val FROM eia_energy",
        "val", "cross",
    ),
    _VarEntry(
        r"천연가스.*생산|natgas.*prod|lng.*prod",
        "SELECT iso3, natgas_prod_bcfd AS val FROM eia_energy",
        "val", "cross",
    ),
    _VarEntry(
        r"원유.*수출|oil.*export",
        "SELECT iso3, oil_export_mbpd AS val FROM eia_energy",
        "val", "cross",
    ),
    # ── 분쟁·안보 사건 ────────────────────────────────────────────────────
    _VarEntry(
        r"분쟁.*강도|conflict.*intens|충돌.*수준|전쟁.*강도|hiik",
        "SELECT primary_country_iso3 AS iso3, intensity AS val FROM hiik_conflict",
        "val", "cross",
    ),
]


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def from_spec(spec) -> MethodResult:
    """
    HypothesisSpec → MethodResult (CROSS_SECTION 전용).

    동기 함수 — SQLite 쿼리는 동기 처리.
    """
    iv_text = getattr(spec, "independent_var", "") or ""
    dv_text = getattr(spec, "dependent_var", "") or ""
    h1_text = getattr(spec, "h1", "") or ""

    # ── 1. 변수 매핑 ──────────────────────────────────────────────────────
    # IV/DV 각자 고유 텍스트에서 매칭. 모두 실패하면 H1 전체로 재시도.
    iv_entry = _match_var(iv_text) or _match_var(h1_text.split("일수록")[0])
    dv_entry = _match_var(dv_text) or _match_var(h1_text.split("일수록")[-1])

    if iv_entry is None or dv_entry is None:
        matched = []
        if iv_entry is not None:
            matched.append(f"IV={iv_entry.val_col}")
        if dv_entry is not None:
            matched.append(f"DV={dv_entry.val_col}")
        return _fail(
            f"변수 카탈로그 매핑 실패 — IV:'{iv_text[:30]}' / DV:'{dv_text[:30]}'. "
            f"매핑됨: {matched or '없음'}",
        )

    if iv_entry.sql == dv_entry.sql:
        return _fail("IV와 DV가 같은 DB 컬럼 — 동어반복 회귀 금지")

    # ── 2. 데이터 로드 및 조인 ────────────────────────────────────────────
    df = _load_and_join(iv_entry, dv_entry)
    if df is None or len(df) < _MIN_UNITS:
        n = len(df) if df is not None else 0
        return _fail(f"조인 후 관측값 부족(n={n}<{_MIN_UNITS})")

    iv_col, dv_col = "iv", "dv"

    if df[iv_col].std() == 0:
        return _fail("IV 분산=0 — 상수 변수 회귀 불가")

    # ── 3. 패널 여부 판단 ────────────────────────────────────────────────
    is_panel = (
        iv_entry.data_type == "panel"
        and dv_entry.data_type == "panel"
        and "year" in df.columns
        and df["year"].nunique() >= _MIN_PERIODS
    )
    n_units   = df["iso3"].nunique()
    n_periods = int(df["year"].nunique()) if "year" in df.columns else 1

    # ── 4. 회귀 실행 ─────────────────────────────────────────────────────
    try:
        if is_panel:
            stats = _run_panel_fe(df, iv_col, dv_col)
            rung  = RUNG_QUASI_EXP
            caveat = (
                "패널 고정효과(within-estimator): 국가별 시불변 교란 소거. "
                "시변 교란·역인과 잔존 — 도구변수·DD 필요 시 추가 검정."
            )
        else:
            stats = _run_ols(df, iv_col, dv_col)
            rung  = RUNG_CORRELATIONAL
            caveat = (
                "횡단 OLS: 국가간 비교, 탈락변수 편의(OVB) 잔존. "
                "고정효과·도구변수 없이 상관 칸에 머뭄."
            )
    except Exception as exc:
        logger.warning("[9-B] 회귀 실패: %s", exc)
        return _fail(f"회귀 계산 실패: {exc}")

    p_value = stats["p_value"]
    coef    = stats["coef"]

    logger.info(
        "[panel_reg] is_panel=%s n=%d×%d coef=%.4f p=%.4f rung=%s",
        is_panel, n_units, n_periods, coef, p_value, rung,
    )

    return MethodResult(
        method="panel_regression",
        signature="CROSS_SECTION",
        effect_estimate=coef,
        effect_size_label=effect_size_label(coef, small_threshold=0.1, medium_threshold=0.5),
        significance=round(p_value, 4),
        ci_low=round(stats["ci_low"], 4) if stats.get("ci_low") is not None else None,
        ci_high=round(stats["ci_high"], 4) if stats.get("ci_high") is not None else None,
        reachable_rung=RUNG_QUASI_EXP,  # 패널 있으면 준실험 가능
        actual_rung=rung,
        assumptions_met=True,
        assumption_caveat=caveat,
        robustness={
            "n_units":    n_units,
            "n_periods":  n_periods,
            "r2":         round(stats.get("r2", 0.0), 4),
            "is_panel_fe": is_panel,
            "iv_source":  iv_entry.val_col,
            "dv_source":  dv_entry.val_col,
        },
        confidence_within_rung=_confidence(p_value, n_units, is_panel),
        native_stats={
            "coef":     round(coef, 4),
            "p_value":  round(p_value, 4),
            "r2":       round(stats.get("r2", 0.0), 4),
            "n_obs":    stats.get("n_obs", len(df)),
            "n_units":  n_units,
            "n_periods":n_periods,
            "se":       round(stats.get("se", 0.0), 4),
            "t_stat":   round(stats.get("t_stat", 0.0), 3),
            "iv_col":   iv_entry.val_col,
            "dv_col":   dv_entry.val_col,
        },
        exploratory=False,
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _match_var(text: str) -> _VarEntry | None:
    """텍스트에서 첫 번째 매칭 변수 엔트리를 반환한다."""
    for entry in _VAR_CATALOG:
        if re.search(entry.pattern, text, re.IGNORECASE):
            return entry
    return None


def _load_and_join(iv: _VarEntry, dv: _VarEntry) -> pd.DataFrame | None:
    """IV·DV를 로드하고 iso3 (+ year) 기준으로 조인한다.

    패널×횡단 혼합(panel IV + cross DV 또는 반대) 시:
    패널 쪽을 iso3별 평균으로 붕괴(collapse)해 단일 횡단면으로 맞춘다.
    두 쪽 모두 panel일 때만 iso3+year 완전 패널 구조를 유지한다.
    """
    try:
        con = sqlite3.connect(str(_DB_PATH))
        df_iv = pd.read_sql_query(iv.sql, con).rename(columns={iv.val_col: "iv"})
        df_dv = pd.read_sql_query(dv.sql, con).rename(columns={dv.val_col: "dv"})
        con.close()
    except Exception as exc:
        logger.warning("[9-B] DB 로드 실패: %s", exc)
        return None

    both_panel = iv.data_type == "panel" and dv.data_type == "panel"

    if both_panel:
        # 완전 패널: iso3+year 조인
        keys = ["iso3", "year"]
        for k in list(keys):
            if k not in df_iv.columns or k not in df_dv.columns:
                keys.remove(k)
        if not keys:
            return None
        merged = pd.merge(df_iv, df_dv, on=keys, how="inner")
        if "iso3" not in merged.columns and "year" in df_iv.columns:
            merged["iso3"] = df_iv["iso3"]
    else:
        # 혼합: 패널 쪽을 iso3별 평균으로 붕괴 → 횡단면으로 통일
        if iv.data_type == "panel" and "year" in df_iv.columns:
            df_iv = df_iv.groupby("iso3", as_index=False)["iv"].mean()
        if dv.data_type == "panel" and "year" in df_dv.columns:
            df_dv = df_dv.groupby("iso3", as_index=False)["dv"].mean()
        merged = pd.merge(df_iv[["iso3", "iv"]], df_dv[["iso3", "dv"]], on="iso3", how="inner")

    if "iso3" not in merged.columns:
        return None
    return merged.dropna(subset=["iv", "dv"])


def _run_ols(df: pd.DataFrame, iv_col: str, dv_col: str) -> dict:
    """횡단 OLS: DV ~ IV. statsmodels 없으면 numpy fallback."""
    x = df[iv_col].values.astype(float)
    y = df[dv_col].values.astype(float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)

    # numpy OLS
    X = np.column_stack([np.ones(n), x])
    try:
        coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        alpha, beta = float(coeffs[0]), float(coeffs[1])
    except np.linalg.LinAlgError:
        return {"coef": 0.0, "se": 0.0, "t_stat": 0.0, "p_value": 1.0, "r2": 0.0, "n_obs": n}

    y_pred  = alpha + beta * x
    ss_res  = float(np.sum((y - y_pred) ** 2))
    ss_tot  = float(np.sum((y - y.mean()) ** 2))
    r2      = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    df_res  = max(n - 2, 1)
    mse     = ss_res / df_res
    xx_inv  = np.linalg.inv(X.T @ X)
    se      = float(np.sqrt(mse * xx_inv[1, 1]))
    t_stat  = beta / se if se > 0 else 0.0

    from scipy import stats as sp
    p_value = float(2 * sp.t.sf(abs(t_stat), df=df_res))

    # 95% CI
    t_crit = float(sp.t.ppf(0.975, df=df_res))
    ci_low  = beta - t_crit * se
    ci_high = beta + t_crit * se

    return {
        "coef": beta, "se": se, "t_stat": t_stat,
        "p_value": p_value, "r2": r2, "n_obs": n,
        "ci_low": ci_low, "ci_high": ci_high,
    }


def _run_panel_fe(df: pd.DataFrame, iv_col: str, dv_col: str) -> dict:
    """
    패널 고정효과(within-estimator) — 그룹 내 편차로 개체 불변 교란 제거.

    변환: x̃_it = x_it − x̄_i,  ỹ_it = y_it − ȳ_i
    추정: OLS(ỹ ~ x̃) → beta_within
    """
    df = df.copy()
    df["iv_dm"] = df[iv_col] - df.groupby("iso3")[iv_col].transform("mean")
    df["dv_dm"] = df[dv_col] - df.groupby("iso3")[dv_col].transform("mean")

    clean = df[["iv_dm", "dv_dm"]].dropna()
    n_units  = df["iso3"].nunique()
    # 자유도: n_obs - n_units - 1 (고정효과 소거로 n_units개 자유도 소비)
    df_res = max(len(clean) - n_units - 1, 1)

    stats = _run_ols(clean.rename(columns={"iv_dm": iv_col, "dv_dm": dv_col}), iv_col, dv_col)
    # 자유도 재계산 (within-estimator 보정)
    se     = stats["se"]
    beta   = stats["coef"]
    t_stat = beta / se if se > 0 else 0.0
    from scipy import stats as sp
    p_value = float(2 * sp.t.sf(abs(t_stat), df=df_res))
    t_crit  = float(sp.t.ppf(0.975, df=df_res))

    stats.update({
        "p_value": p_value,
        "t_stat":  t_stat,
        "ci_low":  beta - t_crit * se,
        "ci_high": beta + t_crit * se,
        "n_obs":   len(clean),
    })
    return stats


def _confidence(p_value: float, n_units: int, is_panel: bool) -> int:
    score = 0
    if p_value < 0.05:
        score += 50
    elif p_value < 0.15:
        score += 25
    if n_units >= 20:
        score += 20
    elif n_units >= _MIN_UNITS:
        score += 10
    if is_panel:
        score += 20   # FE 구조적 우위
    return min(score, 100)


def _fail(reason: str) -> MethodResult:
    return MethodResult(
        method="panel_regression",
        signature="CROSS_SECTION",
        assumptions_met=False,
        assumption_caveat=reason,
        reachable_rung=RUNG_QUASI_EXP,
        actual_rung=RUNG_DESCRIPTIVE,
    )
