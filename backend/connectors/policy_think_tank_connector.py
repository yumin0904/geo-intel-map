"""
policy_think_tank_connector.py — 워싱턴 외교안보 싱크탱크 RSS 수집

State Dept 공식 보도자료가 자동화 차단 → 워싱턴 외교정책 싱크탱크 1차 분석으로 보완.

수집 대상:
  - Atlantic Council  ★★★★☆ 워싱턴 1위 지정학 싱크탱크, 전·현직 외교관 기고, 100건/회
  - Arms Control Assoc ★★★★☆ 핵·군비통제 전문, 1945년 창설, 미 외교부 정책 영향

과정추적 Van Evera 검정 역할:
  - 흡연총(1): "이 가설만 설명하는 미국 정책 논리" 탐색
  - 이중결정(3): 한국(MOFA) + 미국(Atlantic Council) 양측이 동일 메커니즘 언급 = 강한 증거

DB: intel.db → policy_releases 테이블
"""

import hashlib
import logging
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

_DB_PATH   = Path(__file__).parent.parent / "db" / "intel.db"
_HEADERS   = {"User-Agent": "geo-intel-map/1.0 (research tool; contact: youmin0904@gmail.com)"}
_TIMEOUT   = 12

# ── 수집 소스 목록 ──────────────────────────────────────────────────────────
_SOURCES: list[dict] = [
    {
        "name": "Atlantic Council",
        "url":  "https://www.atlanticcouncil.org/feed/",
        # 관련 카테고리 키워드 (지정학 섹터 필터)
        "sector_tags": [
            "Indo-Pacific", "East Asia", "Nuclear", "Cyber",
            "Maritime Security", "Energy", "China", "Korea",
            "Taiwan", "NATO", "Ukraine", "Russia", "Iran",
            "Security & Defense", "Arms Control",
        ],
    },
    {
        "name": "Arms Control Association",
        "url":  "https://www.armscontrol.org/taxonomy/term/91/feed",
        # 핵·군비통제 특화 — 모든 기사가 관련
        "sector_tags": [],   # 빈 리스트 = 필터 없음 (전부 수집)
    },
]


def _init_table(con: sqlite3.Connection) -> None:
    """policy_releases 테이블 생성 (없을 경우)."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS policy_releases (
            id          TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            title       TEXT NOT NULL,
            pub_date    TEXT,
            description TEXT,
            link        TEXT,
            categories  TEXT,
            region_hint TEXT,
            fetched_at  TEXT NOT NULL
        )
    """)
    con.commit()


def _stable_id(source: str, title: str, pub_date: str) -> str:
    """SHA256 기반 안정 ID — Python hash() 랜덤화 방지."""
    raw = f"{source}_{pub_date}_{title[:40]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _tag_region(title: str, desc: str, cats: list[str]) -> "str | None":
    """제목·설명·카테고리에서 지역 코드 추론 (Token-Zero 결정론)."""
    text = (title + " " + desc + " " + " ".join(cats)).lower()
    rules: list[tuple[list[str], str]] = [
        (["korea", "dprk", "north korea", "pyongyang", "한반도"], "korean_peninsula"),
        (["taiwan", "tsmc", "prc", "beijing", "south china sea", "east china sea", "대만", "남중국해"], "taiwan_strait"),
        (["hormuz", "iran", "persian gulf", "gulf of oman", "tehran"], "hormuz"),
        (["south china sea", "scs", "spratly", "paracel", "philippine"], "south_china_sea"),
        (["ukraine", "russia", "nato", "moscow", "kyiv", "donbas", "black sea"], "eastern_europe"),
        (["israel", "gaza", "hamas", "hezbollah", "middle east", "red sea", "suez", "houthis"], "bab_el_mandeb"),
        (["arctic", "북극"], "arctic"),
        (["semiconductor", "chips", "huawei", "tsmc", "5g", "반도체", "공급망"], "techno_supply_chain"),
        (["indo-pacific", "aukus", "quad"], "indo_pacific"),
    ]
    for keywords, code in rules:
        if any(k in text for k in keywords):
            return code
    return None


def _parse_feed(cfg: dict) -> list[dict]:
    """RSS/Atom 피드 파싱 → 아이템 목록 반환."""
    req = Request(cfg["url"], headers=_HEADERS)
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except URLError as exc:
        logger.warning("[PolicyTT] %s 피드 접근 실패: %s", cfg["name"], exc)
        return []

    # line 92 문제처럼 </rss> 뒤 junk 제거
    rss_end = raw.find("</rss>")
    if rss_end != -1:
        raw = raw[: rss_end + 6]

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        logger.warning("[PolicyTT] %s XML 파싱 오류: %s", cfg["name"], exc)
        return []

    items = root.findall(".//item")
    sector_tags = cfg.get("sector_tags", [])
    results = []

    for item in items:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue

        pub_date  = (item.findtext("pubDate") or "")[:50]
        desc      = (item.findtext("description") or "").strip()[:300]
        link      = (item.findtext("link") or "").strip()
        cats      = [c.text.strip() for c in item.findall("category") if c.text]

        # 섹터 태그 필터 (빈 리스트면 전부 허용)
        if sector_tags and not any(st in cats or st.lower() in title.lower() for st in sector_tags):
            continue

        region = _tag_region(title, desc, cats)

        results.append({
            "id":          _stable_id(cfg["name"], title, pub_date),
            "source":      cfg["name"],
            "title":       title,
            "pub_date":    pub_date,
            "description": desc,
            "link":        link,
            "categories":  ", ".join(cats),
            "region_hint": region,
            "fetched_at":  datetime.now(timezone.utc).isoformat(),
        })

    return results


def collect_all() -> int:
    """모든 소스 수집 → policy_releases 저장. 새로 적재된 건수 반환."""
    if not _DB_PATH.parent.exists():
        logger.warning("[PolicyTT] DB 경로 없음: %s", _DB_PATH.parent)
        return 0

    con = sqlite3.connect(str(_DB_PATH))
    _init_table(con)

    total_new = 0
    for cfg in _SOURCES:
        items = _parse_feed(cfg)
        new = 0
        for item in items:
            try:
                con.execute(
                    """
                    INSERT OR IGNORE INTO policy_releases
                        (id, source, title, pub_date, description, link, categories, region_hint, fetched_at)
                    VALUES
                        (:id, :source, :title, :pub_date, :description, :link, :categories, :region_hint, :fetched_at)
                    """,
                    item,
                )
                if con.total_changes > total_new + new:
                    new += 1
            except sqlite3.Error as exc:
                logger.debug("[PolicyTT] INSERT 실패 %s: %s", item.get("id"), exc)
        con.commit()
        logger.info("[PolicyTT] %s: %d건 처리 / %d건 신규", cfg["name"], len(items), new)
        total_new += new

    con.close()
    return total_new


def stats() -> dict:
    """DB 통계 반환."""
    if not _DB_PATH.exists():
        return {"error": "DB 없음"}
    con = sqlite3.connect(str(_DB_PATH))
    try:
        total = con.execute("SELECT COUNT(*) FROM policy_releases").fetchone()[0]
        by_source = con.execute(
            "SELECT source, COUNT(*) FROM policy_releases GROUP BY source"
        ).fetchall()
        by_region = con.execute(
            "SELECT region_hint, COUNT(*) FROM policy_releases WHERE region_hint IS NOT NULL GROUP BY region_hint ORDER BY 2 DESC"
        ).fetchall()
        latest = con.execute(
            "SELECT source, title, pub_date FROM policy_releases ORDER BY pub_date DESC LIMIT 3"
        ).fetchall()
    finally:
        con.close()

    return {
        "total": total,
        "by_source": dict(by_source),
        "by_region": dict(by_region),
        "latest": [{"source": r[0], "title": r[1][:60], "date": r[2][:10]} for r in latest],
    }


def search_local(query: str, limit: int = 10) -> list[dict]:
    """로컬 DB에서 키워드 검색."""
    if not _DB_PATH.exists():
        return []
    con = sqlite3.connect(str(_DB_PATH))
    try:
        cur = con.execute(
            """SELECT source, title, pub_date, region_hint, description
               FROM policy_releases
               WHERE title LIKE ? OR description LIKE ?
               ORDER BY pub_date DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit),
        )
        rows = cur.fetchall()
    finally:
        con.close()
    return [
        {"source": r[0], "title": r[1], "date": r[2], "region": r[3], "desc": r[4][:80]}
        for r in rows
    ]


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if "--stats" in sys.argv:
        import json
        print(json.dumps(stats(), indent=2, ensure_ascii=False))
    elif "--search" in sys.argv:
        idx = sys.argv.index("--search")
        q = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "korea"
        results = search_local(q)
        for r in results:
            print(f"[{r['date'][:10]}] [{r['source']}] {r['title']}")
    else:
        n = collect_all()
        print(f"완료 — 신규 {n}건 적재")
        import json
        print(json.dumps(stats(), indent=2, ensure_ascii=False))
