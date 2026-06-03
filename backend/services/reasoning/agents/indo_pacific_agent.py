"""
services/reasoning/agents/indo_pacific_agent.py

인도-태평양 군사 대치 에이전트 — 동맹이론·A2/AD·제1열도선 기반.
동맹 결집도, A2/AD 영향권, 제1열도선 접촉점을 분석한다.

이론적 근거: Snyder "Alliance Politics" (1997) — 연루·방기 딜레마
            Walt "Origins of Alliances" (1987) — 위협 균형
전략적 함의: 동맹 내 부담 분담과 연루 위험의 동시 관리
"""
from __future__ import annotations

import logging

from .base_agent import SectorAgent

logger = logging.getLogger(__name__)

# 제1열도선 접촉 지역 코드 (오키나와~필리핀~남중국해)
_FIRST_ISLAND_CHAIN = {
    "taiwan_strait", "south_china_sea", "korean_peninsula", "east_china_sea"
}

# A2/AD 주요 접근거부 지역
_A2AD_ZONES: dict[str, str] = {
    "taiwan_strait":  "중국 DF-21D/DF-26 대함 탄도미사일 사거리 내",
    "south_china_sea": "중국 인공섬 HQ-9 SAM + YJ-12 대함미사일 배치",
    "korean_peninsula": "북한 SA-5/SA-20 + KN-25 방사포 A2 레이어",
    "east_china_sea":  "중국 IRBM + 해·공군 원거리 타격 능력 확장",
}

# 인도-태평양 핵심 동맹 페어 (actor 쌍 → 동맹명)
_ALLIANCE_PAIRS: dict[frozenset, str] = {
    frozenset({"USA", "JPN"}): "미일 안보조약 (Art.5 — 상호방위)",
    frozenset({"USA", "KOR"}): "한미 상호방위조약 (전략적 유연성)",
    frozenset({"USA", "AUS"}): "ANZUS + AUKUS (핵잠 이전)",
    frozenset({"USA", "PHL"}): "미필 상호방위조약 (VFA 재활성화)",
    frozenset({"USA", "TWN"}): "대만관계법 (비공식 안보 보장)",
    frozenset({"JPN", "AUS"}): "JAUKUS 확대 논의",
    frozenset({"CHN", "PRK"}): "중조우호협력상호원조조약 (Art.2 — 자동개입?)",
}

# 행위자 → 역할
_ACTOR_ROLE: dict[str, str] = {
    "CHN": "현상 도전자 — 反A2/AD 역량 구축, ADIZ 확장",
    "USA": "현상 유지자 — FONOP, 동맹 확장억제",
    "TWN": "핵심 분쟁 대상 — 비대칭 방어(고슴도치) 전략",
    "PRK": "비핵화 협상 레버리지 행사자",
    "JPN": "능동적 방위 전환 — 반격 능력 보유 결정",
    "KOR": "전략적 자율성 추구 — 핵잠 획득 논의",
    "IND": "인도태평양 전략 관여·비동맹 균형",
    "AUS": "AUKUS 핵잠 획득 — 중거리 미사일 배치 논의",
}


class IndoPacificAgent(SectorAgent):
    sector = "indo_pacific"

    def is_relevant(self, stage_results: dict) -> bool:
        if super().is_relevant(stage_results):
            return True
        s1 = stage_results.get("stages", {}).get("1_facts", {})
        return s1.get("region_code", "") in _FIRST_ISLAND_CHAIN

    def analyze(self, event: dict, stage_results: dict) -> dict:
        s1     = stage_results.get("stages", {}).get("1_facts", {})
        s8     = stage_results.get("stages", {}).get("8_alliance", {})
        region = s1.get("region_code", "")
        actors = [a for a in s1.get("actors", []) if a]

        insights:     list[str] = []
        evidence:     list[dict] = []
        theory_hooks: list[str] = []
        risk = "low"

        # ── 1. 제1열도선 접촉 여부 ────────────────────────────────────────
        if region in _FIRST_ISLAND_CHAIN:
            insights.append(
                f"제1열도선 접촉 지역 ({region}) — "
                "중국 A2/AD 전략과 미국 FONOP의 물리적 교차점"
            )
            theory_hooks.append("제1열도선 전략 — 미국의 서태평양 투사 제한 vs. 중국의 접근거부")
            evidence.append({"type": "first_island_chain", "region": region})
            risk = "high"

        # ── 2. A2/AD 영향권 분석 ──────────────────────────────────────────
        if region in _A2AD_ZONES:
            insights.append(f"A2/AD 영향권 — {_A2AD_ZONES[region]}")
            theory_hooks.append("A2/AD vs. AirSea Battle — 접근거부와 합동타격의 비대칭 경쟁")
            evidence.append({"type": "a2ad_zone", "region": region, "detail": _A2AD_ZONES[region]})

        # ── 3. 동맹 페어 분석 ─────────────────────────────────────────────
        actor_set = frozenset(actors)
        for pair, alliance_name in _ALLIANCE_PAIRS.items():
            if pair.issubset(actor_set) or (len(pair & actor_set) >= 1 and "USA" in actor_set):
                insights.append(f"동맹 프레임: {alliance_name}")
                theory_hooks.append(
                    "Snyder 동맹 딜레마 — 연루(entrapment) vs. 방기(abandonment) 사이 균형"
                )
                evidence.append({"type": "alliance", "name": alliance_name})
                risk = "high" if risk != "high" else risk
                break

        # ── 4. 행위자 역할 매핑 ───────────────────────────────────────────
        for a in actors[:3]:
            if a in _ACTOR_ROLE:
                insights.append(f"{a}: {_ACTOR_ROLE[a]}")
                evidence.append({"type": "actor_role", "actor": a})

        # ── 5. Stage 8 Diffusion Score 재활용 ─────────────────────────────
        diff_score = s8.get("diffusion_score")
        if diff_score is not None:
            risk_label = s8.get("alliance_risk_ko", "")
            insights.append(f"동맹 확산 점수 {diff_score}/100 — {risk_label}")
            evidence.append({"type": "diffusion_score", "score": diff_score})

        # ── 6. 관련 브리핑 ────────────────────────────────────────────────
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
