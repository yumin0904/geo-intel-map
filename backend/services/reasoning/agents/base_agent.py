"""
services/reasoning/agents/base_agent.py

섹터 에이전트 공통 인터페이스.
모든 에이전트는 SectorAgent를 상속해 analyze()를 구현한다.
"""
from __future__ import annotations

import logging
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml

logger = logging.getLogger(__name__)

_CONFIG   = Path(__file__).resolve().parents[3] / "config"
_INTEL_DB = Path(__file__).resolve().parents[3] / "db" / "intel.db"
_LIB_DB   = Path(__file__).resolve().parents[3] / "db" / "library.db"


class SectorAgent(ABC):
    """섹터별 심화 분석 에이전트 기반 클래스."""

    sector: str  # 하위 클래스에서 정의

    # ── 공통 유틸 ──────────────────────────────────────────────────────────

    @contextmanager
    def _intel_db(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(_INTEL_DB)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def _lib_db(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(_LIB_DB)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    def _load_yaml(self, name: str) -> dict | list:
        path = _CONFIG / name
        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("[%s] YAML 로드 실패 %s: %s", self.sector, name, e)
            return {}

    def _library_items(self, limit: int = 5) -> list[dict]:
        """library.db에서 이 섹터의 브리핑·이론 상위 N개 조회."""
        try:
            with self._lib_db() as con:
                rows = con.execute(
                    """
                    SELECT theory_id, title, summary, asset_type, source_org, geopol_region
                    FROM theories
                    WHERE sector_tag = ?
                    ORDER BY published_date DESC NULLS LAST
                    LIMIT ?
                    """,
                    (self.sector, limit),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("[%s] library 조회 실패: %s", self.sector, e)
            return []

    def _cascade_rules(self) -> list[dict]:
        """cascade_rules.yaml에서 이 섹터 관련 룰 추출."""
        rules = self._load_yaml("cascade_rules.yaml")
        if not isinstance(rules, list):
            return []
        return [
            r for r in rules
            if self.sector in r.get("trigger", {}).get("source_type", "")
            or self.sector in str(r.get("theory", {}).get("framework", "")).lower()
            or self.sector in str(r.get("name", "")).lower()
        ]

    # ── 관련성 판정 ────────────────────────────────────────────────────────

    def is_relevant(self, stage_results: dict) -> bool:
        """이벤트가 이 섹터와 관련 있는지 판정."""
        s2 = stage_results.get("stages", {}).get("2_sector", {})
        all_sectors = (
            s2.get("inferred_sectors", [])
            + s2.get("explicit_tags", [])
        )
        return self.sector in all_sectors

    # ── 심화 분석 (하위 클래스 구현) ───────────────────────────────────────

    @abstractmethod
    def analyze(self, event: dict, stage_results: dict) -> dict:
        """
        기존 8단계 결과 + 섹터 전문 데이터 → 심화 인사이트.

        반환 형식:
        {
            "sector": str,
            "insights": list[str],       # 핵심 인사이트 (3개 이하)
            "evidence": list[dict],      # 근거 데이터
            "theory_hooks": list[str],   # 연결 이론
            "risk_level": "low"|"medium"|"high",
        }
        """
        ...
