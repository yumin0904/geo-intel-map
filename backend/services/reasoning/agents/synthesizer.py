"""
services/reasoning/agents/synthesizer.py

종합 에이전트 — 섹터별 결과를 통합해 교차 인사이트를 도출한다.

교차 분석 원칙:
- 2개 이상 섹터가 동시 활성화 → 섹터 교차 인사이트 생성
- 고위험(high) 섹터 수로 종합 위협 등급 산정
- IA 탭의 Gemini 합성 컨텍스트로 사용되는 구조화 보고서 반환
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 섹터 쌍 → 교차 인사이트 템플릿
# 학문적 이론과 현실 사례를 연결
_CROSS_SECTOR_INSIGHTS: dict[frozenset, str] = {
    frozenset({"energy", "maritime"}):
        "에너지·해양 동시 활성 — SLOC × 자원무기화 복합 위기 (호르무즈·말라카 차단 시나리오). "
        "Mahan + Hirschman 이중 렌즈: 해상 통로 지배가 에너지 공급망 통제와 동일시됨.",

    frozenset({"techno", "indo_pacific"}):
        "기술·인도태평양 동시 활성 — 반도체 공급망 단절이 군사 대치와 연동. "
        "Weaponized Interdependence: TSMC 지리 집중이 대만 분쟁 억지력이자 취약점으로 기능.",

    frozenset({"gray_zone", "cyber"}):
        "회색지대·사이버 동시 활성 — 하이브리드전의 사이버 선행 작전 패턴. "
        "Hoffman + Libicki: 물리 공격 전 사이버로 지휘통제·인프라 마비 후 군사행동 가속.",

    frozenset({"energy", "gray_zone"}):
        "에너지·회색지대 동시 활성 — 자원무기화의 비군사적 강압 구현. "
        "Farrell & Newman: 파이프라인 차단·공급 조작이 임계점 이하 강압 수단으로 활용.",

    frozenset({"maritime", "indo_pacific"}):
        "해양·인도태평양 동시 활성 — 제1열도선 SLOC 통제 경쟁. "
        "Mahan × A2/AD: 초크포인트 제압이 반접근 전략의 물리적 구현.",

    frozenset({"techno", "cyber"}):
        "기술·사이버 동시 활성 — 공급망 침투와 사이버 첩보 연동. "
        "Salt Typhoon 사례: 통신 인프라 침투 = 기술 패권 경쟁의 작전 공간.",

    frozenset({"gray_zone", "indo_pacific"}):
        "회색지대·인도태평양 동시 활성 — 살라미 슬라이싱의 지역화. "
        "Mazarr: 남중국해 인공섬·ADIZ 침범이 기정사실화(fait accompli) 전략의 교과서.",

    frozenset({"energy", "techno"}):
        "에너지·기술 동시 활성 — 경제전의 이중 압박 구조. "
        "Jensen 4부작 실증: 희토류(기술) × LNG(에너지) 동시 통제가 서방 전략 취약성 최대화.",

    frozenset({"cyber", "indo_pacific"}):
        "사이버·인도태평양 동시 활성 — Volt Typhoon형 사전 침투 패턴. "
        "유사시 대비 인프라 마비 준비: 사이버가 A2/AD의 비물리 레이어로 통합.",

    frozenset({"maritime", "gray_zone"}):
        "해양·회색지대 동시 활성 — 해상 하이브리드전. "
        "후티 드론·기뢰 전술: 비국가행위자가 핵심 SLOC를 교란하는 비대칭 해양 전략.",
}

# 위험 등급 → 종합 평가
_RISK_MATRIX: dict[int, str] = {
    0: "모니터링 수준 — 직접 위협 낮음",
    1: "주의 — 단일 섹터 경보",
    2: "경계 — 복합 섹터 활성화",
    3: "위기 — 다중 섹터 고위험 교차",
}


def synthesize(
    stage_results: dict,
    agent_results: list[dict],
) -> dict:
    """
    섹터 에이전트 결과를 통합해 종합 보고서 반환.

    반환값은 IA 탭의 Gemini SSE 컨텍스트로 직접 주입된다.
    """
    if not agent_results:
        return {
            "active_sectors": [],
            "cross_insights": [],
            "all_theory_hooks": [],
            "all_evidence": [],
            "risk_grade": 0,
            "risk_label": _RISK_MATRIX[0],
            "summary_context": "",
        }

    active_sectors = [r["sector"] for r in agent_results]
    high_risk_count = sum(1 for r in agent_results if r.get("risk_level") == "high")

    # ── 교차 인사이트 도출 ────────────────────────────────────────────────
    cross_insights: list[str] = []
    sector_set = set(active_sectors)
    for pair, insight in _CROSS_SECTOR_INSIGHTS.items():
        if pair.issubset(sector_set):
            cross_insights.append(insight)

    # ── 전체 이론 훅·증거 통합 ───────────────────────────────────────────
    all_theory_hooks: list[str] = []
    all_evidence:     list[dict] = []
    all_insights:     list[str]  = []
    seen_hooks = set()

    for r in agent_results:
        all_insights.extend(r.get("insights", []))
        all_evidence.extend(r.get("evidence", []))
        for hook in r.get("theory_hooks", []):
            if hook not in seen_hooks:
                all_theory_hooks.append(hook)
                seen_hooks.add(hook)

    # ── 종합 위험 등급 ────────────────────────────────────────────────────
    risk_grade = min(high_risk_count, 3)
    risk_label = _RISK_MATRIX[risk_grade]

    # ── Gemini 컨텍스트 조립 (구조화된 한국어 텍스트) ─────────────────────
    # intel_query.py의 LLM 프롬프트에 주입되는 핵심 컨텍스트
    lines = ["### 섹터별 핵심 인사이트"]
    for r in agent_results:
        sector_label = {
            "maritime": "해양·SLOC", "energy": "에너지 지정학",
            "techno": "기술 패권", "indo_pacific": "인도-태평양",
            "gray_zone": "회색지대", "cyber": "사이버·인지전",
        }.get(r["sector"], r["sector"])
        lines.append(f"\n**[{sector_label}]** (위험: {r.get('risk_level','?')})")
        for ins in r.get("insights", [])[:2]:
            lines.append(f"- {ins}")

    if cross_insights:
        lines.append("\n### 교차 섹터 인사이트")
        for ci in cross_insights:
            lines.append(f"- {ci}")

    if all_theory_hooks:
        lines.append("\n### 연결 이론")
        for hook in all_theory_hooks[:5]:
            lines.append(f"- {hook}")

    lines.append(f"\n### 종합 위험 등급: {risk_grade}/3 — {risk_label}")

    return {
        "active_sectors": active_sectors,
        "cross_insights": cross_insights,
        "all_theory_hooks": all_theory_hooks,
        "all_evidence": all_evidence,
        "all_insights": all_insights,
        "risk_grade": risk_grade,
        "risk_label": risk_label,
        "summary_context": "\n".join(lines),  # Gemini 프롬프트 주입용
    }
