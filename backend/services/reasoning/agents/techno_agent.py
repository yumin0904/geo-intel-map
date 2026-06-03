"""
services/reasoning/agents/techno_agent.py

기술 패권 에이전트 — Techno-nationalism & Digital Iron Curtain 이론 기반.
반도체 공급망, 5G 인프라, AI 패권, 희토류 통제를 분석한다.

이론적 근거: Drezner "The Toothless Tiger? China and the Liberal International Order" (2019)
            Farrell & Newman "Weaponized Interdependence" — 네트워크 지배 노드 통제
전략적 함의: 기술 스택의 비대칭이 Digital Iron Curtain으로 구체화되는 과정
"""
from __future__ import annotations

import logging
import re

from .base_agent import SectorAgent

logger = logging.getLogger(__name__)

# 핵심 기술 공급망 노드 (행위자 → 통제 기술)
_TECH_ACTOR_MAP: dict[str, dict] = {
    "TWN": {
        "asset":   "TSMC — 글로벌 첨단 파운드리 90%+",
        "risk":    "대만 유사시 반도체 공급 전면 차단",
        "theory":  "Techno-nationalism — 단일 지리 의존의 구조적 취약성",
    },
    "CHN": {
        "asset":   "희토류 60% 생산 + 가공 90%, Huawei 5G 장비",
        "risk":    "수출 제한 시 서방 방산·전자 공급망 동시 타격",
        "theory":  "Weaponized Interdependence — 네트워크 허브 위치 활용 강압",
    },
    "USA": {
        "asset":   "ARM ISA + EDA 도구 + CUDA 생태계 지배",
        "risk":    "반도체 수출통제(EAR)로 중국 AI 산업 억제 시도",
        "theory":  "CHIPS Act — 국가안보 동기 산업정책의 제도화",
    },
    "KOR": {
        "asset":   "메모리 반도체(HBM) 70% 공급 (Samsung·SK)",
        "risk":    "HBM 수출통제 → AI 가속기(H100 등) 공급 병목",
        "theory":  "동맹 내 기술 레버리지 — 소부장 의존도의 정치화",
    },
    "NLD": {
        "asset":   "ASML EUV 리소그래피 — 첨단 반도체 유일 장비",
        "risk":    "ASML 수출통제 = 중국 7nm 이하 생산 사실상 봉쇄",
        "theory":  "Chokepoint Tech — 단일 공급자 통제의 지정학 무기화",
    },
    "RUS": {
        "asset":   "사이버 역량 + 에너지-기술 패키지 딜",
        "risk":    "기술 자립(러시아화) 실패 → 서방 반도체 의존 지속",
        "theory":  "Digital Autarky — 기술 고립화의 경제·군사 비용",
    },
}

# 기술 키워드 → 섹터 관련성 신호
_TECH_KEYWORDS = [
    "semiconductor", "chip", "5g", "huawei", "tsmc", "asml",
    "rare earth", "희토류", "반도체", "인공지능", "ai", "drone",
    "satellite", "cyber", "software", "algorithm", "eda", "lithography",
    "gallium", "germanium", "indium", "quantum",
]


class TechnoAgent(SectorAgent):
    sector = "techno"

    def is_relevant(self, stage_results: dict) -> bool:
        if super().is_relevant(stage_results):
            return True
        # 제목/설명에 기술 키워드 포함 시 관련
        s1 = stage_results.get("stages", {}).get("1_facts", {})
        text = (s1.get("title", "") + " " + s1.get("description", "")).lower()
        return any(kw in text for kw in _TECH_KEYWORDS)

    def analyze(self, event: dict, stage_results: dict) -> dict:
        s1     = stage_results.get("stages", {}).get("1_facts", {})
        actors = [a for a in s1.get("actors", []) if a]

        insights:     list[str] = []
        evidence:     list[dict] = []
        theory_hooks: list[str] = []
        risk = "low"

        # ── 1. 행위자별 기술 자산·리스크 ──────────────────────────────────
        tech_actors = []
        for a in actors:
            if a in _TECH_ACTOR_MAP:
                info = _TECH_ACTOR_MAP[a]
                tech_actors.append(info)
                insights.append(f"{a} — {info['asset']}")
                evidence.append({"type": "tech_asset", "actor": a, "asset": info["asset"]})
                theory_hooks.append(info["theory"])
                risk = "high"

        # ── 2. 공급망 교차 위험 (복수 행위자) ─────────────────────────────
        if len(tech_actors) >= 2:
            pair_actors = [a for a in actors if a in _TECH_ACTOR_MAP][:2]
            insights.append(
                f"공급망 교차: {pair_actors[0]}·{pair_actors[1]} 동시 개입 "
                "→ 기술 공급망 이중 압박"
            )
            theory_hooks.append(
                "Digital Iron Curtain — 기술 진영화가 공급망 분리(Decoupling)로 가속"
            )

        # ── 3. 텍스트 기반 기술 키워드 심층 매칭 ──────────────────────────
        s1_text = (s1.get("title", "") + " " + s1.get("description", "")).lower()
        matched_kws = [kw for kw in _TECH_KEYWORDS if kw in s1_text]
        if matched_kws and not insights:
            insights.append(f"기술 키워드 감지: {', '.join(matched_kws[:4])} — techno 섹터 연관")
            risk = "medium"

        # ── 4. 관련 브리핑 (techno) ───────────────────────────────────────
        items = self._library_items(limit=3)
        if items:
            titles = [i["title"] for i in items[:2]]
            insights.append(f"관련 브리핑: {' / '.join(titles)}")
            evidence.extend([{"type": "briefing", "theory_id": i["theory_id"]} for i in items])

        return {
            "sector": self.sector,
            "insights": insights,
            "evidence": evidence,
            "theory_hooks": theory_hooks,
            "risk_level": risk,
        }
