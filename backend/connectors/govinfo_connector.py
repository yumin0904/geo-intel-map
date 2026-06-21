"""
govinfo_connector.py — GovInfo.gov CPD (Compilation of Presidential Documents) 수집

미국 정부 공식 1차 사료 — State Dept 보도자료 차단 대안.
대통령 성명·기자회견·의회 연설 원문을 수집한다.

접근 전략:
  - CPD 컬렉션 직접 스캔 (collections/CPD 엔드포인트)
  - 제목 키워드 필터 → 관련 패키지만 텍스트 추출
  - txtLink로 실제 원문 400자 발췌 → description 저장

과정추적 Van Evera 검정 역할:
  - 이중결정(3): 대통령 성명이 가설의 인과 메커니즘을 공식 확인 → 가장 강한 미국 측 증거
  - 흡연총(1): 특정 정책 결정·채택을 명시한 성명 = 결정적 단서

신뢰도: ★★★★★ 미국 정부 1차 사료 (POTUS 수준)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "db" / "intel.db"
_TIMEOUT = 15

# .env에서 키 로드
def _load_api_key() -> str:
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GOVINFO_API_KEY="):
                return line.split("=", 1)[1].strip()
    import os
    return os.getenv("GOVINFO_API_KEY", "")


_HEADERS = {"Accept": "application/json", "User-Agent": "geo-intel-map/1.0"}

# ── 수집 대상 키워드 (섹터별) ─────────────────────────────────────────────
# 제목에 하나라도 포함되면 수집
_SECTOR_KEYWORDS: list[str] = [
    # 한반도·핵
    "north korea", "dprk", "korean peninsula", "denuclearization",
    # 대만·인도태평양
    "taiwan", "south china sea", "indo-pacific", "aukus",
    # 중동
    "iran", "nuclear deal", "hormuz", "houthi", "red sea",
    # 유럽안보
    "ukraine", "nato", "russia sanctions",
    # 기술패권·사이버
    "semiconductor", "chips act", "cyber",
    # 동맹
    "alliance", "extended deterrence",
]


def _stable_id(pkg_id: str, granule_id: str) -> str:
    """SHA256 안정 ID."""
    raw = f"{pkg_id}_{granule_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _init_table(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS govinfo_releases (
            id              TEXT PRIMARY KEY,
            collection_code TEXT,
            package_id      TEXT,
            granule_id      TEXT,
            title           TEXT NOT NULL,
            pub_date        TEXT,
            description     TEXT,
            region_hint     TEXT,
            fetched_at      TEXT NOT NULL
        )
    """)
    con.commit()


def _tag_region(title: str, desc: str) -> "Optional[str]":
    """제목+설명에서 지역 코드 추론."""
    text = (title + " " + desc).lower()
    rules: list[tuple[list[str], str]] = [
        (["korea", "dprk", "north korea", "pyongyang", "denuclearization"], "korean_peninsula"),
        (["taiwan", "south china sea", "prc", "east china sea"], "taiwan_strait"),
        (["iran", "hormuz", "nuclear deal", "iaea"], "hormuz"),
        (["ukraine", "russia", "nato", "donbas", "zelenskyy"], "eastern_europe"),
        (["houthi", "red sea", "bab el-mandeb", "yemen"], "bab_el_mandeb"),
        (["semiconductor", "chips", "huawei", "5g", "supply chain"], "techno_supply_chain"),
        (["indo-pacific", "aukus", "quad", "pacific alliance"], "indo_pacific"),
        (["arctic", "svalbard"], "arctic"),
    ]
    for keywords, code in rules:
        if any(k in text for k in keywords):
            return code
    return None


def _extract_text_snippet(pkg_id: str, api_key: str, max_chars: int = 400) -> str:
    """패키지 txtLink에서 실제 본문 400자 발췌."""
    url = f"https://api.govinfo.gov/packages/{pkg_id}/summary?api_key={api_key}"
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=_TIMEOUT) as r:
            meta = json.loads(r.read())
        txt_link = meta.get("download", {}).get("txtLink", "")
        if not txt_link:
            return ""
        req2 = Request(txt_link + f"?api_key={api_key}")
        with urlopen(req2, timeout=_TIMEOUT) as r2:
            raw = r2.read().decode("utf-8", "replace")
        # HTML 태그 제거
        clean = re.sub(r"<[^>]+>", " ", raw)
        clean = re.sub(r"&[a-z#0-9]+;", " ", clean)  # HTML 엔티티
        clean = re.sub(r"\s+", " ", clean).strip()
        # CSS 헤더 건너뛰기 — 실제 본문 시작 탐지
        for marker in ["My fellow Americans", "To the Congress", "Dear Mr.", "I am pleased", "The United States"]:
            idx = clean.find(marker)
            if idx > 0:
                return clean[idx: idx + max_chars]
        # fallback: 전체 텍스트의 1/3 지점부터 (CSS 헤더 이후)
        start = len(clean) // 3
        return clean[start: start + max_chars]
    except Exception as exc:
        logger.debug("[GovInfo] 텍스트 추출 실패 %s: %s", pkg_id, exc)
        return ""


def online_search(
    query: str,
    region: str | None = None,
    limit: int = 5,
    api_key: str = "",
) -> list[dict]:
    """
    GovInfo 검색 API 온디맨드 쿼리 + DB 캐싱.

    process_tracing_adapt()에서 직접 호출.
    결과를 govinfo_releases에 저장 → 같은 쿼리 재실행 시 DB 조회.
    """
    if not api_key:
        api_key = _load_api_key()
    if not api_key:
        return []

    payload = json.dumps({
        "query": query,
        "pageSize": limit,
        "offsetMark": "*",
        "resultLevel": "default",
    }).encode()
    url = f"https://api.govinfo.gov/search?api_key={api_key}"
    req = Request(
        url, data=payload,
        headers={**_HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read())
    except URLError as exc:
        logger.warning("[GovInfo] 검색 실패: %s", exc)
        return []

    # 대통령 문서계열만 필터 (CPD=현대, WCPD=주간, DCPD=일간, PPP=Public Papers 레거시)
    _PRES_DOC_CODES = {"CPD", "WCPD", "DCPD", "PPP"}
    all_items = data.get("results", [])
    pres_items = [i for i in all_items if i.get("collectionCode", "") in _PRES_DOC_CODES]
    # 대통령 문서가 없으면 전체 중 상위 사용
    chosen = pres_items if pres_items else all_items

    results = []
    if not _DB_PATH.parent.exists():
        return []
    con = sqlite3.connect(str(_DB_PATH))
    _init_table(con)

    for item in chosen[:limit]:
        pkg_id    = item.get("packageId", "")
        granule_id = item.get("granuleId", "") or ""
        title     = (item.get("title") or "").strip()
        pub_date  = (item.get("dateIssued") or "")[:10]
        coll      = item.get("collectionCode", "CPD")
        uid       = _stable_id(pkg_id, granule_id or "pkg")

        # 이미 DB에 있으면 텍스트 재사용
        row = con.execute(
            "SELECT title, pub_date, description, region_hint FROM govinfo_releases WHERE id=?",
            (uid,),
        ).fetchone()
        if row:
            snippet = row[2] or ""
            region_hit = row[3]
        else:
            snippet    = _extract_text_snippet(pkg_id, api_key)
            region_hit = region or _tag_region(title, snippet)
            try:
                con.execute(
                    """INSERT OR IGNORE INTO govinfo_releases
                       (id, collection_code, package_id, granule_id, title, pub_date, description, region_hint, fetched_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (uid, coll, pkg_id, granule_id, title, pub_date, snippet, region_hit,
                     datetime.now(timezone.utc).isoformat()),
                )
                con.commit()
            except sqlite3.Error:
                pass

        results.append({
            "title":       title,
            "date":        pub_date,
            "source_db":   f"{coll} (White House)",
            "description": snippet[:150],
            "region":      region_hit,
        })

    con.close()
    return results


def collect_recent(days_back: int = 7, api_key: str = "") -> int:
    """최근 N일치 CPD 패키지를 스캔 → 관련 항목 저장. 신규 건수 반환."""
    if not api_key:
        api_key = _load_api_key()
    if not api_key:
        logger.warning("[GovInfo] API 키 없음 — 수집 생략")
        return 0

    # 시작 날짜 계산
    from datetime import timedelta
    start_dt = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")

    # CPD 컬렉션 최근 패키지 목록 (최대 200개)
    url = f"https://api.govinfo.gov/collections/CPD/{start_dt}?pageSize=200&offset=0&api_key={api_key}"
    req = Request(url, headers=_HEADERS)
    try:
        with urlopen(req, timeout=_TIMEOUT) as r:
            data = json.loads(r.read())
    except URLError as exc:
        logger.warning("[GovInfo] 컬렉션 접근 실패: %s", exc)
        return 0

    pkgs = data.get("packages", [])
    logger.info("[GovInfo] CPD %s 이후 %d건 스캔 중…", start_dt[:10], len(pkgs))

    if not _DB_PATH.parent.exists():
        return 0
    con = sqlite3.connect(str(_DB_PATH))
    _init_table(con)

    new_count = 0
    for pkg in pkgs:
        title = pkg.get("title", "").strip()
        title_lower = title.lower()

        # 섹터 키워드 필터
        if not any(k in title_lower for k in _SECTOR_KEYWORDS):
            continue

        pkg_id   = pkg.get("packageId", "")
        pub_date = (pkg.get("dateIssued") or "")[:10]
        uid      = _stable_id(pkg_id, "pkg")

        # 이미 있으면 텍스트 추출 생략 (중복 방지)
        existing = con.execute("SELECT 1 FROM govinfo_releases WHERE id=?", (uid,)).fetchone()
        if existing:
            continue

        # 텍스트 발췌 (API 1회 추가 호출)
        snippet = _extract_text_snippet(pkg_id, api_key)
        region  = _tag_region(title, snippet)

        try:
            con.execute(
                """
                INSERT OR IGNORE INTO govinfo_releases
                    (id, collection_code, package_id, granule_id, title, pub_date, description, region_hint, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uid, "CPD", pkg_id, "", title, pub_date, snippet, region,
                 datetime.now(timezone.utc).isoformat()),
            )
            if con.total_changes > 0:
                new_count += 1
                logger.debug("[GovInfo] 저장: [%s] %s", pub_date, title[:50])
        except sqlite3.Error as exc:
            logger.debug("[GovInfo] INSERT 실패 %s: %s", pkg_id, exc)

    con.commit()
    con.close()
    logger.info("[GovInfo] 완료 — 신규 %d건", new_count)
    return new_count


def search_local(query: str, region: str | None = None, limit: int = 5) -> list[dict]:
    """로컬 DB에서 키워드 + 지역 검색."""
    if not _DB_PATH.exists():
        return []
    con = sqlite3.connect(str(_DB_PATH))
    try:
        if region:
            cur = con.execute(
                """SELECT title, pub_date, description, region_hint
                   FROM govinfo_releases
                   WHERE (region_hint=? OR title LIKE ? OR description LIKE ?)
                   ORDER BY pub_date DESC LIMIT ?""",
                (region, f"%{query}%", f"%{query}%", limit),
            )
        else:
            cur = con.execute(
                """SELECT title, pub_date, description, region_hint
                   FROM govinfo_releases
                   WHERE title LIKE ? OR description LIKE ?
                   ORDER BY pub_date DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            )
        rows = cur.fetchall()
    finally:
        con.close()
    return [
        {
            "title":       r[0] or "",
            "date":        (r[1] or "")[:10],
            "source_db":   "CPD (White House)",
            "description": (r[2] or "")[:150],
            "region":      r[3],
        }
        for r in rows
    ]


def stats() -> dict:
    if not _DB_PATH.exists():
        return {"error": "DB 없음"}
    con = sqlite3.connect(str(_DB_PATH))
    try:
        total = con.execute("SELECT COUNT(*) FROM govinfo_releases").fetchone()[0]
        by_region = con.execute(
            "SELECT region_hint, COUNT(*) FROM govinfo_releases WHERE region_hint IS NOT NULL GROUP BY region_hint ORDER BY 2 DESC"
        ).fetchall()
        latest = con.execute(
            "SELECT title, pub_date FROM govinfo_releases ORDER BY pub_date DESC LIMIT 5"
        ).fetchall()
    finally:
        con.close()
    return {
        "total": total,
        "by_region": dict(by_region),
        "latest": [{"title": r[0][:60], "date": r[1]} for r in latest],
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if "--stats" in sys.argv:
        print(json.dumps(stats(), indent=2, ensure_ascii=False))
    elif "--search" in sys.argv:
        idx = sys.argv.index("--search")
        q = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Korea"
        results = search_local(q)
        for r in results:
            print(f"[{r['date']}] {r['title']}")
            if r['description']:
                print(f"  {r['description'][:100]}")
    else:
        # 최근 30일치 수집 (첫 실행)
        n = collect_recent(days_back=30)
        print(f"완료 — 신규 {n}건")
        print(json.dumps(stats(), indent=2, ensure_ascii=False))
