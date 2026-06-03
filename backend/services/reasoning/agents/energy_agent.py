"""
services/reasoning/agents/energy_agent.py

에너지 지정학 에이전트 — 자원무기화 이론 기반.
파이프라인 취약성, 에너지 cascade 룰, 생산국-소비국 비대칭을 분석한다.

이론적 근거: Farrell & Newman "Weaponized Interdependence" (2019)
            Hirschman "National Power and the Structure of Foreign Trade" (1945)
전략적 함의: 에너지 의존도의 비대칭이 정치적 레버리지로 전환되는 메커니즘
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from .base_agent import SectorAgent

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parents[3] / "data"

# 에너지 관련 지역 → 주요 리스크 서사
_ENERGY_REGION_MAP: dict[str, dict] = {
    "hormuz": {
        "narrative": "호르무즈 차단 시 GCC 원유 수출 90% 봉쇄 — 단기 유가 30~60% 급등 가능",
        "countries": ["SAU", "ARE", "IRN", "IRQ"],
        "theory":    "자원무기화: 이란의 호르무즈 카드 = Hirschman 비대칭 의존 실증",
    },
    "ukraine": {
        "narrative": "러시아 PNG·원유 수출 제재 → 유럽 에너지 믹스 강제 전환 (LNG 수입 +60%)",
        "countries": ["RUS", "UKR", "DEU", "POL"],
        "theory":    "에너지 무기화: Gazprom 공급 차단이 NATO 결속 시험",
    },
    "bab_el_mandeb": {
        "narrative": "후티 공격 → 수에즈 운하 LNG 통과 급감 → 아시아 LNG 가격 스파이크",
        "countries": ["YEM", "SAU", "ARE"],
        "theory":    "SLOC × 에너지: 물리적 차단이 에너지 가격 즉각 반영",
    },
    "south_china_sea": {
        "narrative": "남중국해 분쟁 수역 추정 매장량 11Gb 원유 — 영유권 = 자원권 연동",
        "countries": ["CHN", "VNM", "PHL", "MYS"],
        "theory":    "자원 영유권: 에너지 안보가 영토 분쟁의 실질 동인",
    },
}

# actor ISO3 → 에너지 포지션
_ACTOR_ENERGY_ROLE: dict[str, str] = {
    "RUS": "최대 PNG 수출국 — 에너지 무기화 선례",
    "SAU": "OPEC 맹주 — 감산 카드로 지정학 레버리지",
    "IRN": "호르무즈 봉쇄 위협 보유국",
    "CHN": "최대 에너지 수입국 — 에너지 취약성 = 전략 취약성",
    "USA": "LNG 수출 급증으로 유럽 러시아 의존 대체",
    "QAT": "LNG 생산 3위 — 걸프 위기 시 대체 공급원",
}


def _load_pipelines() -> list[dict]:
    try:
        with open(_DATA / "energy_pipelines.geojson", encoding="utf-8") as f:
            return json.load(f).get("features", [])
    except Exception as e:
        logger.warning("[energy] energy_pipelines.geojson 로드 실패: %s", e)
        return []


def _pipeline_actors(actors: list[str]) -> list[dict]:
    """파이프라인 데이터에서 관련 행위자 국가가 포함된 파이프라인 목록."""
    pipelines = _load_pipelines()
    matched = []
    for feat in pipelines:
        p = feat.get("properties", {})
        countries = str(p.get("countries", "") or p.get("country", "")).upper()
        if any(a in countries for a in actors):
            matched.append({
                "name":      p.get("name", "Unknown"),
                "capacity":  p.get("capacity_bcm", p.get("capacity", "N/A")),
                "countries": countries,
            })
    return matched[:3]


class EnergyAgent(SectorAgent):
    sector = "energy"

    def is_relevant(self, stage_results: dict) -> bool:
        if super().is_relevant(stage_results):
            return True
        s1 = stage_results.get("stages", {}).get("1_facts", {})
        return s1.get("region_code", "") in _ENERGY_REGION_MAP

    def analyze(self, event: dict, stage_results: dict) -> dict:
        s1      = stage_results.get("stages", {}).get("1_facts", {})
        s4      = stage_results.get("stages", {}).get("4_macro", {})
        region  = s1.get("region_code", "")
        actors  = [a for a in s1.get("actors", []) if a]

        insights:     list[str] = []
        evidence:     list[dict] = []
        theory_hooks: list[str] = []
        risk = "low"

        # ── 1. 지역별 에너지 리스크 서사 ───────────────────────────────────
        if region in _ENERGY_REGION_MAP:
            ctx = _ENERGY_REGION_MAP[region]
            insights.append(ctx["narrative"])
            theory_hooks.append(ctx["theory"])
            evidence.append({"type": "energy_region", "region": region})
            risk = "high"

        # ── 2. 행위자별 에너지 포지션 ──────────────────────────────────────
        actor_roles = []
        for a in actors:
            role = _ACTOR_ENERGY_ROLE.get(a)
            if role:
                actor_roles.append(f"{a}: {role}")
                evidence.append({"type": "actor_energy_role", "actor": a, "role": role})
        if actor_roles:
            insights.append("에너지 포지션 — " + " | ".join(actor_roles[:2]))
            theory_hooks.append("Weaponized Interdependence — 의존도 비대칭이 강압 수단으로 전환")
            risk = "high" if risk == "high" else "medium"

        # ── 3. 파이프라인 취약성 ───────────────────────────────────────────
        if actors:
            pipes = _pipeline_actors(actors)
            if pipes:
                names = ", ".join(p["name"] for p in pipes)
                insights.append(f"관련 파이프라인: {names} — 이벤트와 공급망 교차점")
                evidence.extend([{"type": "pipeline", **p} for p in pipes])

        # ── 4. 현재 매크로 지표 (Stage 4 결과 재활용) ──────────────────────
        # stage4 indicators는 list[dict] 형식: [{"indicator": "wti", "value": ...}, ...]
        raw_indicators = s4.get("indicators", [])
        indicator_map = {
            i["indicator"]: i for i in (raw_indicators if isinstance(raw_indicators, list) else [])
        }
        wti_data = indicator_map.get("wti")
        if wti_data:
            val = wti_data.get("value", "N/A")
            insights.append(f"현재 WTI ${val}/bbl — 이벤트 지속 시 상방 압력")
            evidence.append({"type": "macro", "indicator": "wti", "value": val})

        # ── 5. 관련 cascade 룰 ─────────────────────────────────────────────
        rules = self._cascade_rules()
        if rules:
            rnames = [r.get("name", r.get("id", "")) for r in rules[:2]]
            theory_hooks.append(f"Cascade 룰 연동: {', '.join(rnames)}")

        # ── 6. 관련 브리핑 ─────────────────────────────────────────────────
        items = self._library_items(limit=3)
        if items:
            evidence.extend([{"type": "briefing", "theory_id": i["theory_id"]} for i in items])

        return {
            "sector": self.sector,
            "insights": insights,
            "evidence": evidence,
            "theory_hooks": theory_hooks,
            "risk_level": risk,
        }
