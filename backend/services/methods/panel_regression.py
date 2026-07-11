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
# is_count: 카운트 DV — 포아송류 분기 (King 1989 원전 게이트 통과 2026-07-11:
#   OLS/log(y+c)는 카운트에 편향·비효율 [King 1989:126], E(Y)=exp(xβ) 포아송이 正道).
# exposure_col: 노출 통제 컬럼 — King 식(1)의 T·λ 구조. GDELT는 국가별 커버리지
#   총량 차가 커서(보도량≠사건 성향) log(exposure)를 통제항으로 동봉.
class _VarEntry(NamedTuple):
    pattern: str
    sql: str
    val_col: str
    data_type: str  # "panel" | "cross"
    is_count: bool = False
    exposure_col: str = ""


_VAR_CATALOG: list[_VarEntry] = [
    # ── 군사·안보 — 구체적 패턴을 일반 패턴보다 먼저 배치 ────────────────
    _VarEntry(
        r"milex.*usd|군사비.*usd|군사비.*달러|군사비.*규모|military.*usd|defense.*usd",
        "SELECT iso3, year, usd_mn_2022 AS val FROM sipri_milex",
        "val", "panel",
    ),
    _VarEntry(
        # "국방비" 추가: v2_milex_conflict_cross 골드가 이 표현으로 매핑 실패했음
        # (위원회 실측 2026-07-09 — 방위비·군사비와 동일 구성개념, SIPRI milex).
        r"방위비|군사비|국방비|국방.*예산|milex|military.*spend|defense.*spend",
        "SELECT iso3, year, gdp_pct AS val FROM sipri_milex",
        "val", "panel",
    ),
    _VarEntry(
        r"핵탄두|nuclear.*warhead",
        "SELECT iso3, year, value AS val FROM owid_data WHERE dataset='nuclear_warheads'",
        "val", "panel",
    ),
    # ── 민주주의·거버넌스 ────────────────────────────────────────────────
    # V-Dem(vdem_index)·WGI(world_bank_wgi): wave-2 frozen-seed panelization fix
    # (geo-os/wiki/decisions/20260709-data-audit-committee.md) 로 전체 연도 백필 완료.
    # SQL에 year 컬럼 추가 + data_type "panel"로 전환 — n_periods>=2 게이트 통과 가능.
    _VarEntry(
        r"민주주의|democracy|polyarchy|자유화|liberal.*dem",
        "SELECT iso3, year, v2x_polyarchy AS val FROM vdem_index",
        "val", "panel",
    ),
    _VarEntry(
        r"자유민주주의|liberal.*democracy",
        "SELECT iso3, year, v2x_libdem AS val FROM vdem_index",
        "val", "panel",
    ),
    # Polity5: 프로젝트 자체가 2018년으로 시리즈 종료됨 — 백필해도 년도 범위가
    # 안 늘어나 패널화 이득이 없음(체제 변화가 드문 저빈도 지표라 실효 n_periods도 낮음).
    # data_type "cross" 유지.
    _VarEntry(
        r"체제.*유형|regime.*type|권위주의|autocracy|polity",
        "SELECT iso3, polity2_score AS val FROM polity5",
        "val", "cross",
    ),
    _VarEntry(
        r"정치.*안정|political.*stab|내전.*위험",
        "SELECT iso3, year, pv_score AS val FROM world_bank_wgi",
        "val", "panel",
    ),
    _VarEntry(
        r"부패|corruption|청렴",
        "SELECT iso3, year, cc_score AS val FROM world_bank_wgi",
        "val", "panel",
    ),
    _VarEntry(
        r"법치|rule.*of.*law",
        "SELECT iso3, year, rl_score AS val FROM world_bank_wgi",
        "val", "panel",
    ),
    _VarEntry(
        r"규제.*품질|regulatory",
        "SELECT iso3, year, rq_score AS val FROM world_bank_wgi",
        "val", "panel",
    ),
    _VarEntry(
        r"정부.*효율|government.*effect",
        "SELECT iso3, year, ge_score AS val FROM world_bank_wgi",
        "val", "panel",
    ),
    _VarEntry(
        r"표현.*자유|voice.*account",
        "SELECT iso3, year, va_score AS val FROM world_bank_wgi",
        "val", "panel",
    ),
    # WGI 총칭("거버넌스 지수"·"WGI"): 세부 축 미특정 가설의 대표 축으로 GE(정부효율)
    # 사용 — 6축 중 '거버넌스 역량' 총칭에 가장 근접. 세부 축 패턴들이 위에서 먼저
    # 매칭되므로 이 엔트리는 총칭 표현에만 떨어진다 (구체 패턴 우선 배치 원칙).
    # ⚠️ "V-Dem 언론자유"는 여기 매핑 금지 — vdem_index에 press freedom 컬럼 부재
    # (v2x_freexp 미백필), WGI va_score로 보내면 구성개념 치환 (위원회 2026-07-09).
    _VarEntry(
        r"거버넌스|governance|\bwgi\b",
        "SELECT iso3, year, ge_score AS val FROM world_bank_wgi",
        "val", "panel",
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
    # ── 카운트 DV (GDELT 국가-연 집계 — §18-A: 국가급 이상 집계만) ──────────
    # 당해년 제외: 부분 연도 집계가 "급감" 아티팩트를 만든다 (큐 10② 당월제외와 동형).
    # exposure=n_total: 미통제 시 시위 성향이 아니라 GDELT 보도량을 추정하게 됨.
    _VarEntry(
        r"시위.*건수|시위.*빈도|시위.*발생|protest.*count|protest.*event|n_protest",
        "SELECT country AS iso3, CAST(substr(day,1,4) AS INTEGER) AS year, "
        "SUM(n_protest) AS val, SUM(n_total) AS exposure FROM gdelt_country_daily "
        "WHERE substr(day,1,4) < strftime('%Y','now') GROUP BY 1, 2",
        "val", "panel", True, "exposure",
    ),
    _VarEntry(
        r"물리.*충돌.*건수|무력.*충돌.*건수|material.*conflict.*count|물리적.*분쟁.*빈도",
        "SELECT country AS iso3, CAST(substr(day,1,4) AS INTEGER) AS year, "
        "SUM(n_material_conflict) AS val, SUM(n_total) AS exposure FROM gdelt_country_daily "
        "WHERE substr(day,1,4) < strftime('%Y','now') GROUP BY 1, 2",
        "val", "panel", True, "exposure",
    ),
]


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def _procure_entries(spec) -> tuple["_VarEntry | None", "_VarEntry | None"]:
    """spec에서 IV/DV 변수 카탈로그 엔트리를 매핑한다 (from_spec 1단계와 동일 로직).

    IV/DV 각자 고유 텍스트에서 매칭, 실패 시 H1 '일수록' 분할로 재시도.
    조달 게이트(verifier의 Type_B CROSS_SECTION 분기, v9.34.0)와 from_spec이
    같은 눈으로 판정하도록 단일 함수로 공유한다 — 게이트가 어댑터보다 좁으면
    검정 가능 케이스를 PENDING에 가두고, 넓으면 no-op 라우팅 착시가 생긴다.
    """
    iv_text = getattr(spec, "independent_var", "") or ""
    dv_text = getattr(spec, "dependent_var", "") or ""
    h1_text = getattr(spec, "h1", "") or ""
    iv_entry = _match_var(iv_text) or _match_var(h1_text.split("일수록")[0])
    dv_entry = _match_var(dv_text) or _match_var(h1_text.split("일수록")[-1])
    return iv_entry, dv_entry


def can_procure(spec) -> bool:
    """IV·DV가 모두 카탈로그에 조달되고 동어반복이 아닌지 — 조달 게이트용."""
    iv_entry, dv_entry = _procure_entries(spec)
    return (iv_entry is not None and dv_entry is not None
            and iv_entry.sql != dv_entry.sql)


def from_spec(spec) -> MethodResult:
    """
    HypothesisSpec → MethodResult (CROSS_SECTION 전용).

    동기 함수 — SQLite 쿼리는 동기 처리.
    """
    iv_text = getattr(spec, "independent_var", "") or ""
    dv_text = getattr(spec, "dependent_var", "") or ""

    # ── 1. 변수 매핑 ──────────────────────────────────────────────────────
    iv_entry, dv_entry = _procure_entries(spec)

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
    # 카운트 DV → 포아송류 분기 (King 1989 원전 게이트 통과 — OLS 갈래 기각)
    is_count = dv_entry.is_count
    try:
        if is_count and is_panel:
            stats = _run_poisson(df, iv_col, dv_col, fixed_effects=True)
            rung  = RUNG_QUASI_EXP
            caveat = (
                "포아송 FE(국가 더미): 시불변 교란·보도량(log exposure) 통제. "
                "과분산은 HC1 강건 SE로 보정(진단치 robustness.dispersion). "
                "시변 교란·역인과 잔존. GDELT 국가급 집계층(§18-A)."
            )
        elif is_count:
            stats = _run_poisson(df, iv_col, dv_col, fixed_effects=False)
            rung  = RUNG_CORRELATIONAL
            caveat = (
                "횡단 포아송: 카운트 DV의 국가간 비교(OLS 부적합 — King 1989). "
                "보도량 통제에도 OVB 잔존, 상관 칸."
            )
        elif is_panel:
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

    # within-method 강건성 (§9-0 ④): NB2 교차 계수의 부호가 뒤집히면
    # 결론이 분포 가정에 민감하다는 뜻 — 신뢰도 강등 + 캐비엇 명시
    nb2_flip = False
    if is_count and stats.get("nb2_coef") is not None and coef != 0:
        nb2_flip = (stats["nb2_coef"] * coef) < 0
        if nb2_flip:
            caveat += " ⚠️ NB2 교차 계수 부호 반전 — 분포 가정 민감, 결론 유보."

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
            # 카운트 DV(포아송) 전용 진단 — dispersion=Pearson χ²/df(1=정합),
            # nb2_coef=음이항 교차 계수(부호·크기 유지 여부가 within-method 강건성)
            **({"model": stats.get("model"),
                "dispersion": stats.get("dispersion"),
                "nb2_coef": stats.get("nb2_coef")} if is_count else {}),
        },
        confidence_within_rung=max(_confidence(p_value, n_units, is_panel) - (20 if nb2_flip else 0), 0),
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

    # 카운트 DV의 노출 컬럼은 조인을 관통해 보존한다 (포아송 분기에서 통제항)
    if dv.exposure_col and dv.exposure_col in df_dv.columns and dv.exposure_col != "exposure":
        df_dv = df_dv.rename(columns={dv.exposure_col: "exposure"})

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
            if dv.is_count:
                # 카운트는 평균이 아니라 합산 — 평균은 비정수 "카운트"를 만들어
                # 포아송 우도와 어긋난다. 노출도 같이 합산해 비율 구조 유지.
                agg_cols = {"dv": "sum"}
                if "exposure" in df_dv.columns:
                    agg_cols["exposure"] = "sum"
                df_dv = df_dv.groupby("iso3", as_index=False).agg(agg_cols)
            else:
                df_dv = df_dv.groupby("iso3", as_index=False)["dv"].mean()
        dv_cols = ["iso3", "dv"] + (["exposure"] if "exposure" in df_dv.columns else [])
        merged = pd.merge(df_iv[["iso3", "iv"]], df_dv[dv_cols], on="iso3", how="inner")

    if "iso3" not in merged.columns:
        return None
    return merged.dropna(subset=["iv", "dv"])


def _run_poisson(df: pd.DataFrame, iv_col: str, dv_col: str,
                 fixed_effects: bool = False) -> dict:
    """포아송 회귀 (King 1989 원전 게이트 통과 — 2026-07-11 정독).

    E(Y)=λ=exp(xβ), 로그우도 전역 오목[식 5] — OLS/log(y+c)의 편향·비효율
    [King 1989:126]을 피하는 카운트 正道.
    - 노출 통제: 'exposure' 컬럼 존재 시 log(exposure)를 공변량으로 (식 1의 T·λ 구조.
      offset 고정 대신 통제항 — 탄력성 1 강제를 피하고 데이터가 결정).
    - 과분산: HC1 강건 표준오차 + Pearson χ²/df 진단 보고. 경미한 과분산에서
      포아송 계수는 일치추정·SE만 보정하면 된다는 각주 6(Gourieroux 1984) 지침의
      샌드위치 일반화. 강한 과분산은 NB2 교차 강건성으로 노출.
    - 패널 FE: 국가 더미 포아송 — 포아송 FE는 부수 모수 문제 없이 일치추정
      (로짓과 다름). 시불변 교란(국가 크기·언어권 보도 편향 등) 소거.
    - 원인 단정 금지: 과분산의 원인(전염 vs 이질성)은 집계 수준에서 관측 동치
      [King 1989:127, Cramér 정리] — 진단 수치만 보고하고 해석은 유보.
    """
    import statsmodels.api as sm

    work = df.copy()
    cols = [iv_col]
    if "exposure" in work.columns:
        work = work[work["exposure"] > 0]
        work["log_exposure"] = np.log(work["exposure"].astype(float))
        cols.append("log_exposure")

    y = work[dv_col].astype(float)
    X = work[cols].astype(float)
    if fixed_effects:
        dummies = pd.get_dummies(work["iso3"], prefix="fe", drop_first=True, dtype=float)
        X = pd.concat([X, dummies], axis=1)
    X = sm.add_constant(X)

    model = sm.GLM(y, X, family=sm.families.Poisson())
    res = model.fit(cov_type="HC1")

    beta = float(res.params[iv_col])
    se   = float(res.bse[iv_col])
    p    = float(res.pvalues[iv_col])
    ci   = res.conf_int().loc[iv_col]
    # 과분산 진단: Pearson χ²/df — 1이면 등분산(포아송 정합), >1 과분산
    dispersion = float(res.pearson_chi2 / res.df_resid) if res.df_resid > 0 else float("nan")

    # NB2 교차 강건성 — 계수 방향·크기 유지 여부 (실패해도 주 결과는 유효)
    nb_coef = None
    try:
        nb_res = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=1.0)).fit()
        nb_coef = round(float(nb_res.params[iv_col]), 4)
    except Exception:
        pass

    return {
        "coef": beta, "se": se, "t_stat": beta / se if se > 0 else 0.0,
        "p_value": p, "r2": float(1 - res.deviance / res.null_deviance)
                           if res.null_deviance > 0 else 0.0,  # pseudo-R² (deviance)
        "n_obs": int(res.nobs),
        "ci_low": float(ci[0]), "ci_high": float(ci[1]),
        "dispersion": round(dispersion, 2),
        "nb2_coef": nb_coef,
        "model": "poisson_fe" if fixed_effects else "poisson",
    }


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
