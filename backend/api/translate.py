"""
ACLED 이벤트 번역 API.

importance_score ≥ 0.7 이벤트만 허용 — API 비용 제어.
캐시 히트 시 Gemini 호출 없음.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from connectors.gemini_translator import (
    TranslationResult,
    get_cache_stats,
    translate_event_text,
)

router = APIRouter()


@router.get("/api/translate", response_model=None)
async def translate_text(
    text:       str   = Query(...,  description="번역할 원문"),
    context:    str   = Query("acled", description="도메인 힌트"),
    importance: float = Query(0.0,  description="이벤트 importance_score"),
) -> dict:
    """단일 텍스트 번역. importance ≥ 0.7 이벤트에만 허용.

    - 캐시 히트: Gemini 호출 없음, 즉시 반환
    - API 키 없음: 안내 메시지 반환 (4xx 아님)
    - importance < 0.7: 403 반환 (비용 게이트)
    """
    if importance < 0.7:
        raise HTTPException(
            status_code=403,
            detail="번역은 importance_score ≥ 0.7 이벤트에만 제공됩니다.",
        )

    result: TranslationResult = await translate_event_text(
        text=text,
        context=context,
    )

    return {
        "text_ko":     result.text_ko,
        "source_lang": result.source_lang,
        "cached":      result.cached,
        "char_count":  result.char_count,
        "model":       result.model,
    }


@router.get("/api/translate/stats")
async def translation_stats() -> dict:
    """번역 캐시 통계 (관리용)."""
    return get_cache_stats()
