"""
aisstream.py — AISStream.io WebSocket 실시간 선박 AIS 커넥터.

AIS(Automatic Identification System)는 SOLAS 협약에 따라 300GT 이상 선박에
의무 탑재된 자동 식별 장치다. 선박의 MMSI·좌표·속력·침로를 VHF로 broadcast한다.

이 커넥터는 전략 해역(호르무즈·바브엘만데브·말라카·대만해협·남중국해) bbox를
AISStream.io WebSocket에 구독하고, COLLECT_SECONDS 동안 수신된 메시지를
MMSI 기준으로 중복 제거(최신 위치 우선) 후 Event 리스트로 반환한다.

CLAUDE.md 연관 섹터:
  - 섹터 1: 해양 초점주의 & SLOC (Mahan 해양력, 말라카 딜레마)
  - 섹터 2: 에너지 지정학 & 인프라 (원유·LNG 유조선 추적)
  - 섹터 4: 인도-태평양 군사 대치 (대만해협 해상 통제)
  - 섹터 5: 회색지대 & 비전통 안보 (AIS 스푸핑, 선박 위장)

이론 연결 (Mahan 해양력 이론, 1890):
  "해양 통제 = 상업 통제 = 국력의 핵심." 호르무즈·말라카 같은 SLOC 초크포인트에서
  유조선·LNG선의 밀집도·속력·정박 여부는 지역 긴장 수준의 실시간 지표가 된다.
  AIS 스푸핑(위치 조작)은 그 자체로 Gray Zone Strategy의 한 수단이다.

API: wss://stream.aisstream.io/v0/stream
인증: 구독 JSON의 APIKey 필드 (Bearer 토큰 불필요)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import websockets
from dotenv import load_dotenv

from connectors.base import BaseConnector
from models.event import Event
from services.region import get_region, region_for_point

load_dotenv()
logger = logging.getLogger(__name__)

WS_URL = "wss://stream.aisstream.io/v0/stream"

# WebSocket 수집 창 (초). 짧으면 선박 수 부족, 길면 API 응답 지연.
# 기본 45초 — 주요 초크포인트에서 100~300척 확보에 충분한 시간.
COLLECT_SECONDS: int = int(os.getenv("AIS_COLLECT_SECONDS", "45"))

# 연결 타임아웃 — handshake 최대 대기 시간
OPEN_TIMEOUT: float = 10.0

# 모니터링 대상 전략 해역 (regions.yaml region_code 기준)
# 각 지역의 bbox를 자동으로 AISStream 형식으로 변환한다.
_NAVAL_REGIONS: list[str] = [
    # ── AISStream 무료 티어 실제 커버리지 (2026-05-23 실측) ──────────────────
    # 동남아시아 지상국 밀집 지역만 스트리밍 수신 가능.
    # 중동·홍해는 위성 AIS가 필요해 유료 플랜 필요 ($29+/월).
    "malacca",         # ✅ 27척/15초 — 동아시아 에너지 수입 89% (말라카 딜레마)
    "taiwan_strait",   # ✅ 2척/15초 — 반도체 공급망 + A2/AD 마찰축

    # 아래 해역은 지상국 미설치 → 무료 티어 0척, 구독 시 낭비만 됨
    # 각 cascade 룰은 source_type: conflict (ACLED)으로 유지
    # "bab_el_mandeb",  # ❌ 무료 미커버 — 후티 공격 → ACLED로 트리거
    # "south_china_sea",# ❌ 무료 미커버 — 9단선 분쟁 → ACLED로 트리거
    # "hormuz",         # ❌ 무료 미커버 — 걸프 긴장 → ACLED로 트리거
]

# AIS 선박 유형 코드 (ShipType) — IEC 61162-1 기준
# 70-79: 화물선(컨테이너·건화물), 80-89: 유조선(원유·LNG·화학)
# 35: 군용 작전 선박
_STRATEGIC_SHIP_TYPES: frozenset[int] = frozenset(range(70, 90)) | {35}

# ShipType 코드 → 한국어 레이블 (TheoryPanel·마커 툴팁용)
_SHIP_TYPE_LABEL: dict[int, str] = {
    35:  "군함",
    70:  "화물선",        71: "화물선(위험A)",  72: "화물선(화학)",
    73:  "화물선(위험C)", 74: "화물선(위험D)",  75: "화물선",
    76:  "화물선",        77: "화물선",         78: "화물선",       79: "화물선",
    80:  "유조선",        81: "유조선(위험A)",  82: "유조선(화학)",
    83:  "유조선(위험C)", 84: "LNG/LPG선",      85: "LPG선",
    86:  "유조선",        87: "유조선",          88: "유조선",       89: "유조선",
}

# 지역별 이론 태그 — Cascade 엔진 + TheoryPanel에서 재사용
_REGION_THEORY_TAGS: dict[str, list[str]] = {
    "hormuz":          ["SLOC_disruption", "resource_weaponization"],
    "bab_el_mandeb":   ["SLOC_disruption", "resource_weaponization"],
    "malacca":         ["SLOC_disruption"],
    "taiwan_strait":   ["A2AD", "SLOC_disruption"],
    "south_china_sea": ["gray_zone", "A2AD", "SLOC_disruption"],
}

# AIS NavigationalStatus 코드 → 한국어 (ITU-R M.1371-5)
_NAV_STATUS_LABEL: dict[int, str] = {
    0:  "항해중",      1: "묘박중",       2: "기관고장",
    3:  "조종제한",    4: "흘수제한",     5: "계류중",
    6:  "좌초",        7: "어로작업중",   8: "추진없이항행",
    15: "미정의",
}

# 정박/계류/좌초 상태 — 초크포인트 내 차단 가능성을 판단하는 NavStatus 집합
_ANCHORED_STATUSES: frozenset[int] = frozenset({1, 5, 6})


class AISStreamConnector(BaseConnector):
    """AISStream.io WebSocket 실시간 선박 AIS 커넥터.

    전략 해역 bbox를 구독하고 COLLECT_SECONDS 동안 AIS 메시지를 수집한다.
    PositionReport(위치·속력)와 ShipStaticData(선박 유형·IMO·목적지)를
    MMSI 기준으로 병합한 뒤 Event 리스트로 정규화한다.
    """

    def __init__(self) -> None:
        self._api_key = os.getenv("AISSTREAM_API_KEY")
        if not self._api_key:
            raise ValueError("AISSTREAM_API_KEY 환경변수가 설정되지 않았습니다.")
        self._bboxes = self._build_bboxes()

    # ── 초기화 ────────────────────────────────────────────────────────────────

    def _build_bboxes(self) -> list[list[list[float]]]:
        """regions.yaml bbox → AISStream 구독 형식으로 변환한다.

        regions.yaml 순서:  [min_lon, min_lat, max_lon, max_lat]
        AISStream 순서:     [[min_lat, min_lon], [max_lat, max_lon]]
        """
        bboxes: list[list[list[float]]] = []
        for region_code in _NAVAL_REGIONS:
            region_meta = get_region(region_code)
            if not region_meta or "bbox" not in region_meta:
                logger.warning(f"[AIS] {region_code}: regions.yaml에 bbox 없음 — 건너뜀")
                continue
            min_lon, min_lat, max_lon, max_lat = region_meta["bbox"]
            bboxes.append([[min_lat, min_lon], [max_lat, max_lon]])
        return bboxes

    # ── 공개 인터페이스 ────────────────────────────────────────────────────────

    async def fetch(self) -> list[Event]:
        """WebSocket에 연결해 COLLECT_SECONDS 동안 AIS 메시지를 수집 후 정규화한다.

        MMSI 기준 dedup: 같은 선박에서 여러 PositionReport가 오면 마지막(최신) 것만 유지.
        ShipStaticData는 동일 수집 창 내에 수신된 것만 위치 데이터와 병합한다.
        """
        if not self._bboxes:
            logger.error("[AIS] 유효한 bbox가 없습니다. regions.yaml 확인 필요.")
            return []

        # MMSI → 최신 PositionReport 메시지 (좌표·속력·침로)
        positions: dict[int, dict] = {}
        # MMSI → ShipStaticData 메시지 (선박 유형·IMO·이름·목적지)
        static_data: dict[int, dict] = {}

        subscription = {
            "APIKey": self._api_key,
            "BoundingBoxes": self._bboxes,
            # PositionReport: type 1/2/3 (위치 갱신, 수초~수분 간격)
            # ShipStaticData: type 5/24 (정적 정보, 약 6분 간격)
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }

        try:
            async with websockets.connect(
                WS_URL,
                open_timeout=OPEN_TIMEOUT,
            ) as ws:
                await ws.send(json.dumps(subscription))
                logger.info(
                    f"[AIS] 구독 시작 — {len(self._bboxes)}개 해역, "
                    f"{COLLECT_SECONDS}초 수집 창"
                )
                await self._collect(ws, positions, static_data)

        except OSError as e:
            # 네트워크 연결 불가 (DNS, 방화벽 등)
            logger.warning(f"[AIS] 연결 실패: {e}")
            return []
        except websockets.exceptions.WebSocketException as e:
            logger.warning(f"[AIS] WebSocket 오류: {e}")
            return []
        except Exception as e:
            logger.warning(f"[AIS] 예상치 못한 오류: {e}")
            return []

        events = self._normalize(positions, static_data)
        logger.info(
            f"[AIS] {len(events)}개 선박 이벤트 "
            f"(위치 {len(positions)}척, 정적데이터 {len(static_data)}척)"
        )
        return events

    # ── 수집 ──────────────────────────────────────────────────────────────────

    async def _collect(
        self,
        ws,  # websockets.asyncio.client.ClientConnection (버전 무관 덕타이핑)
        positions: dict[int, dict],
        static_data: dict[int, dict],
    ) -> None:
        """COLLECT_SECONDS 동안 WebSocket 메시지를 수신해 캐시에 저장한다.

        asyncio.timeout으로 수집 창을 제어한다 (Python 3.11+).
        TimeoutError는 정상 종료로 간주한다.
        """
        try:
            async with asyncio.timeout(COLLECT_SECONDS):
                async for raw in ws:
                    self._handle_message(raw, positions, static_data)
        except TimeoutError:
            pass  # 수집 창 만료 — 정상 종료

    def _handle_message(
        self,
        raw: str | bytes,
        positions: dict[int, dict],
        static_data: dict[int, dict],
    ) -> None:
        """단일 AIS 메시지를 파싱해 캐시에 저장한다.

        PositionReport: positions[mmsi] 갱신 (항상 최신으로 덮어씀)
        ShipStaticData: static_data[mmsi] 저장 (한 번만 저장, 변경 드묾)
        """
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return

        msg_type: str = msg.get("MessageType", "")
        meta: dict = msg.get("MetaData", {})
        mmsi: int | None = meta.get("MMSI")
        if not mmsi:
            return

        if msg_type == "PositionReport":
            pos = msg.get("Message", {}).get("PositionReport", {})
            if pos:
                positions[mmsi] = {"meta": meta, "pos": pos}

        elif msg_type == "ShipStaticData":
            static = msg.get("Message", {}).get("ShipStaticData", {})
            if static:
                static_data[mmsi] = static

    # ── 정규화 ────────────────────────────────────────────────────────────────

    def _normalize(
        self,
        positions: dict[int, dict],
        static_data: dict[int, dict],
    ) -> list[Event]:
        """수집된 위치 + 정적 데이터를 Event 리스트로 변환한다."""
        events: list[Event] = []
        for mmsi, pos_entry in positions.items():
            try:
                ev = self._build_event(mmsi, pos_entry, static_data.get(mmsi))
                if ev:
                    events.append(ev)
            except Exception as e:
                logger.warning(f"[AIS] MMSI {mmsi} 정규화 실패: {e}")
        return events

    def _build_event(
        self,
        mmsi: int,
        pos_entry: dict,
        static: dict | None,
    ) -> Event | None:
        """단일 선박의 위치·정적 데이터를 Event로 변환한다.

        좌표는 MetaData 우선 → PositionReport.Latitude/Longitude 순으로 시도한다.
        둘 다 (0, 0)이면 위치 불명으로 None 반환한다.
        """
        meta: dict = pos_entry["meta"]
        pos: dict = pos_entry["pos"]

        # 좌표 확보 — MetaData가 AISStream 서버 캐시 좌표(더 신뢰성 높음)
        lat = float(meta.get("latitude") or pos.get("Latitude") or 0)
        lon = float(meta.get("longitude") or pos.get("Longitude") or 0)
        if lat == 0.0 and lon == 0.0:
            return None

        # 선박 식별 정보
        ship_name = (meta.get("ShipName") or "").strip() or f"MMSI-{mmsi}"
        ship_type: int = int(static.get("Type") or 0) if static else 0
        imo: int = int(static.get("ImoNumber") or 0) if static else 0
        destination: str = (static.get("Destination") or "").strip() if static else ""

        # 항법 정보
        sog = float(pos.get("Sog") or 0)        # 대지속력 (knots)
        cog = float(pos.get("Cog") or 0)         # 대지침로 (degree)
        nav_status = int(pos.get("NavigationalStatus") or 15)
        true_heading = int(pos.get("TrueHeading") or 511)  # 511 = 미정의

        timestamp = _parse_ais_time(meta.get("time_utc", ""))
        region_code = region_for_point(lat, lon)
        theory_tags = _REGION_THEORY_TAGS.get(region_code or "", [])
        severity = _calc_severity(ship_type, region_code, sog, nav_status)

        type_label = _SHIP_TYPE_LABEL.get(
            ship_type, f"유형{ship_type}" if ship_type else "미분류"
        )
        nav_label = _NAV_STATUS_LABEL.get(nav_status, "미정의")
        region_meta = get_region(region_code or "")
        region_name = region_meta["name"] if region_meta else (region_code or "해역 미특정")

        desc_parts = [
            f"MMSI: {mmsi}",
            f"IMO: {imo}" if imo else None,
            nav_label,
            f"속력: {sog:.1f}kn",
            f"침로: {cog:.0f}°" if cog > 0 else None,
            f"목적지: {destination}" if destination else None,
        ]
        description = " | ".join(p for p in desc_parts if p)

        return Event(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            source_type="naval",
            source_id=f"ais_{mmsi}",
            location=(round(lat, 5), round(lon, 5)),
            region_code=region_code,
            severity=severity,
            title=f"{ship_name} · {type_label} · {region_name}",
            description=description,
            payload={
                "source":          "AISStream.io",
                "mmsi":            mmsi,
                "imo":             imo,
                "ship_name":       ship_name,
                "ship_type":       ship_type,
                "ship_type_label": type_label,
                "sog":             sog,
                "cog":             cog,
                "true_heading":    true_heading if true_heading != 511 else None,
                "nav_status":      nav_status,
                "nav_status_label": nav_label,
                "destination":     destination,
                "has_static_data": static is not None,
            },
            theory_tags=theory_tags,
        )


# ── 헬퍼 함수 ─────────────────────────────────────────────────────────────────


def _parse_ais_time(time_str: str) -> datetime:
    """AISStream time_utc 문자열을 UTC datetime으로 파싱한다.

    형식 예시: "2025-05-23 08:30:00.000 +0000 UTC"
    파싱 실패 시 현재 UTC 시각으로 대체한다.
    """
    try:
        # 밀리초 포함 앞 23자만 사용 ("+0000 UTC" 부분 무시)
        return datetime.strptime(time_str[:23], "%Y-%m-%d %H:%M:%S.%f").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _calc_severity(
    ship_type: int,
    region_code: str | None,
    sog: float,
    nav_status: int,
) -> int:
    """선박의 전략적 중요도를 0-100 severity로 산출한다.

    계층 1 — 선박 유형 (전략 자산 우선순위):
      군함(35)     → 70  : 직접적 안보 위협 지표
      LNG/LPG(84·85) → 65: 에너지 공급 취약성 (Hirschman 자원무기화)
      유조선(80-89) → 50 : 원유 해상 수송 (SLOC 핵심 화물)
      화물선(70-79) → 35 : 공급망 지표 (Weaponized Interdependence)
      미분류       → 25  : 유형 미확인

    계층 2 — 지역 전략 중요도:
      호르무즈 +15: 글로벌 원유 20% 통과 — 최고 가중치
      바브엘만데브·대만해협 +10: 후티 위협 / 반도체 공급망
      남중국해 +8, 말라카 +5

    계층 3 — 항법 상태:
      정박·계류·좌초(속력 < 0.5kn) +10: 초크포인트 내 잠재적 통항 차단 신호
    """
    if ship_type == 35:
        base = 70
    elif ship_type in (84, 85):
        base = 65
    elif 80 <= ship_type <= 89:
        base = 50
    elif 70 <= ship_type <= 79:
        base = 35
    else:
        base = 25

    region_bonus: int = {
        "hormuz":          15,
        "bab_el_mandeb":   10,
        "taiwan_strait":   10,
        "south_china_sea":  8,
        "malacca":          5,
    }.get(region_code or "", 0)

    # 정박·계류·좌초 상태이면서 속력이 거의 없는 경우만 보너스 부여
    anchor_bonus = 10 if (nav_status in _ANCHORED_STATUSES and sog < 0.5) else 0

    return min(100, base + region_bonus + anchor_bonus)
