"""
services/reasoning/agents/cyber_agent.py

사이버·인지전 에이전트 — APT 귀속 · 인지전 이론 기반.
사이버 공격 패턴, APT 귀속, 인지전 지표를 분석한다.

이론적 근거: Libicki "Cyberdeterrence and Cyberwar" (2009)
            Rid "Active Measures" (2020) — 인지전·허위정보
전략적 함의: 사이버 공간이 회색지대전의 선행 작전 공간으로 기능하는 메커니즘
"""
from __future__ import annotations

import logging
import re

from .base_agent import SectorAgent

logger = logging.getLogger(__name__)

# 알려진 APT 그룹 → 귀속 국가
_APT_GROUPS: dict[str, str] = {
    "apt28":    "RUS",  "fancy bear":    "RUS",  "sandworm":    "RUS",
    "apt29":    "RUS",  "cozy bear":     "RUS",  "killnet":     "RUS",
    "apt10":    "CHN",  "apt41":         "CHN",  "volt typhoon": "CHN",
    "salt typhoon": "CHN", "apt40":      "CHN",  "lazarus":     "PRK",
    "kimsuky":  "PRK",  "apt38":         "PRK",  "charming kitten": "IRN",
    "apt33":    "IRN",  "apt34":         "IRN",  "equation group": "USA",
}

# 사이버 공격 유형 → 전략적 의미
_CYBER_OP_TYPE: dict[str, str] = {
    "ransomware":  "경제적 강압·수익 창출 — 국가 배후 가능성",
    "ddos":        "서비스 교란 — 시위·심리전 효과",
    "espionage":   "전략 정보 수집 — 장기 침투 작전",
    "wiper":       "인프라 파괴 — 전쟁 전 마비 공격",
    "supply chain": "신뢰 체계 훼손 — SolarWinds형 광범위 침투",
    "disinformation": "인지전·여론 조작 — 선거·사회 분열",
    "ics":         "산업제어시스템 공격 — 물리 인프라 타격",
}

# 사이버 키워드
_CYBER_KEYWORDS = [
    "cyber", "hack", "malware", "ransomware", "ddos", "phishing",
    "apt", "intrusion", "breach", "disinformation", "propaganda",
    "internet shutdown", "outage", "wiper", "espionage", "spyware",
    "사이버", "해킹", "랜섬웨어", "허위정보", "인터넷 차단",
]

# 사이버 취약 지역 컨텍스트
_REGION_CYBER_CONTEXT: dict[str, str] = {
    "ukraine":          "러시아 Sandworm — Industroyer2, Wiper 연속 공격 (교과서 사이버전)",
    "taiwan_strait":    "Volt Typhoon 사전 침투 — 유사시 인프라 마비 준비",
    "korean_peninsula": "Lazarus/Kimsuky — 금융·방산 탈취, 핵 협상 정보 수집",
    "hormuz":           "이란 APT33/34 — 걸프 에너지 인프라 ICS 공격 이력",
    "eastern_europe":   "러시아 인지전 — 선거 개입·NATO 여론 분열 작전",
}


class CyberAgent(SectorAgent):
    sector = "cyber"

    def is_relevant(self, stage_results: dict) -> bool:
        if super().is_relevant(stage_results):
            return True
        s1 = stage_results.get("stages", {}).get("1_facts", {})
        text = (s1.get("title", "") + " " + s1.get("description", "")).lower()
        return any(kw in text for kw in _CYBER_KEYWORDS)

    def analyze(self, event: dict, stage_results: dict) -> dict:
        s1     = stage_results.get("stages", {}).get("1_facts", {})
        actors = [a for a in s1.get("actors", []) if a]
        region = s1.get("region_code", "")
        text   = (s1.get("title", "") + " " + s1.get("description", "")).lower()

        insights:     list[str] = []
        evidence:     list[dict] = []
        theory_hooks: list[str] = []
        risk = "low"

        # ── 1. APT 그룹 탐지 ──────────────────────────────────────────────
        for apt, sponsor in _APT_GROUPS.items():
            if apt in text:
                if sponsor in actors or not actors:
                    insights.append(f"APT 탐지: {apt.upper()} → 귀속 국가 {sponsor}")
                    theory_hooks.append(
                        "Attribution Problem — 사이버 귀속의 불확실성이 억지 실패를 유발"
                    )
                    evidence.append({"type": "apt", "group": apt, "sponsor": sponsor})
                    risk = "high"

        # ── 2. 사이버 공격 유형 분류 ──────────────────────────────────────
        for op_type, meaning in _CYBER_OP_TYPE.items():
            if op_type in text:
                insights.append(f"공격 유형: {op_type} — {meaning}")
                evidence.append({"type": "cyber_op", "op_type": op_type})
                risk = "high" if op_type in ("wiper", "ics", "supply chain") else "medium"

        # ── 3. 지역별 사이버 컨텍스트 ────────────────────────────────────
        if region in _REGION_CYBER_CONTEXT:
            insights.append(_REGION_CYBER_CONTEXT[region])
            evidence.append({"type": "cyber_region", "region": region})
            theory_hooks.append(
                "Libicki 사이버 억지 — 비대칭 역량이 핵 억지와 달리 에스컬레이션 통제 취약"
            )

        # ── 4. 행위자 사이버 역량 매핑 ───────────────────────────────────
        _ACTOR_CYBER: dict[str, str] = {
            "RUS": "사이버 공격·인지전 통합 (GRU/SVR 이중 운용)",
            "CHN": "장기 침투·기술 절취 중심 (MSS/PLA Unit 61398)",
            "PRK": "외화 탈취 + 핵·방산 정보 수집",
            "IRN": "ICS 파괴 + 지역 대리 사이버 작전",
            "ISR": "Pegasus급 공세 사이버 + 첩보 통합",
            "USA": "Equation Group·Stuxnet — 물리 파괴 사이버 작전 선례",
        }
        for a in actors:
            if a in _ACTOR_CYBER:
                insights.append(f"{a} 사이버 역량: {_ACTOR_CYBER[a]}")
                evidence.append({"type": "actor_cyber", "actor": a})

        # ── 5. 관련 브리핑 ────────────────────────────────────────────────
        items = self._library_items(limit=3)
        if items:
            titles = [i["title"] for i in items[:2]]
            insights.append(f"관련 브리핑: {' / '.join(titles)}")
            evidence.extend([{"type": "briefing", "theory_id": i["theory_id"]} for i in items])

        if not theory_hooks:
            theory_hooks.append(
                "Cognitive Warfare — 정보 환경 조작을 통한 상대 의사결정 체계 교란"
            )

        return {
            "sector": self.sector,
            "insights": insights,
            "evidence": evidence,
            "theory_hooks": theory_hooks,
            "risk_level": risk,
        }
