"""
services/reasoning/agents/maritime_agent.py

해양 섹터 에이전트 — Mahan 해양력 이론 기반.
초크포인트 근접성, SLOC 취약성, 해저케이블 위협을 분석한다.

이론적 근거: Alfred Thayer Mahan "The Influence of Sea Power upon History" (1890)
전략적 함의: 초크포인트 통제 = 글로벌 무역·에너지 공급망 지배력
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from .base_agent import SectorAgent

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parents[3] / "data"

# 초크포인트별 통과 물동량 가중치 (Mahan 중요도 근사)
_CHOKEPOINT_WEIGHT: dict[str, float] = {
    "hormuz":         1.8,  # 글로벌 원유 20%
    "malacca":        1.6,  # 글로벌 무역 30%
    "bab_el_mandeb":  1.4,  # 수에즈 접근 경로
    "suez":           1.3,
    "taiwan_strait":  1.5,  # 반도체 공급망 요충
    "lombok":         1.1,
    "sunda":          1.0,
}

_RADIUS_KM = 500  # 이벤트 반경: 이 안에 초크포인트가 있으면 영향권


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 간 거리(km) 계산."""
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _load_chokepoints() -> list[dict]:
    try:
        with open(_DATA / "chokepoints.geojson", encoding="utf-8") as f:
            gj = json.load(f)
        return gj.get("features", [])
    except Exception as e:
        logger.warning("[maritime] chokepoints.geojson 로드 실패: %s", e)
        return []


class MaritimeAgent(SectorAgent):
    sector = "maritime"

    def is_relevant(self, stage_results: dict) -> bool:
        if super().is_relevant(stage_results):
            return True
        # 지역 기반 추가 감지: 해양 핵심 지역이면 관련
        s1 = stage_results.get("stages", {}).get("1_facts", {})
        region = s1.get("region_code", "")
        return region in {"hormuz", "malacca", "bab_el_mandeb", "taiwan_strait",
                          "south_china_sea", "suez", "red_sea"}

    def analyze(self, event: dict, stage_results: dict) -> dict:
        props  = event.get("properties", event)
        s1     = stage_results.get("stages", {}).get("1_facts", {})
        coords = s1.get("coordinates")  # [lon, lat] 또는 None
        region = s1.get("region_code", "")

        insights:     list[str] = []
        evidence:     list[dict] = []
        theory_hooks: list[str] = []

        # ── 1. 초크포인트 근접성 분석 ──────────────────────────────────────
        nearby_chokes: list[dict] = []
        if coords:
            lon, lat = coords[0], coords[1]
            for feat in _load_chokepoints():
                geom = feat.get("geometry", {})
                p    = feat.get("properties", {})
                if geom.get("type") == "Point":
                    c_lon, c_lat = geom["coordinates"]
                elif geom.get("type") == "Polygon":
                    pts = geom["coordinates"][0]
                    c_lon = sum(p[0] for p in pts) / len(pts)
                    c_lat = sum(p[1] for p in pts) / len(pts)
                else:
                    continue

                dist = _haversine(lat, lon, c_lat, c_lon)
                if dist <= _RADIUS_KM:
                    name = p.get("name", p.get("id", "unknown"))
                    weight = _CHOKEPOINT_WEIGHT.get(name.lower().replace(" ", "_"), 1.0)
                    nearby_chokes.append({
                        "name": name,
                        "dist_km": round(dist),
                        "importance_weight": weight,
                    })
                    evidence.append({"type": "chokepoint", "name": name, "dist_km": round(dist)})

        if nearby_chokes:
            names = ", ".join(c["name"] for c in nearby_chokes[:2])
            max_w = max(c["importance_weight"] for c in nearby_chokes)
            insights.append(
                f"초크포인트 {names} 반경 {_RADIUS_KM}km 내 이벤트 — "
                f"Mahan 중요도 {max_w:.1f}배 가중 적용"
            )
            theory_hooks.append("Mahan 해양력 이론 — 초크포인트 통제가 해상 지배력을 결정")

        # ── 2. 지역별 SLOC 취약성 서사 ──────────────────────────────────────
        _SLOC_CONTEXT: dict[str, str] = {
            "hormuz":        "글로벌 원유 20% 통과 — 차단 시 유가 즉각 급등",
            "malacca":       "글로벌 무역 30% 통과 — 중국 에너지 수입 80% 경유",
            "bab_el_mandeb": "수에즈 우회 시 아프리카 남단 2주 추가 — 물류비 40% 상승",
            "taiwan_strait": "반도체 공급망의 병목 — TSMC 생산 중단 시 글로벌 반도체 부족",
            "south_china_sea": "연간 3.4조 달러 무역 경유 — 영유권 분쟁과 SLOC 불안정 연동",
        }
        if region in _SLOC_CONTEXT:
            insights.append(_SLOC_CONTEXT[region])
            evidence.append({"type": "sloc_context", "region": region})

        # ── 3. 관련 라이브러리 브리핑 (maritime) ───────────────────────────
        items = self._library_items(limit=3)
        if items:
            titles = [i["title"] for i in items[:2]]
            insights.append(f"관련 브리핑: {' / '.join(titles)}")
            evidence.extend([{"type": "briefing", "theory_id": i["theory_id"]} for i in items])
            theory_hooks.append("Sea Power × 현대 공급망 — Jensen 4부작 실증")

        risk = "high" if nearby_chokes or region in _SLOC_CONTEXT else "low"
        return {
            "sector": self.sector,
            "insights": insights,
            "evidence": evidence,
            "theory_hooks": theory_hooks,
            "risk_level": risk,
        }
