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

-- ── FRED 거시지표 베이스라인 ───────────────────────────────────────────────
-- WTI·금·원달러·대만달러·VIX 일별 종가. baseline_bulk_ingest.py 로 적재.
CREATE TABLE IF NOT EXISTS historical_macro_indices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id   TEXT NOT NULL,   -- FRED series ID (예: 'DCOILWTICO')
    indicator   TEXT NOT NULL,   -- 지표명 (예: 'wti', 'gold', 'usd_krw', 'usd_twd', 'vix')
    date        TEXT NOT NULL,   -- YYYY-MM-DD
    value       REAL NOT NULL,
    source      TEXT DEFAULT 'FRED',
    ingested_at TEXT NOT NULL,
    UNIQUE (series_id, date)
);

CREATE INDEX IF NOT EXISTS idx_macro_indicator ON historical_macro_indices(indicator, date);

-- ── UN Comtrade 무역 의존도 베이스라인 ────────────────────────────────────
-- HS 27(에너지)·8542(반도체)·26(희토류) 연간 수출입. baseline_bulk_ingest.py 로 적재.
-- dependency_ratio: 양자 무역액 / 보고국 전체(WLD) 무역액 (0~1)
CREATE TABLE IF NOT EXISTS historical_trade_matrix (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    period           TEXT NOT NULL,   -- 'YYYY'
    reporter_iso     TEXT NOT NULL,   -- ISO 3자리 (예: 'TWN', 'CHN', 'USA')
    partner_iso      TEXT NOT NULL,   -- ISO 3자리 또는 'WLD' (전 세계 합계)
    hs_code          TEXT NOT NULL,   -- '27' | '8542' | '26'
    trade_flow       TEXT NOT NULL,   -- 'M' (수입) | 'X' (수출)
    trade_value_usd  REAL,
    netweight_kg     REAL,
    dependency_ratio REAL,           -- 자동 계산: bilateral / world_total
    source           TEXT DEFAULT 'UN_Comtrade',
    ingested_at      TEXT NOT NULL,
    UNIQUE (period, reporter_iso, partner_iso, hs_code, trade_flow)
);

CREATE INDEX IF NOT EXISTS idx_trade_reporter ON historical_trade_matrix(reporter_iso, partner_iso, hs_code);

-- ── Cascade 링크 (신뢰도 0.6 이상만 저장) ───────────────────────────────
-- correlation_score = pct_change / (threshold_pct × 2)
-- 0.6 이상 = 임계값의 1.2배 이상 시장 반응 → 노이즈 필터 통과
CREATE TABLE IF NOT EXISTS cascade_links (
    id                  TEXT PRIMARY KEY,
    source_event_id     TEXT NOT NULL,
    target_event_id     TEXT NOT NULL,
    link_type           TEXT NOT NULL DEFAULT 'rule',  -- 'rule' | 'chain' | 'statistical'
    rule_id             TEXT,
    rule_name           TEXT,
    correlation_score   REAL NOT NULL,
    time_delta_seconds  INTEGER NOT NULL,
    depth               INTEGER NOT NULL DEFAULT 1,
    parent_link_id      TEXT,            -- 체인 2단계+ 링크의 부모 링크 ID
    theory_ref          TEXT,
    evidence            TEXT,            -- JSON 직렬화
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (source_event_id, target_event_id, rule_id)
);

CREATE INDEX IF NOT EXISTS idx_cascade_source ON cascade_links(source_event_id);
CREATE INDEX IF NOT EXISTS idx_cascade_target ON cascade_links(target_event_id);
CREATE INDEX IF NOT EXISTS idx_cascade_score  ON cascade_links(correlation_score DESC);

-- 인사이트 분석실 저장 이력
CREATE TABLE IF NOT EXISTS intel_analyses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,          -- 쿼리 앞 30자 자동 생성
    query        TEXT NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'insight',
    regions      TEXT,                   -- JSON 배열
    sectors      TEXT,                   -- JSON 배열
    result_md    TEXT NOT NULL,          -- Gemini 출력 마크다운
    context_chars    INTEGER DEFAULT 0,  -- 컨텍스트 총 글자 수 (품질 지표)
    confidence_score INTEGER DEFAULT NULL, -- §19-D 역산 점수 (0~100)
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_intel_created ON intel_analyses(created_at DESC);

-- IA-Engine-B1: 외부 정형 데이터 (SIPRI · COW · Kiel)

CREATE TABLE IF NOT EXISTS sipri_milex (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    iso3         TEXT NOT NULL,
    country_name TEXT,
    year         INTEGER NOT NULL,
    gdp_pct      REAL,         -- 국방비 % of GDP
    usd_mn_2022  REAL,         -- USD millions (2022 constant prices)
    UNIQUE(iso3, year)
);

CREATE INDEX IF NOT EXISTS idx_sipri_iso3_year ON sipri_milex(iso3, year DESC);

CREATE TABLE IF NOT EXISTS cow_alliances (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    iso3_a       TEXT NOT NULL,
    iso3_b       TEXT NOT NULL,
    name_a       TEXT,
    name_b       TEXT,
    start_year   INTEGER,
    end_year     INTEGER,       -- NULL = 현재 활성
    alliance_type TEXT,         -- defense / neutrality / nonaggression / consultation
    UNIQUE(iso3_a, iso3_b, start_year)
);

CREATE INDEX IF NOT EXISTS idx_cow_iso3_a ON cow_alliances(iso3_a);
CREATE INDEX IF NOT EXISTS idx_cow_iso3_b ON cow_alliances(iso3_b);

-- IA-Engine-B2: EIA Energy + CSIS Cyber

CREATE TABLE IF NOT EXISTS eia_energy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    iso3            TEXT NOT NULL,
    country_name    TEXT,
    crude_prod_mbpd REAL,        -- 원유 생산량 (백만 배럴/일)
    natgas_prod_bcfd REAL,       -- 천연가스 생산량 (십억 입방피트/일)
    oil_export_mbpd REAL,        -- 원유 수출량
    data_year       INTEGER,
    UNIQUE(iso3, data_year)
);

CREATE TABLE IF NOT EXISTS csis_cyber_incidents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id    TEXT UNIQUE,
    incident_date  TEXT,
    actor_iso3     TEXT,
    actor_group    TEXT,
    victim_iso3    TEXT,
    victim_sector  TEXT,         -- government/military/energy/finance/telecom/...
    incident_type  TEXT,         -- espionage/sabotage/ransomware/ddos/...
    title          TEXT,
    description    TEXT
);

CREATE INDEX IF NOT EXISTS idx_csis_actor  ON csis_cyber_incidents(actor_iso3);
CREATE INDEX IF NOT EXISTS idx_csis_victim ON csis_cyber_incidents(victim_iso3);
CREATE INDEX IF NOT EXISTS idx_csis_date   ON csis_cyber_incidents(incident_date DESC);
CREATE INDEX IF NOT EXISTS idx_csis_type   ON csis_cyber_incidents(incident_type);

CREATE TABLE IF NOT EXISTS kiel_ukraine_support (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_iso3       TEXT,
    donor_name       TEXT NOT NULL,
    military_eur_bn  REAL DEFAULT 0,
    financial_eur_bn REAL DEFAULT 0,
    humanitarian_eur_bn REAL DEFAULT 0,
    total_eur_bn     REAL DEFAULT 0,
    data_period      TEXT,       -- 예: "2022-01~2024-12"
    updated_at       TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(donor_iso3, data_period)
);

-- IA-Engine Cycle 6-A: 외부 데이터 2차 적재

CREATE TABLE IF NOT EXISTS sipri_arms_transfers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_iso3    TEXT NOT NULL,
    supplier_name    TEXT,
    recipient_iso3   TEXT NOT NULL,
    recipient_name   TEXT,
    year             INTEGER NOT NULL,
    tiv_mn           REAL,           -- SIPRI TIV (백만 달러 환산 표준화 지수)
    weapon_category  TEXT,           -- aircraft/missile/armoured_vehicle/naval/air_defence/other
    notes            TEXT,
    UNIQUE(supplier_iso3, recipient_iso3, year, weapon_category)
);

CREATE INDEX IF NOT EXISTS idx_arms_supplier  ON sipri_arms_transfers(supplier_iso3, year DESC);
CREATE INDEX IF NOT EXISTS idx_arms_recipient ON sipri_arms_transfers(recipient_iso3, year DESC);

CREATE TABLE IF NOT EXISTS vdem_index (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    iso3          TEXT NOT NULL,
    country_name  TEXT,
    year          INTEGER NOT NULL,
    v2x_libdem    REAL,   -- 자유민주주의 지수 (0-1)
    v2x_regime    INTEGER, -- 0=폐쇄권위, 1=선거권위, 2=선거민주, 3=자유민주
    v2x_polyarchy REAL,   -- 선거민주주의 지수 (0-1)
    v2x_corr      REAL,   -- 정치부패 지수 (0=낮음, 1=높음)
    notes         TEXT,
    UNIQUE(iso3, year)
);

CREATE INDEX IF NOT EXISTS idx_vdem_iso3_year ON vdem_index(iso3, year DESC);
CREATE INDEX IF NOT EXISTS idx_vdem_regime    ON vdem_index(v2x_regime);

CREATE TABLE IF NOT EXISTS cow_wars (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    war_id       INTEGER UNIQUE,
    war_name     TEXT NOT NULL,
    start_year   INTEGER,
    end_year     INTEGER,           -- NULL = 진행 중
    side_a_iso3  TEXT,              -- 파이프(|)로 다국 구분
    side_b_iso3  TEXT,
    region       TEXT,              -- eastern_europe/middle_east/asia/...
    battle_deaths INTEGER,
    outcome      INTEGER,           -- 1=A승/2=B승/3=협상/4=정전/5=진행중
    relevance_tag TEXT              -- 지정학 분석 관련 지역 태그
);

CREATE INDEX IF NOT EXISTS idx_cow_wars_region ON cow_wars(region);
CREATE INDEX IF NOT EXISTS idx_cow_wars_year   ON cow_wars(start_year);
