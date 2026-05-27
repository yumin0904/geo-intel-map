"""
acled_bulk_ingest.py — ACLED 과거 데이터 event_archive 베이스라인 적재 스크립트

CLAUDE.md §18: ACLED는 인입 즉시 event_archive에 귀속되는 베이스라인 상수.
이 스크립트는 1년치(또는 지정 기간) 과거 데이터를 월별로 나눠 적재한다.
archive_manager.write_events() → _insert_archive_from_event() 자동 호출.

사용법:
    cd backend
    python scripts/acled_bulk_ingest.py               # 기본: 12개월, 전체 섹터 국가
    python scripts/acled_bulk_ingest.py --months 6    # 6개월치만
    python scripts/acled_bulk_ingest.py --dry-run     # DB 저장 없이 건수만 확인
    python scripts/acled_bulk_ingest.py --page-size 200  # 페이지당 200건

필수 환경변수 (backend/.env):
    ACLED_EMAIL=...
    ACLED_PASSWORD=...
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# backend/ 디렉터리를 sys.path에 추가 (FastAPI 없이 모듈 직접 임포트)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from connectors.acled import (
    AcledConnector,
    GULF_COUNTRIES,
    INDO_PACIFIC_COUNTRIES,
    MIDDLE_EAST_COUNTRIES,
    SOUTH_CHINA_SEA_COUNTRIES,
)
from db.archive_manager import ArchiveManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 5대 섹터 전체 커버 국가 목록 ──────────────────────────────────────────────
# 섹터별 기존 목록(acled.py)에 동유럽·코카서스 추가
_EASTERN_EUROPE = [
    "Ukraine", "Russia", "Belarus",
    "Georgia", "Armenia", "Azerbaijan",
    "Moldova",
]

# 아프리카 회색지대 (사헬, 소말리아, 수단) — 후티·테러·쿠데타 cascade 대상
_GRAY_ZONE_AFRICA = [
    "Somalia", "Sudan", "Libya", "Mali", "Niger",
    "Ethiopia", "Mozambique", "Nigeria",
]

BULK_COUNTRIES: list[str] = sorted(set(
    INDO_PACIFIC_COUNTRIES
    + GULF_COUNTRIES
    + MIDDLE_EAST_COUNTRIES
    + SOUTH_CHINA_SEA_COUNTRIES
    + _EASTERN_EUROPE
    + _GRAY_ZONE_AFRICA
))

# ACLED API는 한 요청에 국가가 너무 많으면 응답이 느려질 수 있으므로 20개씩 분할
_COUNTRY_BATCH = 20
# 페이지 사이 대기 시간 (초) — ACLED 서버 부하 방지
_SLEEP_BETWEEN_PAGES = 1.0
# 월 사이 대기 시간 (초)
_SLEEP_BETWEEN_MONTHS = 2.0


async def ingest_month(
    connector: AcledConnector,
    archive: ArchiveManager,
    since: datetime,
    until: datetime,
    page_size: int,
    dry_run: bool,
) -> dict[str, int]:
    """한 달치 이벤트를 국가 배치별로 조회해 archive에 적재한다."""
    month_label = since.strftime("%Y-%m")
    all_events = []

    # ACLED API는 국가 목록이 길면 느려짐 → 배치 분할
    for i in range(0, len(BULK_COUNTRIES), _COUNTRY_BATCH):
        batch = BULK_COUNTRIES[i : i + _COUNTRY_BATCH]
        events = await connector.fetch_range(
            since=since,
            until=until,
            countries=batch,
            page_size=page_size,
        )
        all_events.extend(events)
        if not dry_run and events:
            archive.write_events(events)
        await asyncio.sleep(_SLEEP_BETWEEN_PAGES)

    # 같은 ACLED event_id_cnty 중복 제거 (국가 배치 겹침 없지만 방어적)
    seen: set[str] = set()
    unique = []
    for e in all_events:
        sid = e.source_id or e.id
        if sid not in seen:
            seen.add(sid)
            unique.append(e)

    logger.info(
        "[%s] 총 %d건 조회, 중복 제거 후 %d건 %s",
        month_label, len(all_events), len(unique),
        "(dry-run, 저장 안 함)" if dry_run else "→ event_archive 적재",
    )
    return {"month": month_label, "fetched": len(all_events), "unique": len(unique)}


async def main(months: int, page_size: int, dry_run: bool) -> None:
    connector = AcledConnector()
    archive = ArchiveManager()

    if not dry_run:
        archive.init_schema()
        logger.info("[Bulk] DB 스키마 초기화 완료: %s", archive.db_path)

    # ACLED 기준일 probe — ref_date_cache 초기화용
    logger.info("[Bulk] ACLED 최신 데이터 기준일 탐색 중...")
    token = await connector._get_token()
    ref_date_str = await connector._get_ref_date(token)

    if ref_date_str:
        upper = datetime.strptime(ref_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        upper = datetime.now(timezone.utc)
        logger.warning("[Bulk] date_recency 없음, 시스템 시각 사용: %s", upper.date())

    lower = upper - timedelta(days=30 * months)
    logger.info(
        "[Bulk] 적재 기간: %s ~ %s (%d개월, %d개 국가, page_size=%d)",
        lower.strftime("%Y-%m-%d"), upper.strftime("%Y-%m-%d"),
        months, len(BULK_COUNTRIES), page_size,
    )
    logger.info("[Bulk] 대상 국가: %s", ", ".join(BULK_COUNTRIES))

    results = []
    t0 = time.perf_counter()

    # 월별 루프 — 오래된 달부터 최신 달 순서로
    current = lower
    while current < upper:
        next_month = min(current + timedelta(days=31), upper)
        # 월 마지막 날 계산: 다음 달 1일 - 1일
        # timedelta(days=31) 방식으로 단순 처리 (ACLED BETWEEN은 포함 경계)
        month_until = next_month - timedelta(days=1) if next_month < upper else upper

        result = await ingest_month(
            connector, archive, current, month_until, page_size, dry_run
        )
        results.append(result)

        current = next_month
        await asyncio.sleep(_SLEEP_BETWEEN_MONTHS)

    elapsed = time.perf_counter() - t0
    total_fetched = sum(r["fetched"] for r in results)
    total_unique  = sum(r["unique"]  for r in results)

    print("\n" + "=" * 60)
    print(f"ACLED 베이스라인 적재 완료 {'(dry-run)' if dry_run else ''}")
    print(f"  기간      : {lower.date()} ~ {upper.date()} ({months}개월)")
    print(f"  국가 수   : {len(BULK_COUNTRIES)}개")
    print(f"  조회 총계 : {total_fetched:,}건")
    print(f"  고유 이벤트: {total_unique:,}건")
    print(f"  소요 시간 : {elapsed:.1f}초")
    if not dry_run:
        print(f"  저장 위치 : {archive.db_path} → event_archive 테이블")
    print("=" * 60)

    # 월별 요약
    print("\n월별 집계:")
    for r in results:
        print(f"  {r['month']}: {r['unique']:>5,}건")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ACLED 과거 데이터를 event_archive에 베이스라인으로 적재한다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--months", type=int, default=12,
        help="조회할 과거 개월 수 (기본: 12)",
    )
    parser.add_argument(
        "--page-size", type=int, default=500,
        help="ACLED API 페이지당 최대 건수 (기본: 500)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="DB 저장 없이 건수만 확인",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(
        months=args.months,
        page_size=args.page_size,
        dry_run=args.dry_run,
    ))
