"""
services/intel_analyzer.py

멀티소스 병렬 검색 + 컨텍스트 조립 (Token-Zero).

소스:
  1. LIKE 검색 — 한국어 키워드로 브리핑·이론 title/body 검색
  2. 섹터 필터 — 섹터별 최신 브리핑
  3. 브리핑 원문 (body) — 상위 3개 전체 본문 포함 (핵심 개선)
  4. event_archive 통계 — 지역별 집계
  5. cascade_links — 지역 발화 실적 + 이론 텍스트
  6. country_geopolitics.yaml — 행위자 국가 프로파일
"""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import yaml
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from services.entity_parser import ParsedQuery

logger = logging.getLogger(__name__)

_CONFIG   = Path(__file__).resolve().parent.parent / "config"
_INTEL_DB = Path(__file__).resolve().parent.parent / "db" / "intel.db"
_LIB_DB   = Path(__file__).resolve().parent.parent / "db" / "library.db"

# 브리핑 원문 1개당 최대 포함 글자 수 (토큰 절약)
_BODY_MAX_CHARS = 3000
# Gemini 컨텍스트 총 상한 (글자 기준 — 약 30,000 tokens)
_CONTEXT_MAX_CHARS = 20000


@contextmanager
def _db(path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# ── 1. LIKE 기반 한국어 키워드 검색 ─────────────────────────────────────────

def _extract_keywords(query: str) -> list[str]:
    """쿼리에서 유의미한 키워드 추출 (한국어 2자+ / 영어 3자+)."""
    ko = re.findall(r"[가-힣]{2,}", query)
    en = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", query)
          if w.lower() not in {"the", "and", "for", "with", "this", "that"}]
    return (ko + en)[:8]


def _search_library_like(query: str, regions: list[str],
                          sectors: list[str], limit: int = 10) -> list[dict]:
    """
    LIKE 기반 한국어·영어 혼합 검색.
    title + summary + body 전체에서 키워드 매칭.
    """
    keywords = _extract_keywords(query)

    # 지역 한국어 별칭도 검색 키워드에 추가
    _REGION_KO_SEARCH = {
        "ukraine": ["우크라이나", "러시아"], "taiwan_strait": ["대만", "양안"],
        "hormuz": ["호르무즈", "이란"], "bab_el_mandeb": ["홍해", "후티"],
        "south_china_sea": ["남중국해"], "korean_peninsula": ["한반도", "북한"],
        "middle_east": ["중동", "이스라엘"], "east_china_sea": ["동중국해"],
    }
    for r in regions:
        keywords.extend(_REGION_KO_SEARCH.get(r, []))
    keywords = list(dict.fromkeys(keywords))[:10]  # 중복 제거

    if not keywords:
        return []

    try:
        with _db(_LIB_DB) as con:
            # 키워드별 히트 수로 관련도 계산
            conditions = " OR ".join(
                f"(title LIKE ? OR summary LIKE ? OR body LIKE ?)"
                for _ in keywords
            )
            params = []
            for kw in keywords:
                pat = f"%{kw}%"
                params.extend([pat, pat, pat])
            params.append(limit)

            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary,
                       source_org, geopol_region, asset_type,
                       published_date, body
                FROM theories
                WHERE {conditions}
                ORDER BY published_date DESC NULLS LAST
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] LIKE 검색 실패: %s", e)
        return []


# ── 2. 섹터 필터 검색 ────────────────────────────────────────────────────────

def _search_library_by_sector(sectors: list[str], limit: int = 6) -> list[dict]:
    """섹터 필터로 최신 브리핑·이론 조회 (body 포함)."""
    if not sectors:
        return []
    placeholders = ",".join("?" * len(sectors))
    try:
        with _db(_LIB_DB) as con:
            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary,
                       source_org, geopol_region, asset_type,
                       published_date, body
                FROM theories
                WHERE sector_tag IN ({placeholders})
                ORDER BY published_date DESC NULLS LAST
                LIMIT ?
                """,
                (*sectors, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] sector 검색 실패: %s", e)
        return []


# ── 3. event_archive 통계 ────────────────────────────────────────────────────

_REGION_KO: dict[str, list[str]] = {
    "ukraine":          ["우크라이나"],
    "taiwan_strait":    ["대만", "대만해협"],
    "hormuz":           ["호르무즈"],
    "bab_el_mandeb":    ["바브엘만데브", "홍해"],
    "south_china_sea":  ["남중국해"],
    "korean_peninsula": ["한반도", "북한"],
    "malacca":          ["말라카"],
    "suez":             ["수에즈"],
    "middle_east":      ["중동"],
    "east_china_sea":   ["동중국해"],
}


def _get_event_stats(regions: list[str]) -> dict:
    if not regions:
        return {}
    placeholders = ",".join("?" * len(regions))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT region_code, source_type, COUNT(*) as cnt
                FROM event_archive
                WHERE region_code IN ({placeholders})
                GROUP BY region_code, source_type
                ORDER BY cnt DESC LIMIT 20
                """,
                tuple(regions),
            ).fetchall()
            sev_rows = con.execute(
                f"""
                SELECT region_code, ROUND(AVG(severity), 1) as avg_sev,
                       MAX(severity) as max_sev, COUNT(*) as total
                FROM event_archive
                WHERE region_code IN ({placeholders})
                GROUP BY region_code
                """,
                tuple(regions),
            ).fetchall()

        stats: dict = {}
        for r in rows:
            rc = r["region_code"]
            if rc not in stats:
                stats[rc] = {"event_types": {}}
            stats[rc]["event_types"][r["source_type"]] = r["cnt"]
        for r in sev_rows:
            rc = r["region_code"]
            if rc not in stats:
                stats[rc] = {"event_types": {}}
            stats[rc].update({
                "avg_severity": r["avg_sev"],
                "max_severity": r["max_sev"],
                "total_events":  r["total"],
            })
        return stats
    except Exception as e:
        logger.warning("[intel] event_stats 실패: %s", e)
        return {}


# ── 4. cascade_links + cascade_rules 이론 텍스트 ─────────────────────────────

def _get_cascade_context(regions: list[str]) -> dict:
    """cascade_links 발화 실적 + 관련 룰의 이론 텍스트."""
    result: dict = {"links": [], "rules": []}
    if not regions:
        return result

    # cascade_links 조회
    ko_keywords: list[str] = []
    for r in regions:
        ko_keywords.extend(_REGION_KO.get(r, [r]))
    try:
        with _db(_INTEL_DB) as con:
            conditions = " OR ".join(f"rule_name LIKE ?" for _ in ko_keywords)
            params     = [f"%{kw}%" for kw in ko_keywords] + [8]
            rows = con.execute(
                f"""
                SELECT rule_name, correlation_score, depth
                FROM cascade_links
                WHERE {conditions}
                ORDER BY correlation_score DESC LIMIT ?
                """,
                params,
            ).fetchall()
        result["links"] = [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] cascade_links 실패: %s", e)

    # cascade_rules.yaml에서 관련 룰 이론 텍스트 추출
    try:
        with open(_CONFIG / "cascade_rules.yaml", encoding="utf-8") as f:
            rules = yaml.safe_load(f) or []

        region_set = set(regions)
        for rule in rules:
            trigger = rule.get("trigger", {})
            rule_region = trigger.get("region", "")
            if rule_region in region_set or not region_set:
                theory = rule.get("theory", {})
                if theory:
                    result["rules"].append({
                        "name":       rule.get("name", rule.get("id", "")),
                        "framework":  theory.get("framework", ""),
                        "reference":  theory.get("reference", ""),
                        "learning":   theory.get("learning_note", ""),
                    })
    except Exception as e:
        logger.warning("[intel] cascade_rules 로드 실패: %s", e)

    return result


# ── 5. 국가 프로파일 ──────────────────────────────────────────────────────────

def _get_country_profiles(actors: list[str]) -> dict:
    if not actors:
        return {}
    try:
        with open(_CONFIG / "country_geopolitics.yaml", encoding="utf-8") as f:
            cg = yaml.safe_load(f)
        profiles = cg.get("profiles", {})
        return {iso3: profiles[iso3] for iso3 in actors if iso3 in profiles}
    except Exception as e:
        logger.warning("[intel] country_profiles 실패: %s", e)
        return {}


# ── 컨텍스트 조립 ─────────────────────────────────────────────────────────────

def _build_context(
    pq:               ParsedQuery,
    like_items:       list[dict],
    sector_items:     list[dict],
    event_stats:      dict,
    cascade_ctx:      dict,
    country_profiles: dict,
) -> str:
    lines: list[str] = []
    total_chars = 0

    # ── 쿼리 요약 ──────────────────────────────────────────────────────────
    lines.append("## 분석 쿼리 요약")
    lines.append(f"- 지역: {', '.join(pq.regions) or '미지정'}")
    lines.append(f"- 행위자: {', '.join(pq.actors) or '미지정'}")
    lines.append(f"- 섹터: {', '.join(pq.sectors) or '전체'}")
    lines.append("")

    # ── 브리핑·이론 원문 (상위 3개 full body) ─────────────────────────────
    # LIKE 검색 결과 우선, 섹터 필터로 보완, 중복 제거
    seen_ids: set[str] = set()
    all_items: list[dict] = []
    for item in like_items + sector_items:
        tid = item.get("theory_id", "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            all_items.append(item)

    # body 있는 것 우선 정렬
    all_items.sort(key=lambda x: len(x.get("body") or ""), reverse=True)

    body_count = 0
    meta_items = []

    for item in all_items:
        body = (item.get("body") or "").strip()
        org  = f"[{item.get('source_org', '')}] " if item.get("source_org") else ""
        title = item.get("title", "")

        if body and body_count < 3 and total_chars < _CONTEXT_MAX_CHARS:
            # 원문 포함 (최대 3개, 각 3000자)
            truncated = body[:_BODY_MAX_CHARS]
            if len(body) > _BODY_MAX_CHARS:
                truncated += "\n...(이하 생략)"
            section = f"### {org}{title}\n{truncated}\n"
            lines.append(section)
            total_chars += len(section)
            body_count += 1
        else:
            # 원문 초과 시 제목+요약만
            meta_items.append(item)

    if body_count > 0:
        lines.insert(2, f"## 브리핑·이론 원문 ({body_count}개 전문 포함)\n")

    # 나머지는 제목+요약만
    if meta_items:
        lines.append("## 추가 관련 브리핑 (요약)")
        for item in meta_items[:5]:
            org   = f"[{item.get('source_org', '')}] " if item.get("source_org") else ""
            lines.append(f"- {org}{item.get('title', '')}")
            summary = (item.get("summary") or "")[:150]
            if summary:
                lines.append(f"  {summary}")
        lines.append("")

    # ── Cascade 룰 이론 텍스트 ────────────────────────────────────────────
    cascade_rules = cascade_ctx.get("rules", [])
    if cascade_rules:
        lines.append("## Cascade 인과 룰 (이론 근거)")
        for rule in cascade_rules[:4]:
            lines.append(f"- **{rule['name']}**")
            if rule.get("framework"):
                lines.append(f"  이론: {rule['framework']} ({rule.get('reference', '')})")
            if rule.get("learning"):
                lines.append(f"  해석: {rule['learning']}")
        lines.append("")

    # ── Cascade 발화 실적 ─────────────────────────────────────────────────
    cascade_links = cascade_ctx.get("links", [])
    if cascade_links:
        lines.append("## Cascade 발화 실적 (실제 데이터)")
        for lnk in cascade_links[:5]:
            lines.append(
                f"- {lnk['rule_name']} "
                f"(상관계수 {lnk['correlation_score']}, {lnk.get('depth', 1)}단계)"
            )
        lines.append("")

    # ── 이벤트 통계 ───────────────────────────────────────────────────────
    if event_stats:
        lines.append("## ACLED 이벤트 통계")
        for region, stats in event_stats.items():
            total = stats.get("total_events", "?")
            avg_s = stats.get("avg_severity", "?")
            lines.append(f"- **{region}**: 총 {total}건, 평균 심각도 {avg_s}/100")
            top3 = sorted(stats.get("event_types", {}).items(), key=lambda x: -x[1])[:3]
            if top3:
                lines.append("  유형: " + " / ".join(f"{t}({n}건)" for t, n in top3))
        lines.append("")

    # ── 국가 프로파일 ─────────────────────────────────────────────────────
    if country_profiles:
        lines.append("## 행위자 국가 프로파일")
        for iso3, profile in country_profiles.items():
            posture  = profile.get("strategic_posture", "?")
            position = profile.get("strategic_position", "?")
            inst     = profile.get("instrument_of_power", "?")
            risks    = profile.get("key_risks", [])
            lines.append(f"- **{iso3}**: {position}")
            lines.append(f"  포지션={posture} | 주요수단={inst}")
            if risks:
                lines.append(f"  주요위험: {', '.join(str(r) for r in risks[:3])}")
        lines.append("")

    return "\n".join(lines)


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

async def build_intel_context(pq: ParsedQuery) -> dict:
    loop = asyncio.get_event_loop()

    results = await asyncio.gather(
        loop.run_in_executor(None, _search_library_like,
                             pq.raw_query, pq.regions, pq.sectors),
        loop.run_in_executor(None, _search_library_by_sector, pq.sectors),
        loop.run_in_executor(None, _get_event_stats, pq.regions),
        loop.run_in_executor(None, _get_cascade_context, pq.regions),
        loop.run_in_executor(None, _get_country_profiles, pq.actors),
        return_exceptions=True,
    )

    def _safe(r, default):
        return r if not isinstance(r, Exception) else default

    like_items       = _safe(results[0], [])
    sector_items     = _safe(results[1], [])
    event_stats      = _safe(results[2], {})
    cascade_ctx      = _safe(results[3], {"links": [], "rules": []})
    country_profiles = _safe(results[4], {})

    context_text = _build_context(
        pq, like_items, sector_items, event_stats, cascade_ctx, country_profiles
    )

    logger.debug(
        "[intel] 컨텍스트 조립 — LIKE=%d, sector=%d, 총길이=%d자",
        len(like_items), len(sector_items), len(context_text),
    )

    return {
        "context_text": context_text,
        "source_counts": {
            "fts_items":           len(like_items),
            "sector_items":        len(sector_items),
            "event_stats_regions": len(event_stats),
            "cascade_links":       len(cascade_ctx.get("links", [])),
            "country_profiles":    len(country_profiles),
        },
        "like_items":        like_items,
        "sector_items":      sector_items,
        "event_stats":       event_stats,
        "cascade_ctx":       cascade_ctx,
        "country_profiles":  country_profiles,
    }
