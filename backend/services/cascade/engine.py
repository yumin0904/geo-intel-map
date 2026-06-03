"""
engine.py — Cascade(연쇄 분석) 메인 엔진.

새 이벤트(트리거)가 룰의 조건에 맞으면 expected_response 윈도우를 검사해
실제 시장 변동이 임계치를 넘었는지 확인하고, 넘으면 CascadeLink를 생성한다.

지원하는 trigger.source_type:
  - "conflict"        : ACLED 분쟁 이벤트 (30일 과거 데이터)
  - "military_flight" : OpenSky ADS-B 군용기 (실시간 현재 위치)

military_flight 평가 방식:
  OpenSky는 현재 항공기 위치만 제공한다.
  트리거 timestamp를 (지금 - window_hours)로 설정해 yfinance가
  최근 window_hours 동안의 시장 변동을 소급 평가하도록 한다.
  의미: "지금 대만해협에 군용기가 있고, 최근 24h 동안 TSM이 1% 하락했는가?"

정치외교학 연결:
  - conflict 룰: Hirschman(1945) 자원무기화 — 분쟁→유가·안전자산
  - military_flight 룰: Farrell & Newman(2019) 무기화된 상호의존 —
    대만해협 군사 긴장이 반도체 공급망 집중을 통해 TSMC 주가로 전이
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from connectors.acled import (
    AcledConnector,
    GULF_COUNTRIES,
    MIDDLE_EAST_COUNTRIES,
    SOUTH_CHINA_SEA_COUNTRIES,
    SUEZ_COUNTRIES,
)
from connectors.yfinance_adapter import evaluate_response
from models.cascade import CascadeLink, CascadeRule
from models.event import Event
from services.cascade.rule_loader import load_rules
from services.region import region_center, region_for_point

logger = logging.getLogger(__name__)

# 룰당 평가할 트리거 이벤트 상한.
# "날짜별 최고 심각도 1개" 전략을 쓰므로 30일 창 날짜 수(≤30)보다 약간 여유 있게 설정.
_MAX_TRIGGERS_PER_RULE = 15

# Phase 3: 체이닝 최대 깊이. 룰 100개 환경에서도 안전한 상한.
_MAX_CHAIN_DEPTH = 4

# region_code별 트리거 → ACLED 조회 국가 매핑. 새 region 추가 시 여기에 등록.
# 바브엘만데브: 예멘(후티)·지부티·에리트레아가 해협을 둘러쌈.
_TRIGGER_COUNTRIES: dict[str, list[str]] = {
    # ── 활성 룰 ──────────────────────────────────────────────────────────
    "bab_el_mandeb":  ["Yemen", "Djibouti", "Eritrea"],   # → CL=F ↑ (동작 확인)
    "ukraine":        ["Ukraine"],                         # → ZW=F ↑ (동작 확인)
    # ── 신규 활성 룰 (ACLED 데이터 확인 완료) ──────────────────────────
    "middle_east":    MIDDLE_EAST_COUNTRIES,               # → GLD ↑ (안전자산)
    "south_china_sea": SOUTH_CHINA_SEA_COUNTRIES,          # → ITA ↑, NG=F ↑
    "suez":           SUEZ_COUNTRIES,                      # → ZIM ↑ (해운주)
    # ── DB 우선 지역 (live API sev 부족 → events DB에서 로드) ───────────
    "hormuz":         GULF_COUNTRIES,                      # → CL=F ↑
    "korean_peninsula": ["South Korea"],                   # → KRW=X ↑ (한반도 긴장)
    "north_korea":    ["North Korea"],                     # → KRW=X ↑ (북한 도발)
    "east_china_sea": ["China", "Japan"],                  # → ITA ↑ (센카쿠 분쟁)
    "malacca":        ["Malaysia", "Singapore", "Indonesia"],  # → NG=F ↑ (LNG 초크포인트)
    # 대만해협: ACLED는 대만·중국 민간 충돌 위주 (avg sev≈15). 고강도 이벤트(sev≥50)는 희박하지만
    # event_archive 12개월치 데이터를 활용해 cascade 발화 가능. ADS-B(military_flight) 룰과 병행.
    "taiwan_strait":  ["Taiwan", "China"],                    # → SOXX ↓, TSM ↓
}

_INTEL_DB = Path(__file__).resolve().parents[2] / "db" / "intel.db"


def _load_region_events_from_db(region: str) -> list[Event]:
    """events 테이블에서 특정 region_code의 ACLED 이벤트를 로드한다.

    live ACLED API가 희박한 지역(한반도·동중국해·말라카 등)에서
    DB baseline 데이터를 cascade 트리거로 활용한다.
    events 테이블에 고강도(sev≥50) 이벤트가 부족하면 event_archive를 추가 조회한다.
    """
    if not _INTEL_DB.exists():
        return []
    try:
        with sqlite3.connect(_INTEL_DB) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """
                SELECT id, timestamp, source_type, region_code, severity,
                       confidence_score, lat, lon, title, description, payload, theory_tags
                FROM events
                WHERE source_type = 'conflict'
                  AND region_code = ?
                  AND confidence_score >= 1.0
                ORDER BY timestamp DESC
                LIMIT 500
                """,
                (region,),
            ).fetchall()

            # 고강도 이벤트(sev≥50)가 5건 미만이면 event_archive에서 추가 보충
            # 대만해협처럼 ACLED 민간 이벤트 위주인 지역은 archive 12개월치 활용
            high_sev = [r for r in rows if (r["severity"] or 0) >= 50]
            if len(high_sev) < 5:
                archive_rows = con.execute(
                    """
                    SELECT id, timestamp, source_type, region_code, severity,
                           confidence_score,
                           CAST(json_extract(payload, '$.lat') AS REAL) AS lat,
                           CAST(json_extract(payload, '$.lon') AS REAL) AS lon,
                           title, description, payload, theory_tags
                    FROM event_archive
                    WHERE source_type = 'conflict'
                      AND region_code = ?
                      AND confidence_score >= 1.0
                    ORDER BY severity DESC
                    LIMIT 200
                    """,
                    (region,),
                ).fetchall()
                # 중복 id 제거 후 병합
                existing_ids = {r["id"] for r in rows}
                extra = [r for r in archive_rows if r["id"] not in existing_ids]
                rows = list(rows) + extra
                logger.info(
                    "[cascade] region=%s: events 고강도 이벤트 부족(%d건) → archive %d건 보충",
                    region, len(high_sev), len(extra),
                )
        events: list[Event] = []
        for r in rows:
            try:
                payload = json.loads(r["payload"] or "{}")
                evt = Event(
                    id=r["id"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    source_type=r["source_type"],
                    source_id=payload.get("source_id", r["id"]),
                    location=(r["lat"] or 0.0, r["lon"] or 0.0),
                    region_code=r["region_code"],
                    severity=r["severity"] or 0,
                    title=r["title"] or "",
                    description=r["description"] or "",
                    payload=payload,
                    theory_tags=json.loads(r["theory_tags"] or "[]"),
                    confidence_score=r["confidence_score"] or 1.0,
                )
                events.append(evt)
            except Exception:
                continue
        return events
    except Exception as e:
        logger.warning("[cascade] DB region load 실패 (region=%s): %s", region, e)
        return []


async def build_cascade(rules: list[CascadeRule] | None = None) -> dict:
    """모든 룰을 평가해 CascadeLink + 관련 이벤트를 반환한다.

    같은 region을 가진 룰이 여러 개여도 ACLED HTTP 호출은 region당 1회만 수행한다.
    (예: south_china_sea_to_defense + south_china_sea_to_lng → ACLED 1회)
    region fetch는 asyncio.gather로 병렬 실행해 대기 시간을 최소화한다.

    Returns:
        {"links": [...], "events": [...], "metadata": {...}}
        프론트엔드가 trigger→response 점선 화살표를 그리는 데 필요한 모든 데이터.
    """
    rules = rules if rules is not None else load_rules()
    links: list[CascadeLink] = []
    events_by_id: dict[str, Event] = {}

    conflict_rules  = [r for r in rules if r.trigger.source_type == "conflict"]
    military_rules  = [r for r in rules if r.trigger.source_type == "military_flight"]
    other_count     = len(rules) - len(conflict_rules) - len(military_rules)
    if other_count:
        logger.info(f"[cascade] 미지원 source_type 룰 {other_count}개 건너뜀")

    # ── conflict 룰: ACLED 30일 과거 데이터 ────────────────────────────────
    unique_regions = list({r.trigger.region for r in conflict_rules})
    fetched = await asyncio.gather(*[_fetch_region_events(region) for region in unique_regions])
    region_raw: dict[str, list[Event]] = dict(zip(unique_regions, fetched))

    for rule in conflict_rules:
        raw_events = region_raw.get(rule.trigger.region, [])
        triggers = _sample_triggers(raw_events, rule.trigger.severity_min)
        logger.info(f"[cascade] 룰 {rule.id}: 조건 충족 트리거 {len(triggers)}개")

        for trig in triggers:
            link_pair = await _evaluate_trigger(rule, trig)
            if link_pair is None:
                continue
            link, response_event = link_pair
            links.append(link)
            events_by_id[trig.id] = trig
            events_by_id[response_event.id] = response_event

    # ── military_flight 룰: OpenSky 실시간 군용기 ──────────────────────────
    if military_rules:
        military_events = await _fetch_military_events()
        for rule in military_rules:
            trig = _pick_military_trigger(
                military_events,
                rule.trigger.region,
                rule.trigger.severity_min,
                rule.expected_response.window_hours,
            )
            if trig is None:
                logger.info(
                    f"[cascade] 룰 {rule.id}: 군용기 트리거 없음 "
                    f"(region={rule.trigger.region}, sev_min={rule.trigger.severity_min})"
                )
                continue
            logger.info(
                f"[cascade] 룰 {rule.id}: 군용기 트리거 1개 "
                f"(callsign={trig.payload.get('callsign','?')}, sev={trig.severity})"
            )
            link_pair = await _evaluate_trigger(rule, trig)
            if link_pair is None:
                continue
            link, response_event = link_pair
            links.append(link)
            events_by_id[trig.id] = trig
            events_by_id[response_event.id] = response_event

    # ── Phase 3: 다단계 체이닝 ──────────────────────────────────────────────────
    # 1단계 링크 중 chain_output을 가진 것에 한해 후속 룰 평가
    rules_dict = {r.id: r for r in rules}
    rules_by_input = _index_rules_by_input(rules)
    first_level_snapshot = list(links)  # 체이닝 중 links가 변경되므로 스냅샷

    for link in first_level_snapshot:
        rule = rules_dict.get(link.rule_id or "")
        if not rule or not rule.chain_output:
            continue
        # link 자체에 chain_output 기록 (serialization용)
        link.chain_output = rule.chain_output
        descendants = await _evaluate_chain_step(
            parent_link=link,
            rules_by_input=rules_by_input,
            visited_rule_ids={link.rule_id} if link.rule_id else set(),
            depth=1,
        )
        links.extend(descendants)

    chain_count = len(links) - len(first_level_snapshot)
    logger.info(f"[cascade] 체이닝 링크 {chain_count}개 추가 (총 {len(links)}개)")

    # ── 신뢰도 필터 후 DB 저장 (score >= 0.6만 보존) ─────────────────────────
    saved, skipped = _persist_links(links)
    logger.info(f"[cascade] DB 저장 {saved}건 (신뢰도 미달 제외 {skipped}건)")

    return {
        "links": [l.model_dump() for l in links],
        "events": [e.model_dump() for e in events_by_id.values()],
        "metadata": {
            "rule_count": len(rules),
            "link_count": len(links),
            "chain_count": chain_count,
            "saved_to_db": saved,
            "skipped_low_confidence": skipped,
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


# 신뢰도 임계값: threshold의 1.2배 이상 시장 반응 = score 0.6
# score = pct_change / (threshold_pct × 2) 이므로
# 0.6 = 임계값의 1.2배, 0.8 = 1.6배, 1.0 = 2배+
_MIN_PERSIST_SCORE = 0.6


def _persist_links(links: list[CascadeLink]) -> tuple[int, int]:
    """
    신뢰도 0.6 이상 링크만 cascade_links 테이블에 저장한다.

    UNIQUE(source_event_id, target_event_id, rule_id)로 중복 방지.
    score가 높아졌으면 UPDATE, 동일하면 IGNORE.
    """
    saved = skipped = 0
    try:
        with sqlite3.connect(_INTEL_DB) as conn:
            for link in links:
                if link.correlation_score < _MIN_PERSIST_SCORE:
                    skipped += 1
                    continue
                evidence_json = json.dumps(link.evidence) if link.evidence else None
                conn.execute(
                    """
                    INSERT INTO cascade_links
                        (id, source_event_id, target_event_id, link_type,
                         rule_id, rule_name, correlation_score,
                         time_delta_seconds, depth, parent_link_id,
                         theory_ref, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_event_id, target_event_id, rule_id)
                    DO UPDATE SET
                        correlation_score = excluded.correlation_score,
                        time_delta_seconds = excluded.time_delta_seconds,
                        theory_ref = excluded.theory_ref,
                        evidence = excluded.evidence
                    WHERE excluded.correlation_score > cascade_links.correlation_score
                    """,
                    (
                        link.id,
                        link.source_event_id,
                        link.target_event_id,
                        link.link_type,
                        link.rule_id,
                        link.rule_name,
                        link.correlation_score,
                        link.time_delta_seconds,
                        getattr(link, "depth", 1),
                        getattr(link, "parent_link_id", None),
                        link.theory_ref,
                        evidence_json,
                    ),
                )
                saved += 1
            conn.commit()
    except Exception as e:
        logger.warning("[cascade] DB 저장 실패: %s", e)
    return saved, skipped


async def _fetch_region_events(region: str) -> list[Event]:
    """region에 속하는 ACLED 이벤트를 fetch하고 지오펜스 필터만 적용해 반환한다.

    데이터 소스 우선순위:
      1) live ACLED API (region별 국가 목록으로 조회, 최근 30일)
      2) DB fallback (live API 결과가 없거나 부족할 때)
    severity 필터는 룰마다 다르므로 여기서 적용하지 않는다(_sample_triggers가 담당).
    """
    countries = _TRIGGER_COUNTRIES.get(region)
    if not countries:
        logger.warning(f"[cascade] region={region}에 대한 ACLED 국가 매핑 없음")
        return []

    # 1) live ACLED API 시도
    api_events: list[Event] = []
    connector = AcledConnector()
    try:
        raw = await connector.fetch(countries=countries)
        for e in raw:
            lat, lon = e.location
            code = region_for_point(lat, lon)
            if code == region:
                e.region_code = code
                api_events.append(e)
        logger.info(f"[cascade] region={region}: API {len(raw)}건 → 지오펜스 통과 {len(api_events)}건")
    except Exception as e:
        logger.warning(f"[cascade] ACLED API 조회 실패(region={region}): {e}")

    if api_events:
        return api_events

    # 2) DB fallback — live API에 데이터 없는 지역(한반도·동중국해·말라카 등)
    db_events = _load_region_events_from_db(region)
    if db_events:
        logger.info(f"[cascade] region={region}: DB fallback {len(db_events)}건")
    return db_events


def _sample_triggers(raw_events: list[Event], severity_min: int) -> list[Event]:
    """severity_min 이상 이벤트를 날짜별 최고심각도 1개로 샘플링한다.

    날짜별 1개 전략을 쓰는 이유:
      단순 severity 상위 N개 방식은 특정 일자에 평가가 몰려 다른 날의 시장 반응을 놓친다.
      날짜를 분산시키면 30일 창 전체를 고르게 탐색하므로 지연 연쇄를 포착할 수 있다.
    """
    qualifying = [e for e in raw_events if e.severity >= severity_min]

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
        rule_name=rule.name,
        target_timestamp=response_event.timestamp,  # 체이닝 synthetic event 타임스탬프 기준점
        evidence={
            "region": rule.trigger.region,
            "trigger_severity": trigger.severity,
            **result,
        },
        theory_ref=rule.theory.learning_note.strip(),
    )
    return link, response_event


async def _fetch_military_events() -> list[Event]:
    """OpenSky Network에서 현재 군용기 이벤트를 가져온다.

    커넥터 미설정(환경변수 없음)이나 API 오류 시 빈 리스트를 반환해
    conflict 룰 평가에 영향을 주지 않는다.
    """
    try:
        from connectors.opensky import OpenSkyConnector
        connector = OpenSkyConnector()
    except (ValueError, ImportError) as e:
        logger.warning(f"[cascade] OpenSky 커넥터 초기화 실패: {e}")
        return []

    try:
        return await connector.fetch()
    except Exception as e:
        logger.warning(f"[cascade] OpenSky 조회 실패: {e}")
        return []


def _pick_military_trigger(
    events: list[Event],
    region: str,
    severity_min: int,
    window_hours: int,
) -> Event | None:
    """region 내 군용기 이벤트 중 severity_min 이상인 것을 1개 선택한다.

    실시간 데이터이므로 timestamp를 (지금 - window_hours)로 소급 설정한다.
    → yfinance evaluate_response()가 최근 window_hours 구간의 시장 변동을 검색할 수 있다.

    의미: "지금 이 region에 군용기가 있고, 최근 window_hours 동안 시장이 반응했는가?"
    여러 대가 감지되면 severity 최고 항공기 1개만 사용(중복 cascade 링크 방지).
    """
    qualifying = [
        e for e in events
        if e.region_code == region and e.severity >= severity_min
    ]
    if not qualifying:
        return None

    best = max(qualifying, key=lambda e: e.severity)

    # 타임스탬프 소급: yfinance가 "과거" 기간을 평가하도록 이동
    adjusted = best.model_copy()
    adjusted.timestamp = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    return adjusted


# ===================================================================
# Phase 3 신설: 체이닝 핵심 로직
# ===================================================================

def _index_rules_by_input(rules: list[CascadeRule]) -> dict[str, list[CascadeRule]]:
    """chain_input 값을 키로 후속 룰들을 인덱싱.

    예: 'semiconductor_supply_risk' → [chips_act_rule, china_retaliation_rule]
    룰북 로드 시 1회 호출, 이후 O(1) 룩업.
    """
    index: dict[str, list[CascadeRule]] = {}
    for rule in rules:
        chain_input = rule.trigger.chain_input
        if chain_input:
            index.setdefault(chain_input, []).append(rule)
    return index


async def _evaluate_response(event: Event, rule: CascadeRule) -> dict | None:
    """단일 룰의 expected_response를 평가하고 결과 dict 또는 None을 반환한다.

    _evaluate_trigger()와 달리 CascadeLink/Event 생성 없이 순수 평가만 담당.
    체이닝에서 synthetic_event를 입력으로 받을 수 있도록 분리된 함수.
    """
    resp = rule.expected_response
    if resp.source_type != "market":
        # 현재는 시장 지표 응답만 지원. 향후 정책/외교 응답 추가 시 분기.
        return None

    result = await asyncio.to_thread(
        evaluate_response,
        resp.ticker,
        resp.direction,
        event.timestamp,
        resp.window_hours,
        resp.threshold_pct,
    )
    if result is None or not result["matched"]:
        return None

    score = min(1.0, abs(result["pct_change"]) / (resp.threshold_pct * 2))
    target_ts = datetime.fromisoformat(result["extreme_date"])

    return {
        "target_id": f"{resp.ticker}-{target_ts.isoformat()}",
        "time_delta": int((target_ts - event.timestamp).total_seconds()),
        "score": round(score, 2),
        "target_timestamp": target_ts,
        "evidence": {
            "ticker": resp.ticker,
            "pct_change": result["pct_change"],
            "threshold_pct": resp.threshold_pct,
            "direction": resp.direction,
            "region": rule.trigger.region,
        },
    }


async def _evaluate_chain_step(
    parent_link: CascadeLink,
    rules_by_input: dict[str, list[CascadeRule]],
    visited_rule_ids: set[str],
    depth: int,
) -> list[CascadeLink]:
    """parent_link의 chain_output을 받아 다음 단계 룰들을 평가.

    재귀적으로 호출되며, _MAX_CHAIN_DEPTH 또는 매칭 룰 부재 시 종료.
    visited_rule_ids로 사이클 방지 (A→B→A 무한 체인 차단).
    """
    if depth >= _MAX_CHAIN_DEPTH:
        logger.debug(
            "체이닝 최대 깊이 %d 도달 (parent=%s) — 중단",
            _MAX_CHAIN_DEPTH,
            parent_link.id,
        )
        return []

    chain_output = parent_link.chain_output
    if not chain_output:
        return []

    candidate_rules = rules_by_input.get(chain_output, [])
    if not candidate_rules:
        return []

    new_links: list[CascadeLink] = []

    for rule in candidate_rules:
        if rule.id in visited_rule_ids:
            logger.warning("체이닝 사이클 감지: rule=%s 건너뜀", rule.id)
            continue

        # parent_link의 target(시장 지표)이 다음 단계의 가상 트리거가 됨.
        # 실제 새 이벤트 fetch 대신 "이전 결과를 입력으로" 평가.
        synthetic_event = Event(
            id=f"chain-{parent_link.id}",
            timestamp=parent_link.target_timestamp or datetime.now(timezone.utc),
            source_type="chain_signal",
            source_id=parent_link.id,
            location=(0.0, 0.0),  # 체인 신호는 지리적 좌표 없음
            region_code=parent_link.region_code,
            severity=int(parent_link.correlation_score * 100),
            title=f"Chain: {chain_output}",
            description=f"이전 단계 {parent_link.rule_id} 결과로부터 파생",
            payload={"parent_link_id": parent_link.id},
            theory_tags=[],
        )

        response = await _evaluate_response(synthetic_event, rule)
        if response is None:
            continue

        child_link = CascadeLink(
            source_event_id=synthetic_event.id,
            target_event_id=response["target_id"],
            time_delta_seconds=response["time_delta"],
            correlation_score=response["score"],
            link_type="rule",
            rule_id=rule.id,
            rule_name=rule.name,
            depth=depth + 1,
            parent_link_id=parent_link.id,
            chain_output=rule.chain_output,
            region_code=synthetic_event.region_code,
            target_timestamp=response["target_timestamp"],
            evidence=response["evidence"],
            theory_ref=rule.theory.reference if rule.theory else None,
        )
        new_links.append(child_link)

        # 재귀: 이 자식이 또 다른 chain_output을 갖는다면 계속
        descendants = await _evaluate_chain_step(
            child_link,
            rules_by_input,
            visited_rule_ids | {rule.id},
            depth + 1,
        )
        new_links.extend(descendants)

    return new_links


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
