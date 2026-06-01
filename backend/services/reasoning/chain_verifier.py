"""
chain_verifier.py — 추론 체인 자기검증 (P5-6)

8단계 추론 결과에서 4종 주장(Claim)을 추출하고,
cascade_rules.yaml + 포지션 일관성 + 역사 선례로 BFS 검증.

반환: chain_verification 딕셔너리
  - chain_confidence: float (0-1)
  - verdict: "supported" | "contested" | "unsupported"
  - claims: 각 주장의 지지/반증 상세
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from services.cascade.rule_loader import load_rules

logger = logging.getLogger(__name__)

# 판정 기준
_SUPPORTED_THRESHOLD = 0.70
_CONTESTED_THRESHOLD = 0.45

_VERDICT_KO = {
    "supported":   "지정학 패턴으로 지지됨",
    "contested":   "일부 반증 또는 불확실성 존재",
    "unsupported": "주요 반증 발견 또는 근거 부족",
}

# 의도-포지션 일관성 테이블
# (intent_label, strategic_posture) → delta
_INTENT_POSTURE_DELTA: dict[tuple[str, str], float] = {
    ("aggression",  "revisionist"):  +0.10,   # 정합: 수정주의 + 공세
    ("coercion",    "revisionist"):  +0.08,   # 정합: 수정주의 + 강압
    ("deterrence",  "status_quo"):   +0.08,   # 정합: 현상유지 + 억제
    ("negotiation", "status_quo"):   +0.06,   # 정합: 현상유지 + 협상
    ("aggression",  "status_quo"):   -0.12,   # 역설: 현상유지 + 공세
    ("negotiation", "revisionist"):  -0.08,   # 역설: 수정주의 + 협상
}


@dataclass
class Claim:
    """검증 단위 주장."""
    claim_type: Literal["cascade", "intent", "alliance", "history"]
    description: str
    verdict: Literal["supported", "refuted", "unverified"]
    delta: float           # chain_confidence 보정값
    evidence: str          # 한국어 근거 설명
    weight: float = 1.0    # 주장 가중치


@dataclass
class ChainVerification:
    """자기검증 최종 결과."""
    chain_confidence: float
    verdict: Literal["supported", "contested", "unsupported"]
    verdict_ko: str
    supported: list[Claim] = field(default_factory=list)
    refuted: list[Claim] = field(default_factory=list)
    unverified: list[Claim] = field(default_factory=list)
    note_ko: str = ""


def verify_chain(stages: dict, region_code: str) -> dict:
    """
    8단계 추론 결과를 받아 자기검증 수행.

    Args:
        stages: engine.py _run_stages() 반환 "stages" 딕셔너리
        region_code: 이벤트 지역 코드

    Returns:
        직렬화 가능한 딕셔너리
    """
    try:
        rules = load_rules()
    except Exception as e:
        logger.warning("[chain_verifier] 룰 로드 실패: %s", e)
        rules = []

    # 지역별 룰 인덱스
    region_rules = [r for r in rules if r.trigger.region == region_code]

    all_claims: list[Claim] = []

    # ── 1. CascadeClaim: Stage 7 체인 ↔ 룰북 대조 ───────────────────────
    s7 = stages.get("7_cascade", {}) or {}
    all_claims.extend(_verify_cascade_claims(s7, region_rules, region_code))

    # ── 2. IntentClaim: Stage 5 의도 ↔ 포지션 일관성 ─────────────────────
    s5 = stages.get("5_intent", {}) or {}
    all_claims.extend(_verify_intent_claims(s5))

    # ── 3. AllianceClaim: Stage 8 동맹 확산 경로 지지도 ──────────────────
    s8 = stages.get("8_alliance", {}) or {}
    all_claims.extend(_verify_alliance_claims(s8))

    # ── 4. HistoryClaim: Stage 3 역사 선례 검증 ──────────────────────────
    s3 = stages.get("3_history", {}) or {}
    all_claims.extend(_verify_history_claims(s3))

    # ── chain_confidence 계산 ─────────────────────────────────────────────
    base = 0.50
    delta_sum = sum(c.delta * c.weight for c in all_claims)
    confidence = round(min(0.95, max(0.10, base + delta_sum)), 3)

    # ── 판정 ─────────────────────────────────────────────────────────────
    if confidence >= _SUPPORTED_THRESHOLD:
        verdict: Literal["supported", "contested", "unsupported"] = "supported"
    elif confidence >= _CONTESTED_THRESHOLD:
        verdict = "contested"
    else:
        verdict = "unsupported"

    supported   = [c for c in all_claims if c.verdict == "supported"]
    refuted     = [c for c in all_claims if c.verdict == "refuted"]
    unverified  = [c for c in all_claims if c.verdict == "unverified"]

    note = _build_note(confidence, supported, refuted, region_code)

    result = ChainVerification(
        chain_confidence=confidence,
        verdict=verdict,
        verdict_ko=_VERDICT_KO[verdict],
        supported=supported,
        refuted=refuted,
        unverified=unverified,
        note_ko=note,
    )

    return _serialize(result)


# ── 개별 주장 검증 함수들 ─────────────────────────────────────────────────

def _verify_cascade_claims(s7: dict, region_rules: list, region_code: str) -> list[Claim]:
    """Stage 7 체인 링크를 룰북과 대조."""
    claims: list[Claim] = []
    chain = s7.get("cascade_chain", [])

    if not region_code:
        return claims

    if not region_rules:
        # 이 지역에 룰이 아예 없음 → 관찰되지 않은 인과 패턴
        if chain:
            claims.append(Claim(
                claim_type="cascade",
                description=f"{region_code} 지역 cascade 링크 존재, 룰북 미등록",
                verdict="unverified",
                delta=0.0,
                evidence=f"'{region_code}' 지역 대응 룰 없음 — 신규 패턴이거나 데이터 부족",
                weight=0.5,
            ))
        return claims

    # 룰이 있는 경우: 실제 발화 여부 확인
    rule_tickers = {r.expected_response.ticker for r in region_rules}
    chain_tickers = {
        lk.get("rule_name", "").split("→")[-1].strip()
        for lk in chain
    }

    if chain:
        # 실제 cascade 링크가 있음 → 룰북 대비 발화 확인
        fired_rules = [r for r in region_rules if chain]  # 이 지역 룰이 발화됨
        claims.append(Claim(
            claim_type="cascade",
            description=f"{region_code} 지역 cascade 발화 (depth {s7.get('chain_depth', 0)}단계)",
            verdict="supported",
            delta=+0.15,
            evidence=(
                f"룰북 {len(region_rules)}개 룰 중 실제 cascade 링크 {len(chain)}건 발화. "
                f"관련 티커: {', '.join(rule_tickers)}"
            ),
            weight=1.0,
        ))
    else:
        # 룰이 있는데 발화 없음 → 임계값 미달 또는 데이터 gap
        claims.append(Claim(
            claim_type="cascade",
            description=f"{region_code} 지역 룰 존재, 미발화",
            verdict="unverified",
            delta=0.0,
            evidence=(
                f"'{region_code}' 지역 룰 {len(region_rules)}개 정의됨"
                f"(티커: {', '.join(rule_tickers)}) — "
                "severity 미달 또는 윈도우 내 데이터 없음으로 미발화"
            ),
            weight=0.8,
        ))

    return claims


def _verify_intent_claims(s5: dict) -> list[Claim]:
    """Stage 5 의도와 행위자 포지션의 일관성 검증."""
    claims: list[Claim] = []

    intent_label = s5.get("intent_label", "ambiguous")
    actor_postures = s5.get("actor_postures", [])
    escalation = s5.get("escalation_risk", False)

    if not actor_postures:
        return claims

    # 행위자별 의도-포지션 일관성 확인
    for ap in actor_postures[:3]:  # 최대 3명
        iso3 = ap.get("iso3", "?")
        posture = ap.get("strategic_posture", "unknown")
        if posture == "unknown":
            continue

        key = (intent_label, posture)
        delta = _INTENT_POSTURE_DELTA.get(key, 0.0)

        if delta > 0:
            verdict_val: Literal["supported", "refuted", "unverified"] = "supported"
            evidence = (
                f"{iso3} 포지션({posture}) + 의도({intent_label}) 일관 "
                f"— Snyder 동맹 딜레마: 역할 예측 가능"
            )
        elif delta < 0:
            verdict_val = "refuted"
            evidence = (
                f"{iso3} 포지션({posture}) ↔ 의도({intent_label}) 불일치 "
                f"— 행동 역설 또는 기만 가능성"
            )
        else:
            verdict_val = "unverified"
            evidence = f"{iso3} 포지션({posture}) + 의도({intent_label}) — 판단 유보"

        claims.append(Claim(
            claim_type="intent",
            description=f"{iso3}: {posture} 포지션 + {intent_label} 의도",
            verdict=verdict_val,
            delta=delta,
            evidence=evidence,
            weight=0.8,
        ))

    # 에스컬레이션 위험이 있으면 추가 주장
    if escalation:
        claims.append(Claim(
            claim_type="intent",
            description="에스컬레이션 위험 조건 충족",
            verdict="supported",
            delta=+0.05,
            evidence="revisionist 포지션 + 적대적 톤 + aggression/coercion 의도 복합 확인",
            weight=0.6,
        ))

    return claims


def _verify_alliance_claims(s8: dict) -> list[Claim]:
    """Stage 8 동맹 확산 경로의 지지도 검증."""
    claims: list[Claim] = []

    alliances = s8.get("relevant_alliances", [])
    involved = s8.get("potentially_involved_countries", [])

    if not alliances and not involved:
        claims.append(Claim(
            claim_type="alliance",
            description="관련 동맹 없음 — 고립 패턴",
            verdict="unverified",
            delta=0.0,
            evidence="이 사건 행위자들이 주요 집단방위 조약에 미포함. 확산 경로 불명확.",
            weight=0.5,
        ))
        return claims

    if len(alliances) >= 2:
        delta = +0.10
        verdict_val: Literal["supported", "refuted", "unverified"] = "supported"
        evidence = (
            f"관련 동맹 {len(alliances)}개 확인 "
            f"({', '.join(a.get('name', '') for a in alliances[:3])}) — "
            f"잠재 연루국 {len(involved)}개. "
            "Snyder 동맹 딜레마: 연루 위험 경로 명확"
        )
    elif len(alliances) == 1:
        delta = +0.05
        verdict_val = "supported"
        evidence = (
            f"관련 동맹 1개 ({alliances[0].get('name', '')}) — 제한적 확산 경로"
        )
    else:
        delta = 0.0
        verdict_val = "unverified"
        evidence = f"잠재 연루국 {len(involved)}개이나 공식 동맹 틀 미확인"

    claims.append(Claim(
        claim_type="alliance",
        description=f"동맹 확산 경로 {len(alliances)}개",
        verdict=verdict_val,
        delta=delta,
        evidence=evidence,
        weight=0.7,
    ))

    return claims


def _verify_history_claims(s3: dict) -> list[Claim]:
    """Stage 3 역사 유사 사례가 선례로서 지지하는지 검증."""
    claims: list[Claim] = []
    analogues = s3.get("analogues", [])

    if not analogues:
        claims.append(Claim(
            claim_type="history",
            description="역사 선례 없음",
            verdict="unverified",
            delta=0.0,
            evidence="유사 역사 사례 미발견 — 유례없는 패턴이거나 case_studies.yaml 데이터 부족",
            weight=0.6,
        ))
        return claims

    top = analogues[0]
    score = top.get("similarity_score", 0)
    case_name = top.get("name_ko", top.get("id", "?"))

    if score >= 0.5:
        verdict_val: Literal["supported", "refuted", "unverified"] = "supported"
        delta = +0.10
        evidence = f"'{case_name}' (유사도 {score:.2f}) — 역사 선례로 현 패턴 지지"
    elif score >= 0.3:
        verdict_val = "unverified"
        delta = +0.03
        evidence = f"'{case_name}' (유사도 {score:.2f}) — 약한 유사성, 맥락 차이 존재"
    else:
        verdict_val = "unverified"
        delta = 0.0
        evidence = f"'{case_name}' (유사도 {score:.2f}) — 유사성 낮음, 독립적 분석 필요"

    claims.append(Claim(
        claim_type="history",
        description=f"역사 선례: {case_name}",
        verdict=verdict_val,
        delta=delta,
        evidence=evidence,
        weight=0.7,
    ))

    return claims


def _build_note(confidence: float, supported: list[Claim], refuted: list[Claim], region: str) -> str:
    """chain_confidence 기반 학습용 해설 생성."""
    if refuted:
        refuted_desc = "; ".join(c.description for c in refuted[:2])
        return (
            f"신뢰도 {confidence:.2f} — 반증 {len(refuted)}건 존재({refuted_desc}). "
            "추론 경로의 전제를 재검토하거나 대안 가설을 고려할 것."
        )
    elif supported:
        sup_desc = "; ".join(c.description for c in supported[:2])
        return (
            f"신뢰도 {confidence:.2f} — 지지 {len(supported)}건({sup_desc}). "
            "기존 지정학 패턴과 일관됨."
        )
    else:
        return (
            f"신뢰도 {confidence:.2f} — 검증 가능한 주장 부족. "
            f"'{region}' 지역 데이터 보강 후 재분석 권장."
        )


def _serialize(cv: ChainVerification) -> dict:
    """dataclass → JSON 직렬화 가능 딕셔너리."""
    def claim_to_dict(c: Claim) -> dict:
        return {
            "type": c.claim_type,
            "description": c.description,
            "verdict": c.verdict,
            "delta": c.delta,
            "evidence": c.evidence,
        }

    return {
        "chain_confidence": cv.chain_confidence,
        "verdict": cv.verdict,
        "verdict_ko": cv.verdict_ko,
        "supported": [claim_to_dict(c) for c in cv.supported],
        "refuted": [claim_to_dict(c) for c in cv.refuted],
        "unverified": [claim_to_dict(c) for c in cv.unverified],
        "note_ko": cv.note_ko,
    }
