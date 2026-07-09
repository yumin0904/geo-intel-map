"""
scripts/load_gdelt_bq.py

GDELT 국가급 일간 카운트 백필 (§ geo-os/wiki/decisions/20260709-data-audit-committee.md 웨이브 2):
BigQuery 공개 데이터셋(gdelt-bq.gdeltv2.events)에서 2015-01-01~현재 전 기간을
국가×일 단위로 집계해 gdelt_country_daily 테이블에 적재한다.

설계 (와이드 포맷 — 2026-07-09):
  행 = (day, country) 1행. 날짜×국가×루트코드 롱 포맷은 실측 11,045,795행으로
  intel.db(756MB)를 배로 불려 기각. 소비자 실수요 구성개념만 컬럼으로 고정:
    n_total             전체 이벤트 수 (국가 활동량)
    n_protest           EventRootCode='14' PROTEST — "GDELT 시위 이벤트 건수" DV
    n_material_conflict QuadClass=4 (물리적 분쟁 — 무력행사·공격)
    n_verbal_conflict   QuadClass=3 (언어적 분쟁 — 위협·요구)
    mentions            SUM(NumMentions) — 보도량 가중치 재료
    goldstein_avg       AVG(GoldsteinScale) — 협력(+)~분쟁(−) 톤 지표

사용 경계 (geo-intel-map/CLAUDE.md §18-A):
  - GDELT는 국가·region 이상 집계 전용 — 하위국가 지오코딩 단독 사용 금지.
  - 미디어 기반 카운트라 Hammond & Weidmann 지리·보도 편향 잔존 — 언론자유도가
    낮은 국가의 카운트는 검열·접근성으로 하향 편향(북한 등 폐쇄국가는 구조적 미관측).
    소비자는 [한계] 명시 의무.
  - country 키는 CAMEO Actor1CountryCode(대부분 ISO3 일치: PRK·KOR·CHN·USA).
    비ISO3 특수코드(예: 팔레스타인 관련 CAMEO 확장)는 패널 조인 시 자연 탈락 — 삼킴 아님.

비용: 본쿼리 1회 스캔 실측 27.6GB (BigQuery 샌드박스 무료 한도 1TB/월의 2.8%).
      maximum_bytes_billed=60GB 가드로 폭주 차단.

idempotent: UNIQUE(day, country) + INSERT OR REPLACE — 재실행 안전.
인증: gcloud ADC (프로젝트 geo-intel-gdelt-2026, 2026-07-09 사용자 계정 연결).

실행:
    backend/.venv/bin/python backend/scripts/load_gdelt_bq.py [--since 20150101]
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _ROOT / "backend" / "db" / "intel.db"

_BQ_PROJECT = "geo-intel-gdelt-2026"
_MAX_BYTES = 60 * 10**9  # 스캔 폭주 가드 (실측 27.6GB의 ~2배 여유)

_SQL = """
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

_DDL = """
CREATE TABLE IF NOT EXISTS gdelt_country_daily (
    day                 TEXT NOT NULL,   -- 'YYYY-MM-DD'
    country             TEXT NOT NULL,   -- CAMEO Actor1CountryCode (대부분 ISO3)
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


def main(since: int) -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=_BQ_PROJECT)
    job_config = bigquery.QueryJobConfig(
        maximum_bytes_billed=_MAX_BYTES,
        query_parameters=[bigquery.ScalarQueryParameter("since", "INT64", since)],
    )
    logger.info("[gdelt_bq] 쿼리 시작 (since=%s, 스캔 가드=%dGB)", since, _MAX_BYTES // 10**9)
    job = client.query(_SQL, job_config=job_config)
    rows = job.result(page_size=100_000)
    logger.info("[gdelt_bq] 스캔 %.1fGB", job.total_bytes_processed / 1e9)

    con = sqlite3.connect(_DB_PATH)
    con.executescript(_DDL)

    n = 0
    batch: list[tuple] = []
    for r in rows:
        d = str(r.day_int)
        batch.append((
            f"{d[:4]}-{d[4:6]}-{d[6:]}", r.country, r.n_total, r.n_protest,
            r.n_material_conflict, r.n_verbal_conflict, r.mentions, r.goldstein_avg,
        ))
        if len(batch) >= 50_000:
            con.executemany(
                "INSERT OR REPLACE INTO gdelt_country_daily VALUES (?,?,?,?,?,?,?,?)",
                batch,
            )
            con.commit()
            n += len(batch)
            logger.info("[gdelt_bq] 적재 %s행…", f"{n:,}")
            batch = []
    if batch:
        con.executemany(
            "INSERT OR REPLACE INTO gdelt_country_daily VALUES (?,?,?,?,?,?,?,?)",
            batch,
        )
        con.commit()
        n += len(batch)

    total, days, countries = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT day), COUNT(DISTINCT country) FROM gdelt_country_daily"
    ).fetchone()
    con.close()
    logger.info("[gdelt_bq] 완료 — 적재 %s행 (테이블 총 %s행 · %s일 · %s개국)",
                f"{n:,}", f"{total:,}", f"{days:,}", countries)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=20150101, help="YYYYMMDD 시작일")
    args = ap.parse_args()
    main(args.since)
