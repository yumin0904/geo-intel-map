"""
외교부 보도자료 커넥터 (공공데이터포털 15141564)

22,483건 전체를 `mofa_press_releases` 테이블에 수집·저장한다.
키워드 검색은 API가 지원하지 않으므로 로컬 SQLite FTS 또는 LIKE 쿼리로 처리.

실행:
  python3 -m connectors.mofa_press          # 전체 수집
  python3 -m connectors.mofa_press --test   # 1페이지만 테스트
  python3 -m connectors.mofa_press --search 북한 # 로컬 키워드 검색
"""
from __future__ import annotations

import argparse
import hashlib
import html
import logging
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "intel.db"
_BASE_URL = "http://apis.data.go.kr/1262000/pressRlsService/getPressRls"
_PAGE_SIZE = 100
_DELAY_SEC = 0.3  # 서버 부하 방지 — 10,000req/일 한도 내


def _get_api_key() -> str:
    key = os.getenv("MOFA_API_KEY", "")
    if not key:
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("MOFA_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise ValueError("MOFA_API_KEY 환경변수 또는 backend/.env 파일에 키를 설정하세요.")
    return key


def _strip_html(text: str) -> str:
    """HTML 태그 제거 + 엔티티 디코딩."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _fetch_page(api_key: str, page: int) -> dict:
    url = _BASE_URL + "?" + urllib.parse.urlencode({
        "serviceKey": api_key,
        "type": "json",
        "numOfRows": _PAGE_SIZE,
        "pageNo": page,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _init_db(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS mofa_press_releases (
            id           TEXT PRIMARY KEY,   -- updt_date + 순번 해시
            title        TEXT NOT NULL,
            pub_date     TEXT,               -- updt_date (YYYY-MM-DD)
            creator      TEXT,               -- 작성부서
            content_raw  TEXT,               -- HTML 원문
            content_text TEXT,               -- 태그 제거 평문
            file_url     TEXT,               -- 첨부파일 URL
            fetched_at   TEXT NOT NULL,
            region_hint  TEXT                -- 자동 지역 태그 (후처리)
        );
        CREATE INDEX IF NOT EXISTS idx_mofa_pub   ON mofa_press_releases(pub_date);
        CREATE INDEX IF NOT EXISTS idx_mofa_creat ON mofa_press_releases(creator);
    """)
    con.commit()


# 지역 자동 태그 — 제목에서 키워드 매핑 (Token-Zero)
_REGION_KEYWORDS: list[tuple[str, str]] = [
    ("북한|북핵|조선|김정은|핵실험|ICBM|도발",        "korean_peninsula"),
    ("한미|주한미군|확장억제|한미동맹|한미연합",        "korean_peninsula"),
    ("우크라이나|러시아|NATO|루블|젤렌스키",           "eastern_europe"),
    ("대만|TSMC|양안|중국|시진핑",                    "taiwan_strait"),
    ("호르무즈|이란|걸프|사우디|오만",                "hormuz"),
    ("인도태평양|쿼드|AUKUS|남중국해|필리핀",          "indo_pacific"),
    ("이스라엘|하마스|팔레스타인|가자|레바논",         "middle_east"),
    ("사헬|아프리카|말리|니제르",                     "sub_saharan_africa"),
    ("사이버|해킹|APT|랜섬웨어|디지털",               "cyber"),
    ("반도체|AI|첨단기술|공급망|수출통제",             "techno"),
]

def _tag_region(title: str) -> str | None:
    for pattern, region in _REGION_KEYWORDS:
        if re.search(pattern, title):
            return region
    return None


def collect_all(test_only: bool = False) -> int:
    """전체 수집 메인 함수. test_only=True면 1페이지만."""
    api_key = _get_api_key()
    con = sqlite3.connect(str(_DB_PATH))
    _init_db(con)

    # 총 건수 파악
    first = _fetch_page(api_key, 1)
    total = int(first["response"]["body"].get("totalCount", 0))
    total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
    if test_only:
        total_pages = 1
    print(f"[MOFA] 총 {total}건, {total_pages}페이지 수집 시작")

    inserted = 0
    skipped  = 0
    fetched_at = datetime.now(timezone.utc).isoformat()

    for page in range(1, total_pages + 1):
        try:
            if page == 1:
                data = first
            else:
                time.sleep(_DELAY_SEC)
                data = _fetch_page(api_key, page)

            items = data["response"]["body"]["items"].get("item", [])
            if not items:
                break

            rows = []
            for idx, item in enumerate(items):
                title       = (item.get("title") or "").strip()
                pub_date    = (item.get("updt_date") or "").strip()
                creator     = (item.get("creator") or "").strip()
                content_raw = item.get("content") or ""
                content_txt = _strip_html(content_raw)
                file_url    = (item.get("file_url") or "").strip()
                region      = _tag_region(title)

                # 고유 ID: pub_date + 제목 앞 30자 SHA256 (실행간 안정적 해시)
                uid_src = f"{pub_date}_{title[:30]}"
                uid = hashlib.sha256(uid_src.encode()).hexdigest()[:16]

                rows.append((
                    uid, title, pub_date, creator,
                    content_raw, content_txt, file_url, fetched_at, region,
                ))

            con.executemany(
                """INSERT OR IGNORE INTO mofa_press_releases
                   (id,title,pub_date,creator,content_raw,content_text,file_url,fetched_at,region_hint)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            con.commit()
            inserted += len(rows)

            if page % 20 == 0 or page == total_pages:
                print(f"  page {page:3d}/{total_pages} — 누적 {inserted}건")

        except Exception as exc:
            logger.warning("[MOFA] page %d 실패: %s", page, exc)
            skipped += 1
            time.sleep(1)

    con.close()
    print(f"[MOFA] 완료 — 저장 {inserted}건, 실패 {skipped}페이지")
    return inserted


def search_local(keyword: str, limit: int = 20) -> list[dict]:
    """로컬 SQLite에서 키워드 검색 (제목 + 내용)."""
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(
        """SELECT id, title, pub_date, creator, content_text, region_hint
           FROM mofa_press_releases
           WHERE title LIKE ? OR content_text LIKE ?
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
    cur.execute("SELECT COUNT(*), MIN(pub_date), MAX(pub_date) FROM mofa_press_releases")
    cnt, min_d, max_d = cur.fetchone()
    cur.execute("""SELECT region_hint, COUNT(*) as n FROM mofa_press_releases
                   WHERE region_hint IS NOT NULL GROUP BY region_hint ORDER BY n DESC""")
    regions = dict(cur.fetchall())
    con.close()
    return {"total": cnt, "date_range": f"{min_d} ~ {max_d}", "regions": regions}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="외교부 보도자료 수집")
    parser.add_argument("--test",   action="store_true", help="1페이지만 테스트")
    parser.add_argument("--search", metavar="KW",         help="로컬 키워드 검색")
    parser.add_argument("--stats",  action="store_true",  help="수집 현황 통계")
    args = parser.parse_args()

    if args.search:
        results = search_local(args.search, limit=20)
        print(f"[{args.search}] {len(results)}건")
        for r in results:
            print(f"  [{r['pub_date']}] {r['title'][:70]}")
            print(f"           지역={r['region_hint']} 부서={r['creator']}")
    elif args.stats:
        s = stats()
        print(f"수집 현황: {s['total']}건  날짜범위: {s['date_range']}")
        print(f"지역 태그: {s['regions']}")
    else:
        collect_all(test_only=args.test)
