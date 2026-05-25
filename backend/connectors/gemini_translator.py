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
from dotenv import load_dotenv

load_dotenv()  # .env 로드 — 다른 커넥터와 동일 패턴

logger = logging.getLogger(__name__)

SourceLang = Literal["en", "ar", "ru", "zh", "auto"]

_DB_PATH      = Path(__file__).resolve().parents[1] / "db" / "translation_cache.db"
_MODEL        = "gemini-2.0-flash"
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

_CACHE_TTL_HOURS       = 24   # 번역 캐시 유효 기간 (하루 1번만 번역)
MAX_DAILY_TRANSLATIONS = 200  # 일일 Gemini 호출 한도 (free tier 절약)


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
                created_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL DEFAULT '9999-12-31T23:59:59'
            )
            """
        )
        # 기존 DB 마이그레이션: expires_at 컬럼 없으면 추가
        try:
            con.execute(
                "ALTER TABLE translation_cache ADD COLUMN "
                "expires_at TEXT NOT NULL DEFAULT '9999-12-31T23:59:59'"
            )
        except sqlite3.OperationalError:
            pass  # 이미 존재

        # 일일 사용량 추적 테이블 (UTC 날짜 기준 리셋)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_usage (
                date  TEXT PRIMARY KEY,  -- YYYY-MM-DD UTC
                count INTEGER NOT NULL DEFAULT 0
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
    now_iso = datetime.utcnow().isoformat()
    with _db() as con:
        row = con.execute(
            """
            SELECT text_ko, source_lang, model, char_count
            FROM translation_cache
            WHERE hash = ? AND expires_at > ?
            """,
            (text_hash, now_iso),
        ).fetchone()
        if row:
            con.execute(
                "UPDATE translation_cache SET hit_count = hit_count + 1 WHERE hash = ?",
                (text_hash,),
            )
        else:
            # 만료 항목 정리 (hit miss 시 삭제 — 공간 절약)
            con.execute(
                "DELETE FROM translation_cache WHERE hash = ? AND expires_at <= ?",
                (text_hash, now_iso),
            )
    return dict(row) if row else None


def _cache_set(text_hash: str, result: TranslationResult) -> None:
    import datetime as dt_module
    now     = datetime.utcnow()
    expires = now + dt_module.timedelta(hours=_CACHE_TTL_HOURS)
    with _db() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO translation_cache
                (hash, text_ko, source_lang, model, char_count, hit_count, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                text_hash,
                result.text_ko,
                result.source_lang,
                result.model,
                result.char_count,
                now.isoformat(),
                expires.isoformat(),
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
        if resp.status_code == 429:
            try:
                err_status = resp.json().get("error", {}).get("status", "")
            except Exception:
                err_status = ""
            if err_status == "RESOURCE_EXHAUSTED":
                _mark_quota_exhausted()
            resp.raise_for_status()
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

    # 2. API 키 없음 / 할당량 소진 / 일일 한도 초과
    if not _API_KEY:
        return TranslationResult(
            text_ko="번역 기능을 사용하려면 GEMINI_API_KEY가 필요합니다.",
            source_lang=source_lang,
            cached=False,
            char_count=len(text),
            model=_MODEL,
        )
    if _is_quota_exhausted():
        return TranslationResult(
            text_ko=f"(번역 일시 중단 — Gemini 할당량 소진) {text[:80]}",
            source_lang=source_lang,
            cached=False,
            char_count=len(text),
            model=_MODEL,
        )
    daily = _get_daily_count()
    if daily >= MAX_DAILY_TRANSLATIONS:
        logger.warning("[translate] 일일 한도 초과 (%d/%d)", daily, MAX_DAILY_TRANSLATIONS)
        return TranslationResult(
            text_ko=f"(일일 번역 한도 {MAX_DAILY_TRANSLATIONS}회 초과) {text[:60]}",
            source_lang=source_lang,
            cached=False,
            char_count=len(text),
            model=_MODEL,
        )

    # 3. Gemini 호출
    logger.info("[translate] Gemini 호출 #%d: %d chars, ctx=%s", daily + 1, len(text), context)
    text_ko = await _call_gemini(text, context)
    _increment_daily_count()

    result = TranslationResult(
        text_ko=text_ko,
        source_lang=source_lang,
        cached=False,
        char_count=len(text),
        model=_MODEL,
    )

    # 4. 캐시 저장 (24시간 TTL)
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


# ── 일일 번역 카운터 ─────────────────────────────────────────────────────────────
# UTC 날짜 기준으로 daily_usage 테이블에 누적. 서버 재시작 후에도 유지.

def _today_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _get_daily_count() -> int:
    """오늘 UTC 기준 Gemini 실제 호출 횟수."""
    try:
        with _db() as con:
            row = con.execute(
                "SELECT count FROM daily_usage WHERE date = ?", (_today_utc(),)
            ).fetchone()
        return row["count"] if row else 0
    except Exception:
        return 0


def _increment_daily_count() -> int:
    """호출 카운터 +1. 새 카운트 반환."""
    today = _today_utc()
    try:
        with _db() as con:
            con.execute(
                """
                INSERT INTO daily_usage (date, count) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET count = count + 1
                """,
                (today,),
            )
            row = con.execute(
                "SELECT count FROM daily_usage WHERE date = ?", (today,)
            ).fetchone()
        return row["count"] if row else 1
    except Exception:
        return 0


# ── Circuit Breaker — Gemini 할당량 소진 시 일시 차단 ────────────────────────────
# RESOURCE_EXHAUSTED(일일 RPD) 감지 시 다음 UTC 자정까지 API 호출 금지.
# Gemini 일일 할당량은 UTC 00:00에 리셋되므로, 자정 직후 자동 재개된다.
# RPM 초과(일시적 429)는 circuit breaker 를 활성화하지 않음.
_gemini_disabled_until: datetime = datetime(1970, 1, 1)


def _mark_quota_exhausted() -> None:
    """일일 할당량 소진 — 다음 UTC 자정까지 차단."""
    import datetime as dt_module
    global _gemini_disabled_until
    now = datetime.utcnow()
    # 다음 UTC 자정 계산 (오늘 자정이 이미 지났으면 내일 자정)
    next_midnight = (now + dt_module.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    _gemini_disabled_until = next_midnight
    remaining_h = (next_midnight - now).total_seconds() / 3600
    logger.warning(
        "[gemini] 일일 할당량 소진 — %s UTC(약 %.1f시간)까지 비활성화 (KST %s 09:00 이후 재개)",
        next_midnight.strftime("%Y-%m-%d %H:%M"),
        remaining_h,
        next_midnight.strftime("%m-%d"),
    )


def _is_quota_exhausted() -> bool:
    return datetime.utcnow() < _gemini_disabled_until


def reset_quota_circuit_breaker() -> None:
    """관리용: circuit breaker 강제 해제 (서버 재시작 없이 수동 초기화)."""
    global _gemini_disabled_until
    _gemini_disabled_until = datetime(1970, 1, 1)
    logger.info("[gemini] circuit breaker 수동 해제")


def get_quota_status() -> dict:
    """현재 circuit breaker 상태 반환 (stats 엔드포인트용)."""
    now = datetime.utcnow()
    exhausted = _is_quota_exhausted()
    if exhausted:
        remaining_sec = (_gemini_disabled_until - now).total_seconds()
        return {
            "exhausted": True,
            "resets_in_sec": int(max(0, remaining_sec)),
            "resets_at_utc": _gemini_disabled_until.strftime("%Y-%m-%d %H:%M UTC"),
        }
    return {"exhausted": False}


# ── 범용 요약 생성 (커스텀 프롬프트) ────────────────────────────────────────────────

async def generate_summary(
    prompt: str,
    cache_key: str,
    max_tokens: int = 256,
) -> str | None:
    """커스텀 프롬프트 기반 Gemini 요약 생성.

    캐시·일일 한도·circuit breaker를 공유하여 비용을 통제한다.
    실패 시 None 반환 → 호출자가 fallback 처리.

    Args:
        prompt:    완전한 Gemini 프롬프트 문자열
        cache_key: 캐시 키 접두사 포함 식별자 (예: "acled_ctx:...")
        max_tokens: 최대 출력 토큰 수
    """
    h = _text_hash("summary:" + cache_key)
    cached = _cache_get(h)
    if cached:
        logger.debug("[summary] cache hit: %s…", cache_key[:40])
        return cached["text_ko"]

    if not _API_KEY or _is_quota_exhausted():
        return None
    if _get_daily_count() >= MAX_DAILY_TRANSLATIONS:
        logger.warning("[summary] 일일 한도 초과, 건너뜀")
        return None

    url  = _GEMINI_URL.format(key=_API_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body)
            if resp.status_code == 429:
                try:
                    err_status = resp.json().get("error", {}).get("status", "")
                except Exception:
                    err_status = ""
                if err_status == "RESOURCE_EXHAUSTED":
                    _mark_quota_exhausted()
                logger.warning("[summary] 429: %s", err_status or "RATE_LIMIT")
                return None
            resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:
        logger.warning("[summary] Gemini 호출 실패: %s", exc)
        return None

    _increment_daily_count()
    _cache_set(h, TranslationResult(
        text_ko=text,
        source_lang="auto",
        cached=False,
        char_count=len(prompt),
        model=_MODEL,
    ))
    return text


# ── 티커 전용 번역 ──────────────────────────────────────────────────────────────

_HEADLINE_TICKER_PROMPT = (
    "다음 뉴스 헤드라인을 한국어로 요약해줘.\n\n"
    "규칙:\n"
    "- 실제 사건의 주체·행동·결과를 명확히 표현\n"
    "- 'A vs B' 또는 'A와 B의 충돌' 형식 금지\n"
    "- 대신 '중국, 영국 기업 자산 동결' 처럼 구체적 행동 중심으로 작성\n"
    "- 15~25자 내외\n"
    "- 지역 태그 포함: [중동] [인태] [유럽] [동아시아] [아프리카] 등\n"
    "- 이모지로 긴장도 표시: 🔴(전쟁/공습) 🟠(충돌/교전) 🟡(긴장/위협)\n"
    "- 시간 표시 금지. 번역문만 출력. 설명·주석·원문 첨부 금지.\n\n"
    "예시:\n"
    "입력: 'China freezes assets of British firm amid dispute'\n"
    "출력: 🔴 [인태] 중국, 영국 기업 자산 동결 조치\n\n"
    "입력: 'US forces conduct airstrike in Syria'\n"
    "출력: 🔴 [중동] 미군, 시리아 공습 단행\n\n"
    "원문:\n{text}"
)


async def translate_ticker_text(text: str, cache_key: str = "") -> str:
    """뉴스 티커 포맷(이모지 [지역] 요약) 번역.

    Args:
        text:      번역할 헤드라인 (영문 원문 권장)
        cache_key: 캐싱 기준 문자열. source_url 전달 시 URL 기반 캐싱,
                   생략 시 텍스트 해시 기반 (backward-compatible).
    """
    text = text.strip()
    if not text:
        return ""

    # source_url이 있으면 URL 기반, 없으면 텍스트 기반 캐싱
    h = _text_hash("ticker_url:" + cache_key if cache_key else "ticker:" + text)
    cached = _cache_get(h)
    if cached:
        return cached["text_ko"]

    if not _API_KEY or _is_quota_exhausted():
        return text[:60]

    daily = _get_daily_count()
    if daily >= MAX_DAILY_TRANSLATIONS:
        logger.warning("[ticker_translate] 일일 한도 초과 (%d/%d)", daily, MAX_DAILY_TRANSLATIONS)
        return text[:60]

    prompt = _HEADLINE_TICKER_PROMPT.format(text=text)
    url  = _GEMINI_URL.format(key=_API_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 128},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body)
            # RESOURCE_EXHAUSTED = 일일 할당량 소진 → circuit breaker 활성화
            if resp.status_code == 429:
                try:
                    err_status = resp.json().get("error", {}).get("status", "")
                except Exception:
                    err_status = ""
                if err_status == "RESOURCE_EXHAUSTED":
                    _mark_quota_exhausted()
                logger.warning("[ticker_translate] 429: %s", err_status or "RATE_LIMIT")
                return text[:60]
            resp.raise_for_status()
        data = resp.json()
        text_ko = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except httpx.HTTPStatusError:
        return text[:60]
    except Exception as e:
        logger.warning("[ticker_translate] Gemini 호출 실패: %s", e)
        return text[:60]

    _increment_daily_count()
    _cache_set(h, TranslationResult(
        text_ko=text_ko,
        source_lang="auto",
        cached=False,
        char_count=len(text),
        model=_MODEL,
    ))
    return text_ko


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
    """번역 캐시 통계 + 일일 사용량 (관리 페이지용)."""
    now_iso = datetime.utcnow().isoformat()
    try:
        with _db() as con:
            # 유효 항목만 카운트 (만료 제외)
            total = con.execute(
                "SELECT COUNT(*) as n FROM translation_cache WHERE expires_at > ?",
                (now_iso,),
            ).fetchone()["n"]

            total_hits = con.execute(
                "SELECT COALESCE(SUM(hit_count), 0) as n FROM translation_cache WHERE expires_at > ?",
                (now_iso,),
            ).fetchone()["n"]

            top_langs = con.execute(
                """
                SELECT source_lang, COUNT(*) as n
                FROM translation_cache
                WHERE expires_at > ?
                GROUP BY source_lang
                ORDER BY n DESC
                LIMIT 5
                """,
                (now_iso,),
            ).fetchall()

            total_chars = con.execute(
                "SELECT COALESCE(SUM(char_count), 0) as n FROM translation_cache WHERE expires_at > ?",
                (now_iso,),
            ).fetchone()["n"]

            daily_count = con.execute(
                "SELECT COALESCE(count, 0) as n FROM daily_usage WHERE date = ?",
                (_today_utc(),),
            ).fetchone()

        saved_usd  = estimate_cost(total_chars * total_hits) if total_hits else 0.0
        hit_rate   = round(total_hits / max(1, total + total_hits), 3)
        today_used = daily_count["n"] if daily_count else 0

        return {
            "total_entries":          total,
            "cache_hit_rate":         hit_rate,
            "estimated_savings_usd":  round(saved_usd, 4),
            "top_source_langs":       [(r["source_lang"], r["n"]) for r in top_langs],
            "daily_translations_today": today_used,
            "daily_limit":            MAX_DAILY_TRANSLATIONS,
            "daily_remaining":        max(0, MAX_DAILY_TRANSLATIONS - today_used),
            "cache_ttl_hours":        _CACHE_TTL_HOURS,
        }
    except Exception as exc:
        logger.warning("[translate] cache stats 조회 실패: %s", exc)
        return {
            "total_entries": 0,
            "cache_hit_rate": 0.0,
            "estimated_savings_usd": 0.0,
            "top_source_langs": [],
            "daily_translations_today": 0,
            "daily_limit": MAX_DAILY_TRANSLATIONS,
            "daily_remaining": MAX_DAILY_TRANSLATIONS,
            "cache_ttl_hours": _CACHE_TTL_HOURS,
        }
