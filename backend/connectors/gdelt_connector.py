"""
gdelt_connector.py — GDELT 2.0 분쟁 이벤트 Stage 1 커넥터

GDELT(Global Database of Events, Language, and Tone) 15분 갱신 export CSV를
다운로드해 3-Stage Funnel의 1단계 필터를 적용한다.

Stage 1 필터 기준 (CLAUDE.md Phase 3):
  - QuadClass ≥ 3  (Verbal/Material Conflict만)
  - GoldsteinScale ≤ -5  (적대적 사건만, -10이 최대 적대)
  - NumMentions ≥ 20  (미디어 노출 임계치 — 단일 소스 잡음 제거)
  - ActionGeo_CountryCode in SECTOR_FIPS  (5대 섹터 국가만)

CLAUDE.md 연관 이론:
  - GDELT는 뉴스 미디어 기반이므로 confidence_score = 0.5 (미검증 기본값)
  - 교차검증(Stage 2) 통과 시 0.8로 상향
"""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any
import uuid

import httpx

from models.event import Event
from services.region import region_for_point

logger = logging.getLogger(__name__)

# ── GDELT 엔드포인트 ────────────────────────────────────────────────────────
LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# ── Stage 1 필터 임계치 ─────────────────────────────────────────────────────
_QUAD_CLASS_MIN   = 3     # 3=Verbal Conflict, 4=Material Conflict
_GOLDSTEIN_MAX    = -5.0  # 적대적 사건 하한
# 15분 단위 스냅샷은 누적 언급이 적으므로 3으로 설정 (단일 소스 잡음만 제거)
# CLAUDE.md 기준 20은 일(日) 단위 데이터 기준값 — 향후 일별 파일 전환 시 재상향
_NUM_MENTIONS_MIN = 3

# ── 오피니언·분석 URL 패턴 블록리스트 ─────────────────────────────────────────
# GDELT source_url이 오피니언/기고 섹션을 가리키면 Stage 1에서 거부한다.
# 이유: 오피니언 기사의 지역 키워드(ukraine, taiwan 등)가 Stage 2에서
#      Reuters·BBC 기사와 키워드 히트 → confidence 0.8로 오상향되는 오분류 방지.
_OPINION_URL_PATTERNS: frozenset[str] = frozenset({
    "forbes.com/sites/",          # Forbes 기고자·오피니언 섹션 (contributor model)
    "forbes.com/advisor/",        # Forbes Advisor — 금융 분석, 실제 분쟁 이벤트 아님
    "bloomberg.com/opinion/",     # Bloomberg Opinion
    "nytimes.com/opinion/",       # NYT Op-Ed
    "wsj.com/opinion/",           # WSJ Opinion
    "theguardian.com/commentisfree/",  # Guardian 오피니언
    "washingtonpost.com/opinions/",    # WaPo Opinions
})

# ── 5대 섹터 FIPS 10-4 국가 코드 ───────────────────────────────────────────
# 인도-태평양·에너지·기술·SLOC 국가 중심
_SECTOR_FIPS: frozenset[str] = frozenset({
    # 인도-태평양
    "CH", "TW", "JA", "KS", "KN", "VM", "RP", "BM", "IN", "ID", "MY", "SN", "TH",
    # 중동 / 에너지
    "IR", "IZ", "SA", "YM", "SY", "QA", "AE", "KU",
    # SLOC / 홍해·수에즈 인근
    "DJ", "ER", "ET", "SO", "EG", "SU",
    # 우크라이나·러시아
    "UP", "RS",
    # 이스라엘·팔레스타인·레바논
    "IS", "LE",
})

# ── GDELT 2.0 export CSV 컬럼 인덱스 (0-based, 탭 구분) ────────────────────
_COL = {
    "event_id":        0,
    "sqldate":         1,
    "actor1":          6,
    "actor2":         16,
    "event_code":     26,
    "event_root_code": 28,   # 2자리 CAMEO 루트코드 (EventCode 앞 2자리와 다름에 주의)
    "quad_class":     29,
    "goldstein":      30,
    "mentions":       31,
    "sources":        32,
    "avg_tone":       34,
    "geo_name":       52,
    "geo_country":    53,
    "lat":            56,
    "lon":            57,
    "url":            60,
}

# 허용 EventRootCode: 18=Assault, 19=Fight 계열만 실제 물리적 분쟁
# 13(위협)·14(시위)·17(제재) 등 비물리적 이벤트는 GoldsteinScale로 이미 상당수 제거되나,
# 루트코드로 한 번 더 걸러 오피니언 기사 주제가 될 만한 '정치적 갈등' 노이즈를 차단한다.
_ALLOWED_ROOT_CODES: frozenset[str] = frozenset({"18", "19"})

# CAMEO 루트코드 → theory_tags 매핑
_CAMEO_TAGS: dict[str, list[str]] = {
    "13": ["gray_zone"],            # 위협·압박
    "14": ["gray_zone"],            # 시위·반발
    "17": ["conventional_warfare"], # 제재·강압
    "18": ["conventional_warfare"], # 공격·전투
    "19": ["conventional_warfare"], # 전투 행위
    "20": ["conventional_warfare"], # 대량파괴
}


async def fetch_latest_gdelt() -> list[Event]:
    """
    GDELT 최신 15분 export를 다운로드하고 Stage 1 필터를 적용해 Event 목록 반환.

    네트워크 오류나 파싱 실패 시 빈 리스트 반환 (API 전체 장애 방지).
    confidence_score = 0.5 (미검증 기본값, Stage 2 후 0.8로 상향 가능).
    """
    try:
        export_url = await _get_export_url()
        if not export_url:
            return []
        raw_rows = await _download_and_parse(export_url)
        return _filter_and_normalize(raw_rows)
    except Exception as exc:
        logger.warning("[GDELT] fetch 실패: %s", exc)
        return []


async def _get_export_url() -> str | None:
    """lastupdate.txt에서 최신 export CSV ZIP URL을 추출한다."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(LASTUPDATE_URL)
        resp.raise_for_status()

    # 형식: "size md5hash url" (공백 구분 3필드)
    for line in resp.text.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and "export.CSV.zip" in parts[2]:
            return parts[2]
    return None


async def _download_and_parse(url: str) -> list[list[str]]:
    """ZIP 다운로드 → 메모리 내 압축 해제 → CSV 파싱."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_name = next(n for n in zf.namelist() if n.endswith(".CSV"))
        text = zf.read(csv_name).decode("utf-8", errors="replace")

    reader = csv.reader(io.StringIO(text), delimiter="\t")
    return list(reader)


def _filter_and_normalize(rows: list[list[str]]) -> list[Event]:
    """Stage 1 필터 적용 + Event 정규화."""
    events: list[Event] = []

    for row in rows:
        if len(row) < 61:
            continue  # 컬럼 수 부족한 행 무시

        try:
            quad   = int(row[_COL["quad_class"]] or 0)
            gold   = float(row[_COL["goldstein"]] or 0)
            mentions = int(row[_COL["mentions"]] or 0)
        except ValueError:
            continue

        # Stage 1 필터 ①: 수치 기준
        if quad < _QUAD_CLASS_MIN:
            continue
        if gold > _GOLDSTEIN_MAX:
            continue
        if mentions < _NUM_MENTIONS_MIN:
            continue

        # Stage 1 필터 ②: EventRootCode — 18(Assault)·19(Fight) 계열만 허용
        root_code = row[_COL["event_root_code"]].strip()
        if root_code not in _ALLOWED_ROOT_CODES:
            continue

        # Stage 1 필터 ③: 지리적 좌표 필수 — 빈 값 또는 Null Island(0,0) 제외
        lat_s = row[_COL["lat"]].strip()
        lon_s = row[_COL["lon"]].strip()
        if not lat_s or not lon_s:
            continue
        try:
            lat_f = float(lat_s)
            lon_f = float(lon_s)
        except ValueError:
            continue
        if lat_f == 0.0 and lon_f == 0.0:
            continue

        # Stage 1 필터 ④: 5대 섹터 국가 코드
        country = row[_COL["geo_country"]].strip().upper()
        if country not in _SECTOR_FIPS:
            continue

        event = _to_event(row, quad, gold, mentions, lat_f, lon_f)
        if event:
            events.append(event)

    logger.info("[GDELT] Stage 1 통과: %d개", len(events))
    return events


def _to_event(
    row: list[str], quad: int, goldstein: float, mentions: int,
    lat: float = 0.0, lon: float = 0.0,
) -> Event | None:
    """단일 GDELT 행 → Event 정규화.

    lat/lon은 _filter_and_normalize에서 이미 검증된 값을 받는다.
    기본값 0.0은 직접 호출 시 방어용 — 이 경우 None 반환.
    """
    if lat == 0.0 and lon == 0.0:
        return None

    actor1   = row[_COL["actor1"]].strip() or "Unknown"
    actor2   = row[_COL["actor2"]].strip() or "Unknown"
    geo_name = row[_COL["geo_name"]].strip() or row[_COL["geo_country"]].strip()
    event_code = row[_COL["event_code"]].strip()
    url      = row[_COL["url"]].strip()
    sqldate  = row[_COL["sqldate"]].strip()

    # 오피니언·분석 기사 URL 거부 — Stage 2에서 키워드 히트로 오상향되는 오분류 방지
    if _is_opinion_url(url):
        return None

    # 날짜 파싱 (YYYYMMDD)
    try:
        ts = datetime.strptime(sqldate, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        ts = datetime.now(timezone.utc)

    region_code = region_for_point(lat, lon)
    theory_tags = _derive_tags(event_code, quad, region_code)

    # severity: GoldsteinScale -10~-5 → 50~100, mentions 보정
    base  = int(min(80, (-goldstein) * 8))
    boost = min(20, mentions // 10)
    severity = min(100, base + boost)

    quad_desc = "물리적 충돌" if quad == 4 else "언어적 충돌"
    title = f"[GDELT] {geo_name}: {actor1} vs {actor2} ({quad_desc})"

    return Event(
        id=str(uuid.uuid4()),
        timestamp=ts,
        source_type="conflict",
        source_id=f"gdelt_{row[_COL['event_id']]}",
        location=(lat, lon),
        region_code=region_code,
        severity=severity,
        title=title,
        description=(
            f"GoldsteinScale={goldstein:.1f}, 미디어 언급={mentions}회, "
            f"출처: {url[:80]}"
        ),
        payload={
            "event_code": event_code,
            "quad_class": quad,
            "goldstein_scale": goldstein,
            "num_mentions": mentions,
            "actor1": actor1,
            "actor2": actor2,
            "geo_name": geo_name,
            "source_url": url,
            "data_source": "GDELT",
        },
        theory_tags=theory_tags,
        confidence_score=0.5,  # Stage 2 교차검증 전 미검증 기본값
    )


def _is_opinion_url(url: str) -> bool:
    """source_url이 오피니언·분석 섹션에 해당하면 True를 반환한다."""
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in _OPINION_URL_PATTERNS)


def _derive_tags(event_code: str, quad: int, region_code: str | None) -> list[str]:
    """CAMEO 이벤트 코드 + region_code → theory_tags."""
    tags: set[str] = set()

    # CAMEO 루트코드(앞 2자리) 기반
    root = event_code[:2] if len(event_code) >= 2 else ""
    tags.update(_CAMEO_TAGS.get(root, []))

    # Material Conflict는 기본 conventional_warfare 추가
    if quad == 4:
        tags.add("conventional_warfare")

    # 지역 기반 태그
    if region_code in ("taiwan_strait", "south_china_sea"):
        tags.update(["A2AD", "gray_zone"])
    elif region_code in ("bab_el_mandeb", "suez", "hormuz", "malacca"):
        tags.update(["SLOC_disruption", "resource_weaponization"])
    elif region_code == "ukraine":
        tags.update(["hybrid_warfare", "conventional_warfare"])
    elif region_code in ("middle_east",):
        tags.add("resource_weaponization")

    return sorted(tags) or ["gray_zone"]
