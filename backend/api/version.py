"""
backend/api/version.py

앱 버전 정보를 반환하는 엔드포인트.
config/version.json을 읽어서 응답한다 — 버전은 코드가 아닌 파일에서 관리.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

# main.py 기준 상대 경로 → config/version.json
_VERSION_FILE = Path(__file__).parent.parent / "config" / "version.json"


@router.get("/api/version")
async def get_version():
    """
    현재 앱 버전과 Phase 정보를 반환한다.
    프론트엔드 우상단 버전 뱃지가 이 값을 표시한다.
    """
    try:
        data = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="version.json 파일이 없습니다.")
    return data
