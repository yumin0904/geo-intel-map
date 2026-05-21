"""
layers.py — 지도 레이어 GeoJSON 서빙 라우터
각 레이어(군사기지, 파이프라인 등)를 GeoJSON으로 반환한다.
CLAUDE.md 아키텍처: backend/api/layers.py
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from connectors.acled import AcledConnector
from models.event import Event

router = APIRouter(prefix="/api/layers", tags=["layers"])

# ACLED 응답 1시간 캐시 — 분쟁 데이터는 실시간 불필요 (CLAUDE.md 성능 원칙)
_CONFLICT_TTL = timedelta(hours=1)
_conflict_cache: dict = {
    "geojson":     None,
    "expires_at":  datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# 프로젝트 루트 기준으로 data/ 폴더 경로 계산
# 이 파일: backend/api/layers.py → 루트: 두 단계 위
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_geojson(filename: str) -> dict:
    """
    data/ 폴더에서 GeoJSON 파일을 읽어 dict로 반환한다.
    파일이 없으면 404, JSON 파싱 실패 시 500을 반환한다.
    """
    path = DATA_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} 파일을 찾을 수 없습니다.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"GeoJSON 파싱 오류: {e}") from e


@router.get("/conflict-events")
async def get_conflict_events():
    """
    최근 30일, 인도-태평양 분쟁 이벤트 GeoJSON 반환.
    1시간 캐시 적용 — 두 번째 요청부터 즉시 반환.
    연관 이론: Gray Zone Strategy, Hybrid Warfare (CLAUDE.md 섹터 4·5)
    """
    now = datetime.now(timezone.utc)
    if _conflict_cache["geojson"] is not None and now < _conflict_cache["expires_at"]:
        return _conflict_cache["geojson"]

    connector = AcledConnector()
    try:
        events = await connector.fetch()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ACLED API 연결 실패: {e}") from e

    result = _events_to_geojson(events)
    _conflict_cache["geojson"] = result
    _conflict_cache["expires_at"] = now + _CONFLICT_TTL
    return result


def _events_to_geojson(events: list[Event]) -> dict:
    """Event 리스트 → Leaflet이 바로 소비할 GeoJSON FeatureCollection."""
    features = []
    for e in events:
        lat, lon = e.location
        if lat == 0.0 and lon == 0.0:
            continue  # 좌표 없는 이벤트 제외

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                # GeoJSON 표준: [경도, 위도] 순서 (Leaflet과 반대이므로 주의)
                "coordinates": [lon, lat],
            },
            "properties": {
                "id":          e.id,
                "timestamp":   e.timestamp.isoformat(),
                "source_type": e.source_type,
                "source_id":   e.source_id,
                "severity":    e.severity,
                "title":       e.title,
                "description": e.description,
                "theory_tags": e.theory_tags,
                **e.payload,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count":     len(features),
            "source":    "ACLED",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/military-bases")
async def get_military_bases():
    """
    인도-태평양 주요 군사기지 GeoJSON 반환.
    Phase 0 첫 번째 정적 레이어 — 미군/중국/러시아/동맹 기지 약 20개.
    연관 이론: Forward Deployment, A2/AD, String of Pearls
    """
    return _load_geojson("military_bases.geojson")


@router.get("/energy-pipelines")
async def get_energy_pipelines():
    """
    주요 에너지 파이프라인 GeoJSON 반환 (정적 데이터).
    가스관·송유관 10개 — 러시아-유럽, 러시아-중국, 중앙아시아-중국, 중동 경로.
    연관 이론: Weaponized Interdependence (Farrell & Newman), Resource Weaponization
    """
    return _load_geojson("energy_pipelines.geojson")


@router.get("/submarine-cables")
async def get_submarine_cables():
    """
    전략적 해저 광케이블 GeoJSON 반환 (정적 데이터, 18개).
    strategic_risk(high/medium/low)로 중국 주도 vs 미국/동맹 케이블을 구분한다.
    연관 이론: Techno-nationalism, Digital Iron Curtain, Platform Power
    """
    return _load_geojson("submarine_cables.geojson")


@router.get("/chokepoints")
async def get_chokepoints():
    """
    전략적 해상 초점(Chokepoints) GeoJSON 반환 (정적 폴리곤 데이터).
    10개 — 말라카·호르무즈·바브엘만데브·대만해협·루손·수에즈 등.
    연관 이론: Mahan 해양력 이론, SLOC 통제, Resource Weaponization
    """
    return _load_geojson("chokepoints.geojson")
