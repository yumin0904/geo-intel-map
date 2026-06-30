"""
[Phase 10-2] 예측 채점 배치 — 매일 1회 만기 예측을 실측 대조.

resolve_by가 도래한 PENDING 예측을 꺼내 HIT/MISS/UNRESOLVED 라벨.
Token-Zero(LLM 無). 스케줄러(main.py)에서 24시간 주기로 호출.
"""

import logging

from services.prediction_scorer import score_due_predictions

logger = logging.getLogger(__name__)


def run_prediction_scoring_batch() -> None:
    """만기 예측 일괄 채점. 실패해도 스케줄러를 죽이지 않도록 흡수."""
    try:
        s = score_due_predictions()
        logger.info(
            "[10-2 채점배치] 도래=%d → HIT %d · MISS %d · UNRESOLVED %d (적격 적중률=%s)",
            s["due"], s["hit"], s["miss"], s["unresolved"], s["hit_rate_eligible"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[10-2 채점배치] 실패: %s", exc)
