"""
acled.py — ACLED 분쟁 이벤트 커넥터 (OAuth 2.0 인증)
ACLED: Armed Conflict Location & Event Data Project (acleddata.com)

CLAUDE.md 연관 섹터:
  - 섹터 4: 인도-태평양 군사 대치 (A2/AD, 제1열도선)
  - 섹터 5: 회색지대 & 비전통 안보 (Hybrid Warfare, Gray Zone)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from connectors.base import BaseConnector
from models.event import Event
from services.region import region_for_point

load_dotenv()
logger = logging.getLogger(__name__)

TOKEN_URL = "https://acleddata.com/oauth/token"
# OAuth 도입 이후 read endpoint URL이 변경될 수 있음 → 환경변수로 분리
ACLED_URL = os.getenv("ACLED_API_URL", "https://api.acleddata.com/acled/read")

# 인도-태평양 집중 — CLAUDE.md 5대 섹터 기준
# 대만해협·남중국해·한반도·미얀마 등 주요 분쟁지역 포함
INDO_PACIFIC_COUNTRIES = [
    "Myanmar", "Philippines", "Vietnam", "Taiwan",
    "South Korea", "North Korea", "Japan", "China",
    "Indonesia", "Malaysia", "Thailand", "Cambodia",
    "India", "Bangladesh",
]

# 호르무즈 해협 인근 — Cascade 트리거(자원무기화)용 걸프 국가
# 해군 커넥터가 아직 없어 ACLED 분쟁 이벤트를 해상긴장 대용으로 사용한다(Phase 2).
GULF_COUNTRIES = [
    "Iran", "Iraq", "Saudi Arabia", "United Arab Emirates",
    "Oman", "Qatar", "Bahrain", "Kuwait", "Yemen",
]

# 중동 분쟁 → 금(GLD) 안전자산 룰용.
# 레반트(이스라엘·레바논·시리아)와 이라크·이란 포함. 호르무즈/바브엘만데브는 별도 region으로 분리됨.
MIDDLE_EAST_COUNTRIES = [
    "Israel", "Lebanon", "Syria", "Iraq", "Iran",
    "Saudi Arabia", "Yemen",
]

# 남중국해 — 방산주(ITA)·천연가스(NG=F) 룰용.
# 영유권 분쟁 주체: 필리핀·베트남·말레이시아·중국. ACLED에 전술적 충돌·해상민병대 이벤트 포함.
SOUTH_CHINA_SEA_COUNTRIES = [
    "Philippines", "Vietnam", "Malaysia", "China",
]

# 수에즈 운하 인근 — 해운주(ZIM) 룰용.
# 운하 본체(이집트)와 인근 이스라엘이 ACLED 이벤트의 주 발원지.
SUEZ_COUNTRIES = ["Egypt", "Israel"]

# event_type별 severity 기본점수 (0-100 스케일)
# 전투(Battles)가 가장 높고, 시위(Protests)가 가장 낮다
_SEVERITY_BASE: dict[str, int] = {
    "Battles":                     70,
    "Explosions/Remote violence":  65,
    "Violence against civilians":  55,
    "Riots":                       35,
    "Protests":                    15,
    "Strategic developments":      20,
}

# A2AD 적용 지역 (반접근/지역거부: 해양 접근 통제 전략 — 제1열도선 내 지역으로 엄격히 제한)
_A2AD_REGIONS: frozenset[str] = frozenset({"taiwan_strait", "south_china_sea"})

# SLOC 차단 위험 지역 (Sea Lines of Communication — Mahan 해양력 이론)
_SLOC_DISRUPTION_REGIONS: frozenset[str] = frozenset({"bab_el_mandeb", "suez", "hormuz"})

# 자원무기화 지역 (에너지 공급 통제 — Hirschman 1945)
_RESOURCE_WEAPONIZATION_REGIONS: frozenset[str] = frozenset({"hormuz"})

# 예외 1: inter 코드 무관하게 conventional_warfare를 강제하는 geofence region
# 우크라이나: ACLED이 러시아를 inter2=8(External/Other Forces)로 분류해 irregular_warfare가 붙는 오류 방지.
# 국가 간 정규전이 명백하므로 inter 조합 결과를 덮어씀.
_FORCE_CONVENTIONAL_REGIONS: frozenset[str] = frozenset({"ukraine"})

# 예외 2: 국가 파편화·실패국가 내전 — inter1=1 vs inter2=1(국가군 vs 국가군)이어도
# conventional_warfare 대신 civil_war + asymmetric_warfare로 대체한다.
# 이유: 예멘·미얀마 등은 "국가군" 간 충돌이지만 실질은 분열된 파벌 간 내전.
# Lebanon·Palestine·Gaza: 레바논 내전 잔재·하마스-파타 분열·가자 분쟁 구조상 내전 패턴.
# ACLED 국가명(country 필드)으로 판단 — geofence region이 없는 국가도 포괄하기 위함.
_CIVIL_WAR_COUNTRIES: frozenset[str] = frozenset({
    "Yemen", "Myanmar", "Sudan", "Libya", "Syria",
    "Lebanon", "Palestine", "Gaza",
})

# ACLED inter1/inter2 행위자 텍스트 → 정수 코드 매핑
# ACLED API는 숫자(1-8)가 아닌 텍스트 레이블로 inter1/inter2를 반환한다.
_INTER_CODE: dict[str, int] = {
    "State Forces":          1,
    "Rebel Groups":          2,
    "Political Militias":    3,
    "Identity Militias":     4,
    "Rioters":               5,
    "Protesters":            6,
    "Civilians":             7,
    "External/Other Forces": 8,
}
_INTER_STATE = 1  # 국가군
_INTER_REBEL = 2  # 반군


def _inter_code(raw_value) -> int:
    """ACLED inter1/inter2 필드(문자열 or 정수)를 정수 코드로 변환한다.

    ACLED API가 대소문자를 혼용해 반환하므로(예: 'External/Other forces') 소문자로 정규화한다.
    """
    if isinstance(raw_value, int):
        return raw_value
    normalized = str(raw_value).strip().lower()
    for key, code in _INTER_CODE.items():
        if key.lower() == normalized:
            return code
    return 0


def _build_theory_tags(
    event_type: str,
    sub_event_type: str,
    inter1: int,
    inter2: int,
    region_code: str | None,
    country: str = "",
) -> list[str]:
    """event_type·inter1/inter2·sub_event_type·지역 코드·국가를 종합해 이론 태그를 생성한다.

    각 태그의 정치외교학 의미:
    - conventional_warfare: 국가군 간 정규전 (클라우제비츠적 전쟁)
    - insurgency / asymmetric_warfare: 국가 vs 반군 — 비대칭 전력 간 충돌
    - civil_war: 파벌 간 내전 — 국가 분열·파편화 (예멘·미얀마·시리아 패턴)
    - guerrilla_tactics: 매복·기습 — 약자의 전술적 비대칭 우위
    - A2AD: 반접근/지역거부 — 해양 지역 전용 (대만해협·남중국해)
    - SLOC_disruption: 해상교통로 차단 — Mahan 해양력 이론
    - resource_weaponization: 에너지 공급 통제 무기화 — 호르무즈 특화
    """
    tags: set[str] = set()

    # ── event_type 기본 태그 ───────────────────────────────────────────
    if event_type == "Explosions/Remote violence":
        tags.update(["gray_zone", "hybrid_warfare"])
    elif event_type == "Violence against civilians":
        tags.update(["irregular_warfare", "hybrid_warfare"])
    elif event_type == "Riots":
        tags.update(["political_instability", "gray_zone"])
    elif event_type == "Protests":
        tags.add("political_instability")
    elif event_type == "Strategic developments":
        tags.add("gray_zone")
    # Battles는 inter1/inter2 조합으로 결정 (아래)

    # ── inter1/inter2 기반 태그 (Battles·Explosions에 주로 의미 있음) ──
    if event_type in ("Battles", "Explosions/Remote violence"):
        if inter1 == _INTER_STATE and inter2 == _INTER_STATE:
            if country in _CIVIL_WAR_COUNTRIES:
                # 예외 2: 국가 파편화 내전 지역 — ACLED이 두 파벌 모두 State Forces로 분류해도
                # 실질은 내전. 예멘 STC vs Houthi, 시리아 파벌전 등이 대표 사례.
                tags.update(["civil_war", "asymmetric_warfare"])
            else:
                # 국가군 vs 국가군 — 재래식 정규전 (우크라이나 전형)
                tags.add("conventional_warfare")
        elif (inter1 == _INTER_STATE and inter2 == _INTER_REBEL) or \
             (inter1 == _INTER_REBEL and inter2 == _INTER_STATE):
            # 국가군 vs 반군 — 반란 진압·비대칭전 (미얀마 내전 전형)
            tags.update(["insurgency", "asymmetric_warfare"])
        elif inter1 == _INTER_REBEL and inter2 == _INTER_REBEL:
            # 반군 vs 반군 — 내전 파편화 (시리아·리비아 패턴)
            tags.add("civil_war")
        else:
            # 민병대·외부세력 등 비전통 행위자
            tags.add("irregular_warfare")

    # ── sub_event_type 기반 태그 ──────────────────────────────────────
    sub = sub_event_type.lower()
    if "ambush" in sub:
        # 매복: 게릴라 전술의 핵심 — 비대칭 약자의 표준 전술
        tags.add("guerrilla_tactics")
    if "air/drone strike" in sub and inter1 == _INTER_REBEL:
        # 비국가 행위자의 드론 공격 = 회색지대 전술 (후티·친러 민병대 등)
        tags.add("gray_zone")
    if any(k in sub for k in ("shelling", "artillery", "missile")):
        # 포병·미사일: 재래전 화력 사용
        tags.add("conventional_warfare")

    # ── 지역 기반 태그 ────────────────────────────────────────────────
    if region_code in _A2AD_REGIONS:
        # A2AD는 제1열도선 내 해양 접근거부 전략 — 대만해협·남중국해 전용
        tags.add("A2AD")
    if region_code in _SLOC_DISRUPTION_REGIONS:
        tags.add("SLOC_disruption")
    if region_code in _RESOURCE_WEAPONIZATION_REGIONS:
        tags.update(["resource_weaponization", "gray_zone"])

    # ── region 강제 적용 (ukraine conventional_warfare override) ─────
    if region_code in _FORCE_CONVENTIONAL_REGIONS:
        tags.discard("irregular_warfare")
        tags.add("conventional_warfare")

    # ── 최종 정제 (Sanitization) — 상호배제·지역 특화 후처리 ──────────

    # [변경4] south_china_sea + inter 미인식(=0) → irregular_warfare 대신 gray_zone
    # 남중국해 행위자는 해상민병대·해안경비대 혼재로 ACLED inter 코드 미인식이 잦다.
    # gray_zone + hybrid_warfare가 회색지대 전략 학습에 더 적합하다.
    if region_code == "south_china_sea" and inter1 == 0 and "irregular_warfare" in tags:
        tags.discard("irregular_warfare")
        tags.update(["gray_zone", "hybrid_warfare"])

    # [변경1a] conventional_warfare + insurgency 동시 → inter1 기준 우선순위 결정
    # 두 태그가 공존하면 "국가 주도 정규전"과 "비대칭 반란"이 모순 — 하나를 제거.
    if "conventional_warfare" in tags and "insurgency" in tags:
        if inter1 == _INTER_STATE:
            # 국가군 주도(inter1=1): conventional_warfare 유지, insurgency 계열 제거
            tags.discard("insurgency")
            tags.discard("asymmetric_warfare")
        else:
            # 비국가 주도: conventional_warfare 제거 (비대칭 성격이 본질)
            tags.discard("conventional_warfare")

    # [변경1b] south_china_sea → conventional_warfare 제거, gray_zone 강제
    # 남중국해 분쟁은 섬 점령·해상민병대·항행 방해 등 회색지대 전략이 본질.
    # 정규전 태그는 분쟁 성격을 오독하게 만든다.
    if region_code == "south_china_sea":
        tags.discard("conventional_warfare")
        tags.add("gray_zone")

    # [변경2] suez + Explosions/Shelling → 비대칭 태그 제거
    # 수에즈 포격·미사일은 SLOC 차단 효과(운임 급등)가 핵심 학습 포인트.
    # insurgency/asymmetric_warfare는 노이즈 — 4개 태그로 제한한다.
    if region_code == "suez" and event_type == "Explosions/Remote violence" \
            and any(k in sub for k in ("shelling", "artillery", "missile")):
        tags -= {"insurgency", "asymmetric_warfare"}

    return sorted(tags) or ["gray_zone"]

# 모듈 레벨 토큰 캐시 — 앱 재시작 전까지 유지 (DB 불필요)
# access_token: 24시간, refresh_token: 14일
_token_cache: dict = {
    "access_token":  None,
    "refresh_token": None,
    "expires_at":    None,  # datetime (UTC aware)
}

# ACLED 기준 날짜 캐시 — 프로브 호출 결과를 24시간 재사용
# 이유: 시스템 시계(2026)와 ACLED 실제 데이터 범위(~2025)가 달라 매번 probe 불필요
_ref_date_cache: dict = {
    "date":       None,  # str "YYYY-MM-DD"
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}


class AcledConnector(BaseConnector):
    """
    ACLED API에서 분쟁 이벤트를 조회하고 공통 Event 모델로 정규화한다.
    OAuth Resource Owner Password Credentials Grant 방식 사용.
    """

    async def fetch(self, countries: list[str] | None = None) -> list[Event]:
        """최근 30일 분쟁 이벤트를 Event 리스트로 반환한다.

        countries: 조회 대상 국가 목록. 미지정 시 인도-태평양(기존 레이어 동작 유지).
                   Cascade 엔진은 GULF_COUNTRIES를 넘겨 호르무즈 트리거를 수집한다.
        _ref_date_cache로 probe 호출을 24시간에 1회로 줄인다.
        ACLED v2 API: fields 파라미터 지정 시 [[],[]] 형식이므로 사용 금지.
        """
        countries = countries or INDO_PACIFIC_COUNTRIES
        token = await self._get_token()
        acled_today_str = await self._get_ref_date(token)

        if acled_today_str:
            # ACLED date_recency = API 키가 접근 가능한 실제 최신 날짜
            upper = datetime.strptime(acled_today_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            upper = datetime.now(timezone.utc)
            logger.warning("[ACLED] date_recency 없음, 시스템 시각 사용")

        since = upper - timedelta(days=30)
        date_range = f"{since.strftime('%Y-%m-%d')}|{upper.strftime('%Y-%m-%d')}"

        params = {
            "event_date":       date_range,
            "event_date_where": "BETWEEN",
            "country":          "|".join(countries),
            "limit":            1500, # 7/30일 토글 의미 있으려면 ~50건/일 × 30일 = 1500 필요
        }

        resp = await self._get_with_retry(token, params)
        resp.raise_for_status()

        records = resp.json().get("data", [])
        logger.info(f"[ACLED] {len(records)}개 이벤트 수신 (최근 30일, 인도-태평양)")

        events: list[Event] = []
        for raw in records:
            try:
                events.append(self._normalize(raw))
            except Exception as e:
                # 개별 레코드 실패는 무시하되 반드시 로그 기록
                logger.warning(f"[ACLED] 정규화 실패 (id={raw.get('event_id_cnty')}): {e}")

        return events

    async def _get_ref_date(self, token: str) -> str | None:
        """ACLED date_recency.date를 반환한다. 24시간 캐시로 probe 호출을 최소화한다."""
        now = datetime.now(timezone.utc)
        if _ref_date_cache["date"] and now < _ref_date_cache["expires_at"]:
            logger.debug(f"[ACLED] ref_date 캐시 사용: {_ref_date_cache['date']}")
            return _ref_date_cache["date"]

        probe_resp = await self._get_with_retry(
            token, {"country": INDO_PACIFIC_COUNTRIES[0], "limit": 1}
        )
        probe_resp.raise_for_status()
        date_str = (
            probe_resp.json()
            .get("data_query_restrictions", {})
            .get("date_recency", {})
            .get("date")
        )
        if date_str:
            _ref_date_cache["date"] = date_str
            _ref_date_cache["expires_at"] = now + timedelta(hours=24)
            logger.info(f"[ACLED] ref_date 취득 및 캐시: {date_str}")
        return date_str

    async def _get_with_retry(self, token: str, params: dict) -> httpx.Response:
        """API 호출. 401 수신 시 토큰 재발급 후 1회 재시도."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                ACLED_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

        if resp.status_code == 401:
            logger.warning("[ACLED] 401 수신 → 토큰 재발급 후 재시도")
            _token_cache["access_token"] = None
            token = await self._get_token()
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    ACLED_URL,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )

        return resp

    # ── 토큰 관리 ──────────────────────────────────────────────────

    async def _get_token(self) -> str:
        """캐시 확인 → refresh 시도 → login 순서로 유효한 토큰을 반환한다."""
        now = datetime.now(timezone.utc)
        c = _token_cache

        # 만료 5분 전부터 갱신 시도 (경계 시간 여유 확보)
        if (
            c["access_token"]
            and c["expires_at"]
            and now < c["expires_at"] - timedelta(minutes=5)
        ):
            return c["access_token"]

        if c["refresh_token"]:
            try:
                return await self._refresh()
            except Exception as e:
                logger.warning(f"[ACLED] refresh 실패, 재로그인 시도: {e}")

        return await self._login()

    async def _login(self) -> str:
        """이메일/비밀번호로 새 액세스 토큰을 발급받는다."""
        email    = os.getenv("ACLED_EMAIL")
        password = os.getenv("ACLED_PASSWORD")

        if not email or not password:
            raise RuntimeError(
                "ACLED_EMAIL, ACLED_PASSWORD 환경변수가 설정되지 않았습니다. "
                "backend/.env 파일을 확인하세요."
            )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URL, data={
                "username":   email,
                "password":   password,   # 비밀번호는 절대 로그에 출력하지 않음
                "grant_type": "password",
                "client_id":  "acled",
                "scope":      "authenticated",
            })

        if not resp.is_success:
            # 비밀번호 값은 절대 에러 메시지에 포함 금지
            raise RuntimeError(
                f"[ACLED] 로그인 실패 (HTTP {resp.status_code}). "
                "ACLED_EMAIL / ACLED_PASSWORD를 확인하세요."
            )

        self._update_cache(resp.json())
        logger.info("[ACLED] 새 액세스 토큰 발급 완료")
        return _token_cache["access_token"]

    async def _refresh(self) -> str:
        """refresh_token으로 access_token을 갱신한다."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TOKEN_URL, data={
                "grant_type":    "refresh_token",
                "refresh_token": _token_cache["refresh_token"],
                "client_id":     "acled",
            })
        resp.raise_for_status()
        self._update_cache(resp.json())
        logger.info("[ACLED] 액세스 토큰 갱신 완료")
        return _token_cache["access_token"]

    @staticmethod
    def _update_cache(data: dict) -> None:
        """토큰 응답을 캐시에 저장. expires_in(초)으로 만료 시각 계산."""
        _token_cache["access_token"]  = data["access_token"]
        _token_cache["refresh_token"] = data.get("refresh_token")
        expires_in = int(data.get("expires_in", 86400))  # 기본값 24시간
        _token_cache["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        )

    # ── 정규화 ─────────────────────────────────────────────────────

    def _normalize(self, raw: dict) -> Event:
        """ACLED 원본 레코드를 공통 Event 모델로 정규화한다."""
        event_type     = raw.get("event_type", "")
        sub_event_type = raw.get("sub_event_type", "")
        fatalities     = int(raw.get("fatalities", 0) or 0)
        # inter1/inter2: 행위자 유형 (ACLED는 텍스트로 반환 → 정수 코드로 변환)
        inter1 = _inter_code(raw.get("inter1", 0) or 0)
        inter2 = _inter_code(raw.get("inter2", 0) or 0)

        # 사망자 수에 따라 최대 30점 추가 — 분쟁 강도 지표
        base     = _SEVERITY_BASE.get(event_type, 25)
        severity = min(100, base + min(30, fatalities))

        lat = float(raw.get("latitude",  0) or 0)
        lon = float(raw.get("longitude", 0) or 0)

        actor1_name = raw.get("actor1", "")
        actor2_name = raw.get("actor2", "")
        country     = raw.get("country", "")

        if actor2_name:
            title = f"{actor1_name} vs {actor2_name}"
        elif actor1_name:
            title = f"{actor1_name}, {country}"
        else:
            title = f"{event_type} — {country}"

        # 좌표로 region_code 결정 — theory_tags 배정에 사용
        region_code = region_for_point(lat, lon)

        return Event(
            id=str(uuid.uuid4()),
            timestamp=datetime.strptime(
                raw["event_date"], "%Y-%m-%d"
            ).replace(tzinfo=timezone.utc),
            source_type="conflict",
            source_id=raw.get("event_id_cnty", ""),
            location=(round(lat, 5), round(lon, 5)),
            region_code=region_code,
            severity=severity,
            title=title,
            description=(raw.get("notes") or "")[:500],  # 500자 제한
            payload={
                "event_type":     event_type,
                "sub_event_type": sub_event_type,
                "actor1":         actor1_name,
                "actor2":         actor2_name,
                "country":        country,
                "fatalities":     fatalities,
                "inter1":         inter1,
                "inter2":         inter2,
                "source":         raw.get("source", ""),
            },
            theory_tags=_build_theory_tags(
                event_type, sub_event_type, inter1, inter2, region_code,
                country=country,
            ),
        )
