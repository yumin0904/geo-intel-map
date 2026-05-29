"""
gdelt_gkg.py — GDELT 2.0 GKG(Global Knowledge Graph) 커넥터

GKG는 GDELT events와 동일한 15분 주기로 업데이트되며,
각 뉴스 기사(DocumentIdentifier = source URL)에 대해
테마·톤·위치·인물·기관 정보를 구조화한다.

활용 목적:
  - GDELT events 커넥터가 수집한 이벤트의 source_url로 GKG를 조회
  - V2Themes → 7대 축 태그 보강 (cameo_mapper.map_gkg_themes_to_tags)
  - V2Tone → 기사 감성 점수 → confidence 보정
  - 5대 섹터 GKG 테마 독립 이벤트 생성 (events 파일에 없는 보충 신호)

CLAUDE.md §14-A Token-Zero Rule:
  GKG 테마 → 7대 축 매핑도 결정론적 파이썬 로직으로 처리 (LLM 0토큰)

GKG V2 주요 컬럼 (탭 구분):
  0: GKGRECORDID
  1: DATE (YYYYMMDDHHMMSS)
  2: SourceCollectionIdentifier
  3: SourceCommonName
  4: DocumentIdentifier (source URL)
  5: Counts
  6: V2Counts
  7: Themes             ← 세미콜론 구분 GDELT 테마 코드
  8: V2Themes
  9: Locations
 10: V2Locations        ← 위치 정보 (CountryCode 포함)
 11~14: Persons/Orgs
 15: V2Tone             ← 쉼표 구분 7개 점수 (tone,positive,negative,...)
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field
from typing import Iterator

import httpx

logger = logging.getLogger(__name__)

# ── GKG 다운로드 설정 ─────────────────────────────────────────────────────────
LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
_FETCH_TIMEOUT = 90  # GKG는 ~6MB 압축 파일

# ── 컬럼 인덱스 (탭 구분, 0-based) ───────────────────────────────────────────
_COL = {
    "date":      1,
    "source":    3,   # SourceCommonName
    "url":       4,   # DocumentIdentifier
    "themes":    7,   # Themes (세미콜론 구분)
    "v2themes":  8,   # V2Themes (테마;오프셋 형식)
    "v2loc":    10,   # V2Locations (세미콜론 구분)
    "v2tone":   15,   # V2Tone (쉼표 구분 7개 점수)
}

# ── 5대 섹터 관련 GKG 테마 코드 접두사 ────────────────────────────────────────
# GKG 테마는 계층적 코드 (예: CRISISLEX_CRISISLEXREC, TAX_FNCACT_REBEL)
# 접두사 매칭으로 관련 테마 추출
_CONFLICT_THEME_PREFIXES = (
    "CONFLICT",           # 일반 분쟁
    "MILITARY",           # 군사 활동
    "WA_",                # 무기류
    "CRISISLEX_",         # 위기 어휘 (인도주의 위기, 분쟁)
    "PROTEST",            # 시위·반란
    "TAX_FNCACT_REBEL",   # 반군 기능
    "TAX_FNCACT_MILPERSONNELL", # 군 인력
    "UNGP_",              # UN 지도원칙 (인권·분쟁)
    "SANCTIONS",          # 제재
    "EPU_POLICY_",        # 경제정책 불확실성
    "MARITIME_",          # 해양 (자체 GDELT 태그)
)

# ── 5대 섹터 FIPS 코드 (V2Locations CountryCode 필드 매칭용) ──────────────────
_SECTOR_FIPS = frozenset({
    # 인도-태평양
    "CH", "TW", "JA", "KS", "KN", "VM", "RP", "BM", "ID", "MY", "SN",
    # 중동·에너지
    "IR", "IZ", "SA", "AE", "YM", "SY", "LB", "IS",
    # 유럽·우크라이나
    "UP", "RS",
    # 아프리카 회색지대
    "SO", "ML", "SU", "OD", "ET", "LY",
})


@dataclass
class GkgRecord:
    """GKG 1행의 핵심 정보."""
    url:        str              # DocumentIdentifier (source URL)
    source:     str              # SourceCommonName
    themes:     list[str] = field(default_factory=list)   # 충돌 관련 테마 코드만
    tone:       float = 0.0     # V2Tone[0] = Overall Tone (음수 = 부정적)
    positive:   float = 0.0     # V2Tone[1]
    negative:   float = 0.0     # V2Tone[2]
    country_codes: list[str] = field(default_factory=list)  # V2Locations에서 추출


def _parse_tone(tone_str: str) -> tuple[float, float, float]:
    """V2Tone 문자열 → (overall, positive, negative)."""
    parts = tone_str.split(",")
    try:
        overall  = float(parts[0]) if len(parts) > 0 else 0.0
        positive = float(parts[1]) if len(parts) > 1 else 0.0
        negative = float(parts[2]) if len(parts) > 2 else 0.0
        return overall, positive, negative
    except (ValueError, IndexError):
        return 0.0, 0.0, 0.0


def _parse_themes(themes_str: str) -> list[str]:
    """Themes 문자열에서 5대 섹터 관련 테마만 추출."""
    if not themes_str:
        return []
    results: list[str] = []
    for t in themes_str.split(";"):
        t = t.strip()
        if any(t.startswith(p) for p in _CONFLICT_THEME_PREFIXES):
            results.append(t)
    return results


def _parse_locations(loc_str: str) -> list[str]:
    """V2Locations에서 CountryCode 목록 추출.

    V2Locations 형식: Type#Name#CC#ADM1#Lat#Lon#FeatureID;...
    CC(CountryCode)는 FIPS 10-4 2자리.
    """
    codes: list[str] = []
    for entry in loc_str.split(";"):
        parts = entry.split("#")
        if len(parts) >= 3 and parts[2]:
            codes.append(parts[2].upper())
    return list(set(codes))  # 중복 제거


async def _get_gkg_url() -> str | None:
    """lastupdate.txt에서 최신 GKG ZIP URL 추출 + 가용성 확인.

    GDELT GKG 파일은 lastupdate.txt 기재 시각보다 최대 15-30분 지연될 수 있음.
    404 시 이전 15분 슬롯으로 최대 4회 후퇴(fallback).
    """
    from datetime import timedelta

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(LASTUPDATE_URL)
        resp.raise_for_status()

    primary_url: str | None = None
    for line in resp.text.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and ".gkg.csv.zip" in parts[2]:
            primary_url = parts[2]
            break

    if not primary_url:
        return None

    # 가용성 확인: primary → 이전 15분 슬롯 최대 4회 fallback
    import re as _re
    ts_match = _re.search(r"/(\d{14})\.gkg\.csv\.zip$", primary_url)
    if not ts_match:
        return primary_url

    from datetime import datetime
    base_ts = datetime.strptime(ts_match.group(1), "%Y%m%d%H%M%S")
    base_url_prefix = primary_url[:primary_url.rfind("/") + 1]

    async with httpx.AsyncClient(timeout=8) as client:
        for i in range(5):  # primary + 4 fallback
            ts = base_ts - timedelta(minutes=15 * i)
            url = f"{base_url_prefix}{ts.strftime('%Y%m%d%H%M%S')}.gkg.csv.zip"
            try:
                r = await client.head(url, follow_redirects=True)
                if r.status_code == 200:
                    if i > 0:
                        logger.info("[gkg] %d슬롯 후퇴하여 가용 파일 발견: %s", i, url)
                    return url
            except Exception:
                continue

    return None


async def _download_gkg(url: str) -> Iterator[list[str]]:
    """GKG ZIP 다운로드 → 메모리 압축 해제 → CSV 행 이터레이터."""
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
        text = zf.read(csv_name).decode("utf-8", errors="replace")

    return csv.reader(io.StringIO(text), delimiter="\t")


def _parse_gkg_rows(reader) -> list[GkgRecord]:
    """GKG CSV 전체 행 순회 → 5대 섹터 관련 레코드만 추출."""
    records: list[GkgRecord] = []

    for row in reader:
        if len(row) <= _COL["v2tone"]:
            continue

        themes_str = row[_COL["themes"]]
        themes = _parse_themes(themes_str)
        if not themes:
            continue  # 분쟁 테마 없는 행 건너뜀

        loc_str = row[_COL["v2loc"]]
        country_codes = _parse_locations(loc_str)

        # 5대 섹터 FIPS 필터 — 관련 없는 지역 행 제외
        if country_codes and not any(cc in _SECTOR_FIPS for cc in country_codes):
            continue

        url    = row[_COL["url"]].strip()
        source = row[_COL["source"]].strip()
        if not url:
            continue

        tone_str = row[_COL["v2tone"]]
        overall, positive, negative = _parse_tone(tone_str)

        records.append(GkgRecord(
            url=url,
            source=source,
            themes=themes,
            tone=overall,
            positive=positive,
            negative=negative,
            country_codes=country_codes,
        ))

    return records


async def fetch_gkg_records() -> list[GkgRecord]:
    """최신 15분 GKG 파일 다운로드 후 5대 섹터 레코드 반환.

    반환값: URL 기준으로 정규화된 GkgRecord 목록.
    gdelt_pipeline.py에서 source_url로 조인 후 Event 보강에 사용.
    """
    try:
        gkg_url = await _get_gkg_url()
        if not gkg_url:
            logger.warning("[gkg] lastupdate.txt에서 GKG URL 추출 실패")
            return []

        logger.info("[gkg] 다운로드 시작: %s", gkg_url)
        reader = await _download_gkg(gkg_url)
        records = _parse_gkg_rows(reader)
        logger.info("[gkg] 파싱 완료: %d개 레코드 (5대 섹터 필터 후)", len(records))
        return records

    except Exception as e:
        logger.warning("[gkg] 수집 실패: %s", e)
        return []


def build_gkg_index(records: list[GkgRecord]) -> dict[str, GkgRecord]:
    """URL → GkgRecord 인덱스 생성 (gdelt_pipeline 조인용)."""
    return {r.url: r for r in records}
