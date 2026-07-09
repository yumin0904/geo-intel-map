"""
북한 전문 소스 커넥터 (NKNews + 38 North)

두 소스를 `nk_press_releases` 테이블에 수집한다.
  - NKNews (nknews.org): 한반도 전문 뉴스, RSS 300건
  - 38 North (38north.org): Johns Hopkins/Stimson 학술 분석, RSS 8건

과정추적 증거 소스로 사용 (흡연총·후프 검정 보강).
키워드 검색은 로컬 SQLite LIKE 쿼리로 처리.

실행:
  python3 -m connectors.nk_news_connector          # 전체 수집
  python3 -m connectors.nk_news_connector --test   # RSS만 확인 (DB 저장 안 함)
  python3 -m connectors.nk_news_connector --stats  # 수집 현황
  python3 -m connectors.nk_news_connector --search 확장억제
"""
from __future__ import annotations

import argparse
import hashlib
import html
import logging
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "intel.db"

_SOURCES: list[dict] = [
    {
        "name":   "NKNews",
        "url":    "https://www.nknews.org/feed/",
        "region": "korean_peninsula",
    },
    {
        "name":   "38North",
        "url":    "https://www.38north.org/feed/",
        "region": "korean_peninsula",
    },
]


def _fetch_rss(url: str) -> list[dict]:
    """RSS 피드 파싱 → 아이템 리스트."""
    req = urllib.request.Request(url, headers={"User-Agent": "geo-intel-map/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()

    root = ET.fromstring(raw)
    ns_atom = "http://www.w3.org/2005/Atom"

    items = root.findall(".//item")
    if not items:
        items = root.findall(f".//{{{ns_atom}}}entry")

    results = []
    for item in items:
        def _t(tag: str) -> str:
            return (
                item.findtext(tag)
                or item.findtext(f"{{{ns_atom}}}{tag}")
                or ""
            ).strip()

        title   = html.unescape(_t("title"))
        link    = _t("link") or _t("id")
        pub_raw = _t("pubDate") or _t("updated") or _t("published")
        desc    = html.unescape(re.sub(r"<[^>]+>", " ", _t("description") or _t("summary") or ""))
        desc    = re.sub(r"\s+", " ", desc).strip()

        # 날짜 정규화 → YYYY-MM-DD
        pub_date = ""
        if pub_raw:
            try:
                pub_date = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d")
            except Exception:
                # ISO 형식 폴백
                pub_date = (pub_raw or "")[:10]

        results.append({
            "title":    title,
            "link":     link,
            "pub_date": pub_date,
            "desc":     desc,
        })

    return results


def _init_db(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS nk_press_releases (
            id          TEXT PRIMARY KEY,   -- SHA256(source+title+pub_date)[:16]
            source      TEXT NOT NULL,      -- "NKNews" | "38North"
            title       TEXT NOT NULL,
            pub_date    TEXT,               -- YYYY-MM-DD
            description TEXT,              -- RSS 요약 (HTML 제거)
            link        TEXT,               -- 원문 URL
            region_hint TEXT DEFAULT 'korean_peninsula',
            fetched_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_nk_pub ON nk_press_releases(pub_date);
        CREATE INDEX IF NOT EXISTS idx_nk_src ON nk_press_releases(source);
    """)
    con.commit()


def collect_all(test_only: bool = False) -> int:
    """전체 수집. test_only=True면 DB 저장 없이 결과만 출력."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    total_inserted = 0
    fail_count = 0

    if not test_only:
        con = sqlite3.connect(str(_DB_PATH))
        _init_db(con)

    for src in _SOURCES:
        try:
            items = _fetch_rss(src["url"])
            print(f"[{src['name']}] {len(items)}건 수신")

            if test_only:
                for item in items[:3]:
                    print(f"  [{item['pub_date']}] {item['title'][:70]}")
                    print(f"   desc: {item['desc'][:100]}")
                continue

            rows = []
            for item in items:
                uid_src = f"{src['name']}_{item['title'][:40]}_{item['pub_date']}"
                uid = hashlib.sha256(uid_src.encode()).hexdigest()[:16]
                rows.append((
                    uid,
                    src["name"],
                    item["title"],
                    item["pub_date"],
                    item["desc"],
                    item["link"],
                    src["region"],
                    fetched_at,
                ))

            con.executemany(
                """INSERT OR IGNORE INTO nk_press_releases
                   (id, source, title, pub_date, description, link, region_hint, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                rows,
            )
            con.commit()
            total_inserted += len(rows)
            print(f"  → DB 저장 {len(rows)}건")

        except Exception as exc:
            fail_count += 1
            logger.warning("[nk_news] %s 수집 실패: %s", src["name"], exc)
        time.sleep(0.5)

    if not test_only:
        con.close()

    # 판례 20260709: 전체 소스가 실패했는데도 0을 반환하면 "신규 0건"과
    # 구분 불가 — press_releases_job.run_nk_press_batch()의 except가 실제
    # 발동하도록 예외를 던진다. 일부만 실패했으면 나머지로 확보한
    # total_inserted가 정직한 값이므로 그대로 반환한다.
    if not test_only and _SOURCES and fail_count == len(_SOURCES):
        raise RuntimeError(f"[nk_news] 전체 소스({fail_count}개) 접근 실패")

    return total_inserted


def search_local(keyword: str, limit: int = 20) -> list[dict]:
    """로컬 키워드 검색 (제목 + 요약)."""
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """SELECT id, source, title, pub_date, description, link
           FROM nk_press_releases
           WHERE title LIKE ? OR description LIKE ?
           ORDER BY pub_date DESC
           LIMIT ?""",
        (f"%{keyword}%", f"%{keyword}%", limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def stats() -> dict:
    """수집 현황 통계."""
    con = sqlite3.connect(str(_DB_PATH))
    cur = con.cursor()
    try:
        cur.execute("SELECT COUNT(*), MIN(pub_date), MAX(pub_date) FROM nk_press_releases")
        cnt, mn, mx = cur.fetchone()
        cur.execute("SELECT source, COUNT(*) FROM nk_press_releases GROUP BY source")
        by_source = dict(cur.fetchall())
    except sqlite3.OperationalError:
        cnt, mn, mx = 0, None, None
        by_source = {}
    con.close()
    return {"total": cnt, "date_range": f"{mn} ~ {mx}", "by_source": by_source}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="NKNews + 38 North 수집")
    parser.add_argument("--test",   action="store_true", help="DB 저장 없이 RSS만 확인")
    parser.add_argument("--stats",  action="store_true", help="수집 현황")
    parser.add_argument("--search", metavar="KW",        help="로컬 키워드 검색")
    args = parser.parse_args()

    if args.search:
        results = search_local(args.search)
        print(f"[{args.search}] {len(results)}건")
        for r in results:
            print(f"  [{r['pub_date']}] [{r['source']}] {r['title'][:65]}")
    elif args.stats:
        s = stats()
        print(f"수집 현황: {s['total']}건  범위: {s['date_range']}")
        print(f"소스별: {s['by_source']}")
    else:
        n = collect_all(test_only=args.test)
        if not args.test:
            print(f"\n[완료] 총 저장 {n}건")
