"""
api/intel_query.py

POST /api/intel/query  — 인사이트 분석실 SSE 엔드포인트.

흐름:
  1. ParsedQuery 구성 (entity_parser)
  2. 멀티소스 컨텍스트 조립 (intel_analyzer)
  3. P5-7 에이전트 synthesis context 병합 (선택적)
  4. Gemini 2.5 Flash SSE 스트리밍
     - fast 모드: thinkingConfig 생략 (모델 자율)
     - deep 모드: thinkingBudget=8192, 503 시 fast로 자동 fallback
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import AsyncGenerator, Iterator

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_INTEL_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# [9-Q 우선순위 2] 인식론 모드 — 탐색적(exploratory) 카드 본문 규율.
#   배경(P1 HARKing): 엔진은 데이터를 *먼저* 조회한 뒤 Gemini가 그 데이터로 가설을 생성하고,
#   같은 데이터로 검정한다 → "화살 쏜 뒤 과녁 그리기"(사후가설). 탐색을 확증으로 위장하는 순환.
#   백엔드 verifier._apply_epistemic_cap는 구조화 surface(surface_summary·등급)만 캡 →
#   사용자가 실제로 읽는 카드 본문(Gemini 작성 full_text)은 캡을 모른 채 '선행성·인과'를 주장해
#   HARKing이 표면층으로 누출. 그래서 본문에도 동일한 '상관' 상한 + [탐색적] 도장을 강제한다.
#   (확증은 verify 모드 — 사용자가 데이터 보기 전 가설을 직접 선언 → 별도 task에서 [확증] 처리.)
_EXPLORATORY_EPISTEMIC_BLOCK = """\
## [9-Q 인식론 모드 — 탐색적(exploratory)] ★ 다른 모든 등급 규칙보다 우선
이 분석은 **데이터를 먼저 관찰한 뒤 가설을 세우는 탐색 모드**다. 같은 데이터로 만든 가설을
같은 데이터로 검정하면 순환논증(HARKing — 사후가설)이므로, 탐색 결과는 가설의 *생성*이지
*확증*이 아니다. 데이터가 아무리 강해 보여도 다음을 반드시 지켜라:
- [헤드라인] 맨 앞에 `[탐색적]` 도장을 반드시 찍어라 (생략 시 규칙 위반).
- [주장] 등급은 **'상관'을 초과할 수 없다.** [헤드라인]·[주장]에서 **엔진 자신의 단정**으로
  '선행성'·'인과' 동사(유발한다·초래한다·선행한다·앞선다·~로 이어진다·~때문이다·강화한다·약화시킨다)를
  쓰지 마라. 최대 '상관'(상관한다·공변한다·동조한다)까지만. 데이터가 시간 선후를 보여도 탐색에서는 '상관'까지다.
  ※ 단, [통념]·[경쟁설명]의 *이론 예측* 서술, [비자명기여]·[문헌공백]의 *가설적 메커니즘* 서술은
    인과어를 쓸 수 있다 — 그것이 엔진의 검증된 주장이 아니라 '예측'·'가설'임이 분명할 때만. 금지는 [주장]의 단정에 적용된다.
- [검증포인트]에 "확증하려면 데이터를 보기 전 H1·통제변수를 선언하고(검증 모드) 독립 표본·기간으로
  재검정해야 한다"를 반드시 명시하라.

"""


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(_INTEL_DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

from services.entity_parser import parse_query, ParsedQuery
from services.intel_analyzer import build_intel_context
from services.claim_ledger import build_nob_hints
from services.confidence_scorer import (
    score_output,
    apply_data_void_penalty, validate_insight_completeness,
)
from services.hypothesis_extractor import extract_hypotheses, build_measurable_menu
from services.hypothesis_verifier import verify_hypotheses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intel", tags=["intel"])

_GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
_GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:streamGenerateContent?alt=sse&key={{key}}"
)

# ── LLM provider 전환 (클라우드 Gemini ↔ 로컬 Ollama) ──────────────────────
#   왜: Gemini 무료티어 일일 한도(429)·비용에서 자유롭게 개발·테스트하려고
#   로컬 LLM(Ollama)로 갈아끼우는 얇은 전환층. 산술·통계검정은 여전히 Token-Zero
#   파이썬이 담당하고, 이 층은 '자연어 분석문 생성'만 provider를 바꾼다.
#   .env LLM_PROVIDER=gemini(기본) | ollama 로 선택.
_LLM_PROVIDER  = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
_OLLAMA_HOST   = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
# 8GB M1 기준: num_ctx 8192 = 모델 2GB + KV캐시 ~1GB. 프롬프트가 길면 일부 잘릴 수
# 있음(로컬 품질 한계 — 의도된 트레이드오프). 램 여유에 따라 .env로 조절.
_OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
# 간결 카드: 로컬 작은 모델(3B)은 짧고 단순한 형식을 더 잘 따른다 → 풀 11섹션 대신
#   방법론 뼈대 7줄만. 9-Q 규율(탐색/확증·등급상한·연구자판정)은 압축 보존. 기본 on(ollama).
_OLLAMA_COMPACT   = os.getenv("OLLAMA_COMPACT", "1").strip() == "1"
_USE_COMPACT_CARD = (_LLM_PROVIDER == "ollama" and _OLLAMA_COMPACT)

# ── NVIDIA NIM (OpenAI 호환) — Ollama 대체 클라우드 생성 provider ──────────────
#   왜: 로컬 Ollama(3~7b)는 카드 품질이 낮고, Gemini는 503 과부하·무료티어 한도가 있음.
#   NIM은 무료(build.nvidia.com)·OpenAI 호환·대형 모델(70b급)이라 생성 품질과 가용성을
#   동시에 얻는다. 산술·통계·구성타당도 게이트는 여전히 Token-Zero 파이썬 — NIM은 서술만.
#   NIM은 대형 모델이라 압축 카드가 아니라 Gemini와 동일한 풀 11섹션 프롬프트를 받는다.
_NIM_KEY   = os.getenv("NVIDIA_API_KEY")
_NIM_BASE  = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
_NIM_MODEL = os.getenv("NIM_MODEL", "meta/llama-3.3-70b-instruct")

# ── 요청 스키마 ───────────────────────────────────────────────────────────

class IntelQueryRequest(BaseModel):
    query: str
    # 프론트에서 섹터·지역을 직접 지정하면 parser 결과를 override
    sector_override: list[str] = []
    region_override: list[str] = []


# ── 모드별 Gemini 프롬프트 ────────────────────────────────────────────────

# [Ollama 간결 카드] 풀 11섹션 카드(Gemini용)를 7줄 뼈대로 압축한 버전.
#   목적: ① 작은 로컬 모델이 형식을 더 잘 지킴 ② 개발 중 빠르게 읽음.
#   보존(방법론 뼈대): [탐색적] 라벨 + 등급 '상관' 상한(9-Q 우선순위2) · 반증가능 H1 ·
#     경쟁이론 편차 + 우열 판정은 연구자 몫(9-Q 우선순위1) · 비자명/문헌공백 한 줄.
#   생략(장황한 에세이): [통념]·[관찰] 긴 문단·[검증포인트]. (깊이는 Gemini 풀포맷으로.)
_CARD_FMT_COMPACT = """\
아래 [예시 카드]와 **똑같은 7줄 형식**으로, 사용자 주제에 대한 새 카드 **1개**를 작성하라.
⚠️ 예시의 *설명이 아니라 채워진 내용*을 모방하라. 라벨 뒤 안내문구를 그대로 베끼지 말고 실제 분석으로 채워라.
이 분석은 [탐색적] 모드(데이터를 먼저 보고 가설 생성) → 등급 '상관'까지만, 인과 단정 동사
(유발/초래/선행/강화/약화) 금지. '상관한다·동반한다·공변한다'만.

[예시 카드] — 형식 참고용. 주제(대만·반도체)는 무시하고 **사용자 주제로 새로 쓸 것**:
[헤드라인] [탐색적] (등급: 상관) 대만해협 군사활동 증가는 TSMC 주가 하락과 동반 관찰된다
[근거] 2024년 ADIZ 진입 1,711회, TSM 주가 -8% (출처: 국방부·yfinance)
[가설] H1: "대만해협 ADIZ 진입이 증가할 때 SOXX 지수가 유의하게 하락한다 (통제변수: 미국 기준금리)"
[경쟁설명] 공격적현실주의: 압박↑→주가↓ 예측, 실측 -8%로 부합 / 자유주의: 상호의존이 완충 예측, 실측은 하락 / ▶ 우열 판정은 연구자 몫
[비자명기여] 통념은 '긴장→하락'이나 실측은 사건 전날 선반영 → 시장이 사건보다 빠르다
[문헌공백] 기존 연구는 충격 당일에 집중, 선반영 타이밍을 구조적으로 다루지 않는다
[한계] 단일 사건·단기 윈도우, 장기효과·교란요인 미통제

★ [가설]은 **반드시 채워라** — "정량 가설 없음"·"가설 없음"이라고 쓰면 안 된다. 종속변수 Y는 숫자로 잴 수
  있는 것으로 고른다: 유가(Brent/WTI)·주가지수(SOXX 등)·소비자물가(CPI)·환율·분쟁/사건 건수 중 주제에 맞는 것.
  형태: H1: "X가 증가할 때 Y가 통계적으로 유의하게 (상승/하락)한다 (통제변수: Z)". (예: '호르무즈 통행장애가
  증가할 때 Brent 유가가 유의하게 상승한다 (통제: 글로벌 수요)'.)
★ 카드는 **정확히 1개**만 쓰고 멈춰라 (2개 이상 쓰지 마라).

이제 위 형식 그대로 사용자 주제로 새 카드 1개를 작성하라. 라벨 생략 금지. 신뢰도 숫자 금지(서버 산출).
"""


def _build_prompt(pq: ParsedQuery, context_text: str, synthesis_ctx: str) -> str:
    """모드에 따라 Gemini에게 전달할 시스템+유저 프롬프트를 구성한다.

    §19-A 6단계 구조, §19-B 인사이트 카드 형식, §19-B-2 3대 강점,
    §19-C 금지 패턴, §19-D 신뢰도 산출 기준 적용.
    """

    # [비자명기여] 힌트 — 이론 반례 경계를 카드 템플릿 안에 직접 주입 (1순위 수정)
    _nob_hints = build_nob_hints(pq)

    # §19-A 원칙 + §19-B-2 강점 보존 지침 + §19-D 신뢰도 기준
    system_role = (
        "당신은 국제정치학 박사 과정을 지도하는 지정학 분석 전문가입니다.\n\n"

        "## [UNVERIFIED] 태그 규칙 — 정확히 적용할 것\n"
        "✅ <context> 블록 안에 있는 수치·사실·기관명 → [UNVERIFIED] 없이 직접 인용 가능.\n"
        "❌ <context>에 없는 외부 수치·사실 → 반드시 [UNVERIFIED] 태그 첨부.\n"
        "⚠️ [UNVERIFIED] 과잉 사용 금지: context 데이터를 충분히 활용했다면 [UNVERIFIED]는 최소화된다.\n"
        "★ [고유명사 귀속 규칙] 작전명·프로그램명·사건 코드명 등 고유명사는 <context>에 등장한 그대로, "
        "그 출처가 말하는 대상에만 사용하라. context에 없는 고유명사를 지어내지 말 것. "
        "특히 context의 고유명사를 **다른 사건과 등치**시키지 말라 — 예: 한 기사 제목의 작전명을 "
        "'이란전(작전명 X)'처럼 별개 사건의 공식 명칭으로 단정 금지. 두 대상이 같다고 context가 "
        "명시하지 않으면 일반 명칭('미국의 대이란 군사작전')으로 서술하라.\n\n"

        "## 필수 분석 원칙 (§19-A)\n"
        "1. 현상 기술(관찰)에서 멈추지 말고 인과 검증 단계(가설·경쟁이론·데이터·고리강도)까지 진입하라.\n"
        "2. 수치 없는 인과 주장은 [UNVERIFIED] 필수. '시사한다' / '가능성이 높다' 로만 끝내는 것 금지.\n"
        "3. 연쇄 고리마다 강도를 평가하라: HIGH(>70%) / MEDIUM(40~70%) / LOW(<40%). "
        "MEDIUM 이하 고리를 포함한 연쇄 전체에 [SPECULATIVE] 레이블을 붙일 것.\n"
        "4. 경쟁 이론을 반드시 2개 나열하고 **양 이론의 예측 vs 실측 수치 편차**를 제시하라. 단일 이론 수렴 금지.\n"
        "   ★ [해석 주체 원칙 — 9-Q, 필수] 엔진은 증거와 수치 편차(사실)까지만 제시한다. "
        "'어느 이론이 최종적으로 우세한가'의 판정은 **연구자(사용자)의 몫**이다. AI가 우열을 대신 단정하지 말고, "
        "연구자가 스스로 판단하도록 쟁점을 제시하라. (단 한 이론의 예측 대비 실측 '편차'는 산술적 사실이므로 제시한다 — "
        "이건 판정이 아니라 측정값이다.)\n"
        "   ★ [경쟁설명] 섹션은 반드시 아래 형식을 **그대로** 사용할 것 (레이블 변경 금지):\n\n"
        "   이론A명 (학자):\n"
        "     예측: [이 이론이 현 상황에 대해 예측하는 방향·수치]\n"
        "     실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED] 태그]\n"
        "     판정: 우세/열세/전제충족(DV 미검증) — [실측 있으면 편차, [UNVERIFIED]면 반드시 '전제충족(DV 미검증)'으로 종결]\n\n"
        "   이론B명 (학자):\n"
        "     예측: [이 이론이 예측하는 방향·수치]\n"
        "     실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED] 태그]\n"
        "     판정: 우세/열세/전제충족(DV 미검증) — [동일 규칙]\n\n"
        "   ⚠️ 실측이 [UNVERIFIED]인 이론에 우세/열세를 찍는 것은 금지 — 부재(침묵)를\n"
        "      '변화 없음/양보 없음/0%/0건' 같은 실측값으로 위조하지 마라(affirming the null).\n"
        "      정성 관찰이 예측과 상반되면 '정성 증거: …(상반)'로 별도 기재만 — 판정 줄은\n"
        "      '전제충족(DV 미검증)' 유지. [UNVERIFIED] 태그와 우세/열세가 한 줄에 공존하면 위반.\n\n"
        "   ▶ 편차 비교 (사실): 이론A 예측편차 vs 이론B 예측편차 — 실측에 더 가까운 쪽을 수치로만 (우열 단정 금지)\n"
        "   ▶ 당신의 판단 (연구자 몫): 어느 이론이 더 설명력 있는지는 연구자가 직접 판정한다. AI는 결론짓지 말고, "
        "판단 쟁점(숨은 가정·범위조건·metric 상이로 직접비교 불가한 점) 1~2개를 제시하라. "
        "[9-Q 해석 주체] AI가 잠정 견해를 덧붙이려면 반드시 '[참고]' 접두어를 붙이고, 연구자 판정을 대체하지 않는 보조 의견임을 명시하라.\n\n"
        "   ★ 구체적 예시 (반드시 이 형식 준수 — 편차는 context의 (사전계산) 값 인용):\n"
        "   자원무기화 (Hirschman):\n"
        "     예측: 에너지 의존도 증가 시 정치적 양보 빈도 증가\n"
        "     실측: EU 러시아 가스 의존도 45%→8% (변화 -37.0%p, 사전계산) [EIA/FRED]\n"
        "     판정: 열세 — 예측 '의존도 증가→양보' vs 실측 '의존도 -37.0%p 급감' — 방향 불일치\n\n"
        "   자유주의 상호의존 (Keohane):\n"
        "     예측: 상호의존 증가 시 분쟁 억제 효과\n"
        "     실측: EU-러 무역 감소율 [산술 미제공] — context에 변화율 미제공\n"
        "     판정: 열세 — 무역 단절에도 전쟁 지속 → 상호의존 억제력 과장\n\n"
        "   ▶ 편차 비교 (사실): 자원무기화 예측편차 -37.0%p(방향 반대) vs 자유주의 [산술 미제공] — 자원무기화 쪽 편차만 정량 확인됨\n"
        "   ▶ 당신의 판단 (연구자 몫): 위 편차로 어느 이론이 우세한지는 연구자가 판정. (쟁점 예: 두 이론의 metric이 달라 직접 비교엔 주의)\n\n"
        "   ⚠️ '예측:', '실측:', '판정:', '▶ 편차 비교 (사실):', '▶ 당신의 판단 (연구자 몫):' 레이블은 절대 생략 불가. 수사적 기각 금지.\n"
        "   ⚠️ [경쟁이론 엄밀성 강제] '실측:'에는 반드시 <context>의 **구체적 숫자**(연도·단위 포함)를 넣어라. "
        "숫자가 없으면 '실측: [UNVERIFIED] 정량값 부재'로 명시하라 — 정성 서술로 때우지 말 것.\n"
        "   '판정:'은 예측과 실측의 **수치 편차**를 적시하라 (예: '예측 +5% vs 실측 -37%p → 이론 A 열세'). "
        "편차 수치 없이 '한계가 있다 / 약화된다'로 끝내면 수사적 기각으로 간주한다.\n"
        "   '▶ 편차 비교 (사실):'은 두 이론의 편차를 수치로 나란히 제시만 하라(어느 쪽이 실측에 가까운지 수치로). "
        "**우세 이론을 AI가 결론짓지 말라** — 그 판정은 '▶ 당신의 판단'에서 연구자에게 넘긴다.\n"
        "   ★ [8-C 앵커 인용 — 필수 규칙] context에 '앵커(IV 전제조건) — ... (편차 X, 사전계산)' 또는 "
        "'▶ 앵커 종합 (사전계산)'이 **존재하면**:\n"
        "   (1) 해당 앵커 값을 [경쟁설명]의 '판정:' 줄에 반드시 포함해야 한다 — 형식: '(앵커: [값], 전제 충족/미충족, 사전계산)'\n"
        "   (2) 앵커 값을 인용하지 않고 '판정:' 줄을 끝내면 **규칙 위반**이다. 앵커가 있는데 생략하는 것은 허용되지 않는다.\n"
        "   (3) context에 앵커 데이터가 없을 때만 '(앵커: [앵커 미제공])'으로 표기하라.\n"
        "   단 앵커는 IV 전제조건 충족도이지 DV 직접 입증이 아니므로 '전제 충족/미충족' 표현을 유지하고 "
        "'이론이 입증됐다'로 과장하지 말라.\n"
        "   ★ [8-C 이론 출처 강제 — 필수 규칙] <context>에 '## 경쟁 이론 비교 프로파일' 섹션이 있으면:\n"
        "   (1) [경쟁설명]/[단계 4]의 이론A·이론B는 반드시 그 섹션의 '### 이론: [이름]' 목록에서 선택하라 — 자체 이론 선택 금지.\n"
        "   (2) 그 섹션에 없는 이론을 [경쟁설명]에 등장시키면 규칙 위반이다.\n"
        "   (3) '## 경쟁 이론 비교 프로파일' 섹션이 없을 때만 이론을 자유롭게 선택하라.\n\n"
        "5. 결과를 즉시 의도로 귀속하지 말라('강경 정권 온존 = 미국 실패' 형태 금지).\n"
        "6. [비자명성 강제 — 최우선] 인사이트는 통념(뉴스·교과서 수준의 예상 답)을 넘어서야 한다. 절차:\n"
        "   (a) 먼저 이 주제의 **통념**을 한 문장으로 명시하라.\n"
        "   (b) 당신의 결론이 그 통념을 어떻게 **반박·정교화·한정**하는지 보여라. 통념과 결론이 같으면 그것은 인사이트가 아니다.\n"
        "   비자명성의 원천 중 최소 하나를 활용하라:\n"
        "   ① 반직관 — 통념과 반대 방향의 메커니즘 (예: '제재가 오히려 의존도를 낮춰 무기화를 약화')\n"
        "   ② 교차도메인 — 보통 연결되지 않는 두 도메인의 인과 경로 (예: 사이버→에너지 전이)\n"
        "   ③ 범위조건 — 이 패턴이 성립/붕괴하는 경계 식별 ('언제·어디서 깨지는가')\n"
        "   ★ [8-D 원장 → 비자명기여 직결] <context>에 '## 문헌 공백 원장'이 있으면 [비자명기여]의 재료로 직접 써라:\n"
        "      - 원장 '① 반례 클러스터'의 '예측 임계' → 위 ③ 범위조건으로 활용:\n"
        "        형식: '이론 X는 [예측 임계] 조건에서 성립하나, [반례]가 보여주듯 [구체 조건]에서 깨진다 — 이 경계가 문헌 공백'\n"
        "        ★ [임계값 강제] '예측 임계:' 줄에 수치(예: HHI 2500, Polity +6, GDP 2%, 2배 격차)가 있으면\n"
        "           [비자명기여]에 그 수치를 반드시 인용하라. 수치 없는 '조건부 메커니즘' 서술은 비자명 0점.\n"
        "      - 원장 '② 경쟁이론 미해결'의 이론쌍 → 위 ① 반직관 (실측상 예상과 다른 이론이 우세함을 보여라)\n"
        "      - 원장 '③ 교차도메인 밀도'의 희박 섹터·교차 경로 → 위 ② 교차도메인 (문헌이 비운 연결고리를 메커니즘으로 제시)\n"
        "      [비자명기여]는 통념을 강조만 하지 말고, 원장의 구체적 반례·이론충돌·교차공백 중 하나를 수치/경로로 반박하라.\n"
        "   막연한 '추가 연구가 필요하다' / '주목해야 한다'는 비자명성이 아니다. 구체적 메커니즘·조건·임계값을 명시하라.\n"
        "   ★ [통념 재확인 금지 — 자기검열] [비자명기여]를 쓴 뒤, 그것이 [통념]과 **방향 또는 수치가 다른지** 스스로 점검하라. "
        "'~가 중요하다 / ~위험이 크다 / ~를 주시해야 한다'처럼 통념을 강조만 한 것은 비자명성 0점이다. "
        "반드시 통념이 **놓치는 메커니즘·역방향·임계조건** 중 하나를 수치 또는 구체적 경로로 제시하라.\n"
        "   ★ [전이·확산(contagion) 분석 특칙] '한 위기가 다른 지역/시장으로 번진다'는 주장은 그 자체로 통념이다. "
        "비자명성을 얻으려면 전이가 **차단되는 조건**(예: 대체 공급선·완충 재고·금융 헤지) 또는 "
        "전이 **속도/감쇠율의 비대칭**(예: A→B는 48h, B→A는 무반응)을 수치로 식별하라.\n"
        "7. 복수 도메인이 관여된 경우 '어떤 도메인이 어떤 경로로 어떤 도메인에 영향'을 명시적으로 서술하라.\n"
        "8. 이론 레이블마다 '이 이론으로 설명되지 않는 반례' 필드를 반드시 추가하라.\n"
        "9. [시간 역전 탐지] 각 인과 연결 고리에서 원인 이벤트와 결과 이벤트의 날짜를 확인하라. "
        "결과 이벤트가 원인 이벤트보다 이전에 발생한 경우, [TEMPORAL_REVERSAL] 태그를 붙이고 "
        "'A가 B를 유발'이 아닌 '공통 구조적 선행 조건' 또는 'B가 A의 선행 지표'로 재공식화하라.\n"
        "9-b. [선택·생존편향 탐지 — 필수] [관찰]이 **소수 사례**(특히 '차단 성공'·'발견됨'·'보고됨'처럼 "
        "한쪽 결과만 기록에 남는 사례)에 의존해 일반 결론을 추론하면, [한계]에 **선택편향(생존편향)**을 반드시 명시하라. "
        "예: '차단에 성공한 공격만 CSIS DB에 기록되고, 성공한(은폐된) 공격은 과소보고될 수 있어 복원력을 과대평가할 위험'. "
        "단일·소수 사례를 추세로 일반화할 때는 [주장] 등급을 한 단계 낮추고 '이 사례에 한해' 범위를 한정하라.\n"
        "10. [추론 정직성 — 동사 규율, 필수] 모든 인과 주장에 등급을 표기하고 등급에 맞는 동사만 사용하라:\n"
        "   · 기술적(공변 관찰만): '함께 관찰된다 / 동반한다' — 인과 동사 금지\n"
        "   · 상관(통계적 동조): '상관한다 / 공변한다' — '유발/초래/때문에' 금지 (인과 아님)\n"
        "   · 선행성(시간 선행 + 교란 통제): '선행한다 / 앞선다' — 여전히 인과 확정 아님\n"
        "   · 인과(Granger 유의 + 교란 통제 + 이론근거 3조건 동시 충족 시에만): '유발한다' 허용\n"
        "   근거가 상관 수준인데 '유발한다 / ~로 이어진다 / ~때문에'로 단정하면 추론 과대주장이다.\n"
        "   [주장] 첫머리에 '(등급: 상관)' 형태로 등급을 반드시 표기하고, 그 등급을 넘는 단정을 하지 말라.\n"
        "   ★ [헤드라인 동사 규율 — 필수] [헤드라인]의 동사도 [주장]과 **동일한 등급에 종속**된다. "
        "독자는 헤드라인만 읽고 '검증된 발견'으로 오해하므로, 헤드라인이 본문 등급보다 강한 인과를 주장하면 "
        "**헤드라인-데이터 불일치**(가장 흔한 치명적 오류)다.\n"
        "   · [주장] 등급이 기술적/상관이면 헤드라인에 '강화한다 / 유발한다 / 제한한다 / 초래한다 / ~시킨다' 등 "
        "인과 단정 동사 **금지**. 대신 '~와 동반된다 / ~와 함께 관찰된다 / (가설) ~할 가능성 / ~로 보인다'로 쓰라.\n"
        "   · '역설적으로 강화하여 ~를 제한한다'처럼 들리는 헤드라인은 인과 2개를 단정하는 것 — 상관 등급에서 금지.\n"
        "   · 인과 단정 헤드라인은 [주장] 등급이 '인과'(Granger 유의+교란통제+이론 3조건)일 때만 허용된다.\n"
        "   ★ [10-b · 8-gate 정합 — 체제·비선형 변수 특칙, 필수] 독립/종속변수가 '체제·정당성·응집력·"
        "내구성·전쟁 지속 의지'처럼 정량화 불가·비선형(임계·체제전환) 변수이면, 그 주장은 통계 검증 "
        "대상이 아니다 — 서버가 '구조적 논증(선형검정 부적합)'으로 분류한다. 본문이 이를 위반하면 "
        "본문↔검증 블록이 한 카드 안에서 모순된다. 따라서:\n"
        "   · 해당 [주장]에 '(등급: 구조적 논증)'을 표기하고 '유발/상관/선행/~시킨다' 등 통계 함의 동사를 쓰지 말라. "
        "'구조적으로 ~을 가능하게 하는 조건 / ~의 배경 조건이다'처럼 이론적·조건적 서술만 하라.\n"
        "   · 이런 변수를 억지로 측정 가능한 대리지표(예: 분쟁건수·유가)로 바꿔 인과를 주장하지 말라(대리쌍 강제 금지).\n"
        "   · 통계로 안 잡힌다는 사실 자체를 '비선형 전이의 증거'로 제시하지 말라(affirming-the-null 금지). "
        "비선형은 별도의 적극적 검정(임계회귀 등)으로만 주장 가능하다.\n"
        "   ★ [9-Q 질적 갈래 — 과정추적 스캐폴딩 모드, 필수] 서버가 이 분석을 UNQUANTIFIABLE(정량 검정 불가)로 "
        "분류하면, 너는 과정추적(Process Tracing) 조력자로 전환한다.\n"
        "   · [관찰]·[변수]·[가설]·[경쟁이론] 섹션을 정상 작성하되, [가설] H1은 '이 메커니즘이 작동한다면 "
        "어떤 증거 흔적이 남아야 하는가?'의 형태로 공식화하라 (통계 가설 형식 강제 금지).\n"
        "   · [검증포인트]에 연구자가 직접 확인해야 할 1차 사료(외교문서·보도자료·내부기록)를 구체적으로 안내하라.\n"
        "   · 결론(가설 지지/기각 판정)은 절대 내리지 말라 — 서버가 별도로 제공하는 "
        "Van Evera 4검정 스캐폴딩을 보고 연구자가 판정한다. AI가 '~가 원인이다'로 단정하면 "
        "질적 p-해킹(엔진이 서사를 가짜 엄밀성으로 포장)이 된다.\n\n"

        "## Token-Zero 산술 규율 (Phase 8 융합2) — 절대 준수\n"
        "<context>의 편차·변화율·격차·HHI·비율은 **이미 Python으로 계산되어** 제공된다.\n"
        "너는 그 값을 **그대로 인용만** 하라. 직접 빼기·나누기·퍼센트·평균을 계산하지 말라.\n"
        "- '판정: 예측 X vs 실측 Y, 편차 Z'의 Z는 context에 '(사전계산)'/'격차'/'변화'로 "
        "제공된 값을 그대로 쓴다.\n"
        "- context에 그 편차가 없으면 **암산하지 말고** '[산술 미제공]'으로 표기하라.\n"
        "- 두 수의 차이를 네가 머릿속으로 빼서 적으면 산술 환각으로 간주한다 — "
        "context 제공값만 신뢰하라.\n\n"

        "## H1 가설 작성 규칙 (Cycle 6-C/7-D — 검증 가능성 강제)\n"
        "H1의 X(독립변수)와 Y(종속변수)는 반드시 **측정 가능한 정량 지표**여야 한다:\n"
        "✅ 허용: 건수, 가격(USD), 비율(%), 지수(0~1), 금액(bn), 환율, 주가, 생산량(Mbpd)\n"
        "❌ 금지: '의지', '역량', '의도', '신뢰', '포지션', '패권' 같은 추상 개념\n"
        "예시 ✅: 'ACLED 분쟁 이벤트 월별 건수가 증가할 때 WTI 유가(USD/배럴)가 통계적으로 유의하게 상승한다'\n"
        "예시 ❌: '미국의 전략적 억지 의지가 약화될 때 중국의 강압 역량이 증가한다'\n\n"
        "★ [L2-b] 독립변수 X는 가능하면 아래 '검증 가능한 형태'로 설정하라 (Granger 검정 가능):\n"
        "   ① ACLED 분쟁 이벤트 건수 — 단, 반드시 **지역을 명시**할 것 "
        "(예: '사헬 ACLED 분쟁 건수', '호르무즈 분쟁 건수'). 지역 없는 '공격 빈도'는 검증 불가.\n"
        "   ② 시장·거시 지표 — 유가, 환율, 주가지수, 금 등 (context의 FRED·EIA 인용).\n"
        "   '행위자의 행동 빈도'(예: APT 공격 횟수, 침범 횟수)를 X로 쓸 때는 그 자체가 "
        "ACLED·CSIS로 집계되는 사건임을 명시하고 **지역 또는 섹터**를 반드시 붙여라. "
        "지역·집계 출처가 없는 행동 변수는 검증 불가(PENDING)하므로 지양한다.\n\n"
        "카드당 H1은 최대 **1개**만 작성하라. 측정 가능한 정량 H1이 없다면 "
"'[가설] 현 데이터로 검증 가능한 정량 가설 없음'으로 표기하고 [검증포인트]에 대안 서술하라.\n\n"

        "★ [8-A 측정가능성 강제 — 필수] H1의 **종속변수 Y는 반드시 아래 [측정 가능 변수 메뉴]에서 "
        "선택**하라. 메뉴 밖 변수(도발 빈도·억지 의지·역량·신뢰성·취약성 등 추상/행동 변수)를 "
        "Y로 쓰면 통계 검정이 불가능하다. 적합한 측정가능 Y가 없으면 **억지로 무관한 시장지표를 "
        "갖다 붙이지 말고** 솔직히 '[가설] 현 데이터로 검증 가능한 정량 가설 없음'으로 표기하라 "
        "(정직성 > 검정율 — 무관 변수 끼워맞추기는 환각이다).\n"
        f"[측정 가능 변수 메뉴]\n{build_measurable_menu()}\n\n"

        "## [L4-b] 쿼리 키워드 반영\n"
        f"사용자 쿼리: \"{pq.raw_query}\"\n"
        "쿼리에 등장한 핵심 용어(예: 수출규제·봉쇄·억지·제재 등)를 "
        "[헤드라인]과 [관찰]에 반드시 자연스럽게 포함하라. "
        "분석이 질문의 초점을 벗어나지 않도록 한다.\n\n"

        "## 신뢰도 점수 (§19-D) — 절대 자체 산출 금지\n"
        "신뢰도 숫자 점수(N점/100)는 외부 시스템이 자동 산출한다. "
        "출력에 '신뢰도: N점/100' 형태를 절대 포함하지 말 것. "
        "대신 연쇄강도(HIGH/MEDIUM/LOW)와 데이터기반·이론근거(고/중/저)만 카드 헤더에 표기하라.\n\n"

        "모든 답변은 한국어로 작성."
    )

    # §19-B 인사이트 카드 형식 (insight·presentation 공통)
    # ※ 신뢰도 점수는 서버 역산(§19-D)으로만 산출 — 여기서 자체 점수 부여 금지
    _card_fmt = """\
각 인사이트는 아래 카드 형식으로 작성하라. **아래 11개 헤더를 모두 포함할 것 (생략 금지):**

```
[헤드라인] 한 줄 요약 (비자명적 발견 — "A가 증가했다" 수준 금지). 동사는 [주장] 등급에 종속 — 상관 이하면 인과 단정('강화한다/유발한다/제한한다') 금지, '~와 동반된다/(가설)~할 가능성'으로
데이터기반: 고/중/저  |  이론근거: 고/중/저  |  연쇄강도: HIGH/MEDIUM/LOW

[통념]       이 주제의 통상적 해석 한 문장 (뉴스·교과서 수준의 예상 답)
[비자명기여] 위 통념을 어떻게 반박·정교화·한정하는가 — 반직관/교차도메인/범위조건 중 택1 + 구체적 메커니즘 (통념과 같으면 인사이트 아님)
{_NOB_HINTS_PLACEHOLDER}
[관찰]       측정 가능한 현상 (수치·날짜·사례 포함, 없으면 [UNVERIFIED])
[주장]       (등급: 기술적/상관/선행성/인과) 방향·강도·조건.
             ★ 등급별 허용 동사 — 이 표에서만 선택하라:
               기술적  → '동반한다 / 함께 관찰된다 / 수반한다'
               상관    → '상관한다 / 공변한다 / 동조한다'
               선행성  → '선행한다 / 앞선다 / 시간적으로 앞선다'
               인과    → '유발한다 / 초래한다' (Granger 유의 + 교란 통제 + 이론근거 3조건 동시 충족 시만)
             ★ 아래 동사는 등급이 '인과'일 때만 허용 — 상관·선행성·기술적 등급에서 절대 금지:
               '유발한다 / 초래한다 / ~로 이어진다 / ~때문이다 / ~시킨다 / 강화한다 / 약화시킨다'
             ★ '시사한다 / 확인된다 / 보여준다' — 등급이 기술적이면 쓸 수 없다.
               기술적 등급에서는 '함께 관찰된다 / 동반한다'만 사용하라.
[가설]       H1: "X가 증가할 때 Y가 통계적으로 유의하게 변화한다 (통제변수 Z)"
[근거]       데이터 소스명 + 수치 (없으면 [UNVERIFIED])
[한계]       이 분석이 답하지 못하는 것 + 소수/한쪽 사례 의존 시 선택·생존편향 명시
[경쟁설명]   ⚠️ context에 '## 경쟁 이론 비교 프로파일'이 있으면 이론A·B는 그 섹션 목록에서만 선택 (자체 선택 금지)
             대안 이론 A (이론명): 설명
             예측: [이 이론이 현 상황에 대해 예측하는 방향·수치]
             실측: [<context>의 구체적 숫자 — 연도·단위 포함. 없으면 [UNVERIFIED] 정량값 부재]
             판정: 우세/열세/전제충족(DV 미검증) — 실측 있으면 편차, [UNVERIFIED]면 반드시 '전제충족(DV 미검증)'
             대안 이론 B (이론명): 설명
             예측: [이 이론의 예측]
             실측: [구체적 숫자 또는 [UNVERIFIED] 정량값 부재]
             판정: 우세/열세/전제충족(DV 미검증) — 동일 규칙. 부재를 '변화 없음/0%'로 위조 금지(affirming the null)
             ▶ 편차 비교 (사실): A 편차 vs B 편차 직접 비교 (수치만, 우열 단정 금지)
             ▶ 당신의 판단 (연구자 몫): 어느 이론이 우세한지는 연구자가 판정 — AI는 판단 쟁점만 1~2개 제시
[검증포인트] 다음 세션에서 확인할 지표·소스
[문헌공백]   기존 연구가 이 패턴을 못 다루는 **구조적 이유** + 이 분석의 기여 (막연한 '추가 연구 필요' 금지 — 구체적 공백 명시)
```

⚠️ **[문헌공백] 섹션은 절대 생략 불가.** 기존 문헌이 이 패턴을 다루지 못하는 구조적 이유를 반드시 작성하라.
⚠️ **[8-D 원장 grounding 필수]** <context>에 '## 문헌 공백 원장'이 있으면, [문헌공백]은 반드시 그 원장의 **구체적 항목을 인용**해 작성하라:
   - **① 반례 클러스터**의 반례를 들어 "이 이론이 깨지는 경계를 기존 문헌이 충분히 다루지 않는다"를 짚어라.
   - **② 경쟁이론 미해결**의 이론쌍 중 본 쿼리에 해당하는 충돌을 들어 "라이브러리가 충돌만 적고 판정 안 했다"를 기여로 연결하라.
   - **③ 교차도메인 밀도**의 희박 섹터·교차 경로를 들어 "단일도메인 문헌의 사각지대"를 공백으로 지목하라.
   원장에 해당 신호가 없으면 그 항목은 생략하되, 원장이 있는데 한 항목도 인용 안 하면 규칙 위반이다.
⚠️ **[통념]과 [비자명기여]는 반드시 서로 달라야 한다.** 둘이 같은 내용이면 비자명성 0점 — 통념을 반박·정교화·한정하는 구체적 메커니즘을 [비자명기여]에 써라.
"""
    # [비자명기여] 힌트 주입 — placeholder를 실제 반례 경계 데이터로 교체
    _nob_block = _nob_hints if _nob_hints else "     (이 쿼리에 해당하는 이론 반례 데이터 없음 — 자체 분석)"
    _card_fmt = _card_fmt.replace("{_NOB_HINTS_PLACEHOLDER}", _nob_block)

    # [9-Q 우선순위 2] 탐색/확증 라벨을 카드 본문에도 적용 (백엔드 캡과 정합).
    #   탐색(insight·presentation): 데이터→가설 순환 방어 — [탐색적] 도장 + 등급 '상관' 상한.
    #   확증(verify): 사용자가 데이터 보기 전 가설을 선언 → 아래 verify task에서 [확증] 처리.
    if _USE_COMPACT_CARD and pq.mode != "verify":
        # 로컬 ollama 간결모드 — 7줄 뼈대로 교체(탐색 규율 자체 내장 → 풀 블록 미부착)
        _card_fmt = _CARD_FMT_COMPACT
    elif pq.mode != "verify":
        _card_fmt = _EXPLORATORY_EPISTEMIC_BLOCK + _card_fmt

    if pq.mode == "presentation":
        task = f"""## 요청
사용자가 다음 주제로 발표를 준비하고 있습니다: "{pq.raw_query}"

{_card_fmt}

⚠️ <context>에 있는 수치는 [UNVERIFIED] 없이 인용하라. [UNVERIFIED]는 context 외부 사실에만 사용.
⚠️ 각 카드의 [가설] H1은 **1개, 측정 가능한 정량 지표**로만 작성하라.

### 발표 각도 추천 (3~5개)
각 각도마다 위 인사이트 카드 형식으로 작성하되, 카드 끝에 아래를 추가하라:
- **청중 훅**: 발표 시작 30초 안에 관심을 끌 역설적 질문
- **차별점**: 기존 발표에서 흔히 다루는 각도와 무엇이 다른가 (§19-B-2 문헌 공백 활용)

### 추천 슬라이드 구성 (가장 강력한 각도 1개 기준)
슬라이드 흐름을 5~7단계로 제시하고, 각 단계에 '이 슬라이드에서 청중이 가져가야 할 한 문장'을 포함하라."""

    elif pq.mode == "verify":
        task = f"""## 요청
사용자가 다음 주장을 검증하려 합니다: "{pq.raw_query}"

## [9-Q 인식론 모드 — 확증적(confirmatory)]
사용자가 데이터를 보기 **전에** 가설(주장)을 직접 선언했으므로 이 분석은 확증 모드다.
탐색(데이터→가설)과 달리 검정 결과가 지지하는 한도까지 등급을 허용한다(상관 상한 없음).
- [최종 판정]의 **결론** 맨 앞에 `[확증]` 표기를 반드시 붙여라.
- 단, **완전한 사전등록(pre-registration)은 아니다** — 통제변수가 사전 선언되지 않았고
  사용자가 뉴스를 접한 뒤 주장했을 수 있다. [단계 5] 또는 한계에 "통제변수 미사전선언" 캐비엇 1줄을 남겨라.

⚠️ <context>에 있는 수치는 [UNVERIFIED] 없이 인용하라. [UNVERIFIED]는 context 외부 사실에만 사용.

§19-A 6단계 구조로 분석하라:

### [단계 1] 관찰
주장과 관련된 측정 가능한 현상을 수치와 함께 서술하라. 수치 없으면 [UNVERIFIED].

### [단계 2] 변수 식별
- 독립변수(원인 후보):
- 종속변수(결과):
- 통제변수(제거해야 할 혼재 요인):

### [단계 3] 가설 공식화
⚠️ [H1 고정 — 검증 모드 필수] H1은 사용자가 위에서 제시한 주장을 정량 지표로 받아 쓴다.
  AI가 자체 가설을 만들거나 주장의 방향을 바꾸는 것은 금지. 변수 식별·형식화만 담당한다.
- H1 (주장 지지): [반증 가능 형태 — "X가 증가할 때 Y가 유의하게 변화한다"]
  ※ X, Y는 정량 지표(건수·가격·비율·지수)여야 한다. 정량화 불가 시 이 줄 생략하고 [검증포인트]에 서술.
- H0 (귀무 가설): [H1이 틀렸을 때 관찰될 패턴]

### [단계 4] 경쟁 이론
⚠️ [이론 출처 — 필수] <context>에 '## 경쟁 이론 비교 프로파일' 섹션이 있으면 이론A·이론B는 반드시 그 섹션의 '### 이론: [이름]' 목록에서 선택하라. 자체 이론 선택 금지.
이 현상을 다르게 설명하는 이론 2개를 나열하고 **양 이론의 예측 vs 실측 수치 편차**를 제시하라. 어느 이론이 우세한지 최종 판정은 연구자에게 남긴다(AI 단정 금지 — 9-Q 해석 주체 원칙).
각 이론은 반드시 아래 형식을 **그대로** 사용하라 (레이블 변경 금지 — insight 모드와 동일):

이론A명 (학자):
  예측: [이 이론이 현 상황에 대해 예측하는 방향·수치]
  실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED]]
  판정: 우세/열세/전제충족(DV 미검증) — [실측 있으면 편차, [UNVERIFIED]면 반드시 '전제충족(DV 미검증)'으로 종결]
이론B명 (학자):
  예측: [이 이론이 예측하는 방향·수치]
  실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED]]
  판정: 우세/열세/전제충족(DV 미검증) — [동일 규칙]
⚠️ 실측이 [UNVERIFIED]인 이론에 우세/열세 금지 — 부재(침묵)를 '변화 없음/0건'으로 위조 금지(affirming the null). 정성 반대증거는 '정성 증거: …(상반)'로 별도 기재만, 판정 근거 사용 금지.
▶ 편차 비교 (사실): A 편차 vs B 편차 직접 비교 (수치만, 우열 단정 금지)
▶ 당신의 판단 (연구자 몫): 어느 이론이 우세한지는 연구자가 판정 — AI는 판단 쟁점만 제시. [9-Q] 잠정 견해를 덧붙이려면 '[참고]' 접두어 필수(보조 의견, 연구자 판정 비대체)

⚠️ '예측:', '실측:', '판정:', '▶ 편차 비교 (사실):', '▶ 당신의 판단 (연구자 몫):' 레이블 생략 불가. '실측:'은 <context>의 구체적 숫자(없으면 [UNVERIFIED] 정량값 부재),
'판정:'은 예측 대비 실측의 수치 편차를 적시하라(사실). '▶ 편차 비교 (사실):'은 두 이론 편차를 수치로 나란히 제시만, 우세 이론은 AI가 결론짓지 말고 '▶ 당신의 판단'에서 연구자에게 넘겨라. 정성 서술로 끝내면 수사적 기각으로 간주한다.

### [단계 5] 근거 평가
컨텍스트 데이터에서:
- 지지 증거 (소스 + 수치):
- 반증 증거 (소스 + 수치):
- 미검증 항목: [UNVERIFIED] 명시

### [단계 6] 연쇄 고리 강도 자기평가
각 인과 연결고리를 HIGH / MEDIUM / LOW로 평가하고,
MEDIUM 이하가 포함되면 전체 결론에 [SPECULATIVE] 레이블을 붙일 것.

### [동사 자기검열 — 최종 판정 전 필수]
위에서 사용한 동사를 점검하라:
- [단계 3] H1과 [단계 5] 서술에 '유발한다·초래한다·~로 이어진다·~때문이다'가 있으면,
  그 연결고리가 Granger 유의(p<0.05) + 교란 통제 + 이론근거 3조건을 동시 충족하는지 확인하라.
  충족하지 않으면 '상관한다 / 동반한다 / 선행한다'로 교체하라.
- '시사한다·확인된다·보여준다'는 등급이 '상관' 이하라면 '함께 관찰된다'로 교체하라.

### 최종 판정
- **결론**: 지지 / 반증 / 불확실
  ⚠️ [9-Q 해석 주체] 결론은 **H1(사용자가 선언한 반증가능 가설)의 지지/반증/불확실에만** 한정하라.
  쿼리가 'A이론 vs B이론'이라도 "어느 이론이 더 우월하다/설명력이 높다"를 여기서 단정하지 마라 —
  이론 우열 판정은 [경쟁설명]의 '▶ 당신의 판단 (연구자 몫)'과 동일하게 연구자 몫이다.
  (증거가 한 이론의 예측과 더 정합하면 '실측은 A이론 예측 방향과 일치'까지만 사실로 적고, 우열 단정은 금지.)
- **레이블**: [SPECULATIVE] / [PROVISIONAL] / 없음

⚠️ **[단계 완결 최우선]** [단계 1]~[최종 판정]을 **모두 완성**하라. [단계 4]가 길어지면 각 이론 서술을 2~3문장으로 요약하라 — 단계 누락이 내용 부족보다 훨씬 큰 감점이다."""

    else:  # insight
        task = f"""## 요청
다음 질문에 대해 교차 분석 기반 인사이트를 제공하세요: "{pq.raw_query}"

{_card_fmt}

인사이트 카드를 **2개** 작성하라. (깊이 > 넓이 — 카드 수보다 각 카드의 완결성 우선)
각 카드의 [가설] 섹션에 H1은 최대 1개. 측정 불가능하면 '[가설] 정량 가설 없음'으로 표기.
⚠️ "A → B를 시사한다" / "가능성이 높다" 로만 끝내는 것 금지. 연쇄 고리 강도까지 반드시 평가할 것.
⚠️ 각 카드의 [문헌공백] 섹션은 절대 생략 불가 — 카드를 마무리하기 전 반드시 작성하라.
⚠️ <context>에 있는 수치는 [UNVERIFIED] 없이 인용하라. [UNVERIFIED]는 context 외부 사실에만 사용.
⚠️ **[섹션 완결 최우선]** 각 카드의 11개 섹션([헤드라인]~[문헌공백])을 **모두 완성**하라. [경쟁설명]이 길어지면 각 이론 설명을 2~3문장으로 요약하라 — 섹션 누락이 내용 부족보다 훨씬 큰 감점이다.

### 도메인 교차 경로 (§19-B-2 ②)
복수 도메인이 관여된 경우, 아래 형식으로 도메인 간 인과 경로를 명시하라:
[도메인A → 도메인B] 경로 설명 + 전이 조건

### [동사 자기검열 — 카드 완성 후 필수]
각 카드의 [주장] 등급과 본문 동사가 일치하는지 최종 점검하라:
- [주장] 등급이 '기술적'이면 본문에 '시사한다·확인된다·강화한다·유발한다'가 없어야 한다.
  있으면 → '함께 관찰된다 / 동반한다'로 교체.
- [주장] 등급이 '상관'이면 본문에 '유발한다·초래한다·~로 이어진다'가 없어야 한다.
  있으면 → '상관한다 / 공변한다'로 교체.
- [헤드라인]도 같은 등급 제약을 받는다 — 기술적 등급 카드에서 인과 동사가 헤드라인에 있으면 교체."""

    return f"""{system_role}

<context>
{context_text}

{synthesis_ctx}
</context>

{task}"""


# ── Gemini SSE 스트리밍 ───────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _nim_stream_text(prompt: str) -> AsyncGenerator[str, None]:
    """NVIDIA NIM (OpenAI 호환 /chat/completions) SSE 스트리밍 → 텍스트 청크만 yield.

    SSE 형식: 'data: {"choices":[{"delta":{"content":"..."}}]}' — delta.content가 부분 텍스트.
    오류·미연결 시 '⚠️' 경고 텍스트를 yield (SSE 흐름 유지 — 상위가 실패로 판정).
    """
    if not _NIM_KEY:
        yield "⚠️ NVIDIA_API_KEY가 설정되지 않았습니다."
        return
    body = {
        "model":       _NIM_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "stream":      True,
        "temperature": 0.6,
        # 한국어 11섹션 카드는 토큰 소모가 크다(한국어 토큰 효율 낮음). Gemini(16384) 수준으로
        # 상향해 [관찰]~[문헌공백] 전 섹션이 잘리지 않게 한다(4096은 중간 절단 실측).
        "max_tokens":  8192,
    }
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST", f"{_NIM_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {_NIM_KEY}"}, json=body,
            ) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error("[intel] NIM %d: %s", resp.status_code, err[:200])
                    yield f"⚠️ NIM 오류 ({resp.status_code}) — 키·모델·rate limit 확인"
                    return
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    payload = raw_line[6:].strip()
                    if payload in ("[DONE]", ""):
                        continue
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {})
                        text  = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
    except httpx.ConnectError:
        yield f"⚠️ NIM 서버에 연결할 수 없습니다 (base={_NIM_BASE})."
    except httpx.TimeoutException:
        yield "\n\n⚠️ NIM 응답 시간 초과. 다시 시도해주세요."
    except Exception as e:  # noqa: BLE001
        logger.exception("[intel] NIM 스트리밍 예외: %s", e)
        yield f"\n\n⚠️ NIM 오류: {e}"


async def _ollama_stream_text(prompt: str) -> AsyncGenerator[str, None]:
    """로컬 Ollama(/api/generate) 스트리밍 → 텍스트 청크만 yield.

    Ollama 응답은 JSONL(줄마다 JSON) — 각 줄의 'response' 필드가 부분 텍스트.
    오류·미연결 시 사용자에게 보이는 경고 텍스트를 yield (SSE 흐름 유지).
    """
    body = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_ctx": _OLLAMA_NUM_CTX,
            "num_predict": 4096,   # 출력 상한 (인사이트 카드 ~2.5~4k 토큰)
        },
    }
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{_OLLAMA_HOST}/api/generate", json=body) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    logger.error("[intel] Ollama %d: %s", resp.status_code, err[:200])
                    yield f"⚠️ Ollama 오류 ({resp.status_code}) — 모델/서버 확인"
                    return
                async for raw_line in resp.aiter_lines():
                    if not raw_line.strip():
                        continue
                    try:
                        obj = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    text = obj.get("response", "")
                    if text:
                        yield text
                    if obj.get("done"):
                        break
    except httpx.ConnectError:
        yield ("⚠️ Ollama 서버에 연결할 수 없습니다 — `brew services start ollama` 확인 "
               f"(host={_OLLAMA_HOST}).")
    except httpx.TimeoutException:
        yield "\n\n⚠️ Ollama 응답 시간 초과(로컬 모델이 느릴 수 있음). 다시 시도해주세요."
    except Exception as e:  # noqa: BLE001
        logger.exception("[intel] Ollama 스트리밍 예외: %s", e)
        yield f"\n\n⚠️ Ollama 오류: {e}"


async def _stream_gemini(
    prompt: str,
    thinking: bool,
    source_counts: dict | None = None,
    default_regions: list[str] | None = None,
    source_query: str = "",
    mode: str = "insight",
) -> AsyncGenerator[str, None]:
    """Gemini 2.5 Flash SSE 스트리밍. thinking=True 시 thinkingBudget 8192.

    default_regions: H1에 지역명이 없을 때 상속할 쿼리 지역 (Granger 변수
        매핑 오류 방지 — 예: korean_peninsula 쿼리가 middle_east→ITA로 검정되는 버그).
    """

    if _LLM_PROVIDER != "ollama" and not _GEMINI_KEY:
        yield _sse({"text": "⚠️ GEMINI_API_KEY가 설정되지 않았습니다.", "done": False})
        yield _sse({"done": True})
        return

    url  = _GEMINI_URL.format(key=_GEMINI_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
        "generationConfig": {"maxOutputTokens": 16384, "temperature": 0.7},
    }
    if thinking:
        # 1024로 제한: 8192는 출력 시작까지 15~20초 지연 발생
        body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 1024}

    # 503 재시도 대기 시간 (초): 최대 3회, 지수 백오프
    _503_DELAYS = [5, 15, 30]

    async def _do_stream(request_body: dict, _attempt: int = 0) -> AsyncGenerator[str, None]:
        full_text = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, json=request_body) as resp:
                    if resp.status_code == 503:
                        if thinking and _attempt == 0:
                            # thinking 모드 첫 503 → fast 모드로 즉시 fallback
                            logger.warning("[intel] Gemini 503 — thinking 비활성화 후 재시도")
                            yield _sse({"text": "", "done": False, "fallback": True,
                                        "note": "thinking 모드 일시 불가 → 일반 모드로 전환"})
                            fallback_body = {k: v for k, v in request_body.items()}
                            fallback_body["generationConfig"] = {
                                k: v for k, v in request_body["generationConfig"].items()
                                if k != "thinkingConfig"
                            }
                            async for chunk in _do_stream(fallback_body, _attempt + 1):
                                yield chunk
                            return
                        if _attempt < len(_503_DELAYS):
                            # 과부하 재시도: 지수 백오프
                            delay = _503_DELAYS[_attempt]
                            logger.warning(
                                "[intel] Gemini 503 과부하 — %ds 후 재시도 (%d/%d)",
                                delay, _attempt + 1, len(_503_DELAYS),
                            )
                            yield _sse({"text": "", "done": False,
                                        "note": f"⏳ Gemini 일시 과부하 — {delay}초 후 재시도 ({_attempt+1}/{len(_503_DELAYS)})..."})
                            await asyncio.sleep(delay)
                            async for chunk in _do_stream(request_body, _attempt + 1):
                                yield chunk
                            return
                        # 재시도 초과 → 오류 메시지 반환
                        logger.error("[intel] Gemini 503 재시도 초과 (%d회)", len(_503_DELAYS))
                        yield _sse({"text": "⚠️ Gemini API가 현재 과부하 상태입니다. 잠시 후 다시 시도해주세요.", "done": False})
                        yield _sse({"done": True})
                        return

                    if resp.status_code != 200:
                        err = await resp.aread()
                        logger.error("[intel] Gemini %d: %s", resp.status_code, err[:200])
                        yield _sse({"text": f"⚠️ Gemini API 오류 ({resp.status_code})", "done": False})
                        yield _sse({"done": True})
                        return

                    async for raw_line in resp.aiter_lines():
                        if not raw_line.startswith("data: "):
                            continue
                        payload_str = raw_line[6:].strip()
                        if payload_str in ("[DONE]", ""):
                            continue
                        try:
                            chunk    = json.loads(payload_str)
                            parts    = (chunk.get("candidates", [{}])[0]
                                        .get("content", {})
                                        .get("parts", []))
                            for part in parts:
                                # thought=True 파트는 사용자에게 노출하지 않음
                                if part.get("thought"):
                                    continue
                                text = part.get("text", "")
                                if text:
                                    full_text += text
                                    yield _sse({"text": text, "done": False})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

        except httpx.TimeoutException:
            yield _sse({"text": "\n\n⚠️ 응답 시간 초과. 다시 시도해주세요.", "done": False})
        except Exception as e:
            logger.exception("[intel] 스트리밍 예외: %s", e)
            yield _sse({"text": f"\n\n⚠️ 오류: {e}", "done": False})

        async for _ev in _finalize(full_text):
            yield _ev

    async def _finalize(full_text: str) -> AsyncGenerator[str, None]:
        """스트리밍 완료 후 채점·가설추출·예측계측 — provider 무관 후처리.

        Gemini·Ollama 어느 경로든 동일한 full_text를 받아 동일하게 처리한다
        (산술·통계는 Token-Zero 파이썬이므로 provider와 무관).
        """
        # §19-D 신뢰도 점수 역산 — 스트리밍 완료 후 score 이벤트 전송
        if full_text:
            score_result = score_output(full_text)
            # [A1 2축] 추론 등급 기본값: 인과 검정이 없으면 '기술적'(서술적 근거만).
            # 증거 등급(confidence)이 높아도 인과 검증과 무관함을 항상 표시.
            score_result["inference_grade"]  = "기술적"
            score_result["inference_caveat"] = "인과 검정 미수행 — 서술·이론 근거만(인과 아님)"

            # [P0-B / L1-a] 데이터 공백 패널티: ACLED·Cascade 없어도
            # 정형 수치 소스(WBK·ITU·HIIK·CSIS·semi·FRED·SIPRI 등)가 있으면 완화
            if source_counts:
                # 비어있지 않은 정형 수치 소스 개수 집계 (L1-c에서 추가된 카운트 포함)
                _STRUCTURED_KEYS = (
                    "sipri_countries", "cow_alliances", "kiel_donors", "eia_entries",
                    "csis_incidents", "sipri_arms", "vdem_entries", "cow_wars",
                    "fred", "wbk", "polity5", "itu", "hiik", "semi", "owid",
                )
                structured_sources = sum(
                    1 for k in _STRUCTURED_KEYS if source_counts.get(k, 0) > 0
                )
                penalized = apply_data_void_penalty(
                    score_result["confidence"],
                    source_counts.get("event_stats_regions", 0),
                    source_counts.get("cascade_links", 0),
                    structured_sources,
                )
                if penalized != score_result["confidence"]:
                    logger.info(
                        "[intel] 데이터 공백 패널티 적용: %d → %d "
                        "(events=%d cascade=%d structured=%d)",
                        score_result["confidence"], penalized,
                        source_counts.get("event_stats_regions", 0),
                        source_counts.get("cascade_links", 0),
                        structured_sources,
                    )
                    score_result["confidence"] = penalized
                    score_result["provisional"] = penalized < 60

            # IA-Engine-D: H1 가설 추출 → Granger 선행성 검정
            # [학술 재설계 A1] 검증을 신뢰도 숫자에 합치지 않고 '추론 등급'으로 분리.
            #   - 증거 등급(confidence): 데이터·이론 충실도 (§19-D + data_void)
            #   - 추론 등급(inference_grade): 인과추론 사다리 (기술적<상관<선행성)
            # verification_cap 폐기 — 두 축을 하나의 숫자로 뭉개던 결함(Goodhart) 제거.
            specs = extract_hypotheses(full_text, default_regions=default_regions)
            if specs:
                # [9-0] 원본 쿼리를 spec에 주입 — 시그니처 분류 시 H1+H0에 없는 키워드 보완
                # [9-Q 우선순위 2] 인식론 모드 — verify(가설 직접 입력)=확증, 그 외=탐색(HARKing).
                #   탐색형은 데이터를 본 뒤 가설을 생성 → 같은 데이터 검정은 순환 → 등급 '상관' 상한.
                _is_exploratory = (mode != "verify")
                for _s in specs:
                    _s.source_query = source_query
                    _s.exploratory  = _is_exploratory
                specs = await verify_hypotheses(specs)

                # [Phase 10-1] 예측 계측 — 반증가능 타깃·방향·시점을 로그에 동결.
                # Token-Zero(LLM 無). 채점(10-2)은 resolve_by 도래 후 실측 대조.
                # 계측 실패가 SSE 흐름을 막지 않도록 log_predictions 내부에서 흡수됨.
                try:
                    from services.prediction_instrument import log_predictions
                    log_predictions(specs, source_query)
                except Exception as _pred_exc:  # noqa: BLE001
                    logger.warning("[10-1] 예측 계측 호출 실패: %s", _pred_exc)

                # [3-2 발견2] 사다리 최고 등급 — Method Router headline_rung(준실험)도 포함
                # 확증형(verify)은 _apply_epistemic_cap에서 캡 없음 → 준실험 그대로 노출.
                # 탐색형은 캡 후 headline_rung이 이미 '상관'으로 강등돼 있어 준실험 누출 없음.
                _LADDER_ORDER = {"기술적": 0, "상관": 1, "선행성": 2, "준실험": 3}

                def _spec_rung(s: object) -> int:
                    mr = getattr(s, "method_result", None) or {}
                    return max(
                        _LADDER_ORDER.get(s.inference_grade, 0),
                        _LADDER_ORDER.get(mr.get("headline_rung", ""), -1),
                    )

                best_spec = max(specs, key=_spec_rung)
                _mr_best = getattr(best_spec, "method_result", None) or {}
                _ig = best_spec.inference_grade
                _mr_rung = _mr_best.get("headline_rung", "")
                score_result["inference_grade"] = (
                    _mr_rung
                    if _LADDER_ORDER.get(_mr_rung, -1) > _LADDER_ORDER.get(_ig, 0)
                    else _ig
                )
                score_result["inference_caveat"] = best_spec.inference_caveat
                # hypothesis 이벤트 전송
                yield _sse({
                    "type": "hypothesis",
                    "done": False,
                    "hypotheses": [
                        {
                            # [9-P-4] 표면(surface): 비전공자 판독용 한 줄 결론
                            "surface": {
                                "summary": s.surface_summary,
                                "confidence_word": s.confidence_word,
                                "routing_method": s.routing_method,
                                "routing_confidence": s.routing_confidence,
                                "routing_alternatives": s.routing_alternatives,
                                # [9-Q 우선순위 2] 탐색/확증 뱃지용 플래그
                                "exploratory": getattr(s, "exploratory", False),
                            },
                            # [9-P-4] 펼침(detail): 전체 진단·caveat — 전문가/감사용
                            "detail": {
                                "h1": s.h1,
                                "h0": s.h0,
                                "independent_var": s.independent_var,
                                "dependent_var": s.dependent_var,
                                "control_vars": s.control_vars,
                                "region_code": s.region_code,
                                "dependent_region": s.dependent_region,
                                "ticker": s.ticker,
                                "var_type": s.var_type,
                                "proxy_suggestions": s.proxy_suggestions,
                                "linear_testable": s.linear_testable,
                                "testability_reason": s.testability_reason,
                                "is_proxy_pair": s.is_proxy_pair,
                                "verification_status": s.verification_status,
                                "inference_grade": s.inference_grade,
                                "inference_caveat": s.inference_caveat,
                                "theory_grounded": s.theory_grounded,
                                "controlled": s.controlled,
                                "control_name": s.control_name,
                                "granger_p": s.granger_p,
                                "granger_q": s.granger_q,
                                "f_statistic": s.f_statistic,
                                "best_lag": s.best_lag,
                                "differenced": s.differenced,
                                "n_obs": s.n_obs,
                                "error": s.error,
                                # [9-0] Method Router 결과
                                "data_signature": getattr(s, "data_signature", ""),
                                "method_result": getattr(s, "method_result", {}),
                            },
                        }
                        for s in specs
                    ],
                })

            yield _sse({"type": "score", "done": False, **score_result})

        yield _sse({"done": True})

    # === provider 분기: 로컬 Ollama vs 클라우드 Gemini ===
    #   Ollama 경로는 503/thinking 재시도가 불필요(로컬) → 단순 스트림 + 동일 _finalize.
    if _LLM_PROVIDER == "nim":
        _ft = ""
        async for _t in _nim_stream_text(prompt):
            _ft += _t
            yield _sse({"text": _t, "done": False})
        async for _ev in _finalize(_ft):
            yield _ev
        return

    if _LLM_PROVIDER == "ollama":
        _ft = ""
        async for _t in _ollama_stream_text(prompt):
            _ft += _t
            yield _sse({"text": _t, "done": False})
        async for _ev in _finalize(_ft):
            yield _ev
        return

    async for chunk in _do_stream(body):
        yield chunk


# ── 엔드포인트 ────────────────────────────────────────────────────────────

@router.post("/query")
async def intel_query(req: IntelQueryRequest):
    """
    인사이트 분석실 메인 SSE 엔드포인트.

    응답: text/event-stream
    청크 형식: data: {"text": "...", "done": false}
    완료 형식: data: {"done": true, "meta": {...}}
    """
    # ── 1. 엔티티 파싱 ────────────────────────────────────────────────────
    pq = parse_query(req.query)
    if req.sector_override:
        pq.sectors = req.sector_override
    if req.region_override:
        pq.regions = req.region_override

    logger.info(
        "[intel] 쿼리 수신 mode=%s thinking=%s regions=%s sectors=%s",
        pq.mode, pq.thinking, pq.regions, pq.sectors,
    )

    # ── 2. 멀티소스 컨텍스트 조립 ─────────────────────────────────────────
    intel_ctx  = await build_intel_context(pq)
    context_text = intel_ctx["context_text"]
    source_counts = intel_ctx["source_counts"]

    # ── 3. synthesis context 조립 ─────────────────────────────────────────
    synthesis_ctx = ""
    briefing_titles = [
        i.get("title", "") for i in
        (intel_ctx.get("like_items", []) + intel_ctx.get("sector_items", []))[:5]
    ]
    if briefing_titles:
        synthesis_ctx = "### 참조 브리핑\n" + "\n".join(
            f"- {t}" for t in briefing_titles
        )

    # ── 4. 프롬프트 구성 → Gemini SSE ────────────────────────────────────
    prompt = _build_prompt(pq, context_text, synthesis_ctx)

    async def event_stream() -> AsyncGenerator[str, None]:
        # 메타 정보 먼저 전송 (프론트 소스 표시용)
        yield _sse({
            "type":  "meta",
            "mode":  pq.mode,
            "thinking": pq.thinking,
            "regions": pq.regions,
            "actors":  pq.actors,
            "sectors": pq.sectors,
            "source_counts": source_counts,
            "done":  False,
        })

        async for chunk in _stream_gemini(
            prompt, pq.thinking, source_counts,
            default_regions=pq.regions, source_query=req.query,
            mode=pq.mode,
        ):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── 저장 / 조회 / 삭제 ────────────────────────────────────────────────────────

class SaveRequest(BaseModel):
    query:            str
    mode:             str = "insight"
    regions:          list[str] = []
    sectors:          list[str] = []
    result_md:        str
    context_chars:    int = 0
    confidence_score: int | None = None


@router.post("/save")
def intel_save(req: SaveRequest):
    """분석 결과 저장. [P0-A] 저장 전 완결성 검사 통과 시만 허용."""
    # [P0-A] 인사이트 완결성 검사 — 섹션 누락·문장 미완성 시 거부
    ok, reason = validate_insight_completeness(req.result_md)
    if not ok:
        raise HTTPException(status_code=422, detail=f"인사이트 미완성: {reason}")

    title = req.query[:40].strip() + ("..." if len(req.query) > 40 else "")
    with _db() as con:
        cur = con.execute(
            """
            INSERT INTO intel_analyses
                (title, query, mode, regions, sectors, result_md,
                 context_chars, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                req.query,
                req.mode,
                json.dumps(req.regions, ensure_ascii=False),
                json.dumps(req.sectors, ensure_ascii=False),
                req.result_md,
                req.context_chars,
                req.confidence_score,
            ),
        )
    return {"id": cur.lastrowid, "title": title}


@router.get("/history")
def intel_history(limit: int = 30):
    """저장된 분석 목록 반환 (result_md 제외 — 목록 표시용)."""
    with _db() as con:
        rows = con.execute(
            """
            SELECT id, title, query, mode, regions, sectors,
                   context_chars, created_at
            FROM intel_analyses
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            **dict(r),
            "regions": json.loads(r["regions"] or "[]"),
            "sectors": json.loads(r["sectors"] or "[]"),
        }
        for r in rows
    ]


@router.get("/history/{analysis_id}")
def intel_history_detail(analysis_id: int):
    """저장된 분석 상세 (result_md 포함)."""
    with _db() as con:
        row = con.execute(
            "SELECT * FROM intel_analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    d = dict(row)
    d["regions"] = json.loads(d.get("regions") or "[]")
    d["sectors"] = json.loads(d.get("sectors") or "[]")
    return d


@router.delete("/history/{analysis_id}")
def intel_history_delete(analysis_id: int):
    """저장된 분석 삭제."""
    with _db() as con:
        con.execute("DELETE FROM intel_analyses WHERE id = ?", (analysis_id,))
    return {"deleted": analysis_id}
