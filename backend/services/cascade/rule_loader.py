"""
rule_loader.py — cascade_rules.yaml을 로드하고 CascadeRule로 검증한다.

코드 수정 없이 YAML에 룰만 추가하면 등록되는 구조(CLAUDE.md 안티패턴: 룰 하드코딩 금지).
파싱/검증 실패는 무시하지 않고 로그로 남긴 뒤 해당 룰만 건너뛴다.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from models.cascade import CascadeRule

logger = logging.getLogger(__name__)

# 이 파일: backend/services/cascade/rule_loader.py → config: 두 단계 위
_RULES_PATH = Path(__file__).parent.parent.parent / "config" / "cascade_rules.yaml"


@lru_cache(maxsize=1)
def load_rules() -> list[CascadeRule]:
    """cascade_rules.yaml의 모든 룰을 검증된 CascadeRule 리스트로 반환한다.

    lru_cache로 1회만 파싱한다(룰 평가마다 디스크 접근 방지).
    개별 룰 검증 실패 시 그 룰만 건너뛰고 경고 로그를 남긴다.
    """
    if not _RULES_PATH.exists():
        logger.warning(f"[cascade] cascade_rules.yaml 없음: {_RULES_PATH}")
        return []

    raw_rules = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or []
    rules: list[CascadeRule] = []
    for raw in raw_rules:
        try:
            rules.append(CascadeRule(**raw))
        except ValidationError as e:
            logger.warning(f"[cascade] 룰 검증 실패 (id={raw.get('id')}): {e}")

    logger.info(f"[cascade] 룰 {len(rules)}개 로드 완료")
    return rules
