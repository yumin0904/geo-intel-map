"""
scripts/retag_sahel_events.py

[Cycle 7-D L3-a] event_archive 사헬 이벤트 재태깅.

배경: ACLED 대량 적재 시 사헬 국가(Mali·Niger·Burkina Faso·Chad·Sudan·
Mauritania·Nigeria) 이벤트는 region_code가 비어 있어(NULL) Granger·Cascade
검증에서 제외되었다. 데이터는 이미 event_archive에 존재하므로 ACLED API
재호출 없이 region_code = "sahel"만 부여하면 검증 가능해진다.

판정 근거(2026-06-06 스캔): 사헬 핵심국 합산 약 1.9만건 적재 확인.
북극(Russia)은 대부분 우크라이나 전선이라 제외, India는 국내 분쟁 노이즈라 제외.

실행:
    python3 backend/scripts/retag_sahel_events.py          # dry-run (집계만)
    python3 backend/scripts/retag_sahel_events.py --commit  # 실제 UPDATE
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# 사헬 지역 핵심 국가 — 지하디스트 반란·쿠데타 벨트 (ACLED country 필드 기준)
_SAHEL_COUNTRIES = {
    "Mali", "Niger", "Burkina Faso", "Chad", "Sudan",
    "Mauritania", "Nigeria",  # 북부 나이지리아 = Boko Haram/ISWAP
}


def _extract_country(payload: str | None) -> str | None:
    """payload JSON에서 country 필드 추출."""
    if not payload:
        return None
    try:
        p = json.loads(payload)
        return p.get("country") or p.get("actor1") or None
    except (json.JSONDecodeError, AttributeError):
        return None


def main(commit: bool) -> None:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row

    # region_code 미부여(NULL) 이벤트만 대상 — 기존 태깅 보존
    rows = con.execute(
        "SELECT id, payload FROM event_archive WHERE region_code IS NULL"
    ).fetchall()

    target_ids: list[str] = []
    from collections import Counter
    by_country: Counter = Counter()

    for r in rows:
        country = _extract_country(r["payload"])
        if country in _SAHEL_COUNTRIES:
            target_ids.append(r["id"])
            by_country[country] += 1

    logger.info("=== 사헬 재태깅 대상 (region_code IS NULL) ===")
    for c, n in by_country.most_common():
        logger.info("  %-16s %6d건", c, n)
    logger.info("  합계: %d건", len(target_ids))

    if not commit:
        logger.info("[DRY-RUN] --commit 플래그로 실제 UPDATE 실행")
        con.close()
        return

    # 배치 UPDATE
    cur = con.cursor()
    cur.executemany(
        "UPDATE event_archive SET region_code = 'sahel' WHERE id = ?",
        [(tid,) for tid in target_ids],
    )
    con.commit()
    logger.info("✅ %d건 region_code='sahel' 부여 완료", cur.rowcount)

    # 검증: 사헬 일별 시계열 비제로 일수 확인 (Granger 충분성)
    nonzero = con.execute(
        """
        SELECT COUNT(DISTINCT DATE(timestamp)) AS days
        FROM event_archive
        WHERE region_code = 'sahel'
          AND DATE(timestamp) >= DATE('now', '-24 months')
        """
    ).fetchone()
    logger.info("  최근 24개월 사헬 이벤트 발생 일수: %d일", nonzero["days"])
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="사헬 이벤트 region_code 재태깅")
    parser.add_argument("--commit", action="store_true", help="실제 UPDATE 실행")
    args = parser.parse_args()
    main(args.commit)
