"""
backend/services/library/deep_link.py

이론 ID ↔ MapFocusTarget 양방향 매핑.

Forward  : theory_id  → MapFocusTarget  (이론 카드 클릭 → 지도 이동)
Reverse  : region_code → [theory_id, ...]  (지역 클릭 → 관련 이론 목록)
Reverse  : layer_id   → [theory_id, ...]  (레이어 토글 → 관련 이론 목록)

데이터 소스: backend/config/theory_library.yaml
regions.yaml과 독립적으로 동작하지만 region_code는 두 파일이 동기화되어야 한다.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).parent.parent.parent / "config" / "theory_library.yaml"

# regions.yaml의 region 코드 집합 — 동기화 경고용 (런타임 검증, 하드 에러 아님)
_KNOWN_REGIONS: frozenset[str] = frozenset({
    "hormuz", "bab_el_mandeb", "malacca", "taiwan_strait",
    "south_china_sea", "north_korea", "suez", "ukraine",
    "middle_east", "korean_peninsula", "east_china_sea",
    "indian_ocean",   # 아직 regions.yaml 미등록이지만 theory_library에서 사용
})


# ── 데이터 모델 ────────────────────────────────────────────────────────────────

class MapFocusTarget(BaseModel):
    """지도가 이동해야 할 목표 상태."""
    lat: float
    lon: float
    zoom: int
    layers: list[str]       # LayerManager에 등록된 레이어 ID
    region_code: Optional[str] = None


class TheoryLink(BaseModel):
    """theory_library.yaml 단일 항목."""
    theory_id: str
    display_name: str
    sector_tag: str
    map_focus: MapFocusTarget
    related_regions: list[str]

    @field_validator("sector_tag")
    @classmethod
    def _validate_sector(cls, v: str) -> str:
        allowed = {"maritime", "energy", "techno", "indo_pacific", "gray_zone"}
        if v not in allowed:
            raise ValueError(f"sector_tag '{v}' 허용값 아님: {sorted(allowed)}")
        return v


# ── YAML 로더 (앱 시작 시 1회 캐시) ──────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_links() -> list[TheoryLink]:
    """
    theory_library.yaml을 파싱하고 Pydantic 모델 리스트로 반환한다.
    lru_cache로 앱 수명 동안 한 번만 읽는다.
    YAML 변경 시 프로세스 재시작이 필요하다.
    """
    raw: list[dict] = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8")) or []
    links: list[TheoryLink] = []

    for entry in raw:
        try:
            link = TheoryLink.model_validate(entry)
            # regions.yaml과 동기화 경고 (하드 에러가 아님 — 새 region 추가 중 유연성 확보)
            unknown = set(link.related_regions) - _KNOWN_REGIONS
            if unknown:
                logger.warning(
                    "[%s] related_regions에 미등록 region 코드: %s",
                    link.theory_id, unknown,
                )
            links.append(link)
        except Exception as e:  # noqa: BLE001
            logger.error("theory_library.yaml 항목 파싱 실패: %s — %s", entry.get("theory_id"), e)

    logger.info("TheoryLibrary 로드 완료: %d개 항목", len(links))
    return links


def reload() -> None:
    """캐시를 비우고 YAML을 다시 읽는다. 개발·테스트용."""
    _load_links.cache_clear()
    _load_links()


# ── Forward 조회 ──────────────────────────────────────────────────────────────

def get_focus_target(theory_id: str) -> Optional[MapFocusTarget]:
    """
    이론 ID로 MapFocusTarget을 반환한다.

    사용 예: 이론 카드 클릭 → 지도 flyTo() 호출
    반환값이 None이면 해당 theory_id가 theory_library.yaml에 없는 것.
    """
    for link in _load_links():
        if link.theory_id == theory_id:
            return link.map_focus
    logger.debug("MapFocusTarget 없음: %s", theory_id)
    return None


def get_theory_link(theory_id: str) -> Optional[TheoryLink]:
    """theory_id로 TheoryLink 전체(표시명·sector_tag 포함)를 반환한다."""
    for link in _load_links():
        if link.theory_id == theory_id:
            return link
    return None


# ── Reverse 조회 ─────────────────────────────────────────────────────────────

def get_theories_for_region(region_code: str) -> list[TheoryLink]:
    """
    region_code에 연결된 이론 목록을 반환한다.

    사용 예: 지역 클릭 → Theory Panel에 관련 이론 카드 나열
    """
    return [
        link for link in _load_links()
        if region_code in link.related_regions
        or link.map_focus.region_code == region_code
    ]


def get_theories_for_layer(layer_id: str) -> list[TheoryLink]:
    """
    레이어 ID가 map_focus.layers에 포함된 이론 목록을 반환한다.

    사용 예: 레이어 패널에서 레이어 토글 → 관련 이론 하이라이트
    """
    return [
        link for link in _load_links()
        if layer_id in link.map_focus.layers
    ]


# ── 전체 목록 조회 ────────────────────────────────────────────────────────────

def list_all(sector_tag: Optional[str] = None) -> list[TheoryLink]:
    """
    전체 이론 목록을 반환한다. sector_tag를 지정하면 해당 섹터만 필터.

    사용 예: TheoryLibraryView 초기 렌더링
    """
    links = _load_links()
    if sector_tag:
        links = [l for l in links if l.sector_tag == sector_tag]
    return links


# ── 역방향 인덱스 (region → theories) 전체 맵 ────────────────────────────────

def build_region_index() -> dict[str, list[str]]:
    """
    { region_code: [theory_id, ...] } 형태의 역방향 인덱스를 반환한다.

    api/library.py가 이 맵을 JSON으로 내려보내면 프론트엔드가 region 클릭 시
    O(1)로 관련 이론을 조회할 수 있다.
    """
    index: dict[str, list[str]] = {}
    for link in _load_links():
        regions = set(link.related_regions)
        if link.map_focus.region_code:
            regions.add(link.map_focus.region_code)
        for region in regions:
            index.setdefault(region, []).append(link.theory_id)
    return index
