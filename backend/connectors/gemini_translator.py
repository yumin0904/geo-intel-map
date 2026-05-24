"""
분쟁 사건 on-demand 번역 래퍼 (Gemini API).

배경:
  ACLED·GDELT 원본은 영문이지만, 학습자는 한국어 모국어로 패턴을 인지할 때
  훨씬 빠르게 이론과 연결한다. 다만 모든 이벤트를 수집 시점에 일괄 번역하면
  API 비용이 폭증하므로, 다음 정책을 채택:
    1. 수집 시점에는 원문(영문) 저장
    2. 사용자가 디테일 패널을 여는 등 명시적 접촉 시점에만 번역
    3. translation_cache.db로 동일 텍스트 재번역 방지
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Literal, Optional

import httpx

logger = logging.getLogger(__name__)

SourceLang = Literal["en", "ar", "ru", "zh", "auto"]

_DB_PATH      = Path(__file__).resolve().parents[1] / "db" / "translation_cache.db"
_MODEL        = "gemini-1.5-flash"
_GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_MODEL}:generateContent?key={{key}}"
)
_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")

# 글자 수 → 토큰 환산 계수 (Gemini 영문 기준 ~4자/토큰)
_CHARS_PER_TOKEN  = 4
# Gemini 1.5 Flash 입력/출력 단가 (USD/1M tokens)
_PRICE_INPUT_PER_M  = 0.075
_PRICE_OUTPUT_PER_M = 0.30
# 번역문은 원문의 약 1.2배 길이, 안전계수 1.1 적용
_OUTPUT_RATIO = 1.32


@dataclass
class TranslationResult:
    """번역 결과 + 메타데이터.

    cached=True면 비용 발생 0, cached=False면 Gemini 호출이 실제 발생.
    프론트엔드 디버그 표시용으로 출처 노출.
    """
    text_ko:     str
    source_lang: SourceLang
    cached:      bool
    char_count:  int
    model:       str


# ── SQLite 캐시 ────────────────────────────────────────────────────────────────

@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS translation_cache (
                hash        TEXT PRIMARY KEY,
                text_ko     TEXT NOT NULL,
                source_lang TEXT NOT NULL,
                model       TEXT NOT NULL,
                char_count  INTEGER NOT NULL,
                hit_count   INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
            """
        )
        con.commit()
        yield con
        con.commit()
    finally:
        con.close()


def _text_hash(text: str) -> str:
    """SHA-256으로 텍스트 캐시 키를 생성한다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(text_hash: str) -> Optional[dict]:
    with _db() as con:
        row = con.execute(
            "SELECT text_ko, source_lang, model, char_count FROM translation_cache WHERE hash = ?",
            (text_hash,),
        ).fetchone()
        if row:
            # 조회 시마다 hit_count 증가
            con.execute(
                "UPDATE translation_cache SET hit_count = hit_count + 1 WHERE hash = ?",
                (text_hash,),
            )
    return dict(row) if row else None


def _cache_set(text_hash: str, result: TranslationResult) -> None:
    with _db() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO translation_cache
                (hash, text_ko, source_lang, model, char_count, hit_count, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                text_hash,
                result.text_ko,
                result.source_lang,
                result.model,
                result.char_count,
                datetime.utcnow().isoformat(),
            ),
        )


# ── 프롬프트 ────────────────────────────────────────────────────────────────────

_DOMAIN_GLOSSARY = (
    "Houthi→후티, PLA→인민해방군, IDF→이스라엘 방위군, "
    "IRGC→이란혁명수비대, NATO→나토, ROK→한국군, DPRK→북한, "
    "airstrike→공습, militia→민병대, fatalities→사망자, shelling→포격, "
    "convoy→수송대, IED→급조폭발물, ceasefire→휴전, siege→포위, "
    "insurgent→반군, clashes→교전"
)


def _build_prompt(text: str, context: Optional[str]) -> str:
    ctx_note = f"\n출처 맥락: {context}" if context else ""
    return (
        "당신은 군사·외교·지정학 분야 전문 한국어 번역가입니다.\n"
        "아래 영문 분쟁 사건 텍스트를 자연스러운 한국어로 번역해주세요.\n"
        f"용어 기준: {_DOMAIN_GLOSSARY}\n"
        "규칙: 번역문만 출력. 설명·주석·원문 첨부 금지.{ctx_note}\n\n"
        f"원문:\n{text}"
    )


# ── Gemini 호출 ─────────────────────────────────────────────────────────────────

async def _call_gemini(text: str, context: Optional[str]) -> str:
    """Gemini 1.5 Flash로 번역 요청. 번역문만 반환."""
    prompt = _build_prompt(text, context)
    url  = _GEMINI_URL.format(key=_API_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()

    data = resp.json()
    return (
        data["candidates"][0]["content"]["parts"][0]["text"].strip()
    )


# ── 공개 API ────────────────────────────────────────────────────────────────────

async def translate_event_text(
    text: str,
    source_lang: SourceLang = "auto",
    context: Optional[str] = None,
) -> TranslationResult:
    """단일 이벤트 description 또는 title 번역.

    Args:
        text:        원문 (영문/아랍어/러시아어/중국어 등)
        source_lang: 명시적 지정 또는 'auto'
        context:     도메인 힌트 (예: "ACLED conflict event, naval clash")

    Returns:
        TranslationResult — 캐시 히트 시 즉시 반환, API 호출 없음
    """
    text = text.strip()
    if not text:
        return TranslationResult(
            text_ko="(번역할 텍스트 없음)",
            source_lang=source_lang,
            cached=False,
            char_count=0,
            model=_MODEL,
        )

    h = _text_hash(text)

    # 1. 캐시 조회
    cached = _cache_get(h)
    if cached:
        logger.debug("[translate] cache hit: %s…", text[:30])
        return TranslationResult(
            text_ko=cached["text_ko"],
            source_lang=cached["source_lang"],
            cached=True,
            char_count=cached["char_count"],
            model=cached["model"],
        )

    # 2. API 키 없음
    if not _API_KEY:
        return TranslationResult(
            text_ko="번역 기능을 사용하려면 GEMINI_API_KEY가 필요합니다.",
            source_lang=source_lang,
            cached=False,
            char_count=len(text),
            model=_MODEL,
        )

    # 3. Gemini 호출
    logger.info("[translate] Gemini 호출: %d chars, ctx=%s", len(text), context)
    text_ko = await _call_gemini(text, context)

    result = TranslationResult(
        text_ko=text_ko,
        source_lang=source_lang,
        cached=False,
        char_count=len(text),
        model=_MODEL,
    )

    # 4. 캐시 저장
    _cache_set(h, result)
    return result


async def translate_batch(
    texts: list[str],
    source_lang: SourceLang = "auto",
) -> list[TranslationResult]:
    """배치 번역 — 캐시 히트 항목은 API 호출 없이 즉시 반환.

    캐시 miss 항목은 개별 호출 (10개 이하 소규모 배치 가정).
    """
    results: list[TranslationResult] = []
    for text in texts:
        results.append(await translate_event_text(text, source_lang=source_lang))
    return results


def estimate_cost(char_count: int, model: str = _MODEL) -> float:
    """예상 번역 비용 (USD) 추정 — 관리자 로그용.

    Gemini 1.5 Flash: 입력 $0.075/1M tokens, 출력 $0.30/1M tokens.
    4자 ≈ 1 token, 한국어 출력 ≈ 원문의 1.32배 길이.
    """
    input_tokens  = char_count / _CHARS_PER_TOKEN
    output_tokens = input_tokens * _OUTPUT_RATIO
    cost = (
        input_tokens  / 1_000_000 * _PRICE_INPUT_PER_M
        + output_tokens / 1_000_000 * _PRICE_OUTPUT_PER_M
    )
    return round(cost, 6)


def get_cache_stats() -> dict:
    """번역 캐시 통계 (관리 페이지용)."""
    try:
        with _db() as con:
            total = con.execute(
                "SELECT COUNT(*) as n FROM translation_cache"
            ).fetchone()["n"]

            total_hits = con.execute(
                "SELECT COALESCE(SUM(hit_count), 0) as n FROM translation_cache"
            ).fetchone()["n"]

            top_langs = con.execute(
                """
                SELECT source_lang, COUNT(*) as n
                FROM translation_cache
                GROUP BY source_lang
                ORDER BY n DESC
                LIMIT 5
                """
            ).fetchall()

            total_chars = con.execute(
                "SELECT COALESCE(SUM(char_count), 0) as n FROM translation_cache"
            ).fetchone()["n"]

        saved_usd = estimate_cost(total_chars * total_hits) if total_hits else 0.0
        hit_rate  = round(total_hits / max(1, total + total_hits), 3)

        return {
            "total_entries":        total,
            "cache_hit_rate_7d":    hit_rate,
            "estimated_savings_usd": round(saved_usd, 4),
            "top_source_langs":     [(r["source_lang"], r["n"]) for r in top_langs],
        }
    except Exception as exc:
        logger.warning("[translate] cache stats 조회 실패: %s", exc)
        return {
            "total_entries": 0,
            "cache_hit_rate_7d": 0.0,
            "estimated_savings_usd": 0.0,
            "top_source_langs": [],
        }
