"""
services/methods/granger_adapter.py  (9-0)

기존 Granger 결과(HypothesisSpec) → MethodResult 공통 스키마 변환.

Granger는 사다리에서 '선행성' 칸까지 도달 가능한 첫 번째 어댑터.
assumptions_met 자가검증:
  - n_obs >= d4_insufficient_threshold (데이터 충분성)
  - theory_grounded=True (화이트리스트 인과 메커니즘)
  - linear_testable=True (8-gate 통과)
  둘 다 충족해야 '선행성' 칸 자격. 미충족 시 '상관' 또는 '기술적'으로 상한.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from services.methods.base import (
    MethodResult,
    RUNG_DESCRIPTIVE,
    RUNG_CORRELATIONAL,
    RUNG_PRECEDENCE,
)
from services.methods.grader import effect_size_label

_THR_PATH = Path(__file__).parent.parent.parent / "config" / "granger_thresholds.yaml"
_THR: dict = yaml.safe_load(_THR_PATH.read_text(encoding="utf-8"))
_D4_THRESHOLD: int = _THR["d4_insufficient_threshold"]
_P_VERIFIED: float = _THR["p_verified"]
_P_PARTIAL: float  = _THR["p_partial"]


def from_spec(spec) -> MethodResult:
    """
    HypothesisSpec → MethodResult.

    spec은 verify_hypotheses 실행 후 완성된 상태여야 한다.
    assumptions_met 판정 기준:
      1. linear_testable=True (8-gate)
      2. n_obs >= D4 임계 (데이터 충분)
      3. granger_p is not None (검정 실행됨)
    '선행성' 칸 추가 조건: theory_grounded=True + controlled=True
    """
    p   = spec.granger_p
    n   = spec.n_obs or 0
    lt  = getattr(spec, "linear_testable", True)
    tg  = spec.theory_grounded
    ctl = spec.controlled

    # ── 가정 자가검증 ──────────────────────────────────────────────────────────
    data_ok    = n >= _D4_THRESHOLD
    tested_ok  = p is not None
    assumptions_met = lt and data_ok and tested_ok

    caveat_parts: list[str] = []
    if not lt:
        caveat_parts.append("선형검정 부적합(8-gate)")
    if not data_ok:
        caveat_parts.append(f"데이터 부족(n={n}<{_D4_THRESHOLD})")
    if not tested_ok:
        caveat_parts.append("Granger 미실행")
    assumption_caveat = " · ".join(caveat_parts) if caveat_parts else ""

    # ── 도달 가능 칸 ──────────────────────────────────────────────────────────
    if not assumptions_met:
        reachable = RUNG_DESCRIPTIVE
        actual    = RUNG_DESCRIPTIVE
    elif p is not None and p < _P_VERIFIED and tg and ctl:
        reachable = RUNG_PRECEDENCE
        actual    = RUNG_PRECEDENCE
    elif p is not None and p < _P_PARTIAL:
        reachable = RUNG_PRECEDENCE   # 가정 충족 시 선행성 가능
        actual    = RUNG_CORRELATIONAL
    elif p is not None and p < _P_VERIFIED:
        reachable = RUNG_PRECEDENCE
        actual    = RUNG_CORRELATIONAL  # 교란 미통제 → 상관 상한
    else:
        reachable = RUNG_PRECEDENCE
        actual    = RUNG_DESCRIPTIVE

    # ── 효과 크기 [②] — F통계량을 효과 크기 대리로 사용 ──────────────────────
    f = spec.f_statistic
    eff_label = effect_size_label(f, small_threshold=2.0, medium_threshold=5.0)

    return MethodResult(
        method="granger",
        signature=getattr(spec, "data_signature", "PAIRED_TIMESERIES"),
        effect_estimate=f,
        effect_size_label=eff_label,
        significance=p,
        ci_low=None,   # Granger는 CI 미산출 → 추후 bootstrap으로 확장
        ci_high=None,
        reachable_rung=reachable,
        actual_rung=actual,
        assumptions_met=assumptions_met,
        assumption_caveat=assumption_caveat,
        robustness={
            "extreme_p": getattr(spec, "extreme_granger_p", None),
            "differenced": spec.differenced,
            "controlled": ctl,
        },
        confidence_within_rung=_confidence_score(p, tg, ctl, n),
        native_stats={
            "granger_p":   p,
            "granger_q":   spec.granger_q,
            "f_statistic": f,
            "best_lag":    spec.best_lag,
            "n_obs":       n,
        },
        exploratory=getattr(spec, "exploratory", False),
    )


def _confidence_score(
    p: float | None,
    theory_grounded: bool,
    controlled: bool,
    n_obs: int,
) -> int:
    """칸 안에서의 신뢰도 0~100."""
    if p is None:
        return 0
    score = 0
    if p < _P_VERIFIED:
        score += 50
    elif p < _P_PARTIAL:
        score += 25
    if theory_grounded:
        score += 25
    if controlled:
        score += 15
    if n_obs >= _D4_THRESHOLD * 2:  # 80개+ → 통계력 충분
        score += 10
    return min(score, 100)
