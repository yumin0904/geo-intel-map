-- schema.sql — intel.db 테이블 정의 (CLAUDE.md §18 계층형 TTL 정책)
-- archive_manager.py 초기화 시 자동 실행된다.

-- ── 핫 테이블 (이벤트 버퍼) ────────────────────────────────────────────────
-- GDELT/FIRMS/AIS/ADS-B 이벤트가 먼저 이 테이블에 적재된다.
-- TTL 정책에 따라 event_archive로 이관되거나 삭제된다.
CREATE TABLE IF NOT EXISTS events (
    id               TEXT PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    source_type      TEXT NOT NULL,      -- 'conflict' | 'fire' | 'naval' | 'military_flight'
    region_code      TEXT,
    severity         INTEGER DEFAULT 0,
    confidence_score REAL    DEFAULT 0.5,
    importance_score REAL    DEFAULT 0.0,
    is_staging       INTEGER DEFAULT 1,  -- 1=버퍼대기, 0=승격완료 (SQLite boolean)
    title            TEXT,
    description      TEXT,
    lat              REAL,
    lon              REAL,
    payload          TEXT,               -- JSON 직렬화
    theory_tags      TEXT,               -- JSON array 직렬화
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_region    ON events(region_code);
CREATE INDEX IF NOT EXISTS idx_events_source    ON events(source_type);
CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_staging   ON events(is_staging);

-- ── 영구 보관 테이블 ──────────────────────────────────────────────────────
-- 고가치 자산 및 ACLED 베이스라인을 영구 보존한다. 삭제 금지.
CREATE TABLE IF NOT EXISTS event_archive (
    id               TEXT PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    source_type      TEXT NOT NULL,
    region_code      TEXT,
    severity         INTEGER DEFAULT 0,
    confidence_score REAL    DEFAULT 1.0,
    importance_score REAL    DEFAULT 0.0,
    title            TEXT,
    description      TEXT,
    payload          TEXT,               -- JSON
    theory_tags      TEXT,               -- JSON array
    archived_at      TEXT NOT NULL,
    archive_reason   TEXT                -- 'acled_baseline' | 'high_confidence' | 'cascade_linked'
);

CREATE INDEX IF NOT EXISTS idx_archive_region   ON event_archive(region_code);
CREATE INDEX IF NOT EXISTS idx_archive_source   ON event_archive(source_type);
CREATE INDEX IF NOT EXISTS idx_archive_ts       ON event_archive(timestamp);
CREATE INDEX IF NOT EXISTS idx_archive_reason   ON event_archive(archive_reason);

-- ── 물리 센서 스냅샷 (Verification Funnel Stage 3) ────────────────────────
-- FIRMS 열점 / AIS 선박 / ADS-B 군용기의 시간·위치 스냅샷.
-- 검증 펀넬에서 근접 센서 증거로 활용. TTL 24-48h 자동 소멸.
CREATE TABLE IF NOT EXISTS sensor_snapshots (
    id          TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,    -- 'fire' | 'naval' | 'military_flight'
    timestamp   TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    region_code TEXT,
    payload     TEXT              -- JSON (원본 소스별 추가 필드)
);

CREATE INDEX IF NOT EXISTS idx_sensor_ts     ON sensor_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_sensor_type   ON sensor_snapshots(source_type);
CREATE INDEX IF NOT EXISTS idx_sensor_latlon ON sensor_snapshots(lat, lon);
