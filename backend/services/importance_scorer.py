"""
backend/services/importance_scorer.py

ACLED 이벤트 복합 중요도 점수 계산 + 지역-기간-행위자 기반 클러스터링.

importance_score 구성요소 (가중합 = 1.0):
  severity        × 0.3  severity / 100
  recency         × 0.3  오늘=1.0, 30일전=0.0 선형 감소
  cascade_hit     × 0.2  cascade_rules.yaml 트리거 지역이면 1.0
  repeat_region   × 0.1  동일 region 30일 내 반복 횟수 / 10 (상한 1.0)
  gdelt_confirmed × 0.1  GDELT가 같은 지역을 보도한 경우 1.0

클러스터링 기준:
  동일 region_code + 7일 이내 + 동일 inter1(행위자 유형)
  → 대표 1개(severity 최고값)로 통합, cluster_count에 원본 수 기록
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from models.event import Event

logger = logging.getLogger(__name__)

_CASCADE_RULES_PATH = Path(__file__).parent.parent / "config" / "cascade_rules.yaml"

# ── recency 감쇠 창 (B15 수리 2026-07-14) ─────────────────────────────────────
# 배치 상대 정규화를 **절대 감쇠**로 대체하면서 도입한 상수.
# 점수의 의미가 "이 응답에 뭐가 같이 들어왔나"가 아니라 "지평에서 얼마나 멀어졌나"가 된다.
_RECENCY_WINDOW_DAYS = 90.0
# ACLED/일반 이벤트. 지평(ref_time)에서 90일 지나면 recency 기여 0.
# 90일 근거: 6대 섹터의 분쟁 국면 전환 주기의 대략적 하한(분기). 이 값을 바꾸면
# 프론트의 줌별 가시성 임계(ConflictEventsLayer.js §4)가 함께 흔들린다 — 같이 재라.

_REPEAT_SATURATION = 500.0
# repeat_region 포화점 — 전역 권역 이벤트 수가 이 값이면 rep_s=1.0.
# 500 근거: 실측 권역별 event_archive 분포의 중위권(bab_el_mandeb 8,571 · taiwan_strait 1,181 ·
# suez 640대). 소수 대형 권역(우크라 87k)이 전 권역을 1.0으로 포화시키지 않게 잡았다.

_GDELT_RECENCY_WINDOW_HOURS = 72.0
# GDELT. §18 TTL의 핫 보관 창(72h)과 **일부러 같게** 맞췄다 —
# importance는 "TTL 만료 전에 아카이브로 승격할 가치가 있나"를 재는 값이므로,
# 감쇠 창이 TTL 창과 다르면 점수가 무엇을 뜻하는지 아무도 설명할 수 없다.

# cascade_rules.yaml에서 trigger.region 목록을 읽어 캐싱
_CASCADE_TRIGGER_REGIONS: Optional[frozenset] = None


def _load_cascade_regions() -> frozenset:
    global _CASCADE_TRIGGER_REGIONS
    if _CASCADE_TRIGGER_REGIONS is not None:
        return _CASCADE_TRIGGER_REGIONS
    try:
        rules = yaml.safe_load(_CASCADE_RULES_PATH.read_text(encoding="utf-8")) or []
        regions = {
            r.get("trigger", {}).get("region")
            for r in rules
            if r.get("trigger", {}).get("region")
        }
        _CASCADE_TRIGGER_REGIONS = frozenset(regions)
        logger.debug("[importance] cascade trigger regions: %s", _CASCADE_TRIGGER_REGIONS)
    except Exception as exc:
        logger.warning("[importance] cascade_rules.yaml 읽기 실패: %s", exc)
        _CASCADE_TRIGGER_REGIONS = frozenset()
    return _CASCADE_TRIGGER_REGIONS


def score_events(
    events: list[Event],
    gdelt_regions: frozenset[str],
    ref_time: Optional[datetime] = None,
    region_activity: Optional[dict[str, int]] = None,
) -> list[Event]:
    """
    events 배열 전체를 받아 importance_score를 in-place로 채운 뒤 반환.

    Args:
        events:        ACLED connector에서 반환된 Event 리스트 (이미 클러스터링 완료)
        gdelt_regions: GDELT GeoJSON에서 추출한 region_code 집합
        ref_time:      **최신도의 기준점 = 그 소스의 데이터 지평.**
                       ACLED는 event_date 랙이 365일이므로 `now`를 쓰면 모든 이벤트가
                       rec=0이 된다 → 호출자가 **ACLED의 최신 event_date**를 넘겨야 한다.
                       None이면 `now`(실시간 소스용 기본값).
                       ⚠️ 2026-07-14 이전엔 "미사용"으로 방치돼 있었고, 그 대신
                       배치 min/max로 정규화하는 바람에 **같은 이벤트가 배치 구성에 따라
                       다른 점수를 받았다**(B15).
    """
    if not events:
        return events

    cascade = _load_cascade_regions()

    # ── recency (B15 수리 2026-07-14) ────────────────────────────────────────
    # ⚠️ 구 코드는 **배치 안에서** min/max로 정규화했다:
    #       rec_s = (t - ts_min) / (ts_max - ts_min)
    #    그래서 **같은 이벤트가 배치 구성에 따라 다른 점수를 받았다**:
    #      · 배치의 가장 오래된 이벤트는 **어제 것이어도 rec=0.0**
    #      · 배치의 가장 최근 이벤트는 **5년 전 것이어도 rec=1.0**
    #      · 배치에 한 건뿐이면(ts_range=0) **아무리 오래돼도 rec=1.0**
    #
    #    그리고 이 점수는 프론트(`ConflictEventsLayer.js`)의 **줌별 마커 가시성**과
    #    **등급 기호**를 정한다 — **어떤 이벤트가 보이느냐가 쿼리 구성에 좌우됐다.**
    #    분모가 세계가 아니라 배치였다.
    #
    #    구 주석의 변명("절대 시간은 ACLED 랙 때문에 항상 0이 된다")은 **진단은 맞고
    #    처방이 틀렸다.** ACLED 이벤트는 실제로 오래됐다 — 그 사실을 배치로 감추는 대신,
    #    **소스의 데이터 지평(`ref_time`)을 기준**으로 잰다. 지평은 세계의 성질이지
    #    쿼리의 우연이 아니다. 호출자가 해당 소스의 최신 event_date를 넘기면 된다.
    #    (`ref_time`은 원래 시그니처에 있었고 "미사용"으로 방치돼 있었다)
    anchor = (ref_time or datetime.now(timezone.utc)).timestamp()
    window = _RECENCY_WINDOW_DAYS * 86_400.0

    # ── repeat_region (B15 수리 2026-07-14) ──────────────────────────────────
    # ⚠️ 구 코드는 **배치 안 등장 횟수 / 10**이었다 — recency와 **같은 병**이다.
    #    같은 이벤트가 무엇과 함께 조회됐느냐에 따라 점수가 달라진다.
    #    (의장은 초판에서 "이건 의도된 배치 상대"라고 합리화했다가 **자기 테스트에
    #     반박당했다** — 점수가 마커 가시성을 정하는 이상 **모든 성분이 배치 불변**이어야 한다)
    #
    #    `region_activity`(전역 권역별 이벤트 수)를 **호출자가 넘기면** 그것으로 잰다.
    #    안 넘기면 **0으로 둔다** — 없는 숫자를 배치로 지어내지 않는다.
    #    `_score_breakdown.repeat_region_source`가 어느 쪽이었는지 자백한다.
    rep_source = "global" if region_activity else "none(미제공 — 0으로 둠)"

    scored: list[Event] = []
    for e in events:
        sev_s   = e.severity / 100.0
        # 지평으로부터의 나이로 선형 감쇠 — **배치와 무관하다**
        age     = anchor - e.timestamp.timestamp()
        rec_s   = max(0.0, min(1.0, 1.0 - age / window))
        casc_s  = 1.0 if e.region_code in cascade        else 0.0
        rep_s   = (
            min(1.0, (region_activity or {}).get(e.region_code or "", 0) / _REPEAT_SATURATION)
            if region_activity
            else 0.0
        )
        gdelt_s = 1.0 if e.region_code in gdelt_regions  else 0.0

        score = (
            sev_s   * 0.3 +
            rec_s   * 0.3 +
            casc_s  * 0.2 +
            rep_s   * 0.1 +
            gdelt_s * 0.1
        )

        # Pydantic v2: model_copy로 불변 필드 업데이트
        scored.append(e.model_copy(update={
            "importance_score": round(min(1.0, score), 4),
            "payload": {
                **e.payload,
                "_score_breakdown": {
                    "severity":        round(sev_s   * 0.3, 4),
                    "recency":         round(rec_s   * 0.3, 4),
                    "cascade_hit":     round(casc_s  * 0.2, 4),
                    "repeat_region":   round(rep_s   * 0.1, 4),
                    "repeat_region_source": rep_source,
                    "gdelt_confirmed": round(gdelt_s * 0.1, 4),
                },
            },
        }))

    return scored


def score_gdelt_events(
    events: list[Event],
    ref_time: Optional[datetime] = None,
) -> list[Event]:
    """GDELT 이벤트 importance_score 계산.

    ACLED 스코어와 다른 가중치를 사용한다:
      severity        × 0.3  (Goldstein → 0-100 정규화된 값)
      recency         × 0.4  (GDELT는 15분 단위 실시간 → 최신성 가중치 높임)
      confidence_score × 0.3 (0.8=교차검증, 0.5=미검증)
      cascade_hit / repeat_region = 0  (GDELT는 region 매칭이 약함)

    recency는 **지금으로부터의 나이**로 잰다 — GDELT는 실시간 소스(TTL 72h)라 이것이
    옳은 기준이다. ⚠️ 구 코드는 배치 min/max 정규화였고, recency가 **점수의 40%**를
    차지하므로 피해가 ACLED보다 컸다: 배치에 한 건만 들어오면(ts_range=0) 아무리
    오래된 이벤트도 rec=1.0을 받았다(B15).
    """
    if not events:
        return events

    # GDELT는 실시간 → 지평은 `now`. TTL 창(72h)으로 선형 감쇠한다.
    anchor = (ref_time or datetime.now(timezone.utc)).timestamp()
    window = _GDELT_RECENCY_WINDOW_HOURS * 3600.0

    scored: list[Event] = []
    for e in events:
        sev_s  = e.severity / 100.0
        age    = anchor - e.timestamp.timestamp()
        rec_s  = max(0.0, min(1.0, 1.0 - age / window))
        conf_s = e.confidence_score  # 0.8(교차검증) or 0.5(미검증)

        score = sev_s * 0.3 + rec_s * 0.4 + conf_s * 0.3

        scored.append(e.model_copy(update={
            "importance_score": round(min(1.0, score), 4),
            "payload": {
                **e.payload,
                "_score_breakdown": {
                    "severity":         round(sev_s  * 0.3, 4),
                    "recency":          round(rec_s  * 0.4, 4),
                    "confidence":       round(conf_s * 0.3, 4),
                },
            },
        }))

    return scored


def cluster_events(events: list[Event]) -> list[Event]:
    """
    동일 region_code + 7일 이내 + 동일 inter1 그룹을 대표 이벤트 1개로 통합.

    - 대표 이벤트: 그룹 내 severity 최고값
    - cluster_count: 통합된 원본 이벤트 수
    - 좌표 없는 이벤트(lat=lon=0)와 region_code=None은 클러스터링 제외(단독 유지)
    """
    _WINDOW_DAYS = 7

    # 클러스터 키: (region_code, inter1, week_bucket)
    # week_bucket = timestamp를 7일 단위로 내림 (epoch 기준 정수 나눔)
    clusters: dict[tuple, list[Event]] = {}
    unclustered: list[Event] = []

    for e in events:
        lat, lon = e.location
        inter1   = e.payload.get("inter1", 0)
        rc       = e.region_code

        if not rc or (lat == 0.0 and lon == 0.0):
            unclustered.append(e)
            continue

        epoch_days = int(e.timestamp.timestamp() / 86_400)
        bucket     = epoch_days // _WINDOW_DAYS

        key = (rc, inter1, bucket)
        clusters.setdefault(key, []).append(e)

    result: list[Event] = []
    for group in clusters.values():
        if len(group) == 1:
            result.append(group[0])
            continue

        # 대표: severity 최고값
        representative = max(group, key=lambda e: e.severity)
        result.append(representative.model_copy(update={
            "cluster_count": len(group),
        }))

    result.extend(unclustered)
    return result
