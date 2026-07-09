"""
acled_job.py — ACLED 분쟁 이벤트 라이브 수집 잡.

배경 (판례 20260709-os-observability-committee):
    커넥터(connectors/acled.py)는 존재했으나 collect_standalone 잡 목록에
    미등록 상태였다 — 2026-05-26 1회 백필(acled_bulk_ingest.py) 이후
    6주간 신규 수집 0건, 무경고. 이 잡이 그 배선 공백을 메운다.

    ACLED는 학술 접근 tier 특성상 event_date 자체가 실제 대비 최대
    ~14개월 지연된다(실측: 시스템 시각 2026-07 vs ACLED 최신 이벤트
    2025-05-29). 따라서 신선도 판정은 timestamp(event_date)가 아니라
    created_at(수집 시각) 기준이어야 한다 — config/source_roster.yaml 참조.

수집 범위:
    acled_bulk_ingest.py의 BULK_COUNTRIES(5대 섹터 전체 커버 국가)를
    ACLED 권장 배치 크기(20개국)로 나눠 AcledConnector.fetch()를 호출한다.
    fetch()는 내부적으로 ACLED 기준일(date_recency) 대비 최근 30일
    롤링 윈도우를 조회한다.

멱등성:
    connectors/acled.py의 _normalize()가 event_id_cnty 기반 안정 UUID를
    생성하도록 수정됐다 (판례 20260709) — 매일 재실행해도 같은 사건이
    새 랜덤 id로 중복 적재되지 않고 INSERT OR REPLACE로 덮어써진다.

실행 주기: collect_standalone 1일 2회(launchd). ACLED 원본 갱신이 주
단위라 이 주기로도 충분하고 API 호출도 과하지 않다.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# ACLED API는 국가 목록이 길면 응답이 느려지거나 불안정해질 수 있어
# acled_bulk_ingest.py와 동일하게 20개국씩 나눠 호출한다.
_COUNTRY_BATCH = 20


async def _run_acled_async() -> dict:
    """국가 배치별로 ACLED 최근 이벤트를 조회해 event_archive에 기록한다."""
    from connectors.acled import AcledConnector
    from scripts.acled_bulk_ingest import BULK_COUNTRIES
    from db.archive_manager import ArchiveManager

    connector = AcledConnector()
    archive = ArchiveManager()

    all_events = []
    for i in range(0, len(BULK_COUNTRIES), _COUNTRY_BATCH):
        batch = BULK_COUNTRIES[i : i + _COUNTRY_BATCH]
        events = await connector.fetch(countries=batch)
        all_events.extend(events)
        logger.debug("[AcledJob] 배치 %s...(%d개국) → %d건", batch[0], len(batch), len(events))

    # 국가 배치 간 겹침은 없지만(리스트 슬라이스) 방어적으로 event_id_cnty 기준 중복 제거
    seen: set[str] = set()
    unique = []
    for e in all_events:
        sid = e.source_id or e.id
        if sid not in seen:
            seen.add(sid)
            unique.append(e)

    written = archive.write_events(unique)
    logger.info(
        "[AcledJob] 완료 — 조회 %d건(중복제거 후 %d건) → 기록 %d건 (event_archive 즉시 귀속)",
        len(all_events), len(unique), written,
    )
    return {"fetched": len(all_events), "unique": len(unique), "written": written}


def run_acled_batch() -> None:
    """동기 래퍼 — collect_standalone/APScheduler에서 호출."""
    asyncio.run(_run_acled_async())
