"""
services/reasoning/agents/gray_zone_agent.py

회색지대·하이브리드전 에이전트 — Hybrid Warfare · Gray Zone Strategy 기반.
비국가행위자, 프록시 네트워크, 에스컬레이션 단계를 분석한다.

이론적 근거: Hoffman "Conflict in the 21st Century" (2007) — 하이브리드전
            Mazarr "Mastering the Gray Zone" (2015) — 회색지대 전략
전략적 함의: 임계점 이하 강압으로 현상 변경을 추구하는 전략의 탐지·대응
"""
from __future__ import annotations

import logging

from .base_agent import SectorAgent

logger = logging.getLogger(__name__)

# ACLED event_type → 하이브리드전 단계 분류
# 낮을수록 임계점 이하, 높을수록 정규전에 근접
_HYBRID_STAGE: dict[str, int] = {
    "Protests":                    1,
    "Riots":                       2,
    "Strategic developments":      2,
    "Non-violent actions":         2,
    "Violence against civilians":  3,
    "Remote violence":             4,
    "Explosions/Remote violence":  4,
    "Battles":                     5,
}

_HYBRID_STAGE_LABEL: dict[int, str] = {
    1: "정보전·여론조작 (임계점 훨씬 이하)",
    2: "회색지대 — 부인 가능한 강압",
    3: "하이브리드 — 비국가행위자 활용",
    4: "원거리 타격 — 임계점 근접",
    5: "준정규전 — 정규전 경계",
}

# 알려진 프록시 행위자 패턴
_PROXY_PATTERNS: dict[str, dict] = {
    "houthi": {"sponsor": "IRN", "label": "예멘 후티 (이란 프록시)", "sector": "gray_zone"},
    "hezbollah": {"sponsor": "IRN", "label": "헤즈볼라 (이란 레버넌 프록시)"},
    "hamas": {"sponsor": "IRN", "label": "하마스 (이란 가자 프록시)"},
    "wagner": {"sponsor": "RUS", "label": "바그너 (러시아 아프리카 프록시)"},
    "pmc":    {"sponsor": "RUS", "label": "러시아 민간군사기업"},
    "militia": {"sponsor": "IRN", "label": "친이란 민병대 (이라크·시리아)"},
    "separatist": {"sponsor": "RUS", "label": "친러 분리주의 세력"},
}

# 지역별 하이브리드전 취약성
_REGION_HYBRID_RISK: dict[str, str] = {
    "ukraine":         "러시아 하이브리드전 교과서 — 정보전·사이버·프록시 동시 운용",
    "bab_el_mandeb":   "후티 드론·해상 기뢰 — 비대칭 해양 하이브리드",
    "taiwan_strait":   "회색지대 압박 — ADIZ 침범·해경 통제·경제 강압 병행",
    "south_china_sea": "살라미 슬라이싱 — 단계적 도서 점거로 기정사실화",
    "korean_peninsula":"GPS 교란·오물 풍선·해킹 — 임계점 이하 복합 도발",
    "hormuz":          "이란 선박 나포·기뢰·드론 — 호르무즈 하이브리드 압박",
}


class GrayZoneAgent(SectorAgent):
    sector = "gray_zone"

    def is_relevant(self, stage_results: dict) -> bool:
        if super().is_relevant(stage_results):
            return True
        s1 = stage_results.get("stages", {}).get("1_facts", {})
        # 프록시 키워드 또는 회색지대 지역
        text = (s1.get("title", "") + " " + s1.get("description", "")).lower()
        proxy_hit = any(k in text for k in _PROXY_PATTERNS)
        region_hit = s1.get("region_code", "") in _REGION_HYBRID_RISK
        return proxy_hit or region_hit

    def analyze(self, event: dict, stage_results: dict) -> dict:
        s1       = stage_results.get("stages", {}).get("1_facts", {})
        s5       = stage_results.get("stages", {}).get("5_intent", {})
        region   = s1.get("region_code", "")
        ev_type  = s1.get("event_type", "")
        title    = s1.get("title", "").lower()
        desc     = s1.get("description", "").lower()

        insights:     list[str] = []
        evidence:     list[dict] = []
        theory_hooks: list[str] = []
        risk = "low"

        # ── 1. 하이브리드전 단계 분류 ─────────────────────────────────────
        stage_num = _HYBRID_STAGE.get(ev_type, 0)
        if stage_num > 0:
            label = _HYBRID_STAGE_LABEL[stage_num]
            insights.append(f"하이브리드전 단계 {stage_num}/5 — {label}")
            theory_hooks.append("Hoffman 하이브리드전 스펙트럼 — 정규전과 비정규전의 동시 혼합")
            evidence.append({"type": "hybrid_stage", "stage": stage_num, "label": label})
            risk = "high" if stage_num >= 4 else "medium"

        # ── 2. 프록시 행위자 탐지 ────────────────────────────────────────
        for keyword, info in _PROXY_PATTERNS.items():
            if keyword in title or keyword in desc:
                insights.append(f"프록시 탐지: {info['label']} → 후원국 {info['sponsor']}")
                theory_hooks.append(
                    "Mazarr 회색지대 전략 — 부인 가능한 프록시 활용으로 귀속 회피"
                )
                evidence.append({"type": "proxy", "actor": keyword, "sponsor": info["sponsor"]})
                risk = "high"

        # ── 3. 지역별 하이브리드 취약성 ──────────────────────────────────
        if region in _REGION_HYBRID_RISK:
            insights.append(_REGION_HYBRID_RISK[region])
            evidence.append({"type": "hybrid_region", "region": region})

        # ── 4. Stage 5 에스컬레이션 위험 재활용 ──────────────────────────
        esc_risk = s5.get("escalation_risk")
        if esc_risk:
            intent = s5.get("intent_label_ko", "")
            insights.append(f"에스컬레이션 위험 — 의도 분류: {intent}")
            evidence.append({"type": "escalation", "intent": intent})
            risk = "high"

        # ── 5. 관련 브리핑 ────────────────────────────────────────────────
        items = self._library_items(limit=3)
        if items:
            evidence.extend([{"type": "briefing", "theory_id": i["theory_id"]} for i in items])

        if not theory_hooks:
            theory_hooks.append("Gray Zone Strategy — 현상 변경을 위한 임계점 이하 강압의 지속")

        return {
            "sector": self.sector,
            "insights": insights,
            "evidence": evidence,
            "theory_hooks": theory_hooks,
            "risk_level": risk,
        }
