"""
archive_manager.py — 계층형 데이터 보관 관리자 (TTL Tiered Archive)

CLAUDE.md §18 TTL 정책:
  GDELT/RSS 미검증(confidence<0.8, importance<0.7)  → 72h 후 완전 삭제
  GDELT/RSS 고가치(confidence≥0.8 or importance≥0.7) → event_archive 이관 후 핫삭제
  ACLED                                             → 인입 즉시 event_archive 귀속 (베이스라인)
  FIRMS                                             → 48h, 미매칭 삭제
  AIS/ADS-B                                         → 24h, 미매칭 삭제

APScheduler에 의해 1시간마다 run_full_cycle() 호출.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.event import Event

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent / "intel.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# 승격 기준 (CLAUDE.md §16)
_ARCHIVE_CONFIDENCE_MIN = 0.8
_ARCHIVE_IMPORTANCE_MIN = 0.7

# source_type → 핫 테이블 보관 시간 (hours)
_TTL_HOURS: dict[str, int] = {
    "conflict":        72,   # GDELT 분쟁 (source_type='conflict', data_source='GDELT')
    "fire":            48,   # FIRMS 화재/열점
    "naval":           24,   # AIS 선박
    "military_flight": 24,   # ADS-B 군용기
}


class ArchiveManager:
    """SQLite intel.db 기반 TTL 계층형 보관 관리자."""

    def __init__(self, db_path: str | Path = _DB_PATH) -> None:
        self.db_path = Path(db_path)

    def init_schema(self) -> None:
        """schema.sql로 테이블을 초기화한다. 앱 시작 시 한 번 호출."""
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as con:
            con.executescript(ddl)
        logger.info("[Archive] 스키마 초기화 완료: %s", self.db_path)

    def run_full_cycle(self) -> dict:
        """전체 보관 사이클 실행. APScheduler에서 1시간마다 호출.

        Returns:
            dict — 단계별 처리 건수 요약
        """
        summary: dict[str, int] = {}
        try:
            with self._connect() as con:
                summary["acled_archived"]  = self._archive_acled(con)
                summary["gdelt_promoted"]  = self._promote_high_value(con)
                summary["expired_deleted"] = self._delete_expired(con)
                summary["sensor_pruned"]   = self._prune_sensors(con)
            logger.info("[Archive] 사이클 완료: %s", summary)
        except Exception as exc:
            logger.error("[Archive] 사이클 오류: %s", exc)
        return summary

    def archive_single(self, event_id: str, reason: str = "cascade_linked") -> bool:
        """단일 이벤트를 즉시 archive로 이관 (Cascade 매칭 콜백용)."""
        try:
            with self._connect() as con:
                return self._move_to_archive(con, event_id, reason)
        except Exception as exc:
            logger.warning("[Archive] archive_single 실패 (id=%s): %s", event_id, exc)
            return False

    def write_events(self, events: list[Event]) -> int:
        """Event 목록을 핫 테이블에 기록한다.

        GDELT 파이프라인 또는 ACLED 커넥터에서 호출해 이벤트를 영속화한다.
        ACLED 이벤트(data_source='ACLED')는 즉시 event_archive에도 귀속된다.
        """
        if not events:
            return 0
        written = 0
        with self._connect() as con:
            for evt in events:
                lat, lon = evt.location
                data_source = evt.payload.get("data_source", "")
                try:
                    con.execute(
                        """
                        INSERT OR REPLACE INTO events
                        (id, timestamp, source_type, region_code, severity,
                         confidence_score, importance_score, is_staging,
                         title, description, lat, lon, payload, theory_tags, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            evt.id,
                            evt.timestamp.isoformat(),
                            evt.source_type,
                            evt.region_code,
                            evt.severity,
                            evt.confidence_score,
                            evt.importance_score,
                            1 if evt.is_staging else 0,
                            evt.title,
                            evt.description,
                            round(lat, 5),
                            round(lon, 5),
                            json.dumps(evt.payload, ensure_ascii=False),
                            json.dumps(evt.theory_tags, ensure_ascii=False),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    written += 1

                    # ACLED는 핫 테이블 기록과 동시에 archive 귀속
                    if data_source == "ACLED":
                        self._insert_archive_from_event(con, evt, "acled_baseline")

                except Exception as exc:
                    logger.warning("[Archive] write_events 실패 (id=%s): %s", evt.id, exc)

        logger.debug("[Archive] %d개 이벤트 핫 테이블 기록", written)
        return written

    def write_sensor_snapshot(
        self,
        event_id: str,
        source_type: str,
        lat: float,
        lon: float,
        timestamp: datetime,
        region_code: str | None = None,
        payload: dict | None = None,
    ) -> None:
        """물리 센서(FIRMS/AIS/ADS-B) 스냅샷을 sensor_snapshots에 기록한다."""
        try:
            with self._connect() as con:
                con.execute(
                    """
                    INSERT OR IGNORE INTO sensor_snapshots
                    (id, source_type, timestamp, lat, lon, region_code, payload)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        event_id,
                        source_type,
                        timestamp.isoformat(),
                        round(lat, 5),
                        round(lon, 5),
                        region_code,
                        json.dumps(payload or {}, ensure_ascii=False),
                    ),
                )
        except Exception as exc:
            logger.debug("[Archive] sensor_snapshot 기록 실패: %s", exc)

    # ── 내부 사이클 단계 ─────────────────────────────────────────────────────

    def _archive_acled(self, con: sqlite3.Connection) -> int:
        """핫 테이블의 ACLED 이벤트를 event_archive에 복사 (핫 테이블 보존).

        payload JSON에서 data_source='ACLED'를 식별한다.
        """
        rows = con.execute(
            """
            SELECT * FROM events
             WHERE source_type = 'conflict'
               AND json_extract(payload, '$.data_source') = 'ACLED'
               AND id NOT IN (SELECT id FROM event_archive)
            """
        ).fetchall()

        count = 0
        for row in rows:
            try:
                self._insert_archive(con, dict(row), "acled_baseline")
                count += 1
            except sqlite3.IntegrityError:
                pass  # 이미 존재하면 skip

        if count:
            logger.info("[Archive] ACLED 베이스라인 %d건 archive 귀속", count)
        return count

    def _promote_high_value(self, con: sqlite3.Connection) -> int:
        """고가치 GDELT 이벤트를 event_archive로 이관하고 핫 테이블에서 제거."""
        rows = con.execute(
            """
            SELECT * FROM events
             WHERE source_type = 'conflict'
               AND json_extract(payload, '$.data_source') = 'GDELT'
               AND (confidence_score >= ? OR importance_score >= ?)
               AND id NOT IN (SELECT id FROM event_archive)
            """,
            (_ARCHIVE_CONFIDENCE_MIN, _ARCHIVE_IMPORTANCE_MIN),
        ).fetchall()

        count = 0
        for row in rows:
            try:
                self._insert_archive(con, dict(row), "high_confidence")
                con.execute("DELETE FROM events WHERE id = ?", (row["id"],))
                count += 1
            except Exception as exc:
                logger.warning("[Archive] 고가치 이관 실패 (id=%s): %s", row["id"], exc)

        if count:
            logger.info("[Archive] 고가치 GDELT %d건 archive 이관", count)
        return count

    def _delete_expired(self, con: sqlite3.Connection) -> int:
        """TTL 초과·미검증 이벤트 완전 삭제."""
        total = 0
        now = datetime.now(timezone.utc)

        for source_type, ttl_h in _TTL_HOURS.items():
            cutoff = (now - timedelta(hours=ttl_h)).isoformat()
            result = con.execute(
                """
                DELETE FROM events
                 WHERE source_type = ?
                   AND timestamp < ?
                   AND confidence_score < ?
                   AND importance_score < ?
                   AND id NOT IN (SELECT id FROM event_archive)
                """,
                (source_type, cutoff,
                 _ARCHIVE_CONFIDENCE_MIN, _ARCHIVE_IMPORTANCE_MIN),
            )
            if result.rowcount:
                logger.info("[Archive] TTL 삭제: type=%s, %d건", source_type, result.rowcount)
            total += result.rowcount

        return total

    def _prune_sensors(self, con: sqlite3.Connection) -> int:
        """물리 센서 스냅샷 중 TTL 초과분 삭제.

        cascade_links 테이블이 없는 경우 graceful fallback — 단순 시간 기준으로만 삭제.
        """
        now = datetime.now(timezone.utc)
        cutoff_48h = (now - timedelta(hours=48)).isoformat()
        cutoff_24h = (now - timedelta(hours=24)).isoformat()

        # cascade_links 테이블 존재 여부 확인
        has_cascade_table = _table_exists(con, "cascade_links")

        pruned = 0

        if has_cascade_table:
            # cascade 매칭된 센서는 보존
            r1 = con.execute(
                """
                DELETE FROM sensor_snapshots
                 WHERE source_type = 'fire' AND timestamp < ?
                   AND id NOT IN (
                       SELECT source_event_id FROM cascade_links
                       UNION ALL
                       SELECT target_event_id FROM cascade_links
                   )
                """,
                (cutoff_48h,),
            )
            r2 = con.execute(
                """
                DELETE FROM sensor_snapshots
                 WHERE source_type IN ('naval', 'military_flight')
                   AND timestamp < ?
                   AND id NOT IN (
                       SELECT source_event_id FROM cascade_links
                       UNION ALL
                       SELECT target_event_id FROM cascade_links
                   )
                """,
                (cutoff_24h,),
            )
        else:
            # cascade_links 없음 — 시간 기준만 적용
            r1 = con.execute(
                "DELETE FROM sensor_snapshots WHERE source_type = 'fire' AND timestamp < ?",
                (cutoff_48h,),
            )
            r2 = con.execute(
                "DELETE FROM sensor_snapshots WHERE source_type IN ('naval','military_flight') AND timestamp < ?",
                (cutoff_24h,),
            )

        pruned = r1.rowcount + r2.rowcount
        if pruned:
            logger.info("[Archive] 센서 스냅샷 %d건 정리", pruned)
        return pruned

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _move_to_archive(
        self, con: sqlite3.Connection, event_id: str, reason: str
    ) -> bool:
        """핫 테이블의 단일 이벤트를 archive로 이관."""
        row = con.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if not row:
            return False
        self._insert_archive(con, dict(row), reason)
        con.execute("DELETE FROM events WHERE id = ?", (event_id,))
        return True

    def _insert_archive(
        self, con: sqlite3.Connection, row: dict, reason: str
    ) -> None:
        """events 행 dict → event_archive 삽입."""
        con.execute(
            """
            INSERT OR IGNORE INTO event_archive
            (id, timestamp, source_type, region_code, severity,
             confidence_score, importance_score, title, description,
             payload, theory_tags, archived_at, archive_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("id"),
                row.get("timestamp"),
                row.get("source_type"),
                row.get("region_code"),
                row.get("severity", 0),
                row.get("confidence_score", 1.0),
                row.get("importance_score", 0.0),
                row.get("title"),
                row.get("description"),
                row.get("payload"),
                row.get("theory_tags"),
                datetime.now(timezone.utc).isoformat(),
                reason,
            ),
        )

    def _insert_archive_from_event(
        self, con: sqlite3.Connection, evt: Event, reason: str
    ) -> None:
        """Event 객체 → event_archive 직접 삽입 (write_events 내부용)."""
        try:
            con.execute(
                """
                INSERT OR IGNORE INTO event_archive
                (id, timestamp, source_type, region_code, severity,
                 confidence_score, importance_score, title, description,
                 payload, theory_tags, archived_at, archive_reason)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    evt.id,
                    evt.timestamp.isoformat(),
                    evt.source_type,
                    evt.region_code,
                    evt.severity,
                    evt.confidence_score,
                    evt.importance_score,
                    evt.title,
                    evt.description,
                    json.dumps(evt.payload, ensure_ascii=False),
                    json.dumps(evt.theory_tags, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                    reason,
                ),
            )
        except Exception as exc:
            logger.debug("[Archive] _insert_archive_from_event 실패: %s", exc)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    """sqlite_master에서 테이블 존재 여부를 확인한다."""
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None
