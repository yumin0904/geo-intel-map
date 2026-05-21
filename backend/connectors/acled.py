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

# event_type → 정치외교학 이론 태그 자동 매핑
# Hybrid Warfare(하이브리드전): 재래전+비재래전 혼합 — 러시아·중국의 전형적 회색지대 전술
# A2/AD(반접근/지역거부): 제1열도선 내 미군 접근 차단 — 남중국해 분쟁의 핵심 전략
_THEORY_TAGS: dict[str, list[str]] = {
    "Battles":                     ["conventional_warfare", "A2AD"],
    "Explosions/Remote violence":  ["gray_zone", "hybrid_warfare"],
    "Violence against civilians":  ["irregular_warfare", "hybrid_warfare"],
    "Riots":                       ["political_instability", "gray_zone"],
    "Protests":                    ["political_instability"],
    "Strategic developments":      ["gray_zone"],
}

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

    async def fetch(self) -> list[Event]:
        """최근 30일, 인도-태평양 분쟁 이벤트를 Event 리스트로 반환한다.

        _ref_date_cache로 probe 호출을 24시간에 1회로 줄인다.
        ACLED v2 API: fields 파라미터 지정 시 [[],[]] 형식이므로 사용 금지.
        """
        token = await self._get_token()
        acled_today_str = await self._get_ref_date(token)

        if acled_today_str:
            upper = datetime.strptime(acled_today_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            upper = datetime.now(timezone.utc)
            logger.warning("[ACLED] date_recency 없음, 시스템 시각 사용")

        since = upper - timedelta(days=30)
        date_range = f"{since.strftime('%Y-%m-%d')}|{upper.strftime('%Y-%m-%d')}"

        params = {
            "event_date":       date_range,
            "event_date_where": "BETWEEN",
            "country":          "|".join(INDO_PACIFIC_COUNTRIES),
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
        event_type = raw.get("event_type", "")
        fatalities = int(raw.get("fatalities", 0) or 0)

        # 사망자 수에 따라 최대 30점 추가
        # 재래전 전투의 사망자 수는 분쟁 강도의 핵심 지표
        base     = _SEVERITY_BASE.get(event_type, 25)
        severity = min(100, base + min(30, fatalities))

        lat = float(raw.get("latitude",  0) or 0)
        lon = float(raw.get("longitude", 0) or 0)

        actor1  = raw.get("actor1", "")
        actor2  = raw.get("actor2", "")
        country = raw.get("country", "")

        if actor2:
            title = f"{actor1} vs {actor2}"
        elif actor1:
            title = f"{actor1}, {country}"
        else:
            title = f"{event_type} — {country}"

        return Event(
            id=str(uuid.uuid4()),
            timestamp=datetime.strptime(
                raw["event_date"], "%Y-%m-%d"
            ).replace(tzinfo=timezone.utc),
            source_type="conflict",
            source_id=raw.get("event_id_cnty", ""),
            location=(round(lat, 5), round(lon, 5)),
            region_code=None,   # Phase 2: regions.yaml 기반 자동 할당 예정
            severity=severity,
            title=title,
            description=(raw.get("notes") or "")[:500],  # 500자 제한
            payload={
                "event_type":     event_type,
                "sub_event_type": raw.get("sub_event_type", ""),
                "actor1":         actor1,
                "actor2":         actor2,
                "country":        country,
                "fatalities":     fatalities,
                "source":         raw.get("source", ""),
            },
            theory_tags=_THEORY_TAGS.get(event_type, ["gray_zone"]),
        )
