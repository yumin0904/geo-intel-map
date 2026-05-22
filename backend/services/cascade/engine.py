"""
engine.py — Cascade(연쇄 분석) 메인 엔진.

새 이벤트(트리거)가 룰의 조건에 맞으면 expected_response 윈도우를 검사해
실제 시장 변동이 임계치를 넘었는지 확인하고, 넘으면 CascadeLink를 생성한다.

Phase 2 시작 단계: trigger.source_type="conflict"만 지원한다(해군 커넥터 미구현).
ACLED 걸프 분쟁 이벤트를 호르무즈 해상긴장의 대용 신호로 사용한다.

정치외교학 연결: 룰 hormuz_tension_to_oil은 Hirschman(1945)의 자원무기화 이론을 적용한 것.
호르무즈(원유 해상운송 ~20% 통과)의 군사 충격이 유가로 전이되는 메커니즘을 추적한다.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from connectors.acled import AcledConnector, GULF_COUNTRIES
from connectors.yfinance_adapter import evaluate_response
from models.cascade import CascadeLink, CascadeRule
from models.event import Event
from services.cascade.rule_loader import load_rules
from services.region import region_center, region_for_point

logger = logging.getLogger(__name__)

# 룰당 평가할 트리거 이벤트 상한.
# "날짜별 최고 심각도 1개" 전략을 쓰므로 30일 창 날짜 수(≤30)보다 약간 여유 있게 설정.
_MAX_TRIGGERS_PER_RULE = 15

# region_code별 트리거 → ACLED 조회 국가 매핑. 새 region 추가 시 여기에 등록.
# 바브엘만데브: 예멘(후티)·지부티·에리트레아가 해협을 둘러쌈.
_TRIGGER_COUNTRIES: dict[str, list[str]] = {
    "hormuz":       GULF_COUNTRIES,
    "bab_el_mandeb": ["Yemen", "Djibouti", "Eritrea"],
    # 우크라이나-러시아 분쟁 → 밀 선물(ZW=F) 룰 (food_security / resource_weaponization)
    "ukraine":       ["Ukraine"],
}


async def build_cascade(rules: list[CascadeRule] | None = None) -> dict:
    """모든 룰을 평가해 CascadeLink + 관련 이벤트를 반환한다.

    Returns:
        {"links": [...], "events": [...], "metadata": {...}}
        프론트엔드가 trigger→response 점선 화살표를 그리는 데 필요한 모든 데이터.
    """
    rules = rules if rules is not None else load_rules()
    links: list[CascadeLink] = []
    events_by_id: dict[str, Event] = {}

    for rule in rules:
        if rule.trigger.source_type != "conflict":
            logger.info(f"[cascade] 룰 {rule.id}: source_type={rule.trigger.source_type} 미지원(Phase 2 시작), 건너뜀")
            continue

        triggers = await _fetch_conflict_triggers(rule)
        logger.info(f"[cascade] 룰 {rule.id}: 조건 충족 트리거 {len(triggers)}개")

        for trig in triggers:
            link_pair = await _evaluate_trigger(rule, trig)
            if link_pair is None:
                continue
            link, response_event = link_pair
            links.append(link)
            events_by_id[trig.id] = trig
            events_by_id[response_event.id] = response_event

    return {
        "links": [l.model_dump() for l in links],
        "events": [e.model_dump() for e in events_by_id.values()],
        "metadata": {
            "rule_count": len(rules),
            "link_count": len(links),
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


async def _fetch_conflict_triggers(rule: CascadeRule) -> list[Event]:
    """룰의 trigger 조건(지역·심각도)을 만족하는 분쟁 이벤트를 수집한다.

    ACLED에서 해당 지역 국가의 이벤트를 가져와 region/severity로 필터링한 뒤
    **날짜별 최고심각도 1개**를 샘플링해 반환한다.

    날짜별 1개 전략을 쓰는 이유:
      단순 severity 상위 N개 방식은 특정 일자(예: 대규모 전투가 집중된 날)에
      평가가 몰려 다른 날의 시장 반응을 놓친다. 날짜를 분산시키면 30일 창 전체를
      고르게 탐색하므로 "조용한 날 이후 시장 급반응" 같은 지연 연쇄를 포착할 수 있다.
    """
    countries = _TRIGGER_COUNTRIES.get(rule.trigger.region)
    if not countries:
        logger.warning(f"[cascade] region={rule.trigger.region}에 대한 ACLED 국가 매핑 없음")
        return []

    connector = AcledConnector()
    try:
        events = await connector.fetch(countries=countries)
    except Exception as e:
        logger.warning(f"[cascade] ACLED 조회 실패(region={rule.trigger.region}): {e}")
        return []

    qualifying: list[Event] = []
    for e in events:
        lat, lon = e.location
        code = region_for_point(lat, lon)
        if code == rule.trigger.region and e.severity >= rule.trigger.severity_min:
            e.region_code = code
            qualifying.append(e)

    # 날짜별 최고 심각도 1개 선택 → 전체 30일 창을 균일하게 샘플링
    by_date: dict = {}
    for e in qualifying:
        d = e.timestamp.date()
        if d not in by_date or e.severity > by_date[d].severity:
            by_date[d] = e

    sampled = sorted(by_date.values(), key=lambda ev: ev.severity, reverse=True)
    return sampled[:_MAX_TRIGGERS_PER_RULE]


async def _evaluate_trigger(
    rule: CascadeRule, trigger: Event
) -> tuple[CascadeLink, Event] | None:
    """트리거 1개에 대해 expected_response를 평가하고, 충족 시 (링크, 응답이벤트)를 만든다."""
    resp = rule.expected_response
    # yfinance는 블로킹 → 이벤트 루프를 막지 않도록 스레드에서 실행
    result = await asyncio.to_thread(
        evaluate_response,
        resp.ticker,
        resp.direction,
        trigger.timestamp,
        resp.window_hours,
        resp.threshold_pct,
    )
    if result is None or not result["matched"]:
        return None

    response_event = _build_response_event(rule, trigger, result)
    delta = int((response_event.timestamp - trigger.timestamp).total_seconds())

    # 단순 상관 점수: 임계치에서 0.5, 임계치의 2배 변동에서 1.0 (Phase 2 통계분석 전 임시값)
    score = min(1.0, abs(result["pct_change"]) / (resp.threshold_pct * 2))

    link = CascadeLink(
        id=str(uuid.uuid4()),
        source_event_id=trigger.id,
        target_event_id=response_event.id,
        time_delta_seconds=delta,
        correlation_score=round(score, 2),
        link_type="rule",
        rule_id=rule.id,
        evidence={
            "region": rule.trigger.region,
            "trigger_severity": trigger.severity,
            **result,
        },
        theory_ref=rule.theory.learning_note.strip(),
    )
    return link, response_event


def _build_response_event(rule: CascadeRule, trigger: Event, result: dict) -> Event:
    """시장 변동을 Event로 정규화한다(좌표 없으므로 region 대표점에 앵커링)."""
    resp = rule.expected_response
    center = region_center(rule.trigger.region) or trigger.location
    pct = result["pct_change"]

    return Event(
        id=str(uuid.uuid4()),
        timestamp=datetime.fromisoformat(result["extreme_date"]),
        source_type="market",
        source_id=resp.ticker,
        location=center,
        region_code=rule.trigger.region,
        severity=min(100, int(abs(pct) * 10)),  # 변동률 10배를 심각도로 (10% → 100)
        title=f"{resp.ticker} {pct:+.2f}%",
        description=(
            f"{rule.trigger.region} 긴장 후 {resp.window_hours}h 내 "
            f"{resp.ticker} {result['baseline_price']}→{result['extreme_price']} "
            f"({pct:+.2f}%)"
        ),
        payload=result,
        theory_tags=[rule.theory.framework],
    )
