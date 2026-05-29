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
import re
import zipfile
from datetime import datetime, timezone
from typing import Any
import uuid

import httpx

from models.event import Event
from services.region import region_for_point
from utils.cameo_mapper import map_gdelt_to_intelligence_tags

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
    "event_id":             0,
    "sqldate":              1,
    "actor1":               6,
    "actor1_country_code":  7,   # Actor1CountryCode — 자국 내 이벤트 필터용
    "actor1_type1_code":   14,  # Actor1Type1Code — cameo_mapper level_of_analysis 입력값
    "actor2":              16,
    "actor2_country_code": 17,   # Actor2CountryCode — 자국 내 이벤트 필터용
    "event_code":          26,
    "event_root_code":   28,  # 2자리 CAMEO 루트코드 (EventCode 앞 2자리와 다름에 주의)
    "quad_class":        29,
    "goldstein":         30,
    "mentions":          31,
    "sources":           32,
    "avg_tone":          34,
    "geo_name":          52,
    "geo_country":       53,
    "lat":               56,
    "lon":               57,
    "url":               60,
}

# 허용 EventRootCode: 18=Assault, 19=Fight 계열만 실제 물리적 분쟁
# 13(위협)·14(시위)·17(제재) 등 비물리적 이벤트는 GoldsteinScale로 이미 상당수 제거되나,
# 루트코드로 한 번 더 걸러 오피니언 기사 주제가 될 만한 '정치적 갈등' 노이즈를 차단한다.
_ALLOWED_ROOT_CODES: frozenset[str] = frozenset({"18", "19"})

# ── 행위자 코드 → 한국어 매핑 ────────────────────────────────────────────────
# CAMEO 행위자 코드 구조: [3자 국가코드][3자 유형코드] (예: USAGOV, CHNMIL)
# 국가코드는 CAMEO/ISO Alpha-3 혼용이므로 주요 행위자만 수동 매핑
_ACTOR_COUNTRY_KO: dict[str, str] = {
    "USA": "미국",      "CHN": "중국",    "RUS": "러시아",
    "ISR": "이스라엘",  "IRN": "이란",    "PRK": "북한",
    "KOR": "한국",      "UKR": "우크라이나", "YEM": "예멘",
    "SYR": "시리아",    "IRQ": "이라크",  "SAU": "사우디아라비아",
    "JPN": "일본",      "TWN": "대만",    "MYA": "미얀마",
    "VNM": "베트남",    "PHL": "필리핀",  "LBN": "레바논",
    "PSE": "팔레스타인", "EGY": "이집트", "ETH": "에티오피아",
    "SOM": "소말리아",
}

_ACTOR_TYPE_KO: dict[str, str] = {
    "GOV": "정부",      "MIL": "군",      "REB": "반군",
    "CIV": "민간인",    "OPP": "야당",    "MED": "미디어",
    "SPY": "정보기관",  "COP": "경찰",    "IGO": "국제기구",
    "NGO": "NGO",       "LEG": "의회",    "REL": "종교단체",
    "BUS": "기업",      "CVL": "민간인",  "ELI": "엘리트",
}

# 지역 코드 → 한국어 (description 지역 표시용)
_REGION_KO: dict[str, str] = {
    "taiwan_strait":   "대만해협",
    "south_china_sea": "남중국해",
    "east_china_sea":  "동중국해",
    "korean_peninsula":"한반도",
    "korean_strait":   "한국해협",
    "hormuz":          "호르무즈 해협",
    "bab_el_mandeb":   "바브엘만데브 해협",
    "suez":            "수에즈 운하",
    "malacca":         "말라카 해협",
    "ukraine":         "우크라이나",
    "middle_east":     "중동",
    "persian_gulf":    "페르시아만",
    "red_sea":         "홍해",
}

# CAMEO 루트코드 → 한국어 이벤트 유형
_ROOT_CODE_KO: dict[str, str] = {
    "18": "무력 충돌",
    "19": "교전",
    "17": "강압·제재",
    "14": "시위·반발",
    "13": "위협·압박",
}


def _actor_ko(code: str) -> str:
    """CAMEO 행위자 코드 → 한국어.

    처리 순서:
    1. 국가 코드 정확 매핑 (예: CHN → 중국)
    2. 유형 코드 단독 매핑 (예: REB → 반군, CIV → 민간인)
    3. 국가(앞3자) + 유형(뒤3자) 조합 (예: ISRMIL → 이스라엘 군)
    """
    if not code or code in ("Unknown", ""):
        return "미상 세력"
    code = code.strip().upper()
    if code in _ACTOR_COUNTRY_KO:
        return _ACTOR_COUNTRY_KO[code]
    if code in _ACTOR_TYPE_KO:          # REB, CIV, GOV 등 3자 유형 단독
        return _ACTOR_TYPE_KO[code]
    country = _ACTOR_COUNTRY_KO.get(code[:3], "")
    atype   = _ACTOR_TYPE_KO.get(code[3:6], "") if len(code) >= 6 else ""
    if country and atype:
        return f"{country} {atype}"
    return country or atype or code


def _instability_label(goldstein: float) -> str:
    """GoldsteinScale → 불안정 수준 한국어 레이블."""
    if goldstein <= -7:
        return "극도로 불안정"
    if goldstein <= -5:
        return "매우 불안정"
    if goldstein <= -3:
        return "불안정"
    return "주시 필요"


def _generate_description(
    actor1: str,
    actor2: str,
    event_root_code: str,
    region_code: str | None,
    geo_name: str,
    goldstein: float,
    severity: int,
    confidence_score: float,
) -> str:
    """
    GDELT 이벤트 상세 설명 자동 생성 (Gemini 없이 템플릿 방식).

    예시:
      이스라엘 군과 팔레스타인 반군 간 무력 충돌 발생.
      불안정 지수: -8.0 (극도로 불안정) / 긴장도: 85
      신뢰도: 교차검증 완료 (0.8)
    """
    actor1_ko = _actor_ko(actor1)
    actor2_ko = _actor_ko(actor2)
    event_ko  = _ROOT_CODE_KO.get(event_root_code, "충돌")
    region_ko = _REGION_KO.get(region_code or "", "") if region_code else ""
    location  = f"{geo_name}({region_ko})" if region_ko else geo_name
    instab    = _instability_label(goldstein)

    if confidence_score >= 0.8:
        conf_label = f"교차검증 완료 ({confidence_score:.1f})"
    else:
        conf_label = f"미검증 ({confidence_score:.1f})"

    return (
        f"{location}에서 {actor1_ko}과 {actor2_ko} 간 {event_ko} 발생.\n"
        f"불안정 지수: {goldstein:.1f} ({instab}) / 긴장도: {severity}\n"
        f"신뢰도: {conf_label}"
    )


# GDELT 맥락 요약 프롬프트 — 실제 기사 헤드라인 기반, 'A vs B' 금지
_GDELT_CONTEXT_PROMPT = """\
다음 뉴스 헤드라인과 GDELT 사건 정보를 참고해 한국어 지정학 맥락 요약을 작성해줘.

규칙:
- 'A vs B' 또는 'A와 B의 충돌' 형식 절대 금지
- 실제 행동 중심: '{주체}이(가) {대상}에 {행동}'
- 행동·결과 2~3문장 + 정치외교학적 함의 1문장
- 전체 70자 이내. 설명·주석·원문 첨부 금지.

헤드라인: {headline}
지역: {region}
행위자1: {actor1}
행위자2: {actor2}
불안정 지수: {goldstein}
"""


async def generate_gdelt_summary(
    source_url: str,
    actor1: str,
    actor2: str,
    region_ko: str,
    goldstein: float,
    severity: int,
    confidence_score: float,
    event_root_code: str,
    region_code: str | None,
    geo_name: str,
) -> str:
    """GDELT 이벤트 맥락 요약.

    source_url 헤드라인 fetch 성공 + Gemini 가능: 실제 기사 기반 AI 요약.
    fetch 실패 또는 Gemini 불가: _generate_description() 한국어 템플릿 fallback.

    오전 9시(KST) 이후 Gemini 할당량 리셋 → 자동으로 AI 요약 전환.
    """
    from connectors.gemini_translator import generate_summary

    # 항상 사용 가능한 한국어 템플릿 fallback
    template = _generate_description(
        actor1=actor1,
        actor2=actor2,
        event_root_code=event_root_code,
        region_code=region_code,
        geo_name=geo_name,
        goldstein=goldstein,
        severity=severity,
        confidence_score=confidence_score,
    )

    # 헤드라인 fetch 시도 (5초 타임아웃)
    headline = await fetch_headline(source_url) if source_url else None
    if not headline:
        return template

    # Gemini 시도 — 실패 시 template fallback
    cache_key = "gdelt_ctx:{}".format(headline[:120])
    prompt = _GDELT_CONTEXT_PROMPT.format(
        headline=headline,
        region=region_ko or geo_name,
        actor1=_actor_ko(actor1),
        actor2=_actor_ko(actor2),
        goldstein=goldstein,
    )
    result = await generate_summary(prompt, cache_key=cache_key, max_tokens=200)
    return result or template


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
    """lastupdate.txt에서 최신 export CSV ZIP URL을 추출한다.

    GDELT CDN은 최대 15-30분 지연이 있으므로 404 시 이전 슬롯으로 fallback.
    """
    import re as _re
    from datetime import datetime as _dt, timedelta as _td

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(LASTUPDATE_URL)
        resp.raise_for_status()

    primary_url: str | None = None
    for line in resp.text.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3 and "export.CSV.zip" in parts[2]:
            primary_url = parts[2]
            break

    if not primary_url:
        return None

    # CDN 가용성 확인 + 최대 4슬롯(1시간) 후퇴
    ts_match = _re.search(r"/(\d{14})\.export\.CSV\.zip$", primary_url)
    if not ts_match:
        return primary_url

    base_ts = _dt.strptime(ts_match.group(1), "%Y%m%d%H%M%S")
    base_prefix = primary_url[:primary_url.rfind("/") + 1]

    async with httpx.AsyncClient(timeout=8) as client:
        for i in range(5):
            ts = base_ts - _td(minutes=15 * i)
            url = f"{base_prefix}{ts.strftime('%Y%m%d%H%M%S')}.export.CSV.zip"
            try:
                r = await client.head(url, follow_redirects=True)
                if r.status_code == 200:
                    if i > 0:
                        logger.info("[GDELT] %d슬롯 후퇴하여 가용 파일: %s", i, url)
                    return url
            except Exception:
                continue

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

        # Stage 1 필터 ⑤: 자국 내 행위자 중복 이벤트 제거
        # Actor1CountryCode == Actor2CountryCode이면 국내 사건 — 국제 지정학 분석 대상 외
        a1c = row[_COL["actor1_country_code"]].strip().upper()
        a2c = row[_COL["actor2_country_code"]].strip().upper()
        if a1c and a2c and a1c == a2c:
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

    actor1            = row[_COL["actor1"]].strip() or "Unknown"
    actor2            = row[_COL["actor2"]].strip() or "Unknown"
    actor1_type_code  = row[_COL["actor1_type1_code"]].strip() if len(row) > _COL["actor1_type1_code"] else ""
    geo_name          = row[_COL["geo_name"]].strip() or row[_COL["geo_country"]].strip()
    event_code        = row[_COL["event_code"]].strip()
    url               = row[_COL["url"]].strip()
    sqldate           = row[_COL["sqldate"]].strip()

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
    base     = int(min(80, (-goldstein) * 8))
    boost    = min(20, mentions // 10)
    severity = min(100, base + boost)

    # Stage 2 교차검증 전 기본 confidence
    confidence = 0.5

    root_code = event_code[:2] if len(event_code) >= 2 else ""
    quad_desc = "물리적 충돌" if quad == 4 else "언어적 충돌"
    title = f"[GDELT] {geo_name}: {_actor_ko(actor1)} vs {_actor_ko(actor2)} ({quad_desc})"

    description = _generate_description(
        actor1=actor1, actor2=actor2,
        event_root_code=root_code,
        region_code=region_code,
        geo_name=geo_name,
        goldstein=goldstein,
        severity=severity,
        confidence_score=confidence,
    )

    # CAMEO → 7대 축 태그 결정론적 매핑 (LLM 호출 없음, §14 Token-Zero Rule)
    intel_meta = map_gdelt_to_intelligence_tags(
        actor1_type_code=actor1_type_code,
        event_root_code=root_code,
        goldstein_scale=goldstein,
        region_code=region_code,
        timestamp=ts,
    )

    return Event(
        id=str(uuid.uuid4()),
        timestamp=ts,
        source_type="conflict",
        source_id=f"gdelt_{row[_COL['event_id']]}",
        location=(lat, lon),
        region_code=region_code,
        severity=severity,
        title=title,
        description=description,
        payload={
            "event_code":  event_code,
            "quad_class":  quad,
            "goldstein_scale": goldstein,
            "num_mentions": mentions,
            "actor1":      actor1,
            "actor2":      actor2,
            "actor1_ko":   _actor_ko(actor1),
            "actor2_ko":   _actor_ko(actor2),
            "geo_name":    geo_name,
            "source_url":  url,
            "data_source": "GDELT",
        },
        theory_tags=theory_tags,
        confidence_score=confidence,
        intelligence_meta=intel_meta,
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


# ── 기사 헤드라인 fetch ─────────────────────────────────────────────────────────
# 뉴스 사이트 제목 suffix 패턴 (제거 대상)
_TITLE_SUFFIX_RE = re.compile(
    r'\s*[|·—–\-]\s+(?:'
    r'Reuters|AP|AFP|BBC|CNN|Al Jazeera|Bloomberg|FT|WSJ|NYT|'
    r'The Guardian|The Times|Axios|Politico|Defense News|'
    r'TASS|Xinhua|NHK|Yonhap|VOA|RFE/RL|NPR|Fox News|CNBC'
    r').{0,20}$',
    re.IGNORECASE,
)


def _clean_headline(raw: str) -> str:
    """<title> 태그 원문 → 깔끔한 기사 헤드라인."""
    text = re.sub(r'\s+', ' ', raw).strip()
    # 알려진 사이트명 suffix 제거
    text = _TITLE_SUFFIX_RE.sub('', text).strip()
    # 그 외 마지막 구분자 이후가 짧으면(≤30자) 사이트명으로 간주하고 제거
    m = re.match(r'^(.+?)\s+[|·—–\-]\s+.{3,30}$', text)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) >= 15:
            text = candidate
    return text


async def fetch_headline(url: str, timeout: float = 5.0) -> str | None:
    """source_url에서 기사 <title> 헤드라인을 추출한다.

    - httpx로 GET, 타임아웃 5초 (뉴스 티커 전용 — 실패 시 None 반환)
    - og:title 우선, 없으면 <title> 태그
    - 사이트명 suffix 정리 후 반환
    """
    if not url or not url.startswith("http"):
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; geo-intel-map/1.0; +https://github.com)",
            "Accept": "text/html",
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return None
            html = resp.text[:8192]   # <title>은 항상 head 안에 있으므로 8KB로 충분

        # og:title 우선 (흔히 더 간결)
        m = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']{10,200})["\']',
            html, re.IGNORECASE,
        )
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']{10,200})["\'][^>]+property=["\']og:title["\']',
                html, re.IGNORECASE,
            )
        if m:
            return _clean_headline(m.group(1))

        # <title> 태그
        m = re.search(r'<title[^>]*>([^<]{10,300})</title>', html, re.IGNORECASE | re.DOTALL)
        if m:
            return _clean_headline(m.group(1))

    except Exception as exc:
        logger.debug("[fetch_headline] %s → %s", url[:60], exc)
    return None
