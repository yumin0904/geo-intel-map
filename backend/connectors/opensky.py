"""
opensky.py — OpenSky Network REST API 군용기 ADS-B 커넥터.

CLAUDE.md 연관 섹터:
  - 섹터 1: 해양 초점주의 & SLOC (대만해협·남중국해 군용기 초계 활동)
  - 섹터 4: 인도-태평양 군사 대치 (ISR·폭격기 포워드 디플로이먼트, A2/AD)
  - 섹터 5: 회색지대 & 비전통 안보 (식별 불명 군용기 활동, 그레이존 전술)

ADS-B(Automatic Dependent Surveillance-Broadcast)는 항공기가 자신의 GPS 위치를
1090 MHz로 자발적으로 방송하는 신호다. 군용기는 운용 규정에 따라 ADS-B를
꺼두기도 하지만, 대만해협의 미군 정찰기(RC-135·P-8)와 폭격기(B-52)는
이 해역을 통과할 때 ADS-B를 켠 채 비행해 중국에 의도적 신호를 보내는 경우가 많다.
이것이 Cascade 룰 taiwan_strait_to_tsm·soxx의 핵심 트리거 신호다.

군사 이론 연결 (Farrell & Newman, 2019 — Weaponized Interdependence):
  대만해협에서 군용기가 감지되면 TSMC·SOXX 관련 cascade 룰이 평가된다.
  반도체 공급망 집중(대만 90%+ 파운드리)이 군사 긴장의 금융 전달 경로가 된다.

API: https://opensky-network.org/api/states/all
인증: Basic Auth (OPENSKY_USERNAME / OPENSKY_PASSWORD — .env 필수)
요금: 등록 계정 무료 티어 — 400 크레딧/일, bbox 조회 1 크레딧/요청
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from connectors.base import BaseConnector
from models.event import Event
from services.region import get_region, region_for_point

load_dotenv()
logger = logging.getLogger(__name__)

OPENSKY_BASE_URL = "https://opensky-network.org/api"

# 조회 대상 지역 — 대만해협·남중국해·동중국해가 핵심 군사 마찰 공간
# east_china_sea는 대만 북방 확장 감시 (중국 ADIZ 선포 2013 구역 포함)
_TARGET_REGIONS: list[str] = [
    "taiwan_strait",
    "south_china_sea",
    "east_china_sea",
]

# 미국 군용 ICAO24 블록: AE0000–AFFFFF
# USAF(AE0000-AE3FFF)·US Army(AE4000-AEFFFF)·USN/USMC(AF0000-AFFFFF) 통합.
# 이 범위 내 항공기는 콜사인 검사 없이 군용으로 분류된다.
_US_MILITARY_ICAO24_MIN = 0xAE0000
_US_MILITARY_ICAO24_MAX = 0xAFFFFF

# 알려진 군용기 콜사인 접두사 (소문자). ICAO24 범위 외 국가 포함.
_MILITARY_CALLSIGN_PREFIXES: frozenset[str] = frozenset({
    # US Air Force — 전략 공수·VIP·전술
    "rch", "reach",   # AMC 전략 공수 (C-17, C-5)
    "sam",            # Special Air Mission (대통령기 등 VIP)
    "spar",           # USAF VIP 수송
    "exec",           # 고위 지휘부 수송
    "iron", "steel", "havoc", "duke", "coho", "rocky",
    # USAF 전략 폭격기 — 핵억제 시위용 포워드 디플로이먼트
    "forte",          # B-52 스트라토포트리스
    "ghost",          # B-2 스피릿 (스텔스 폭격기)
    "dragon",         # B-2 교대 콜사인
    # USAF 공중급유기 — 장기 순찰 작전 지원
    "lagr", "polo",   # KC-135/KC-46
    # USAF 정보·감시·정찰 (ISR) — 가장 민감한 신호
    "quid",           # RC-135W 리벳조인트: 중국 레이더·통신 SIGINT
    "magma",          # 신호정보 수집기
    "topgt",          # EP-3 에리에스 (하이난 사태 2001 주인공)
    # US Navy
    "jake",           # P-8 포세이돈: 잠수함 추적·해상 감시
    "venus",          # USN VIP 수송
    "bronco", "buck",
    # US Marines
    "valor",          # MV-22 Osprey
    "vmm",            # USMC MV-22 편대
    # Japan Self-Defense Forces
    "jdf", "jsdf",
    # Taiwan ROC Air Force
    "caf", "rocaf",
    # Australia
    "raaf", "aussie",
    # UK RAF
    "ascot",
    # Korea
    "rokaf", "roka",
})

# ISR 콜사인 — 정보·감시·정찰 임무.
# 이 항공기들이 대만해협에 있다는 것 자체가 외교·군사 신호 (Gray Zone 회색지대).
_ISR_PREFIXES: frozenset[str] = frozenset({
    "quid",   # RC-135W — 중국의 레이더·미사일·통신 SIGINT 수집
    "topgt",  # EP-3 에리에스 — 전자정보수집
    "magma",  # SIGINT 수집기
    "jake",   # P-8 포세이돈 — 잠수함·해상 감시
})

# 전략 폭격기 콜사인 — 핵억제력 시위.
# B-52의 대만해협 통과 → 중국 PLAAF 긴급발진(스크램블) → PLA ADS-B 급증 패턴.
_BOMBER_PREFIXES: frozenset[str] = frozenset({
    "forte",  # B-52 스트라토포트리스
    "ghost",  # B-2 스피릿
    "dragon", # B-2 교대 콜사인
})

# 공중급유기 콜사인 — 전투기 장시간 순찰 지원의 간접 지표
_TANKER_PREFIXES: frozenset[str] = frozenset({
    "polo", "lagr",
})

# OpenSky state vector 필드 인덱스 (공식 API 문서 기준)
# https://openskynetwork.github.io/opensky-api/rest.html#all-state-vectors
_IDX_ICAO24          = 0
_IDX_CALLSIGN        = 1
_IDX_ORIGIN_COUNTRY  = 2
_IDX_TIME_POSITION   = 3
_IDX_LAST_CONTACT    = 4
_IDX_LONGITUDE       = 5
_IDX_LATITUDE        = 6
_IDX_BARO_ALTITUDE   = 7  # m (기압고도)
_IDX_ON_GROUND       = 8
_IDX_VELOCITY        = 9  # m/s
_IDX_TRUE_TRACK      = 10 # 진북 기준 도(°), 시계방향
_IDX_VERTICAL_RATE   = 11 # m/s
_IDX_SENSORS         = 12
_IDX_GEO_ALTITUDE    = 13 # m (GPS 고도)
_IDX_SQUAWK          = 14
_IDX_SPI             = 15
_IDX_POSITION_SOURCE = 16 # 0=ADS-B, 1=ASTERIX, 2=MLAT, 3=FLARM

# region별 이론 태그 (Cascade 엔진·TheoryPanel 재사용)
_REGION_THEORY_TAGS: dict[str, list[str]] = {
    "taiwan_strait":    ["A2AD", "weaponized_interdependence", "gray_zone"],
    "south_china_sea":  ["A2AD", "gray_zone", "SLOC_disruption"],
    "east_china_sea":   ["A2AD", "conventional_warfare"],
    "korean_peninsula": ["conventional_warfare", "extended_deterrence"],
}


class OpenSkyConnector(BaseConnector):
    """OpenSky Network REST API 군용기 ADS-B 커넥터.

    대만해협·남중국해·동중국해 bbox를 병렬 조회해 군용기만 필터링하고
    military_flight 타입 Event로 정규화한다.

    동일 항공기가 여러 bbox에 포함되면 (예: 대만해협-동중국해 경계)
    icao24 기준으로 최신 last_contact 위치만 보존한다.
    """

    def __init__(self) -> None:
        username = os.getenv("OPENSKY_USERNAME")
        password = os.getenv("OPENSKY_PASSWORD")
        if not username or not password:
            raise ValueError(
                "OPENSKY_USERNAME, OPENSKY_PASSWORD 환경변수가 필요합니다. "
                ".env 파일에 추가하세요."
            )
        self._auth = (username, password)

    async def fetch(self) -> list[Event]:
        """모든 대상 지역의 군용기를 병렬 조회 후 정규화한다."""
        async with httpx.AsyncClient(
            auth=self._auth,
            timeout=30.0,
        ) as client:
            tasks = [
                self._fetch_region(client, region_code)
                for region_code in _TARGET_REGIONS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # icao24 기준 중복 제거 — last_contact 최신 우선
        by_icao24: dict[str, list] = {}
        for region_code, result in zip(_TARGET_REGIONS, results):
            if isinstance(result, Exception):
                logger.warning(f"[OpenSky] {region_code} 조회 실패: {result}")
                continue
            for state in result:
                icao24 = state[_IDX_ICAO24] or ""
                last_contact = state[_IDX_LAST_CONTACT] or 0
                prev = by_icao24.get(icao24)
                if prev is None or last_contact > (prev[_IDX_LAST_CONTACT] or 0):
                    by_icao24[icao24] = state

        events: list[Event] = []
        for state in by_icao24.values():
            ev = self._normalize_state(state)
            if ev is not None:
                events.append(ev)

        logger.info(
            f"[OpenSky] {len(events)}대 군용기 수집 "
            f"({len(_TARGET_REGIONS)}개 지역, 중복 제거 후)"
        )
        return events

    async def _fetch_region(
        self, client: httpx.AsyncClient, region_code: str
    ) -> list[list]:
        """단일 지역 bbox 내 항공기를 조회하고 군용기만 반환한다."""
        region_meta = get_region(region_code)
        if not region_meta or "bbox" not in region_meta:
            logger.warning(f"[OpenSky] {region_code}: regions.yaml에 bbox 없음")
            return []

        min_lon, min_lat, max_lon, max_lat = region_meta["bbox"]
        # OpenSky bbox: lamin(남위), lomin(서경), lamax(북위), lomax(동경)
        params = {
            "lamin": min_lat,
            "lomin": min_lon,
            "lamax": max_lat,
            "lomax": max_lon,
        }

        try:
            resp = await client.get(
                f"{OPENSKY_BASE_URL}/states/all", params=params
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            extra = " (인증 실패 — OPENSKY_USERNAME/PASSWORD 확인)" if status == 403 else ""
            logger.warning(f"[OpenSky] {region_code} HTTP {status}{extra}")
            return []
        except httpx.RequestError as e:
            logger.warning(f"[OpenSky] {region_code} 네트워크 오류: {e}")
            return []

        data = resp.json()
        states: list[list] = data.get("states") or []

        military = [s for s in states if _is_military(s)]
        logger.debug(
            f"[OpenSky] {region_code}: 전체 {len(states)}대 → 군용기 {len(military)}대"
        )
        return military

    def _normalize_state(self, state: list) -> Event | None:
        """OpenSky state vector 1개를 Event로 변환한다."""
        try:
            icao24          = (state[_IDX_ICAO24] or "").strip()
            callsign        = (state[_IDX_CALLSIGN] or "").strip()
            origin_country  = state[_IDX_ORIGIN_COUNTRY] or ""
            lon             = state[_IDX_LONGITUDE]
            lat             = state[_IDX_LATITUDE]
            baro_alt        = state[_IDX_BARO_ALTITUDE]   # m
            geo_alt         = state[_IDX_GEO_ALTITUDE]    # m
            velocity        = state[_IDX_VELOCITY]         # m/s
            true_track      = state[_IDX_TRUE_TRACK]       # °
            on_ground       = state[_IDX_ON_GROUND]
            last_contact    = state[_IDX_LAST_CONTACT]
            squawk          = state[_IDX_SQUAWK] or ""

            if lat is None or lon is None:
                return None

            timestamp = (
                datetime.fromtimestamp(last_contact, tz=timezone.utc)
                if last_contact
                else datetime.now(tz=timezone.utc)
            )

            region_code = region_for_point(lat, lon)
            callsign_lower = callsign.lower()
            severity = _calc_severity(callsign_lower, region_code, baro_alt, on_ground)
            theory_tags = _REGION_THEORY_TAGS.get(region_code or "", ["conventional_warfare"])

            alt_m = baro_alt or geo_alt or 0
            alt_ft = int(alt_m * 3.281)
            vel_kts = int((velocity or 0) * 1.944)
            aircraft_type = _infer_type(callsign_lower)

            region_meta = get_region(region_code) if region_code else None
            region_name = region_meta["name"] if region_meta else (region_code or "미상 해역")

            display = callsign or icao24  # 콜사인 없으면 ICAO24 코드 표시

            return Event(
                id=str(uuid.uuid4()),
                timestamp=timestamp,
                source_type="military_flight",
                source_id=f"opensky_{icao24}_{int(last_contact or 0)}",
                location=(round(lat, 5), round(lon, 5)),
                region_code=region_code,
                severity=severity,
                title=f"군용기 {display} · {region_name}",
                description=(
                    f"{aircraft_type} | {origin_country} | "
                    f"고도 {alt_ft:,}ft | 속도 {vel_kts}kts | 침로 {int(true_track or 0)}°"
                    + (" | 지상 대기" if on_ground else "")
                ),
                payload={
                    "source":            "OpenSky Network",
                    "icao24":            icao24,
                    "callsign":          callsign,
                    "origin_country":    origin_country,
                    "baro_altitude_m":   baro_alt,
                    "geo_altitude_m":    geo_alt,
                    "velocity_ms":       velocity,
                    "true_track_deg":    true_track,
                    "on_ground":         on_ground,
                    "squawk":            squawk,
                    "last_contact_unix": last_contact,
                    "aircraft_type":     aircraft_type,
                    "position_source":   state[_IDX_POSITION_SOURCE],
                },
                theory_tags=theory_tags,
            )
        except Exception as e:
            logger.warning(
                f"[OpenSky] state 정규화 실패: {e} "
                f"| icao24={state[_IDX_ICAO24] if state else '?'}"
            )
            return None


# ── 내부 판별 함수 ──────────────────────────────────────────────────────────

def _is_military(state: list) -> bool:
    """ICAO24 블록 또는 콜사인 접두사로 군용기 여부를 판별한다.

    판별 우선순위:
      1. 미국 군용 ICAO24 블록 AE0000-AFFFFF (신뢰도 높음)
      2. 알려진 군용 콜사인 접두사 패턴 (동맹국 포함)
    """
    icao24_raw = state[_IDX_ICAO24] or ""
    callsign_raw = (state[_IDX_CALLSIGN] or "").strip().lower()

    # 1순위: 미국 군용 ICAO24 블록
    try:
        icao24_int = int(icao24_raw, 16)
        if _US_MILITARY_ICAO24_MIN <= icao24_int <= _US_MILITARY_ICAO24_MAX:
            return True
    except ValueError:
        pass

    # 2순위: 콜사인 접두사 매칭
    if callsign_raw:
        for prefix in _MILITARY_CALLSIGN_PREFIXES:
            if callsign_raw.startswith(prefix):
                return True

    return False


def _calc_severity(
    callsign_lower: str,
    region_code: str | None,
    altitude_m: float | None,
    on_ground: bool,
) -> int:
    """군용기 심각도를 0-100으로 산출한다.

    ISR 항공기(RC-135·P-8)가 대만해협에 있으면 severity가 높다.
    이 값이 cascade 룰 severity_min(=50)을 넘을 때 Taiwan→TSM 연쇄가 평가된다.

    대만해협 × ISR = severity 84 → taiwan_strait_to_tsm 룰 즉시 트리거.
    """
    if on_ground:
        return 20  # 지상 대기 — 즉각적 위협 없음

    base = 50  # 공중 군용기 기본 심각도

    # ISR: 신호정보 수집·감시 임무 = 적 탐지 노출 수용, 가장 높은 긴장 신호
    if any(callsign_lower.startswith(p) for p in _ISR_PREFIXES):
        base += 20
    # 폭격기: 핵억제력 시위. B-52 통과 → 중국 긴급발진 패턴 반복됨
    elif any(callsign_lower.startswith(p) for p in _BOMBER_PREFIXES):
        base += 25
    # 공중급유기: 장시간 전술 작전의 간접 증거
    elif any(callsign_lower.startswith(p) for p in _TANKER_PREFIXES):
        base += 8

    # 대만해협 가중치: 반도체 공급망 집중 × 군사 긴장 = cascade 민감도 최고
    if region_code == "taiwan_strait":
        base = int(base * 1.2)

    return max(20, min(100, base))


def _infer_type(callsign_lower: str) -> str:
    """콜사인에서 항공기 임무 유형을 추론한다."""
    if any(callsign_lower.startswith(p) for p in _ISR_PREFIXES):
        return "ISR (정보·감시·정찰)"
    if any(callsign_lower.startswith(p) for p in _BOMBER_PREFIXES):
        return "전략 폭격기"
    if any(callsign_lower.startswith(p) for p in _TANKER_PREFIXES):
        return "공중급유기"
    if callsign_lower.startswith(("rch", "reach")):
        return "전략 공수기"
    if callsign_lower.startswith(("sam", "spar", "venus", "exec")):
        return "VIP 수송기"
    if callsign_lower.startswith("jake"):
        return "해상초계기"
    if callsign_lower.startswith(("valor", "vmm")):
        return "틸트로터 (MV-22)"
    return "군용기"
