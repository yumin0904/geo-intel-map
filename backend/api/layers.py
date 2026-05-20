"""
layers.py — 지도 레이어 GeoJSON 서빙 라우터
각 레이어(군사기지, 파이프라인 등)를 GeoJSON으로 반환한다.
CLAUDE.md 아키텍처: backend/api/layers.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from connectors.acled import AcledConnector
from models.event import Event

router = APIRouter(prefix="/api/layers", tags=["layers"])

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
    ACLED API 실시간 조회 → Event 정규화 → GeoJSON 변환.
    연관 이론: Gray Zone Strategy, Hybrid Warfare (CLAUDE.md 섹터 4·5)
    """
    connector = AcledConnector()
    try:
        events = await connector.fetch()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ACLED API 연결 실패: {e}") from e

    return _events_to_geojson(events)


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
