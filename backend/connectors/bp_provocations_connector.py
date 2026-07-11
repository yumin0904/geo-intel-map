"""
bp_provocations_connector.py — CSIS Beyond Parallel 북한 도발 DB 수집

CNS 북한 미사일 DB(NTI) 2026-04 단종의 병렬 후속 소스 (채택위 2026-07-11,
geo-os wiki/decisions/20260711-bp-adoption-committee).

⚠️ 채택위 가드 — 이 커넥터의 존재 조건이므로 삭제·완화 금지:
  1. 격리 적재: event_archive 혼입 금지 — 전용 테이블 bp_provocations.
     CNS(발사 단위·제원 구조화)와 BP(사건 단위·서술만)는 모집단 granularity가
     달라(실측: 2018~2024 겹침 구간 BP 106 vs CNS 185) 섞으면 이중 카운트.
  2. 접합 금지: CNS 시계열과 단일 연속 카운트 시리즈 생성 금지.
     기간별 단일 소스 규칙 — ≤2024-11은 CNS, 이후는 BP. 겹침 구간 BP행은
     카운팅 제외, 브리지 교차검증 전용.
  3. 층위 라벨: BP는 "사건 발생·유형층"이다 — 제원(기종·사거리·정점고도)
     소스 아님. 제원은 구조적 공백으로 명시(서술 텍스트 정규식 추출 성공률
     33~43% 실측 — 자동 파이프라인 근거 미달). LLM 파싱은 14-A [판단필요].
  4. 프레임 캐비엇: 'provocation' 코딩은 CSIS(미국·남한 안보 관점) 프레임 —
     물리 임계 기준이던 CNS와 달리 규범 판단이 내장된 분류다.
  5. fail-loud: 파싱 행수·최신일자 assert — HTML 구조 변경 시 "0건 성공"으로
     조용히 죽는 silent failure 차단.

수집 예절: robots.txt Crawl-delay 10 — 이 커넥터는 페이지 1회 fetch만 하므로
자연 충족. 다중 요청 확장 시 10초 간격 의무.

신뢰도: ★★★★ (CSIS 싱크탱크 큐레이션 — 1차 사료 아님, 출처 URL 동봉)
"""

from __future__ import annotations

import hashlib
import html as html_mod
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "db" / "intel.db"
_URL = "https://beyondparallel.csis.org/database-north-korean-provocations/"
_TIMEOUT = 30
_HEADERS = {"User-Agent": "Mozilla/5.0 (geo-intel-map research; personal study)"}

# fail-loud 임계 (채택위 가드 5) — 실측 2026-07-11: 493행, 최신 2026-07-03
_MIN_ROWS = 400            # 이하로 파싱되면 구조 변경 의심 → 예외
_MAX_STALE_DAYS = 365      # 최신 행이 1년 이상 낡으면 수집 정지 의심 → 예외


def _stable_id(event_date: str, title: str) -> str:
    return hashlib.sha256(f"{event_date}_{title}".encode()).hexdigest()[:16]


def _init_table(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS bp_provocations (
            id          TEXT PRIMARY KEY,
            event_date  TEXT NOT NULL,
            prov_type   TEXT,
            title       TEXT NOT NULL,
            description TEXT,
            source_url  TEXT,
            fetched_at  TEXT NOT NULL
        )
    """)
    con.commit()


def _strip(cell: str) -> str:
    """셀 HTML → 평문."""
    text = re.sub(r"<[^>]+>", " ", cell)
    return re.sub(r"\s+", " ", html_mod.unescape(text)).strip()


def _parse_rows(page: str) -> list[dict]:
    """임베드 테이블 파싱 — 셀 5개(날짜·유형·사건명·서술·출처) 행만 채택."""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 4:
            continue
        date = _strip(cells[0])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue
        # 출처 셀은 href 우선 (표시 텍스트가 잘린 URL일 수 있음)
        src = ""
        if len(cells) >= 5:
            m = re.search(r'href="([^"]+)"', cells[4])
            src = m.group(1) if m else _strip(cells[4])
        out.append({
            "event_date":  date,
            "prov_type":   _strip(cells[1]),
            "title":       _strip(cells[2]),
            "description": _strip(cells[3]),
            "source_url":  src,
        })
    return out


def collect(force: bool = False) -> int:
    """BP 도발 DB 전량 수집 (idempotent — INSERT OR IGNORE). 신규 건수 반환.

    전량 fetch가 매번 일어나지만 페이지 1장(≈580KB)이라 증분 API 설계 불필요.
    """
    req = Request(_URL, headers=_HEADERS)
    with urlopen(req, timeout=_TIMEOUT) as r:
        page = r.read().decode("utf-8", "replace")

    rows = _parse_rows(page)

    # ── fail-loud 가드 (채택위 5) ──────────────────────────────────────────
    if len(rows) < _MIN_ROWS:
        raise RuntimeError(
            f"[BP] 파싱 {len(rows)}행 < 임계 {_MIN_ROWS} — HTML 구조 변경 의심 (silent failure 차단)")
    latest = max(r["event_date"] for r in rows)
    stale_days = (datetime.now(timezone.utc)
                  - datetime.fromisoformat(latest).replace(tzinfo=timezone.utc)).days
    if stale_days > _MAX_STALE_DAYS:
        raise RuntimeError(
            f"[BP] 최신 행 {latest} ({stale_days}일 경과) — 상류 갱신 정지 의심")

    if not _DB_PATH.parent.exists():
        return 0
    con = sqlite3.connect(str(_DB_PATH))
    _init_table(con)
    new_count = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        uid = _stable_id(row["event_date"], row["title"])
        cur = con.execute(
            """INSERT OR IGNORE INTO bp_provocations
               (id, event_date, prov_type, title, description, source_url, fetched_at)
               VALUES (?,?,?,?,?,?,?)""",
            (uid, row["event_date"], row["prov_type"], row["title"],
             row["description"], row["source_url"], now),
        )
        new_count += cur.rowcount
    con.commit()
    con.close()
    logger.info("[BP] 수집 완료 — 파싱 %d행 / 신규 %d건 / 최신 %s", len(rows), new_count, latest)
    return new_count


def stats() -> dict:
    if not _DB_PATH.exists():
        return {"error": "DB 없음"}
    con = sqlite3.connect(str(_DB_PATH))
    try:
        total = con.execute("SELECT COUNT(*) FROM bp_provocations").fetchone()[0]
        by_type = dict(con.execute(
            "SELECT prov_type, COUNT(*) FROM bp_provocations GROUP BY 1 ORDER BY 2 DESC"))
        rng = con.execute(
            "SELECT MIN(event_date), MAX(event_date) FROM bp_provocations").fetchone()
        post_cns = con.execute(
            "SELECT COUNT(*) FROM bp_provocations "
            "WHERE event_date > '2024-11-04' AND prov_type LIKE 'Missile%'").fetchone()[0]
    finally:
        con.close()
    return {"total": total, "by_type": by_type, "range": list(rng),
            "missile_post_cns_gap": post_cns}


if __name__ == "__main__":
    import json
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--stats" in sys.argv:
        print(json.dumps(stats(), indent=2, ensure_ascii=False))
    else:
        n = collect()
        print(f"완료 — 신규 {n}건")
        print(json.dumps(stats(), indent=2, ensure_ascii=False))
