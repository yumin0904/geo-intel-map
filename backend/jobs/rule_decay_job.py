"""
[P5] 룰 부패 감시 배치 — 주 1회 cascade 룰북 반증 감사.

데이터효용위(2026-07-12) P5. collect_standalone 편승(신규 launchd 잡 없음),
기존 산출물이 6일 미만이면 스킵(주 1회 스로틀 — 게이트 ⑥ 저빈도).
산출은 exports/rule_decay_audit.json 부패 플래그뿐 — 룰 자동 재작성 금지.
"""

import logging

from scripts.rule_decay_audit import export, is_fresh

logger = logging.getLogger(__name__)


def run_rule_decay_batch() -> None:
    """주 1회 룰 감사. 실패해도 수집 사이클을 죽이지 않도록 흡수."""
    try:
        if is_fresh():
            logger.info("[P5 룰감사] 산출물 신선(<6일) — 스킵")
            return
        import json
        d = json.loads(export().read_text())
        logger.info("[P5 룰감사] 룰 %d개 · decay_flag %d개: %s",
                    d["rules_audited"], len(d["decay_flagged"]),
                    ", ".join(d["decay_flagged"]) or "없음")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[P5 룰감사] 실패: %s", exc)
