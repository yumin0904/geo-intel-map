"""
services/methods/grader.py  (9-0)

일반화된 grader — _classify_inference_grade(Granger 전용)를 대체.

원칙:
  1. assumptions_met=True인 방법 중 reachable_rung이 가장 강한 것을 헤드라인으로.
  2. 삼각측량: 복수 방법이면 수렴/발산 판정 + 전부 보고.
  3. 수렴해도 칸은 승격하지 않는다 (수렴=강건성, 칸=식별전략 — 직교).
  4. assumptions_met=False는 칸 자격 박탈 (method-type laundering 차단).
"""
from __future__ import annotations

import logging

from services.methods.base import (
    MethodResult,
    TriangulationResult,
    RUNG_ORDER,
    RUNG_DESCRIPTIVE,
)

logger = logging.getLogger(__name__)


def grade(results: list[MethodResult]) -> TriangulationResult:
    """
    방법집합 결과 목록 → 삼각측량 종합 판정.

    assumptions_met=True 결과만 등급 자격 부여.
    헤드라인 칸 = 자격 있는 방법 중 reachable_rung이 가장 강한 것.
    """
    if not results:
        return TriangulationResult(
            headline_rung=RUNG_DESCRIPTIVE,
            headline_method="none",
            convergence=None,
            convergence_note="방법 결과 없음",
        )

    # 1. 가정 충족 결과만 자격 부여 (laundering 차단)
    eligible = [r for r in results if r.assumptions_met]
    if not eligible:
        return TriangulationResult(
            headline_rung=RUNG_DESCRIPTIVE,
            headline_method="none",
            convergence=None,
            convergence_note="가정 미충족 — 모든 방법 칸 자격 박탈",
            all_results=results,
        )

    # 2. 헤드라인 = 가장 강한 reachable_rung
    best = max(eligible, key=lambda r: RUNG_ORDER.get(r.reachable_rung, 0))
    headline_rung   = best.actual_rung    # 실제 달성 칸 (가정 충족 후 보정)
    headline_method = best.method

    # 3. 삼각측량 (복수 방법인 경우)
    convergence: bool | None = None
    convergence_note = ""
    if len(eligible) >= 2:
        rungs = {r.actual_rung for r in eligible}
        if len(rungs) == 1:
            convergence = True
            convergence_note = (
                f"수렴 — {len(eligible)}개 방법 모두 '{next(iter(rungs))}' 칸 일치. "
                "강건성↑ (단, 수렴해도 칸 승격 없음 — 각 방법의 식별전략 강도 그대로)."
            )
        else:
            convergence = False
            rung_summary = " / ".join(f"{r.method}:{r.actual_rung}" for r in eligible)
            convergence_note = (
                f"발산 — 방법별 칸 엇갈림({rung_summary}). "
                "발산 자체가 발견: 단기·국소 효과는 있으나 전역·지속 선행성은 없을 수 있음."
            )
        logger.info("[grader] 삼각측량 convergence=%s note=%s", convergence, convergence_note[:60])

    return TriangulationResult(
        headline_rung=headline_rung,
        headline_method=headline_method,
        convergence=convergence,
        convergence_note=convergence_note,
        all_results=results,
        fdr_applied=False,  # FDR은 verifier에서 적용 후 결과 갱신
    )


def effect_size_label(
    estimate: float | None,
    *,
    small_threshold: float = 0.1,
    medium_threshold: float = 0.3,
) -> str:
    """
    [②] 효과 크기를 실질 임계와 비교해 자연어 라벨 반환.
    통계 유의성과 분리 — p<0.05여도 효과가 미미하면 '무시할 수준'으로 표기.
    """
    if estimate is None:
        return "측정불가"
    abs_e = abs(estimate)
    if abs_e < small_threshold:
        return "무시할 수준"
    if abs_e < medium_threshold:
        return "작음"
    if abs_e < 0.5:
        return "중간"
    return "큼"
