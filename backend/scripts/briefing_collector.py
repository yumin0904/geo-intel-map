"""
briefing_collector.py — 브리핑 수집러 (1단계)

RSS 피드에서 새 보고서를 수집해 briefing_queue.yaml에 추가한다.
분석·등록은 사용자가 직접 수행한다.

사용법:
    python3 scripts/briefing_collector.py          # 수집 실행
    python3 scripts/briefing_collector.py --dry-run # 추가 없이 목록만 출력
    python3 scripts/briefing_collector.py --done <id>  # 항목 done 처리

워크플로우:
    1. 이 스크립트 실행 → briefing_queue.yaml 업데이트
    2. queue 파일 열어서 관심 항목 확인
    3. URL 열어 읽고 분석 요약 작성 → Claude Code에 붙여넣기
    4. 등록 완료 후 → python3 scripts/briefing_collector.py --done <id>
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import yaml

# 최근 N일 이내 발행된 보고서만 수집
_MAX_AGE_DAYS = 60

# ── 경로 설정 ────────────────────────────────────────────────────────────────
_ROOT    = Path(__file__).resolve().parents[1]
_CONFIG  = _ROOT / "config"
_SOURCES = _CONFIG / "briefing_sources.yaml"
_QUEUE   = _CONFIG / "briefing_queue.yaml"
_DONE    = _CONFIG / "briefing_done.yaml"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GeoIntelMap-Collector/1.0)"}


# ── 설정 로드 ────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """HTML 태그 및 엔티티 제거."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return " ".join(text.split())[:500]  # 최대 500자


def _parse_date(date_str: str) -> datetime | None:
    """RSS pubDate(RFC 2822) 또는 ISO 8601 날짜 파싱."""
    if not date_str:
        return None
    # RFC 2822 (RSS 2.0)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    # ISO 8601 (Atom)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt[:len(date_str)])
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


# ── RSS 파싱 ─────────────────────────────────────────────────────────────────

def fetch_rss(url: str) -> list[dict]:
    """RSS 피드를 가져와 항목 목록으로 반환."""
    try:
        r = httpx.get(url, headers=_HEADERS, timeout=15, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  fetch 실패: {e}")
        return []

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"  ⚠️  XML 파싱 실패: {e}")
        return []

    # RSS 2.0 또는 Atom 형식 모두 지원
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS)

    # RSS 2.0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url_  = (item.findtext("link") or "").strip()
        desc  = _strip_html(item.findtext("description") or "")
        pub   = (item.findtext("pubDate") or "").strip()
        if not (title and url_):
            continue
        # 날짜 필터: 파싱 실패하면 포함 (최신일 가능성)
        pub_dt = _parse_date(pub)
        if pub_dt and pub_dt < cutoff:
            continue
        items.append({"title": title, "url": url_, "description": desc, "published": pub})

    # Atom
    for entry in root.findall(".//atom:entry", ns):
        title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
        link  = entry.find("atom:link", ns)
        url_  = (link.get("href", "") if link is not None else "").strip()
        desc  = _strip_html(entry.findtext("atom:summary", namespaces=ns) or "")
        pub   = (entry.findtext("atom:published", namespaces=ns) or "").strip()
        if not (title and url_):
            continue
        pub_dt = _parse_date(pub)
        if pub_dt and pub_dt < cutoff:
            continue
        items.append({"title": title, "url": url_, "description": desc, "published": pub})

    return items


# ── 섹터 힌트 추정 ────────────────────────────────────────────────────────────

def guess_sector(title: str, description: str, sector_keywords: dict) -> str:
    """제목+설명에서 가장 잘 맞는 섹터를 추정한다."""
    text = (title + " " + description).lower()
    best_sector = "unknown"
    best_count  = 0

    for sector, keywords in sector_keywords.items():
        count = sum(1 for kw in keywords if kw.lower() in text)
        if count > best_count:
            best_count = count
            best_sector = sector

    return best_sector if best_count > 0 else "unknown"


def is_relevant(title: str, description: str,
                sector_keywords: dict, exclude_keywords: list,
                min_relevance: int) -> bool:
    """이 보고서가 5대 섹터와 관련이 있는지 판단한다."""
    text = (title + " " + description).lower()

    # 제외 키워드 체크
    for kw in exclude_keywords:
        if kw.lower() in text:
            return False

    # 섹터 키워드 매칭 점수
    total = sum(
        sum(1 for kw in kws if kw.lower() in text)
        for kws in sector_keywords.values()
    )
    return total >= min_relevance


def make_id(org: str, url: str) -> str:
    """org + URL 해시로 고유 ID 생성."""
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    slug = org.lower().replace(" ", "-")
    return f"{slug}-{h}"


# ── 메인 수집 로직 ────────────────────────────────────────────────────────────

def collect(dry_run: bool = False) -> int:
    """RSS 피드를 순회하며 새 항목을 queue에 추가한다."""
    cfg     = load_yaml(_SOURCES)
    queue   = load_yaml(_QUEUE)
    done    = load_yaml(_DONE)

    sources          = cfg.get("sources", [])
    sector_keywords  = cfg.get("sector_keywords", {})
    exclude_keywords = cfg.get("exclude_keywords", [])

    # done URL 인덱스 (id + url 기준)
    done_ids  = {d.get("id", "") for d in done.get("done", [])}
    done_urls = {d.get("url", "") for d in done.get("done", [])}

    # 현재 queue URL 인덱스
    pending = queue.get("pending") or []
    queue_urls = {p.get("url", "") for p in pending}

    added = 0
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for src in sources:
        if not src.get("enabled", True):
            continue

        org  = src["org"]
        name = src["name"]
        url  = src["url"]
        min_r = src.get("min_relevance", 1)

        print(f"\n📡 {org} — {name}")
        items = fetch_rss(url)
        print(f"   RSS 항목 {len(items)}개 수신")

        new_count = 0
        for item in items:
            item_url   = item["url"]
            item_title = item["title"]
            item_desc  = item.get("description", "")
            item_pub   = item.get("published", "")

            item_id = make_id(org, item_url)

            # 이미 처리됐거나 queue에 있으면 건너뜀
            if item_id in done_ids or item_url in done_urls or item_url in queue_urls:
                continue

            # 섹터 관련성 필터
            if not is_relevant(item_title, item_desc, sector_keywords, exclude_keywords, min_r):
                continue

            sector = guess_sector(item_title, item_desc, sector_keywords)

            entry = {
                "id":           item_id,
                "org":          org,
                "title":        item_title,
                "url":          item_url,
                "published":    item_pub,
                "sector_hint":  sector,
                "collected_at": now,
            }

            if not dry_run:
                pending.append(entry)
                queue_urls.add(item_url)

            print(f"   ✅ [{sector:12}] {item_title[:60]}")
            new_count += 1
            added += 1

        if new_count == 0:
            print("   — 새 항목 없음")

    if not dry_run and added > 0:
        queue["pending"] = pending
        save_yaml(_QUEUE, queue)
        print(f"\n💾 briefing_queue.yaml 저장 완료 — 총 {added}개 추가")
    elif dry_run:
        print(f"\n🔍 dry-run 모드 — 실제 저장 없음. 추가 예정: {added}개")
    else:
        print("\n✨ 새로운 보고서 없음")

    return added


def mark_done(item_id: str) -> None:
    """queue에서 항목을 꺼내 done으로 이동한다."""
    queue = load_yaml(_QUEUE)
    done  = load_yaml(_DONE)

    pending = queue.get("pending") or []
    target  = next((p for p in pending if p.get("id") == item_id), None)

    if target is None:
        print(f"❌ ID '{item_id}'를 queue에서 찾을 수 없음")
        return

    # done으로 이동
    done_list = done.get("done") or []
    done_list.append({
        "id":    target["id"],
        "org":   target["org"],
        "title": target["title"],
        "url":   target.get("url", ""),
    })

    queue["pending"] = [p for p in pending if p.get("id") != item_id]
    done["done"] = done_list

    save_yaml(_QUEUE, queue)
    save_yaml(_DONE, done)
    print(f"✅ '{target['title'][:50]}' → done 처리 완료")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="브리핑 수집러")
    parser.add_argument("--dry-run", action="store_true", help="저장 없이 목록만 출력")
    parser.add_argument("--done", metavar="ID", help="해당 ID를 done으로 이동")
    args = parser.parse_args()

    if args.done:
        mark_done(args.done)
    else:
        collect(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
