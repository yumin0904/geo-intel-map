"""
region.py — 좌표를 자체 지역 코드(region_code)로 매핑하는 서비스.

Cascade 룰은 위경도가 아니라 "지역"으로 trigger/response를 매칭한다.
예: 어떤 분쟁 이벤트가 호르무즈 해협 bbox 안에 있으면 region_code="hormuz".

config/regions.yaml을 1회 로드해 메모리에 캐시한다(외부 I/O 없음 → sync 함수).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

# 이 파일: backend/services/region.py → config: 한 단계 위의 config/
_REGIONS_PATH = Path(__file__).parent.parent / "config" / "regions.yaml"


@lru_cache(maxsize=1)
def _load_regions() -> dict[str, dict]:
    """regions.yaml을 로드해 {region_code: {name, bbox, center, theory}} 형태로 반환.

    lru_cache로 파일을 1회만 읽는다(룰 평가마다 디스크 접근 방지).
    """
    if not _REGIONS_PATH.exists():
        raise FileNotFoundError(f"regions.yaml을 찾을 수 없습니다: {_REGIONS_PATH}")
    data = yaml.safe_load(_REGIONS_PATH.read_text(encoding="utf-8")) or {}
    return data


def get_region(region_code: str) -> dict | None:
    """region_code로 지역 메타데이터(name, bbox, center, theory)를 조회한다."""
    return _load_regions().get(region_code)


def region_center(region_code: str) -> tuple[float, float] | None:
    """지역 대표점을 (lat, lon)으로 반환한다.

    좌표 없는 이벤트(예: 시장 지표)를 지도에 앵커링할 때 사용한다.
    regions.yaml의 center는 [lon, lat] 순서이므로 뒤집어서 반환한다.
    """
    region = get_region(region_code)
    if not region or "center" not in region:
        return None
    lon, lat = region["center"]
    return (lat, lon)


def region_for_event(
    lat: float,
    lon: float,
    *,
    country: str = "",
    actors: tuple[str, ...] = (),
) -> str | None:
    """행위자·발생국 신호를 좌표보다 우선하는 region 판정.

    왜 좌표만으로 부족한가: north_korea 같은 '행위자형' region은 국가 행위자의
    행동을 추적하는 분석 단위인데, ACLED는 북한 도발을 접촉점(판문점·DMZ 남측)에
    좌표코딩하므로 발생지 bbox만으로는 원리적으로 놓친다. 반대로 bbox가 서울을
    물면 남한 시위가 '북한 도발' 버킷에 섞인다 (2026-07-09 오염 3,136건 실측,
    geo-os 판례 20260709-nk-region-bbox-contamination).

    판정 순서 (사전 선언 — 결과 보고 무관 결정론):
    1. actor_match — 행위자명 부분 문자열 매치 (행위자형 region 전용)
    2. country_match — 발생국 정확 매치 (좌표 경계 정밀도 갭 보완)
    3. region_for_point(lat, lon) — bbox 폴백 (좌표만 있는 소스: FIRMS·AIS 등)
    """
    regions = _load_regions()
    for code, meta in regions.items():
        if not isinstance(meta, dict):
            continue
        for keyword in meta.get("actor_match", []):
            if any(keyword in (actor or "") for actor in actors):
                return code
    if country:
        for code, meta in regions.items():
            if not isinstance(meta, dict):
                continue
            if country in meta.get("country_match", []):
                return code
    return region_for_point(lat, lon)


def region_for_point(lat: float, lon: float) -> str | None:
    """좌표가 속한 첫 번째 region_code를 반환한다(없으면 None).

    bbox는 [min_lon, min_lat, max_lon, max_lat] 순서.
    지역이 겹치지 않는다는 가정 하에 단순 bbox 포함 검사를 사용한다.
    """
    if lat == 0.0 and lon == 0.0:
        return None  # 좌표 미상 이벤트는 지역 판정 불가
    for code, meta in _load_regions().items():
        bbox = meta.get("bbox")
        if not bbox:
            continue
        min_lon, min_lat, max_lon, max_lat = bbox
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return code
    return None
