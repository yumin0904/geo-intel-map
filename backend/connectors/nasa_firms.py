"""
nasa_firms.py — NASA FIRMS VIIRS S-NPP NRT 위성 화재/열점 커넥터.

CLAUDE.md 연관 섹터:
  - 섹터 2: 에너지 지정학 (정유시설·파이프라인 화재 감지)
  - 섹터 4: 인도-태평양 군사 대치 (교전 지역 폭발·인프라 파괴)
  - 섹터 5: 회색지대 & 비전통 안보 (소이 무기, 강제 이주용 방화)

열점(Fire Hotspot)은 화재이기도 하지만, 분쟁 지역에서 높은 FRP(Fire Radiative Power)는
대규모 폭발·정유 시설 파괴·농경지 방화의 위성 신호다.
우크라이나의 FRP 급등이 밀 선물 가격과 상관된 사례(Food Security weaponization)처럼,
Cascade 엔진과 즉시 연동 가능하다.

API: https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{W,S,E,N}/{day_range}
소스: VIIRS_SNPP_NRT — 위성 통과 후 ~3시간 이내 제공(Near Real Time).
"""
from __future__ import annotations

import asyncio
import csv
import io
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

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
VIIRS_SOURCE = "VIIRS_SNPP_NRT"
DAY_RANGE = 1  # 최근 1일 (NRT 최소 갱신 단위)

# 화재 모니터링 대상 지역 — regions.yaml에 정의된 분쟁 연관 지역만 선별.
# 말라카·동중국해처럼 해상 전용 지역은 육상 열점과 관련성이 낮아 제외.
_FIRE_REGIONS: list[str] = [
    "ukraine",         # 러시아-우크라이나 전선, 농경지·인프라 파괴
    "middle_east",     # 가자·레바논·이라크·시리아 분쟁
    "bab_el_mandeb",   # 예멘 후티 교전 지역
    "hormuz",          # 이란 주변 인프라 감시
    "south_china_sea", # 남중국해 도서 모니터링
    "taiwan_strait",   # 대만 해협 주변
    "korean_peninsula",# 한반도 (DMZ 북방 포함)
    "north_korea",     # 북한 군사시설 활동
    "suez",            # 시나이 반도·이스라엘 남부
]

# region별 이론 태그 — Cascade 엔진과 TheoryPanel에서 재사용
_REGION_THEORY_TAGS: dict[str, list[str]] = {
    "ukraine":          ["food_security", "conventional_warfare"],
    "middle_east":      ["resource_weaponization", "gray_zone"],
    "bab_el_mandeb":    ["SLOC_disruption", "resource_weaponization"],
    "hormuz":           ["resource_weaponization", "SLOC_disruption"],
    "south_china_sea":  ["gray_zone", "A2AD"],
    "taiwan_strait":    ["A2AD", "gray_zone"],
    "korean_peninsula": ["conventional_warfare"],
    "north_korea":      ["conventional_warfare"],
    "suez":             ["SLOC_disruption"],
}


class NasaFirmsConnector(BaseConnector):
    """NASA FIRMS VIIRS S-NPP NRT 열점 커넥터.

    분쟁 지역 bbox를 기준으로 최근 1일 화재 열점을 병렬 조회하고
    Event 모델로 정규화한다.
    """

    def __init__(self) -> None:
        self._map_key = os.getenv("FIRMS_MAP_KEY")
        if not self._map_key:
            raise ValueError("FIRMS_MAP_KEY 환경변수가 설정되지 않았습니다.")

    async def fetch(self) -> list[Event]:
        """모든 대상 지역의 VIIRS 열점을 병렬 조회 후 정규화한다.

        겹치는 bbox(예: north_korea ⊂ korean_peninsula)로 인한 중복 열점은
        source_id 기준으로 제거한다.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = [
                self._fetch_region(client, region_code)
                for region_code in _FIRE_REGIONS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_source_ids: set[str] = set()
        events: list[Event] = []
        for region_code, result in zip(_FIRE_REGIONS, results):
            if isinstance(result, Exception):
                logger.warning(f"[FIRMS] {region_code} 조회 실패: {result}")
                continue
            for ev in result:
                if ev.source_id not in seen_source_ids:
                    seen_source_ids.add(ev.source_id)
                    events.append(ev)

        logger.info(
            f"[FIRMS] {len(events)}개 열점 수집 "
            f"({len(_FIRE_REGIONS)}개 지역, 중복 제거 후)"
        )
        return events

    async def _fetch_region(
        self, client: httpx.AsyncClient, region_code: str
    ) -> list[Event]:
        """단일 지역 bbox의 VIIRS NRT 열점을 조회한다."""
        region_meta = get_region(region_code)
        if not region_meta or "bbox" not in region_meta:
            logger.warning(f"[FIRMS] {region_code}: regions.yaml에 bbox 없음")
            return []

        min_lon, min_lat, max_lon, max_lat = region_meta["bbox"]
        # FIRMS bbox 파라미터 순서: W,S,E,N (= min_lon, min_lat, max_lon, max_lat)
        bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        url = f"{FIRMS_BASE_URL}/{self._map_key}/{VIIRS_SOURCE}/{bbox_str}/{DAY_RANGE}"

        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[FIRMS] {region_code} HTTP {e.response.status_code} | {url}"
            )
            return []
        except httpx.RequestError as e:
            logger.warning(f"[FIRMS] {region_code} 네트워크 오류: {e}")
            return []

        text = resp.text.strip()
        # 빈 응답이거나 API 키 오류 XML이면 열점 없음으로 처리
        if not text or text.startswith("<?xml") or text.startswith("<html"):
            logger.debug(f"[FIRMS] {region_code}: 열점 없음 (응답 비어있거나 XML)")
            return []

        events = self._parse_csv(text, region_code)
        logger.debug(f"[FIRMS] {region_code}: {len(events)}개 열점")
        return events

    def _parse_csv(self, csv_text: str, hint_region: str) -> list[Event]:
        """FIRMS CSV 응답을 Event 리스트로 정규화한다.

        hint_region은 fetch 요청 시 사용한 region_code다.
        실제 열점 좌표가 bbox 경계 근처일 경우 region_for_point()로 재확인한다.
        """
        events: list[Event] = []
        reader = csv.DictReader(io.StringIO(csv_text))

        for row in reader:
            try:
                ev = self._normalize_row(row, hint_region)
                if ev:
                    events.append(ev)
            except Exception as e:
                logger.warning(f"[FIRMS] 행 파싱 실패: {e} | {row}")

        return events

    def _normalize_row(self, row: dict[str, str], hint_region: str) -> Event | None:
        """VIIRS CSV 행 하나를 Event로 변환한다.

        VIIRS_SNPP_NRT CSV 컬럼:
          latitude, longitude, bright_ti4, scan, track,
          acq_date, acq_time, satellite, instrument,
          confidence, version, bright_ti5, frp, daynight
        """
        lat = float(row["latitude"])
        lon = float(row["longitude"])

        # acq_date: "2025-01-15", acq_time: "830" → "0830" (HHMM, 선행 0 보정)
        acq_date = row["acq_date"]
        acq_time = row["acq_time"].zfill(4)
        timestamp = datetime.strptime(
            f"{acq_date} {acq_time}", "%Y-%m-%d %H%M"
        ).replace(tzinfo=timezone.utc)

        frp = float(row.get("frp") or 0)
        confidence = (row.get("confidence") or "n").strip().lower()
        bright_ti4 = float(row.get("bright_ti4") or 0)
        bright_ti5 = float(row.get("bright_ti5") or 0)

        # bbox 경계 근처 포인트는 region_for_point로 재확인
        region_code = region_for_point(lat, lon) or hint_region
        theory_tags = _REGION_THEORY_TAGS.get(region_code, ["conventional_warfare"])
        severity = _calc_severity(frp, confidence)

        region_meta = get_region(region_code)
        region_name = region_meta["name"] if region_meta else region_code

        # FIRMS 고유 ID 없음 → 위치+시간 조합으로 중복 방지 키 생성
        source_id = f"firms_{acq_date}_{acq_time}_{lat:.3f}_{lon:.3f}"

        return Event(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            source_type="fire",
            source_id=source_id,
            location=(round(lat, 5), round(lon, 5)),
            region_code=region_code,
            severity=severity,
            title=f"위성 열점 · {region_name}",
            description=(
                f"VIIRS S-NPP NRT 감지 | "
                f"FRP {frp:.1f} MW | "
                f"신뢰도 {confidence.upper()} | "
                f"밝기온도 {bright_ti4:.1f} K"
            ),
            payload={
                "source": "NASA FIRMS VIIRS_SNPP_NRT",
                "frp": frp,
                "confidence": confidence,
                "bright_ti4": bright_ti4,
                "bright_ti5": bright_ti5,
                "scan": float(row.get("scan") or 0),
                "track": float(row.get("track") or 0),
                "satellite": row.get("satellite", ""),
                "instrument": row.get("instrument", ""),
                "daynight": row.get("daynight", ""),
                "version": row.get("version", ""),
                "acq_date": acq_date,
                "acq_time": acq_time,
            },
            theory_tags=theory_tags,
        )


def _calc_severity(frp: float, confidence: str) -> int:
    """FRP(화재 복사에너지, MW)와 위성 신뢰도로 0-100 severity를 산출한다.

    FRP는 화재 강도의 물리적 지표다. 분쟁 지역의 고FRP는
    단순 산불이 아닌 정유시설·탄약고·농경지 대형 화재와 상관된다.

    티어 기준 (현장 관측 기반):
      <10 MW  → 소규모: 농업 화재, 차량 등
      10~50   → 중규모: 건물·소형 인프라 파괴
      50~200  → 대규모: 산업 시설, 연료 저장소
      200+ MW → 극대: 정유·LNG 시설, 대형 탄약고
    """
    if frp < 10:
        base = 20
    elif frp < 50:
        base = 38
    elif frp < 200:
        base = 58
    else:
        base = 78

    # 위성 감지 신뢰도 보정 (VIIRS confidence: l/n/h)
    conf_adj = {"h": 12, "n": 0, "l": -12}.get(confidence, 0)
    return max(10, min(100, base + conf_adj))
