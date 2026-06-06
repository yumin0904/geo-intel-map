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
from services.confidence_scorer import (
    score_output,
    apply_data_void_penalty, validate_insight_completeness,
)
from services.hypothesis_extractor import extract_hypotheses
from services.hypothesis_verifier import verify_hypotheses

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intel", tags=["intel"])

_GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
_GEMINI_MODEL = "gemini-2.5-flash"
_GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:streamGenerateContent?alt=sse&key={{key}}"
)

# ── 요청 스키마 ───────────────────────────────────────────────────────────

class IntelQueryRequest(BaseModel):
    query: str
    # 프론트에서 섹터·지역을 직접 지정하면 parser 결과를 override
    sector_override: list[str] = []
    region_override: list[str] = []


# ── 모드별 Gemini 프롬프트 ────────────────────────────────────────────────

def _build_prompt(pq: ParsedQuery, context_text: str, synthesis_ctx: str) -> str:
    """모드에 따라 Gemini에게 전달할 시스템+유저 프롬프트를 구성한다.

    §19-A 6단계 구조, §19-B 인사이트 카드 형식, §19-B-2 3대 강점,
    §19-C 금지 패턴, §19-D 신뢰도 산출 기준 적용.
    """

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
        "4. 경쟁 이론을 반드시 2개 나열하고 **양 이론 간 수치 비교 종합 판정**을 제시하라. 단일 이론 수렴 금지.\n"
        "   ★ [경쟁설명] 섹션은 반드시 아래 형식을 **그대로** 사용할 것 (레이블 변경 금지):\n\n"
        "   이론A명 (학자):\n"
        "     예측: [이 이론이 현 상황에 대해 예측하는 방향·수치]\n"
        "     실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED] 태그]\n"
        "     판정: 우세/열세 — [예측 대비 실측 편차: 예측 X vs 실측 Y, 편차 Z]\n\n"
        "   이론B명 (학자):\n"
        "     예측: [이 이론이 예측하는 방향·수치]\n"
        "     실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED] 태그]\n"
        "     판정: 우세/열세 — [예측 대비 실측 편차]\n\n"
        "   ▶ 종합 판정: 이론A 우세/이론B 우세 — [이론A 예측 편차 vs 이론B 예측 편차 수치 비교 1줄]\n\n"
        "   ★ 구체적 예시 (반드시 이 형식 준수):\n"
        "   자원무기화 (Hirschman):\n"
        "     예측: 에너지 의존도 증가 시 정치적 양보 빈도 증가\n"
        "     실측: EU 러시아 가스 의존도 2021년 45% → 2024년 8% (EIA/FRED)\n"
        "     판정: 열세 — 예측 '의존도 증가→양보' vs 실측 '의존도 -37%p 급감' — 방향 불일치\n\n"
        "   자유주의 상호의존 (Keohane):\n"
        "     예측: 상호의존 증가 시 분쟁 억제 효과\n"
        "     실측: EU-러 무역 2022년 이후 70%+ 급감, 전쟁 지속\n"
        "     판정: 열세 — 제재 후 무역 단절에도 전쟁 지속 → 상호의존 억제력 과장\n\n"
        "   ▶ 종합 판정: 자원무기화 열세 (의존도 역전) / 자유주의 열세 (전쟁 미억제) — 양 이론 모두 약세, 구조적 지정학(Mearsheimer)이 더 설명적\n\n"
        "   ⚠️ '예측:', '실측:', '판정:', '▶ 종합 판정:' 레이블은 절대 생략 불가. 수사적 기각 금지.\n"
        "   ⚠️ [경쟁이론 엄밀성 강제] '실측:'에는 반드시 <context>의 **구체적 숫자**(연도·단위 포함)를 넣어라. "
        "숫자가 없으면 '실측: [UNVERIFIED] 정량값 부재'로 명시하라 — 정성 서술로 때우지 말 것.\n"
        "   '판정:'은 예측과 실측의 **수치 편차**를 적시하라 (예: '예측 +5% vs 실측 -37%p → 이론 A 열세'). "
        "편차 수치 없이 '한계가 있다 / 약화된다'로 끝내면 수사적 기각으로 간주한다.\n"
        "   '▶ 종합 판정:'은 두 이론의 편차를 직접 비교하여 어느 이론이 실측에 더 가까운지 수치로 결론지어라.\n\n"
        "5. 결과를 즉시 의도로 귀속하지 말라('강경 정권 온존 = 미국 실패' 형태 금지).\n"
        "6. [비자명성 강제 — 최우선] 인사이트는 통념(뉴스·교과서 수준의 예상 답)을 넘어서야 한다. 절차:\n"
        "   (a) 먼저 이 주제의 **통념**을 한 문장으로 명시하라.\n"
        "   (b) 당신의 결론이 그 통념을 어떻게 **반박·정교화·한정**하는지 보여라. 통념과 결론이 같으면 그것은 인사이트가 아니다.\n"
        "   비자명성의 원천 중 최소 하나를 활용하라:\n"
        "   ① 반직관 — 통념과 반대 방향의 메커니즘 (예: '제재가 오히려 의존도를 낮춰 무기화를 약화')\n"
        "   ② 교차도메인 — 보통 연결되지 않는 두 도메인의 인과 경로 (예: 사이버→에너지 전이)\n"
        "   ③ 범위조건 — 이 패턴이 성립/붕괴하는 경계 식별 ('언제·어디서 깨지는가')\n"
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
        "   · 인과 단정 헤드라인은 [주장] 등급이 '인과'(Granger 유의+교란통제+이론 3조건)일 때만 허용된다.\n\n"

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
[관찰]       측정 가능한 현상 (수치·날짜·사례 포함, 없으면 [UNVERIFIED])
[주장]       (등급: 기술적/상관/선행성/인과) 방향·강도·조건. 등급에 맞는 동사만 — 상관 이하는 '유발' 금지
[가설]       H1: "X가 증가할 때 Y가 통계적으로 유의하게 변화한다 (통제변수 Z)"
[근거]       데이터 소스명 + 수치 (없으면 [UNVERIFIED])
[한계]       이 분석이 답하지 못하는 것 + 소수/한쪽 사례 의존 시 선택·생존편향 명시
[경쟁설명]   대안 이론 A (이론명): 설명
             예측: [이 이론이 현 상황에 대해 예측하는 방향·수치]
             실측: [<context>의 구체적 숫자 — 연도·단위 포함. 없으면 [UNVERIFIED] 정량값 부재]
             판정: 우세/열세 — 예측 X vs 실측 Y, 편차 Z
             대안 이론 B (이론명): 설명
             예측: [이 이론의 예측]
             실측: [구체적 숫자 또는 [UNVERIFIED] 정량값 부재]
             판정: 우세/열세 — 예측 X vs 실측 Y, 편차 Z
             ▶ 종합 판정: 이론A/이론B 우세 — [A 편차 vs B 편차 직접 비교, 우세 이론 결론 1줄]
[검증포인트] 다음 세션에서 확인할 지표·소스
[문헌공백]   기존 연구가 이 패턴을 못 다루는 **구조적 이유** + 이 분석의 기여 (막연한 '추가 연구 필요' 금지 — 구체적 공백 명시)
```

⚠️ **[문헌공백] 섹션은 절대 생략 불가.** 기존 문헌이 이 패턴을 다루지 못하는 구조적 이유를 반드시 작성하라.
⚠️ **[통념]과 [비자명기여]는 반드시 서로 달라야 한다.** 둘이 같은 내용이면 비자명성 0점 — 통념을 반박·정교화·한정하는 구체적 메커니즘을 [비자명기여]에 써라.
"""

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

⚠️ <context>에 있는 수치는 [UNVERIFIED] 없이 인용하라. [UNVERIFIED]는 context 외부 사실에만 사용.

§19-A 6단계 구조로 분석하라:

### [단계 1] 관찰
주장과 관련된 측정 가능한 현상을 수치와 함께 서술하라. 수치 없으면 [UNVERIFIED].

### [단계 2] 변수 식별
- 독립변수(원인 후보):
- 종속변수(결과):
- 통제변수(제거해야 할 혼재 요인):

### [단계 3] 가설 공식화
- H1 (주장 지지): [반증 가능 형태 — "X가 증가할 때 Y가 유의하게 변화한다"]
  ※ X, Y는 정량 지표(건수·가격·비율·지수)여야 한다. 정량화 불가 시 이 줄 생략하고 [검증포인트]에 서술.
- H0 (귀무 가설): [H1이 틀렸을 때 관찰될 패턴]

### [단계 4] 경쟁 이론
이 현상을 다르게 설명하는 이론 2개를 나열하고 **양 이론 간 수치 비교 종합 판정**을 제시하라.
각 이론은 반드시 아래 형식을 **그대로** 사용하라 (레이블 변경 금지 — insight 모드와 동일):

이론A명 (학자):
  예측: [이 이론이 현 상황에 대해 예측하는 방향·수치]
  실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED]]
  판정: 우세/열세 — [예측 X vs 실측 Y, 편차 Z]
이론B명 (학자):
  예측: [이 이론이 예측하는 방향·수치]
  실측: [<context> 데이터의 실제 수치 — 없으면 [UNVERIFIED]]
  판정: 우세/열세 — [예측 X vs 실측 Y, 편차 Z]
▶ 종합 판정: 이론A/이론B 우세 — [A 편차 vs B 편차 직접 비교, 우세 이론 결론 1줄]

⚠️ '예측:', '실측:', '판정:', '▶ 종합 판정:' 레이블 생략 불가. '실측:'은 <context>의 구체적 숫자(없으면 [UNVERIFIED] 정량값 부재),
'판정:'은 예측 대비 실측의 수치 편차로 우열을 적시하라. '▶ 종합 판정:'은 두 이론 편차를 직접 비교해 우세 이론을 수치로 결론지어라. 정성 서술로 끝내면 수사적 기각으로 간주한다.

### [단계 5] 근거 평가
컨텍스트 데이터에서:
- 지지 증거 (소스 + 수치):
- 반증 증거 (소스 + 수치):
- 미검증 항목: [UNVERIFIED] 명시

### [단계 6] 연쇄 고리 강도 자기평가
각 인과 연결고리를 HIGH / MEDIUM / LOW로 평가하고,
MEDIUM 이하가 포함되면 전체 결론에 [SPECULATIVE] 레이블을 붙일 것.

### 최종 판정
- **결론**: 지지 / 반증 / 불확실
- **레이블**: [SPECULATIVE] / [PROVISIONAL] / 없음"""

    else:  # insight
        task = f"""## 요청
다음 질문에 대해 교차 분석 기반 인사이트를 제공하세요: "{pq.raw_query}"

{_card_fmt}

인사이트 카드를 **2개** 작성하라. (깊이 > 넓이 — 카드 수보다 각 카드의 완결성 우선)
각 카드의 [가설] 섹션에 H1은 최대 1개. 측정 불가능하면 '[가설] 정량 가설 없음'으로 표기.
⚠️ "A → B를 시사한다" / "가능성이 높다" 로만 끝내는 것 금지. 연쇄 고리 강도까지 반드시 평가할 것.
⚠️ 각 카드의 [문헌공백] 섹션은 절대 생략 불가 — 카드를 마무리하기 전 반드시 작성하라.
⚠️ <context>에 있는 수치는 [UNVERIFIED] 없이 인용하라. [UNVERIFIED]는 context 외부 사실에만 사용.

### 도메인 교차 경로 (§19-B-2 ②)
복수 도메인이 관여된 경우, 아래 형식으로 도메인 간 인과 경로를 명시하라:
[도메인A → 도메인B] 경로 설명 + 전이 조건"""

    return f"""{system_role}

<context>
{context_text}

{synthesis_ctx}
</context>

{task}"""


# ── Gemini SSE 스트리밍 ───────────────────────────────────────────────────

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_gemini(
    prompt: str,
    thinking: bool,
    source_counts: dict | None = None,
    default_regions: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """Gemini 2.5 Flash SSE 스트리밍. thinking=True 시 thinkingBudget 8192.

    default_regions: H1에 지역명이 없을 때 상속할 쿼리 지역 (Granger 변수
        매핑 오류 방지 — 예: korean_peninsula 쿼리가 middle_east→ITA로 검정되는 버그).
    """

    if not _GEMINI_KEY:
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

    async def _do_stream(request_body: dict) -> AsyncGenerator[str, None]:
        full_text = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, json=request_body) as resp:
                    if resp.status_code == 503 and thinking:
                        # thinking 모드 503 → fast 모드로 자동 fallback
                        logger.warning("[intel] Gemini 503 — thinking 비활성화 후 재시도")
                        yield _sse({"text": "", "done": False, "fallback": True,
                                    "note": "thinking 모드 일시 불가 → 일반 모드로 전환"})
                        fallback_body = {k: v for k, v in request_body.items()}
                        fallback_body["generationConfig"] = {
                            k: v for k, v in request_body["generationConfig"].items()
                            if k != "thinkingConfig"
                        }
                        async for chunk in _do_stream(fallback_body):
                            yield chunk
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
                specs = await verify_hypotheses(specs)
                # 사다리 최고 등급을 인사이트 대표 추론 등급으로 (인과 단정 아님)
                _LADDER_ORDER = {"기술적": 0, "상관": 1, "선행성": 2}
                best_spec = max(
                    specs, key=lambda s: _LADDER_ORDER.get(s.inference_grade, 0)
                )
                score_result["inference_grade"]  = best_spec.inference_grade
                score_result["inference_caveat"] = best_spec.inference_caveat
                # hypothesis 이벤트 전송
                yield _sse({
                    "type": "hypothesis",
                    "done": False,
                    "hypotheses": [
                        {
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
                            "verification_status": s.verification_status,
                            # 학술 재설계: 인과추론 사다리 필드
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
                        }
                        for s in specs
                    ],
                })

            yield _sse({"type": "score", "done": False, **score_result})

        yield _sse({"done": True})

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
            prompt, pq.thinking, source_counts, default_regions=pq.regions
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
