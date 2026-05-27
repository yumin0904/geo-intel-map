"""
backend/services/library/md_indexer.py

library/ 디렉토리의 마크다운 파일을 파싱하여 SQLite FTS5 인덱스를 구축한다.
TheoryLibraryView에 데이터를 공급하는 유일한 소스.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

import frontmatter  # python-frontmatter: YAML front matter 파싱 전용

logger = logging.getLogger(__name__)

# ── 경로 상수 ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # geo-intel-map/
LIBRARY_DIR = _PROJECT_ROOT / "library"
DB_PATH = Path(__file__).parent.parent.parent / "db" / "library.db"

# ── 도메인 상수 ────────────────────────────────────────────────────────────────
# CLAUDE.md 5대 섹터와 1:1 매핑 — 이 범위 밖 태그는 거부
ALLOWED_SECTOR_TAGS    = frozenset({"maritime", "energy", "techno", "indo_pacific", "gray_zone"})
ALLOWED_ASSET_TYPES    = frozenset({"theory", "case_study", "profile", "norm"})
ALLOWED_ERAS           = frozenset({"cold_war", "unipolar", "multipolar"})  # 레거시 era 필드
ALLOWED_TEMPORAL_ERAS  = frozenset({"cold_war", "post_cold", "us_china_rivalry", "hot"})  # 7대 축 §15
ALLOWED_USE_CASES      = frozenset({"concept", "case_study", "data", "norm"})
ALLOWED_LEVELS         = frozenset({"systemic", "state_domestic", "non_state"})
ALLOWED_INSTRUMENTS    = frozenset({"diplomatic", "informational", "military", "economic"})
ALLOWED_POSTURES       = frozenset({"status_quo", "revisionist"})

# asset_type → use_case 자동 파생 (front matter에 use_case 없을 때 적용)
_ASSET_TO_USE_CASE = {"theory": "concept", "case_study": "case_study", "profile": "data", "norm": "norm"}

REQUIRED_FIELDS = ("theory_id", "title", "sector_tag", "theorists", "year", "summary", "regions")

# ── DDL ────────────────────────────────────────────────────────────────────────
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS theories (
    theory_id          TEXT PRIMARY KEY,
    title              TEXT NOT NULL,
    sector_tag         TEXT NOT NULL,
    theorists          TEXT NOT NULL,   -- JSON 배열 문자열 (["Mahan", ...])
    year               INTEGER,
    summary            TEXT NOT NULL,
    regions            TEXT NOT NULL,   -- JSON 배열 문자열 (["taiwan_strait", ...])
    body               TEXT DEFAULT '',
    file_path          TEXT,
    updated_at         TEXT NOT NULL,
    asset_type         TEXT DEFAULT 'theory',
    era                TEXT,
    use_case           TEXT DEFAULT 'concept',
    -- 7대 축 다차원 태그 (CLAUDE.md §15) ─────────────────────────────
    geopol_region      TEXT,            -- 주 지정학 지역 코드
    temporal_era       TEXT,            -- cold_war|post_cold|us_china_rivalry|hot
    level_of_analysis  TEXT,            -- systemic|state_domestic|non_state
    instrument_of_power TEXT,           -- diplomatic|informational|military|economic
    strategic_posture  TEXT             -- status_quo|revisionist
);

-- FTS5 가상 테이블: theories 테이블을 content source로 사용
-- 제목·이론가·요약·지역·본문 전체를 전문 검색 대상으로 설정
CREATE VIRTUAL TABLE IF NOT EXISTS theories_fts USING fts5(
    title,
    theorists,
    summary,
    regions,
    body,
    content='theories',
    content_rowid='rowid'
);
"""


def _get_conn() -> sqlite3.Connection:
    """library.db 연결을 반환한다. DB 파일이 없으면 자동 생성하고 스키마를 적용한다."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    # 기존 DB에 신규 컬럼이 없으면 추가 (마이그레이션)
    _new_cols = [
        ("asset_type",          "'theory'"),
        ("era",                 "NULL"),
        ("use_case",            "'concept'"),
        ("geopol_region",       "NULL"),
        ("temporal_era",        "NULL"),
        ("level_of_analysis",   "NULL"),
        ("instrument_of_power", "NULL"),
        ("strategic_posture",   "NULL"),
    ]
    for col, default in _new_cols:
        try:
            conn.execute(f"ALTER TABLE theories ADD COLUMN {col} TEXT DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시
    return conn


def scan_library(library_dir: Path = LIBRARY_DIR) -> Iterator[Path]:
    """
    library/ 디렉토리를 재귀 순회하여 .md 파일 경로를 yield한다.

    숨김 파일(.으로 시작)과 숨김 디렉토리는 제외한다.
    """
    if not library_dir.exists():
        logger.warning("라이브러리 디렉토리가 없습니다: %s", library_dir)
        return

    for path in sorted(library_dir.rglob("*.md")):
        # .git, .obsidian 등 숨김 경로 제외
        if any(part.startswith(".") for part in path.parts):
            continue
        yield path


def parse_front_matter(path: Path) -> dict:
    """
    마크다운 파일의 YAML front matter를 파싱하고 필수 필드를 검증한다.

    Args:
        path: 파싱할 .md 파일 경로

    Returns:
        {"meta": {필드명: 값, ...}, "body": "본문 텍스트"}

    Raises:
        ValueError: 필수 필드 누락 또는 sector_tag 허용값 위반
    """
    post = frontmatter.load(str(path))
    meta = dict(post.metadata)

    # 필수 필드 존재 여부 검증
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"[{path.name}] 필수 필드 누락: {missing}")

    # sector_tag는 반드시 5대 섹터 중 하나여야 함 (범위 강제)
    tag = meta["sector_tag"]
    if tag not in ALLOWED_SECTOR_TAGS:
        raise ValueError(
            f"[{path.name}] 허용되지 않는 sector_tag: '{tag}'. "
            f"허용값: {sorted(ALLOWED_SECTOR_TAGS)}"
        )

    # asset_type / era: 선택 필드. 누락 시 기본값 적용
    asset_type = meta.get("asset_type", "theory")
    if asset_type not in ALLOWED_ASSET_TYPES:
        logger.warning("[%s] 허용되지 않는 asset_type '%s', 'theory'로 대체", path.name, asset_type)
        asset_type = "theory"
    meta["asset_type"] = asset_type

    era = meta.get("era")
    if era and era not in ALLOWED_ERAS:
        logger.warning("[%s] 허용되지 않는 era '%s', None으로 대체", path.name, era)
        era = None
    meta["era"] = era

    # use_case: front matter 명시 → 없으면 asset_type에서 자동 파생
    use_case = meta.get("use_case")
    if use_case not in ALLOWED_USE_CASES:
        use_case = _ASSET_TO_USE_CASE.get(meta["asset_type"], "concept")
    meta["use_case"] = use_case

    # ── 7대 축 필드 (§15) — 선택 필드, 허용값 외 값은 None으로 정규화 ──────
    geopol_region = meta.get("geopol_region")  # None이면 그대로 None
    meta["geopol_region"] = geopol_region

    temporal_era = meta.get("temporal_era")
    if temporal_era not in ALLOWED_TEMPORAL_ERAS:
        temporal_era = None
    meta["temporal_era"] = temporal_era

    level = meta.get("level_of_analysis")
    if level not in ALLOWED_LEVELS:
        level = None
    meta["level_of_analysis"] = level

    instrument = meta.get("instrument_of_power")
    if instrument not in ALLOWED_INSTRUMENTS:
        instrument = None
    meta["instrument_of_power"] = instrument

    posture = meta.get("strategic_posture")
    if posture not in ALLOWED_POSTURES:
        posture = None
    meta["strategic_posture"] = posture

    # list 타입 필드를 JSON 문자열로 직렬화 (SQLite TEXT 컬럼 저장용)
    for field in ("theorists", "regions"):
        val = meta[field]
        if isinstance(val, list):
            meta[field] = json.dumps(val, ensure_ascii=False)
        else:
            # YAML에서 단일 문자열로 기재된 경우 1-item 배열로 정규화
            meta[field] = json.dumps([str(val)], ensure_ascii=False)

    return {"meta": meta, "body": post.content}


def build_fts_index(library_dir: Path = LIBRARY_DIR) -> dict:
    """
    library/ 전체를 스캔하여 theories 테이블에 upsert하고
    FTS5 인덱스를 전체 재구축한다.

    소규모 라이브러리(< 100개)이므로 rebuild 방식이 가장 단순·안전하다.
    Row 단위 증분 갱신보다 rebuild가 FTS 인덱스 정합성을 보장한다.

    Returns:
        {"upserted": int, "skipped": int, "errors": list[str]}
    """
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()

    upserted = 0
    skipped = 0
    errors: list[str] = []

    try:
        for path in scan_library(library_dir):
            try:
                parsed = parse_front_matter(path)
            except ValueError as e:
                logger.warning("파싱 실패 — 건너뜀: %s", e)
                errors.append(str(e))
                skipped += 1
                continue

            meta = parsed["meta"]
            body = parsed["body"]

            conn.execute(
                """
                INSERT OR REPLACE INTO theories
                    (theory_id, title, sector_tag, theorists, year,
                     summary, regions, body, file_path, updated_at,
                     asset_type, era, use_case,
                     geopol_region, temporal_era, level_of_analysis,
                     instrument_of_power, strategic_posture)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meta["theory_id"],
                    meta["title"],
                    meta["sector_tag"],
                    meta["theorists"],
                    meta.get("year"),
                    meta["summary"],
                    meta["regions"],
                    body,
                    str(path.relative_to(_PROJECT_ROOT)),
                    now,
                    meta["asset_type"],
                    meta["era"],
                    meta["use_case"],
                    meta["geopol_region"],
                    meta["temporal_era"],
                    meta["level_of_analysis"],
                    meta["instrument_of_power"],
                    meta["strategic_posture"],
                ),
            )
            upserted += 1
            logger.debug("upserted: %s (%s)", meta["theory_id"], path.name)

        # INSERT OR REPLACE는 DELETE → INSERT 순으로 동작하므로
        # content FTS 테이블의 rowid 정합성이 깨질 수 있다.
        # rebuild 명령으로 theories 테이블 전체를 기준으로 FTS를 재구축한다.
        conn.execute("INSERT INTO theories_fts(theories_fts) VALUES ('rebuild')")
        conn.commit()

    finally:
        conn.close()

    logger.info(
        "인덱스 구축 완료 — upserted=%d, skipped=%d, errors=%d",
        upserted,
        skipped,
        len(errors),
    )
    return {"upserted": upserted, "skipped": skipped, "errors": errors}


def search_theories(query: str, limit: int = 20) -> list[dict]:
    """
    FTS5 전문 검색. 제목·요약·이론가·지역·본문 전체에서 검색한다.

    Args:
        query: 검색어. SQLite FTS5 쿼리 문법 사용 가능 (예: "Mahan OR 해양력")
        limit: 최대 반환 결과 수

    Returns:
        theory 딕셔너리 리스트 (FTS5 rank 오름차순 — 관련도 높을수록 앞)
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.theory_id, t.title, t.sector_tag,
                   t.theorists, t.year, t.summary, t.regions, t.file_path
            FROM theories t
            JOIN theories_fts f ON t.rowid = f.rowid
            WHERE theories_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_db_theory(theory_id: str) -> Optional[dict]:
    """
    SQLite에서 단일 이론을 반환한다. body 마크다운 본문 포함.

    theory_library.yaml에 없는 theory_id라도 SQLite에 직접 조회한다.
    없으면 None 반환.
    """
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM theories WHERE theory_id = ?", (theory_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_db_theories(sector_tag: Optional[str] = None) -> list[dict]:
    """
    SQLite에서 이론 목록을 반환한다. body 제외 (리스트 뷰 성능 최적화).

    DB가 비어있으면 빈 리스트 반환 — library/ 디렉토리에 .md 파일이 없을 때 정상.
    """
    conn = _get_conn()
    try:
        sql = (
            "SELECT theory_id, title, sector_tag, theorists, year, "
            "summary, regions, file_path, asset_type, era, use_case FROM theories"
        )
        conditions: list[str] = []
        params: list = []
        if sector_tag:
            conditions.append("sector_tag = ?")
            params.append(sector_tag)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    # python -m backend.services.library.md_indexer 로 직접 실행 시 인덱스 재구축
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = build_fts_index()
    print(f"결과: {result}")
