"""
backend/api/library.py

이론 라이브러리 API.

엔드포인트:
  GET  /api/library/theories              전체 이론 목록 (sector 필터 가능)
  GET  /api/library/theories/{id}         단일 이론 상세 (본문 포함)
  GET  /api/library/theories/{id}/focus   MapFocusTarget
  GET  /api/library/search?q=...          FTS5 전문 검색
  GET  /api/library/region-index          { region_code: [theory_id, ...] }
  POST /api/library/reindex               인덱스 재구축 (개발용)
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from services.library import deep_link as _deep_link
from services.library.ai_explain import stream_ai_explain
from services.library.deep_link import (
    build_region_index,
    get_theory_link,
    list_all,
)
from services.library.md_indexer import (
    build_fts_index,
    get_db_theory,
    list_db_theories,
    search_theories,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/library", tags=["library"])


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _parse_json_field(val) -> list:
    """SQLite TEXT 컬럼의 JSON 배열 문자열을 list로 변환한다."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            pass
    return []


def _merge(theory_link, db_row: Optional[dict], include_body: bool = False) -> dict:
    """
    TheoryLink(deep_link.yaml) + SQLite row 병합.

    SQLite 인덱스가 없을 때도 theory_library.yaml 기반 최소 정보는 반환한다.
    include_body=False 이면 body 필드를 제외 (목록 뷰 성능).
    """
    out = {
        "theory_id":       theory_link.theory_id,
        "display_name":    theory_link.display_name,
        "sector_tag":      theory_link.sector_tag,
        "map_focus":       theory_link.map_focus.model_dump(),
        "related_regions": theory_link.related_regions,
        "theorists":   [],
        "year":        None,
        "summary":     "",
        "file_path":   None,
        "asset_type":          "theory",
        "use_case":            "concept",
        "era":                 None,
        "geopol_region":       None,
        "temporal_era":        None,
        "level_of_analysis":   None,
        "instrument_of_power": None,
        "strategic_posture":   None,
    }
    if include_body:
        out["body"] = ""

    if db_row:
        out.update({
            "theorists":           _parse_json_field(db_row.get("theorists")),
            "year":                db_row.get("year"),
            "summary":             db_row.get("summary") or "",
            "file_path":           db_row.get("file_path"),
            "asset_type":          db_row.get("asset_type") or "theory",
            "use_case":            db_row.get("use_case") or "concept",
            "era":                 db_row.get("era"),
            "geopol_region":       db_row.get("geopol_region"),
            "temporal_era":        db_row.get("temporal_era"),
            "level_of_analysis":   db_row.get("level_of_analysis"),
            "instrument_of_power": db_row.get("instrument_of_power"),
            "strategic_posture":   db_row.get("strategic_posture"),
        })
        if include_body:
            out["body"] = db_row.get("body") or ""

    return out


def _merge_db_only(db_row: dict, include_body: bool = False) -> dict:
    """theory_library.yaml 미등록 항목(norm/sanction 등) — DB만으로 구성."""
    out = {
        "theory_id":       db_row["theory_id"],
        "display_name":    db_row["title"],
        "sector_tag":      db_row["sector_tag"],
        "map_focus":       None,
        "related_regions": _parse_json_field(db_row.get("regions")),
        "theorists":       _parse_json_field(db_row.get("theorists")),
        "year":            db_row.get("year"),
        "summary":         db_row.get("summary") or "",
        "file_path":       db_row.get("file_path"),
        "asset_type":          db_row.get("asset_type") or "norm",
        "use_case":            db_row.get("use_case") or "norm",
        "era":                 db_row.get("era"),
        "geopol_region":       db_row.get("geopol_region"),
        "temporal_era":        db_row.get("temporal_era"),
        "level_of_analysis":   db_row.get("level_of_analysis"),
        "instrument_of_power": db_row.get("instrument_of_power"),
        "strategic_posture":   db_row.get("strategic_posture"),
    }
    if include_body:
        out["body"] = db_row.get("body") or ""
    return out


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.get("/items")
async def list_items(
    sector:              Optional[str] = Query(None),
    asset_type:          Optional[str] = Query(None),
    use_case:            Optional[str] = Query(None),
    era:                 Optional[str] = Query(None),
    region:              Optional[str] = Query(None),
    temporal_era:        Optional[str] = Query(None),
    level_of_analysis:   Optional[str] = Query(None),
    instrument_of_power: Optional[str] = Query(None),
    strategic_posture:   Optional[str] = Query(None),
):
    """통합 라이브러리 목록. 8축 필터 지원.

    기존 5축: sector·asset_type·use_case·era·region
    신규 3축 (7대 축 §15): temporal_era·level_of_analysis·instrument_of_power·strategic_posture

    body 제외 (목록 뷰 성능).
    theory_library.yaml 등록 항목 + SQLite-only 항목(norm 등) 모두 포함.
    """
    links   = list_all(sector_tag=sector)
    db_rows = list_db_theories(sector_tag=sector)
    db_map  = {r["theory_id"]: r for r in db_rows}

    # yaml 등록 항목
    linked_ids = {link.theory_id for link in links}
    results = [_merge(link, db_map.get(link.theory_id)) for link in links]

    # DB-only 항목 (sanctions/norm 등 yaml 미등록)
    for db_row in db_rows:
        if db_row["theory_id"] not in linked_ids:
            results.append(_merge_db_only(db_row))

    # ── 기존 5축 필터 ────────────────────────────────────────────────
    if asset_type:
        results = [r for r in results if r["asset_type"] == asset_type]
    if use_case:
        results = [r for r in results if r.get("use_case") == use_case]
    if era:
        results = [r for r in results if r["era"] == era]
    if region:
        results = [r for r in results if region in (r.get("related_regions") or [])]

    # ── 신규 7대 축 필터 (§15) ───────────────────────────────────────
    if temporal_era:
        results = [r for r in results if r.get("temporal_era") == temporal_era]
    if level_of_analysis:
        results = [r for r in results if r.get("level_of_analysis") == level_of_analysis]
    if instrument_of_power:
        results = [r for r in results if r.get("instrument_of_power") == instrument_of_power]
    if strategic_posture:
        results = [r for r in results if r.get("strategic_posture") == strategic_posture]

    return results


@router.get("/theories")
async def list_theories(sector: Optional[str] = Query(None)):
    """하위 호환 유지. /api/library/items 사용 권장."""
    links  = list_all(sector_tag=sector)
    db_map = {r["theory_id"]: r for r in list_db_theories(sector_tag=sector)}
    return [_merge(link, db_map.get(link.theory_id)) for link in links]


@router.get("/theories/{theory_id}/focus")
async def get_focus(theory_id: str):
    """
    이론 ID에 해당하는 MapFocusTarget 반환.

    프론트엔드 flyTo() 용도. 레이어 활성화 권장 목록 포함.
    """
    link = get_theory_link(theory_id)
    if not link:
        raise HTTPException(404, f"이론을 찾을 수 없습니다: {theory_id}")
    return link.map_focus.model_dump()


@router.get("/theories/{theory_id}")
async def get_theory(theory_id: str):
    """단일 이론 상세 반환. body(마크다운 본문) 포함."""
    link   = get_theory_link(theory_id)
    db_row = get_db_theory(theory_id)
    if link:
        return _merge(link, db_row, include_body=True)
    if db_row:
        return _merge_db_only(db_row, include_body=True)
    raise HTTPException(404, f"이론을 찾을 수 없습니다: {theory_id}")


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(20, le=50)):
    """
    FTS5 전문 검색. 이론 제목·요약·이론가·지역·본문 전체 대상.

    SQLite 인덱스가 비어있으면 빈 배열 반환 (오류 없음).
    """
    try:
        rows = search_theories(query=q, limit=limit)
    except Exception as exc:
        logger.warning("FTS 검색 실패: %s", exc)
        return []

    results = []
    for row in rows:
        link = get_theory_link(row.get("theory_id", ""))
        if link:
            results.append(_merge(link, row, include_body=False))
        else:
            # SQLite에 있지만 theory_library.yaml에 없는 경우 — 무시
            logger.debug("FTS 결과에 미등록 theory_id: %s", row.get("theory_id"))
    return results


@router.get("/region-index")
async def get_region_index():
    """
    { region_code: [theory_id, ...] } 역방향 인덱스.

    프론트엔드가 지역 클릭 시 O(1) 이론 조회에 사용한다.
    """
    return build_region_index()


@router.post("/reindex")
async def reindex():
    """library/ 디렉토리를 스캔하여 FTS5 인덱스를 재구축한다. 개발용."""
    _deep_link.reload()          # theory_library.yaml lru_cache 갱신
    result = build_fts_index()
    return result


@router.post("/theories/{theory_id}/ai-explain")
async def ai_explain(theory_id: str):
    """
    Gemini 1.5 Flash로 이론의 추가 사례 + 현재 지정학적 함의를 스트리밍 생성.

    응답: text/event-stream (SSE)
      data: {"text": "...", "done": false}   — 누적 텍스트 청크
      data: {"done": true, "cached": bool}   — 완료 신호

    GEMINI_API_KEY 없으면 fallback 안내 메시지를 동일 포맷으로 반환.
    동일 theory_id 재호출 시 캐시에서 즉시 반환 (API 비용 0).
    """
    link = get_theory_link(theory_id)
    if not link:
        raise HTTPException(404, f"이론을 찾을 수 없습니다: {theory_id}")

    db_row = get_db_theory(theory_id)
    summary = (db_row.get("summary") or "") if db_row else link.display_name

    return StreamingResponse(
        stream_ai_explain(
            theory_id=theory_id,
            display_name=link.display_name,
            summary=summary,
            sector_tag=link.sector_tag,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # nginx 버퍼링 비활성화
        },
    )
