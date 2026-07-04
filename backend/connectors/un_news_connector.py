"""
UN News RSS 커넥터 (news.un.org)

UN 공식 뉴스를 `un_news_releases` 테이블에 수집한다.
평화안보 토픽 RSS를 수집 → 지역 자동 태그 → 과정추적 이중결정 검정 다자 소스로 활용.

UN News RSS는 토픽별 최신 30건만 제공 → 주기적 실행(일 1~2회)으로 누적.

실행:
  python3 -m connectors.un_news_connector          # 전체 수집
  python3 -m connectors.un_news_connector --test   # RSS만 확인 (DB 저장 안 함)
  python3 -m connectors.un_news_connector --stats  # 수집 현황
  python3 -m connectors.un_news_connector --search 북한
"""
from __future__ import annotations

import argparse
import gzip
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

# UN News 토픽별 RSS (확인된 것만)
_UN_FEEDS: list[dict] = [
    {
        "topic": "peace_security",
        "url":   "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml",
        "label": "UN 평화안보",
    },
]

# 지역 키워드 태깅 (Token-Zero)
_REGION_KEYWORDS: list[tuple[str, str]] = [
    (r"Korea|DPRK|North Korea|Kim Jong|Pyongyang|nuclear test|denuclearization",
     "korean_peninsula"),
    (r"Ukraine|Russia|NATO|Zelensky|Putin|Kyiv|Donbas|Mariupol",
     "eastern_europe"),
    (r"Taiwan|TSMC|strait|PLA|Beijing|Xi Jinping",
     "taiwan_strait"),
    (r"Hormuz|Iran|Persian Gulf|Saudi|OPEC",
     "hormuz"),
    (r"Gaza|Israel|Hamas|Lebanon|Hezbollah|West Bank",
     "middle_east"),
    (r"South China Sea|Philippines|ASEAN|Indo.Pacific|AUKUS|Quad",
     "indo_pacific"),
    (r"Sahel|Mali|Niger|Burkina|Sudan|Somalia",
     "sub_saharan_africa"),
    (r"cyber|ransomware|APT|hack|malware|disinformation",
     "cyber"),
    (r"semiconductor|chip|AI|supply chain|export control|5G",
     "techno"),
]


def _tag_region(title: str, desc: str) -> str | None:
    text = f"{title} {desc}"
    for pattern, region in _REGION_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return region
    return None


def _parse_date(raw: str) -> str:
    """RFC 2822 or ISO 8601 → YYYY-MM-DD."""
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except Exception:
        return raw[:10]


def _fetch_rss(url: str) -> list[dict]:
    """RSS 피드 파싱 → 아이템 리스트.

    일시적 응답 이상(HTML 오류 페이지·CDN 임의 gzip 등)에 대비해 1회 재시도하고,
    파싱 실패 시 응답 앞부분을 로그에 남겨 사후 진단이 가능하게 한다
    (배경: 2026-07-04 01:32 수집에서 'not well-formed: line 1, column 0' — 응답이
    XML이 아니었는데 무엇이었는지 기록이 없어 원인 확정 불가였음).
    """
    root = None
    for attempt in (1, 2):
        req = urllib.request.Request(url, headers={
            "User-Agent": "geo-intel-map/1.0",
            # CDN이 협상 없이 gzip을 주는 경우가 있어 명시적으로 비압축 요청
            "Accept-Encoding": "identity",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")

        # 그래도 gzip으로 오면(매직 바이트 1f 8b) 풀어서 파싱
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)

        try:
            root = ET.fromstring(raw)
            break
        except ET.ParseError as exc:
            logger.warning(
                "[un_news] XML 파싱 실패 (시도 %d/2, Content-Type=%s, 응답 앞 100B=%r): %s",
                attempt, ctype, raw[:100], exc,
            )
            if attempt == 2:
                raise
            time.sleep(3)  # 일시적 소스 이상 대비 — 짧게 쉬고 1회만 재시도

    items = root.findall(".//item")

    results = []
    for item in items:
        title   = html.unescape((item.findtext("title") or "").strip())
        link    = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        desc    = html.unescape(
            re.sub(r"<[^>]+>", " ",
                   item.findtext("description") or item.findtext("content") or "")
        )
        desc = re.sub(r"\s+", " ", desc).strip()

        results.append({
            "title":    title,
            "link":     link,
            "pub_date": _parse_date(pub_raw),
            "desc":     desc[:800],  # 800자 상한
        })

    return results


def _init_db(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS un_news_releases (
            id          TEXT PRIMARY KEY,   -- SHA256(title+pub_date)[:16]
            topic       TEXT NOT NULL,      -- UN News 토픽 코드
            title       TEXT NOT NULL,
            pub_date    TEXT,               -- YYYY-MM-DD
            description TEXT,              -- RSS 요약
            link        TEXT,               -- 원문 URL
            region_hint TEXT,              -- 자동 지역 태그 (없으면 NULL)
            fetched_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_un_pub    ON un_news_releases(pub_date);
        CREATE INDEX IF NOT EXISTS idx_un_region ON un_news_releases(region_hint);
    """)
    con.commit()


def collect_all(test_only: bool = False) -> int:
    """전체 수집. test_only=True면 DB 저장 없이 출력만."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    total = 0

    if not test_only:
        con = sqlite3.connect(str(_DB_PATH))
        _init_db(con)

    for feed in _UN_FEEDS:
        try:
            items = _fetch_rss(feed["url"])
            print(f"[{feed['label']}] {len(items)}건 수신")

            rows = []
            for item in items:
                region = _tag_region(item["title"], item["desc"])
                uid_src = f"{item['title'][:40]}_{item['pub_date']}"
                uid = hashlib.sha256(uid_src.encode()).hexdigest()[:16]

                if test_only:
                    print(f"  [{item['pub_date']}] [{region or '미분류'}] {item['title'][:60]}")
                    print(f"   desc: {item['desc'][:90]}")
                else:
                    rows.append((
                        uid,
                        feed["topic"],
                        item["title"],
                        item["pub_date"],
                        item["desc"],
                        item["link"],
                        region,
                        fetched_at,
                    ))

            if not test_only:
                con.executemany(
                    """INSERT OR IGNORE INTO un_news_releases
                       (id, topic, title, pub_date, description, link, region_hint, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    rows,
                )
                con.commit()
                total += len(rows)
                print(f"  → DB 저장 {len(rows)}건")

        except Exception as exc:
            logger.warning("[un_news] %s 수집 실패: %s", feed["label"], exc)
        time.sleep(0.5)

    if not test_only:
        con.close()

    return total


def search_local(keyword: str, limit: int = 20) -> list[dict]:
    """로컬 키워드 검색."""
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """SELECT id, topic, title, pub_date, description, region_hint
           FROM un_news_releases
           WHERE title LIKE ? OR description LIKE ?
           ORDER BY pub_date DESC LIMIT ?""",
        (f"%{keyword}%", f"%{keyword}%", limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def stats() -> dict:
    """수집 현황."""
    con = sqlite3.connect(str(_DB_PATH))
    cur = con.cursor()
    try:
        cur.execute("SELECT COUNT(*), MIN(pub_date), MAX(pub_date) FROM un_news_releases")
        cnt, mn, mx = cur.fetchone()
        cur.execute(
            "SELECT region_hint, COUNT(*) FROM un_news_releases "
            "WHERE region_hint IS NOT NULL GROUP BY region_hint ORDER BY 2 DESC"
        )
        regions = dict(cur.fetchall())
    except sqlite3.OperationalError:
        cnt, mn, mx = 0, None, None
        regions = {}
    con.close()
    return {"total": cnt, "date_range": f"{mn} ~ {mx}", "regions": regions}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="UN News RSS 수집")
    parser.add_argument("--test",   action="store_true", help="DB 저장 없이 RSS만 확인")
    parser.add_argument("--stats",  action="store_true", help="수집 현황")
    parser.add_argument("--search", metavar="KW",        help="로컬 키워드 검색")
    args = parser.parse_args()

    if args.search:
        results = search_local(args.search)
        print(f"[{args.search}] {len(results)}건")
        for r in results:
            print(f"  [{r['pub_date']}] [{r['region_hint']}] {r['title'][:65]}")
    elif args.stats:
        s = stats()
        print(f"수집 현황: {s['total']}건  범위: {s['date_range']}")
        print(f"지역: {s['regions']}")
    else:
        n = collect_all(test_only=args.test)
        if not args.test:
            print(f"\n[완료] 총 저장 {n}건")
