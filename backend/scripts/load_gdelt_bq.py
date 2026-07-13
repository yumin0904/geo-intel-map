"""
scripts/load_gdelt_bq.py

GDELT 국가급 일간 카운트 백필 (BigQuery `gdelt-bq.gdeltv2.events` → intel.db).

━━ 2026-07-13 구성 타당도 수리 (엔진수리위 GDELT 재적재석) ━━━━━━━━━━━━━━━━━━━━

**결함 1 — 잘못된 키.** 구 로더는 `Actor1CountryCode`(행위자 국적)로 집계했다.
  그건 "사건이 어디서 일어났나"가 아니라 "누가 등장했나"다. 그래서 세계 어디서
  일어난 사건이든 모나코 국적 행위자가 코딩되면 '모나코의 물리적 충돌'로 셌다.
  → 신 테이블 `gdelt_geo_country_daily`는 **`ActionGeo_CountryCode`(발생지)** 로 센다.

**결함 2 — CAMEO 코더의 스포츠 오탐.** 발생지 키로 바꿔도 안 고쳐진다. 모나코의
  2026-06 물리충돌 279건은 발생지 기준으로도 **전부 F1 그랑프리 기사**였다
  (실측: "MONACO vs POLE"=폴 포지션, 행위자 MONEGASQUE, 출처 formula1.com).
  → **행위자 유형 필터**(config/gdelt_actor_types.yaml)로 국가기구·무장조직 쌍만
    세는 `*_pol` 카운트를 **병기**한다. 모나코 279→2, 룩셈부르크 208→0,
    우크라이나 30,999→1,065 (전쟁국 신호는 유지).

**아무것도 버리지 않는다 (설계 제약).**
  - 구 테이블 `gdelt_country_daily`(행위자 국적 키)는 **그대로 둔다.** 행위자 국적은
    "누가 이 사건에 등장하는가"라는 별개 구성개념이고 나름의 용도가 있다.
    이 스크립트로 계속 갱신할 수 있다 (`--target actor`).
  - 신 테이블은 **원본 카운트와 필터 카운트를 둘 다** 적재한다. 소비자가 고르고,
    필터가 과했는지 나중에 검증할 수 있어야 한다 (우크라이나도 96.6%가 떨어진다 —
    그게 옳은지는 데이터가 말하게 하라).
  - 미매핑 FIPS(해양 지오코딩 등)도 원본 fips를 남기고 country_iso3만 NULL로 적재.

**왜 새 테이블인가 (마이그레이션 선택 근거).**
  행 키 자체가 바뀌기 때문이다. 한 이벤트는 행위자 국적과 발생지를 **둘 다** 갖고,
  둘은 대개 다르다. 같은 테이블에 컬럼만 추가하려면 (a) 키를 발생지로 바꿔
  기존 계열을 파괴하거나 (b) (day, actor, geo) 3키로 행을 폭증시켜야 한다.
  둘 다 제약 위반이라 **새 테이블 + 소비자 전환**이 유일한 비파괴 경로다.

━━ 스키마 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

gdelt_geo_country_daily — 행 = (day, fips) 1행. 행 키가 iso3가 아니라 fips인 이유:
  FIPS→ISO3는 다대일이다(가자 GZ + 서안 WE → PSE). fips를 키로 두면 원본 해상도를
  보존하면서 소비자는 iso3로 GROUP BY·SUM 하면 된다. iso3를 키로 접으면 원본이 소실된다.

  n_total / n_protest / n_material_conflict / n_verbal_conflict   원본 (발생지 키)
  n_*_pol                                                          + 행위자 유형 필터
  mentions                                                         SUM(NumMentions)
  goldstein_avg  ⚠️ 국가-일/월 평균으로는 **전쟁을 탐지하지 못한다** — 아래 경고 참조.

⚠️ goldstein_avg 경고 (실측 2026-07-13):
  우크라이나 2022-02(전면 침공) 월평균 goldstein = **+0.41**로 2021-11 평시(+0.02)보다
  오히려 *협조적*이다. 국가-월 평균은 폭력(음수)과 그 폭력이 유발한 격렬 외교(양수,
  회담·성명·지원 약속)를 상쇄시킨다. **이 컬럼을 국가 단위 긴장·분쟁 지표로 쓰지 마라.**
  이벤트 단위 GoldsteinScale(connectors/gdelt_connector.py)은 이 결함과 무관하다 —
  상쇄는 평균 낼 때 생긴다. 컬럼은 진단·재현용으로 보존하되 소비자 주입은 금지.

━━ 사용 경계 (geo-intel-map/CLAUDE.md §18-A) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - GDELT는 **국가·region 이상 집계 전용** — 하위국가 지오코딩 단독 사용 금지.
    이 테이블은 국가급 집계이므로 §18-A 준수. 소비자가 fips를 하위국가로 쪼개는 것 금지.
  - 미디어 기반 카운트 — Hammond & Weidmann(2014) 지리·보도 편향 잔존. 언론자유도가
    낮은 국가는 하향 편향(북한 등 폐쇄국가는 구조적 미관측). 소비자는 [한계] 명시 의무.

━━ 비용·멱등성 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  발생지 쿼리 1회 스캔 실측 **39.5GB** (BigQuery 샌드박스 무료 1TB/월의 4.0%).
  maximum_bytes_billed=80GB 가드. 재실행 안전 — UNIQUE(day, fips) + INSERT OR REPLACE.
  인증: gcloud ADC (프로젝트 geo-intel-gdelt-2026).

실행:
    backend/.venv/bin/python backend/scripts/load_gdelt_bq.py --dry-run   # 비용만 확인
    backend/.venv/bin/python backend/scripts/load_gdelt_bq.py             # 발생지 재적재
    backend/.venv/bin/python backend/scripts/load_gdelt_bq.py --target actor   # 구 테이블 갱신
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]        # backend/
_DB_PATH = _ROOT / "db" / "intel.db"
_CONFIG = _ROOT / "config"

_BQ_PROJECT = "geo-intel-gdelt-2026"
_MAX_BYTES = 80 * 10**9   # 스캔 폭주 가드 (발생지 쿼리 실측 39.5GB의 ~2배 여유)
_BATCH = 50_000


# ── config 로드 (헌법 §7: 매직 넘버·매핑은 코드가 아니라 config/) ──────────────

def _load_fips_map() -> dict[str, str]:
    """FIPS 10-4 → ISO3 크로스워크 (config/fips_iso3.yaml, 출처 GeoNames)."""
    data = yaml.safe_load((_CONFIG / "fips_iso3.yaml").read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data["fips_to_iso3"].items()}


def _load_actor_types() -> tuple[list[str], list[str]]:
    """행위자 유형 필터 집합 (config/gdelt_actor_types.yaml — F1 오탐 소거 근거 동봉)."""
    data = yaml.safe_load((_CONFIG / "gdelt_actor_types.yaml").read_text(encoding="utf-8"))
    f = data["material_conflict_filter"]
    return list(f["actor1_types"]), list(f["actor2_types"])


# ── 쿼리 ──────────────────────────────────────────────────────────────────────

# 발생지(ActionGeo) 키 — 결함 1·2 수리본. is_pol = 행위자 유형 필터 통과 플래그.
# IFNULL(...,FALSE): Actor*Type1Code가 NULL이면 필터 미통과로 확정 (NULL 전파 차단).
_SQL_GEO = """
WITH ev AS (
  SELECT
    SQLDATE,
    ActionGeo_CountryCode AS fips,
    EventRootCode, QuadClass, NumMentions, GoldsteinScale,
    IFNULL(Actor1Type1Code IN UNNEST(@actor1_types)
           AND Actor2Type1Code IN UNNEST(@actor2_types), FALSE) AS is_pol
  FROM `gdelt-bq.gdeltv2.events`
  WHERE SQLDATE >= @since
    AND ActionGeo_CountryCode IS NOT NULL
    AND ActionGeo_CountryCode != ''
)
SELECT
  SQLDATE                                        AS day_int,
  fips,
  COUNT(*)                                       AS n_total,
  COUNTIF(EventRootCode = '14')                  AS n_protest,
  COUNTIF(QuadClass = 4)                         AS n_material_conflict,
  COUNTIF(QuadClass = 3)                         AS n_verbal_conflict,
  SUM(NumMentions)                               AS mentions,
  ROUND(AVG(GoldsteinScale), 3)                  AS goldstein_avg,
  COUNTIF(is_pol)                                AS n_total_pol,
  COUNTIF(is_pol AND EventRootCode = '14')       AS n_protest_pol,
  COUNTIF(is_pol AND QuadClass = 4)              AS n_material_conflict_pol,
  COUNTIF(is_pol AND QuadClass = 3)              AS n_verbal_conflict_pol
FROM ev
GROUP BY day_int, fips
"""

# 행위자 국적 키 — 구 테이블(gdelt_country_daily) 유지용. 폐기 아님: "누가 등장했나"는
# "어디서 일어났나"와 다른 구성개념이다. 다만 발생지 해석에 쓰면 안 된다.
_SQL_ACTOR = """
SELECT
  SQLDATE                                   AS day_int,
  Actor1CountryCode                         AS country,
  COUNT(*)                                  AS n_total,
  COUNTIF(EventRootCode = '14')             AS n_protest,
  COUNTIF(QuadClass = 4)                    AS n_material_conflict,
  COUNTIF(QuadClass = 3)                    AS n_verbal_conflict,
  SUM(NumMentions)                          AS mentions,
  ROUND(AVG(GoldsteinScale), 3)             AS goldstein_avg
FROM `gdelt-bq.gdeltv2.events`
WHERE SQLDATE >= @since
  AND Actor1CountryCode IS NOT NULL
GROUP BY day_int, country
"""

_DDL_GEO = """
CREATE TABLE IF NOT EXISTS gdelt_geo_country_daily (
    day                     TEXT NOT NULL,   -- 'YYYY-MM-DD'
    fips                    TEXT NOT NULL,   -- ActionGeo_CountryCode 원본 (FIPS 10-4)
    country_iso3            TEXT,            -- config/fips_iso3.yaml 매핑 (미매핑 NULL)
    -- 원본 카운트 (발생지 키, 필터 없음)
    n_total                 INTEGER NOT NULL,
    n_protest               INTEGER NOT NULL,
    n_material_conflict     INTEGER NOT NULL,
    n_verbal_conflict       INTEGER NOT NULL,
    mentions                INTEGER,
    goldstein_avg           REAL,            -- ⚠️ 전쟁 미탐지(UKR 2022-02=+0.41). 소비 금지
    -- 행위자 유형 필터 카운트 (국가기구·무장조직 쌍만 — config/gdelt_actor_types.yaml)
    n_total_pol             INTEGER NOT NULL,
    n_protest_pol           INTEGER NOT NULL,
    n_material_conflict_pol INTEGER NOT NULL,
    n_verbal_conflict_pol   INTEGER NOT NULL,
    UNIQUE(day, fips)
);
CREATE INDEX IF NOT EXISTS idx_gdelt_geo_iso3 ON gdelt_geo_country_daily(country_iso3, day);
"""

_DDL_ACTOR = """
CREATE TABLE IF NOT EXISTS gdelt_country_daily (
    day                 TEXT NOT NULL,   -- 'YYYY-MM-DD'
    country             TEXT NOT NULL,   -- CAMEO Actor1CountryCode (행위자 국적 — 발생지 아님)
    n_total             INTEGER NOT NULL,
    n_protest           INTEGER NOT NULL,
    n_material_conflict INTEGER NOT NULL,
    n_verbal_conflict   INTEGER NOT NULL,
    mentions            INTEGER,
    goldstein_avg       REAL,
    UNIQUE(day, country)
);
CREATE INDEX IF NOT EXISTS idx_gdelt_cd_country ON gdelt_country_daily(country, day);
"""

_INSERT_GEO = (
    "INSERT OR REPLACE INTO gdelt_geo_country_daily "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)
_INSERT_ACTOR = "INSERT OR REPLACE INTO gdelt_country_daily VALUES (?,?,?,?,?,?,?,?)"


def _ymd(day_int: int) -> str:
    d = str(day_int)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


# ── 적재 ──────────────────────────────────────────────────────────────────────

def _run_query(client, sql: str, since: int, dry_run: bool, params: list | None = None):
    from google.cloud import bigquery

    qp = [bigquery.ScalarQueryParameter("since", "INT64", since)] + (params or [])
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=_MAX_BYTES, query_parameters=qp, dry_run=dry_run,
        use_query_cache=not dry_run,
    )
    job = client.query(sql, job_config=job_config)
    if dry_run:
        logger.info("[gdelt_bq] DRY-RUN 스캔 예상 %.1fGB (무료 한도 1TB/월의 %.1f%%)",
                    job.total_bytes_processed / 1e9,
                    job.total_bytes_processed / 1e12 * 100)
        return None
    return job


def load_geo(client, since: int, dry_run: bool) -> None:
    """발생지 키 + 행위자 유형 필터 병기 적재."""
    from google.cloud import bigquery

    fips_map = _load_fips_map()
    a1, a2 = _load_actor_types()
    logger.info("[gdelt_bq] config — FIPS 매핑 %d개 · 행위자 필터 actor1=%d종 actor2=%d종",
                len(fips_map), len(a1), len(a2))

    job = _run_query(client, _SQL_GEO, since, dry_run, params=[
        bigquery.ArrayQueryParameter("actor1_types", "STRING", a1),
        bigquery.ArrayQueryParameter("actor2_types", "STRING", a2),
    ])
    if job is None:
        return

    rows = job.result(page_size=100_000)
    logger.info("[gdelt_bq] 스캔 %.1fGB", job.total_bytes_processed / 1e9)

    con = sqlite3.connect(_DB_PATH)
    con.executescript(_DDL_GEO)

    n = 0
    unmapped: dict[str, int] = {}   # 삼킴 금지 — 미매핑 FIPS를 세어 보고한다
    batch: list[tuple] = []
    for r in rows:
        iso3 = fips_map.get(r.fips)
        if iso3 is None:
            unmapped[r.fips] = unmapped.get(r.fips, 0) + r.n_total
        batch.append((
            _ymd(r.day_int), r.fips, iso3,
            r.n_total, r.n_protest, r.n_material_conflict, r.n_verbal_conflict,
            r.mentions, r.goldstein_avg,
            r.n_total_pol, r.n_protest_pol, r.n_material_conflict_pol,
            r.n_verbal_conflict_pol,
        ))
        if len(batch) >= _BATCH:
            con.executemany(_INSERT_GEO, batch)
            con.commit()
            n += len(batch)
            logger.info("[gdelt_bq] 적재 %s행…", f"{n:,}")
            batch = []
    if batch:
        con.executemany(_INSERT_GEO, batch)
        con.commit()
        n += len(batch)

    total, days, iso3s, ev, ev_null = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT day), COUNT(DISTINCT country_iso3), "
        "SUM(n_total), SUM(CASE WHEN country_iso3 IS NULL THEN n_total ELSE 0 END) "
        "FROM gdelt_geo_country_daily"
    ).fetchone()
    con.close()

    logger.info("[gdelt_bq] 완료 — 적재 %s행 (테이블 %s행 · %s일 · ISO3 %s개국)",
                f"{n:,}", f"{total:,}", f"{days:,}", iso3s)
    if unmapped:
        top = sorted(unmapped.items(), key=lambda kv: -kv[1])[:10]
        logger.warning(
            "[gdelt_bq] 미매핑 FIPS %d종 — 이벤트 %s건 (전체의 %.2f%%). 상위: %s "
            "(원본 fips는 보존, country_iso3만 NULL)",
            len(unmapped), f"{ev_null:,}", (ev_null or 0) / (ev or 1) * 100, top,
        )


def load_actor(client, since: int, dry_run: bool) -> None:
    """구 테이블(행위자 국적 키) 갱신 — 유지용 경로. 발생지 해석에 쓰지 말 것."""
    job = _run_query(client, _SQL_ACTOR, since, dry_run)
    if job is None:
        return
    rows = job.result(page_size=100_000)
    logger.info("[gdelt_bq] 스캔 %.1fGB", job.total_bytes_processed / 1e9)

    con = sqlite3.connect(_DB_PATH)
    con.executescript(_DDL_ACTOR)
    n = 0
    batch: list[tuple] = []
    for r in rows:
        batch.append((
            _ymd(r.day_int), r.country, r.n_total, r.n_protest,
            r.n_material_conflict, r.n_verbal_conflict, r.mentions, r.goldstein_avg,
        ))
        if len(batch) >= _BATCH:
            con.executemany(_INSERT_ACTOR, batch)
            con.commit()
            n += len(batch)
            logger.info("[gdelt_bq] 적재 %s행…", f"{n:,}")
            batch = []
    if batch:
        con.executemany(_INSERT_ACTOR, batch)
        con.commit()
        n += len(batch)
    total, days, countries = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT day), COUNT(DISTINCT country) FROM gdelt_country_daily"
    ).fetchone()
    con.close()
    logger.info("[gdelt_bq] 완료 — 적재 %s행 (테이블 총 %s행 · %s일 · %s개국)",
                f"{n:,}", f"{total:,}", f"{days:,}", countries)


def remap(dry_run: bool = False) -> None:
    """BigQuery 없이 country_iso3만 config 기준으로 재매핑 (0원·0바이트).

    왜 필요한가: FIPS 매핑은 **데이터가 가르쳐 준다.** 1차 적재의 미매핑 로그에서
    세르비아 국가급 코드 'RB'(1.6M건)를 발견했다. 매핑 한 줄 고치자고 39.5GB를
    다시 스캔하는 것은 낭비다 — 원본 fips를 행에 보존해 둔 설계의 배당금.
    """
    fips_map = _load_fips_map()
    con = sqlite3.connect(_DB_PATH)
    before = con.execute(
        "SELECT COUNT(*) FROM gdelt_geo_country_daily WHERE country_iso3 IS NULL"
    ).fetchone()[0]
    if not dry_run:
        con.executemany(
            "UPDATE gdelt_geo_country_daily SET country_iso3 = ? WHERE fips = ?",
            [(iso3, fips) for fips, iso3 in fips_map.items()],
        )
        con.commit()
    after, ev_null, ev = con.execute(
        "SELECT COUNT(CASE WHEN country_iso3 IS NULL THEN 1 END), "
        "SUM(CASE WHEN country_iso3 IS NULL THEN n_total ELSE 0 END), SUM(n_total) "
        "FROM gdelt_geo_country_daily"
    ).fetchone()
    con.close()
    logger.info("[gdelt_bq] 재매핑 — 미매핑 행 %s → %s · 잔여 미매핑 이벤트 %s건(%.3f%%)",
                f"{before:,}", f"{after:,}", f"{ev_null:,}", (ev_null or 0) / (ev or 1) * 100)


def main(since: int, target: str, dry_run: bool) -> None:
    if target == "remap":                      # BigQuery 인증조차 불필요
        remap(dry_run)
        return

    from google.cloud import bigquery

    client = bigquery.Client(project=_BQ_PROJECT)
    logger.info("[gdelt_bq] target=%s since=%s dry_run=%s (스캔 가드 %dGB)",
                target, since, dry_run, _MAX_BYTES // 10**9)
    if target in ("geo", "both"):
        load_geo(client, since, dry_run)
    if target in ("actor", "both"):
        load_actor(client, since, dry_run)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="GDELT 국가급 일간 카운트 백필")
    ap.add_argument("--since", type=int, default=20150101, help="YYYYMMDD 시작일")
    ap.add_argument("--target", choices=("geo", "actor", "both", "remap"), default="geo",
                    help="geo=발생지 키(신·기본) · actor=행위자 국적 키(구 테이블 유지) · "
                         "remap=FIPS→ISO3 매핑만 재적용(BQ 미조회, 0바이트)")
    ap.add_argument("--dry-run", action="store_true", help="스캔 비용만 확인하고 종료")
    args = ap.parse_args()
    main(args.since, args.target, args.dry_run)
