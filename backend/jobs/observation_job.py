"""
[P1] 관찰 원장 배치 — 일 1회 report-only 변화 스캔.

데이터효용위(2026-07-12) P1. Token-Zero(LLM 無). 기존 launchd 수집 잡
(collect_standalone, 매일 09/21시)에 편승하되 서비스 자체의 observation_runs
날짜 마커가 일 1회로 스로틀한다(게이트 ⑥ — 신규 launchd 잡 증설 금지).
산출은 observation_ledger 행뿐 — 어떤 게이트·등급·라우터도 참조하지 않는다.
"""

import logging

from services.observation_ledger import run_scan

logger = logging.getLogger(__name__)


def run_observation_batch() -> None:
    """전 가족 스캔. 실패해도 수집 사이클을 죽이지 않도록 흡수."""
    try:
        s = run_scan()
        if s.get("skipped"):
            logger.info("[P1 관찰원장] 오늘 기실행 — 스킵")
            return
        logger.info(
            "[P1 관찰원장] 가족=%d 후보=%d BH통과=%d (신규 %d·확인 %d)",
            s["families"], s["candidates"], s["passed"],
            s["inserted"], s["updated"],
        )
        for line in s.get("observations", []):
            logger.info("[P1 관찰원장]   %s", line)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[P1 관찰원장] 실패: %s", exc)
