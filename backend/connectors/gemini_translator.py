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

from dataclasses import dataclass
from typing import Literal


SourceLang = Literal["en", "ar", "ru", "zh", "auto"]


@dataclass
class TranslationResult:
    """번역 결과 + 메타데이터.

    cached=True면 비용 발생 0, cached=False면 Gemini 호출이 실제 발생.
    프론트엔드 디버그 표시용으로 출처 노출.
    """

    text_ko: str
    source_lang: SourceLang
    cached: bool
    char_count: int
    model: str  # 사용된 모델 (gemini-1.5-flash 권장)


async def translate_event_text(
    text: str,
    source_lang: SourceLang = "auto",
    context: str | None = None,
) -> TranslationResult:
    """단일 이벤트 description 또는 title 번역.

    context 인자는 정치외교학 도메인 어휘 정확도 향상용 — 예를 들어
    "Houthi"를 "후티"로, "PLA"를 "인민해방군"으로 일관되게 번역하도록
    프롬프트에 "이 텍스트는 군사·외교 분쟁 보도이며 ACLED 출처임"이라는
    힌트를 주입.

    Args:
        text: 원문 (영문/아랍어/러시아어/중국어)
        source_lang: 명시적 지정 또는 'auto'
        context: 도메인 힌트 (예: "ACLED conflict event, naval clash")

    Returns:
        TranslationResult — 캐시 히트 시 즉시 반환
    """
    # TODO: 실제 구현
    #   1. translation_cache.db에서 hash(text) 조회
    #   2. 캐시 miss 시 Gemini 1.5 Flash 호출 (System Instruction에 도메인 제약)
    #   3. 결과 캐시 저장 후 반환
    pass


async def translate_batch(
    texts: list[str],
    source_lang: SourceLang = "auto",
) -> list[TranslationResult]:
    """배치 번역 (디테일 패널이 여러 필드를 동시 요청할 때).

    Gemini API는 단일 호출에 multi-text 입력을 받을 수 있으나, 캐시 정합성을
    위해 내부적으로는 각 항목 단위로 hash 조회 → miss 항목만 묶어서 1회 호출.

    Args:
        texts: 번역할 텍스트 목록 (최대 10개 권장)
        source_lang: 전체 항목 공통 언어

    Returns:
        입력 순서 보존된 결과 리스트
    """
    # TODO: 실제 구현
    pass


def estimate_cost(char_count: int, model: str = "gemini-1.5-flash") -> float:
    """예상 번역 비용 (USD) 추정 — 관리자 대시보드/로그용.

    Gemini 1.5 Flash 기준 입력 $0.075 / 1M tokens. 한국어 출력은 입력의
    약 1.2배 토큰 차지하므로 안전 계수 1.3 적용. 학생 자비 예산 관리를 위한
    가시성 확보가 목적.

    Args:
        char_count: 원문 글자 수
        model: 모델명

    Returns:
        예상 비용 (USD, 소수점 4자리)
    """
    # TODO: 실제 구현 — 모델별 단가 테이블 + 토큰 환산
    pass


def get_cache_stats() -> dict:
    """번역 캐시 통계 (관리 페이지용).

    Returns:
        {
            "total_entries": int,
            "cache_hit_rate_7d": float,  # 0-1
            "estimated_savings_usd": float,
            "top_source_langs": list[tuple[str, int]],
        }
    """
    # TODO: 실제 구현
    pass
