"""
layers.py — 지도 레이어 GeoJSON 서빙 라우터
각 레이어(군사기지, 파이프라인 등)를 GeoJSON으로 반환한다.
CLAUDE.md 아키텍처: backend/api/layers.py
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

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


@router.get("/military-bases")
async def get_military_bases():
    """
    인도-태평양 주요 군사기지 GeoJSON 반환.
    Phase 0 첫 번째 정적 레이어 — 미군/중국/러시아/동맹 기지 약 20개.
    연관 이론: Forward Deployment, A2/AD, String of Pearls
    """
    return _load_geojson("military_bases.geojson")
