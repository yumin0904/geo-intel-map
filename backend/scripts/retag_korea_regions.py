"""
scripts/retag_korea_regions.py

[판례 20260709-nk-region-bbox-contamination] Korea권 region_code 오염 소급 수리.

배경: north_korea bbox 남위 경계(37.5N)가 서울을 물어 남한 시위 3,136건(events)·
3,128건(event_archive)이 '북한 도발' 버킷에 배정됐고, korean_peninsula bbox 경계
정밀도 갭으로 제주·독도 이벤트 183건이 east_china_sea로 낙하했다.
수리된 배정 규칙(region_for_event: 행위자 1차 → 발생국 2차 → bbox 폴백)을
기존 행에 소급 적용한다.

원자성(방법론 심사석 필수 조건): region_code와 theory_tags를 동시 재유도한다 —
theory_tags는 인제스트 시 region_code로 파생되므로 region만 고치면
"region=korean_peninsula인데 태그는 북한 파생"인 모순 행이 생긴다.

대상: events(좌표 있음 — region_for_event 전체 경로) +
      event_archive(좌표 없음 — 행위자/발생국 신호만, 신호 없으면 보존)
      중 region_code IN (north_korea, korean_peninsula, east_china_sea).
비ACLED 행(payload에 ACLED 필드 없음)은 region만 재배정하고 태그는 보존한다.

실행:
    PYTHONPATH=. .venv/bin/python scripts/retag_korea_regions.py           # dry-run
    PYTHONPATH=. .venv/bin/python scripts/retag_korea_regions.py --commit  # 실제 UPDATE
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.acled import _build_theory_tags  # noqa: E402
from services.region import region_for_event, region_for_point  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# 수리 대상 버킷 — Korea권 3개 region만 (다른 region은 이번 판례 범위 밖)
_TARGET_REGIONS = ("north_korea", "korean_peninsula", "east_china_sea")


def _reassign(payload: dict, lat: float | None, lon: float | None,
              current: str) -> str:
    """수리된 배정 규칙을 한 행에 적용한다.

    좌표가 있으면(events) region_for_event 전체 경로,
    없으면(event_archive) 행위자/발생국 신호만 — 신호가 없으면 현행 유지
    (좌표 없이 bbox 폴백이 불가능하므로 추측 재배정을 하지 않는다: 정직성 원칙).
    """
    country = payload.get("country", "") or ""
    actors = (payload.get("actor1", "") or "", payload.get("actor2", "") or "")

    if lat is not None and lon is not None and not (lat == 0.0 and lon == 0.0):
        return region_for_event(lat, lon, country=country, actors=actors) or current

    # 좌표 없음 — 신호 기반 판정만 (region_for_event의 1·2차와 동일 로직)
    if any("North Korea" in a for a in actors):
        return "north_korea"
    if country == "North Korea":
        return "north_korea"
    if country == "South Korea":
        return "korean_peninsula"
    return current


def _retag_table(con: sqlite3.Connection, table: str, has_coords: bool,
                 commit: bool) -> dict:
    """한 테이블의 대상 행을 재배정하고 (from→to) 통계를 반환한다."""
    placeholders = ",".join("?" for _ in _TARGET_REGIONS)
    cols = "id, region_code, payload" + (", lat, lon" if has_coords else "")
    rows = con.execute(
        f"SELECT {cols} FROM {table} WHERE region_code IN ({placeholders})",
        _TARGET_REGIONS,
    ).fetchall()

    moves: Counter = Counter()
    tag_updates = 0
    updates: list[tuple] = []

    for row in rows:
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}

        lat = row["lat"] if has_coords else None
        lon = row["lon"] if has_coords else None
        new_region = _reassign(payload, lat, lon, row["region_code"])

        if new_region == row["region_code"]:
            continue
        moves[(row["region_code"], new_region)] += 1

        # ACLED 행만 theory_tags 재유도 — 태그가 region_code 파생이므로 원자적 동반 수정
        if payload.get("data_source") == "ACLED":
            new_tags = _build_theory_tags(
                payload.get("event_type", ""),
                payload.get("sub_event_type", ""),
                int(payload.get("inter1", 0) or 0),
                int(payload.get("inter2", 0) or 0),
                new_region,
                country=payload.get("country", "") or "",
            )
            updates.append((new_region, json.dumps(new_tags, ensure_ascii=False),
                            row["id"]))
            tag_updates += 1
        else:
            updates.append((new_region, None, row["id"]))

    if commit:
        for new_region, tags_json, row_id in updates:
            if tags_json is not None:
                con.execute(
                    f"UPDATE {table} SET region_code = ?, theory_tags = ? WHERE id = ?",
                    (new_region, tags_json, row_id),
                )
            else:
                con.execute(
                    f"UPDATE {table} SET region_code = ? WHERE id = ?",
                    (new_region, row_id),
                )

    return {"scanned": len(rows), "moved": sum(moves.values()),
            "moves": moves, "tag_updates": tag_updates}


def _verify(con: sqlite3.Connection) -> None:
    """수리 후 순도 검증 — north_korea 버킷의 발생국 분포 (전량 NK/신호행이어야 정상)."""
    for table in ("events", "event_archive"):
        dist = con.execute(
            f"""SELECT COALESCE(json_extract(payload, '$.country'), '(payload 없음)') AS c,
                       COUNT(*) FROM {table}
                WHERE region_code = 'north_korea' GROUP BY c ORDER BY 2 DESC"""
        ).fetchall()
        logger.info("[검증] %s north_korea 버킷 발생국 분포: %s",
                    table, {r[0]: r[1] for r in dist})


def main(commit: bool) -> None:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row

    for table, has_coords in (("events", True), ("event_archive", False)):
        stats = _retag_table(con, table, has_coords, commit)
        logger.info("[%s] %s: 스캔 %d행 → 이동 %d행 (theory_tags 재유도 %d행)",
                    "COMMIT" if commit else "DRY-RUN", table,
                    stats["scanned"], stats["moved"], stats["tag_updates"])
        for (src, dst), n in sorted(stats["moves"].items(), key=lambda x: -x[1]):
            logger.info("    %s → %s: %d행", src, dst, n)

    if commit:
        con.commit()
        _verify(con)
        logger.info("커밋 완료.")
    else:
        logger.info("dry-run — DB 무변경. 실제 적용은 --commit.")
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Korea권 region_code 소급 수리")
    parser.add_argument("--commit", action="store_true", help="실제 UPDATE 수행")
    main(parser.parse_args().commit)
