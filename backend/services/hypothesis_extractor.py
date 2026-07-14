"""
services/hypothesis_extractor.py

Gemini 출력 마크다운에서 [가설] 섹션을 파싱해 HypothesisSpec 목록을 반환한다.
Token-Zero 원칙: LLM 없이 정규식+키워드 매핑만 사용.

변수 매핑 전략:
  independent_var (지역/행위자 기반) → region_code → event_archive 시계열
  dependent_var   (지표 키워드 기반) → ticker       → market/indicator 시계열
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

_MEASURABLE_YAML = Path(__file__).resolve().parents[1] / "config" / "measurable_variables.yaml"

# ── 데이터 모델 ───────────────────────────────────────────────────────────────

VerificationStatus = Literal[
    "PENDING",       # 아직 안 쟀다 (검정 미수행)
    "PARTIAL",       # 경향성 (p<0.15)
    "VERIFIED",      # 선행성 유의 (p<0.05)
    "REJECTED",      # ★ 쟀고, **잴 검정력이 있었고**, 관계 없었다 — 정직한 귀무는 발견이다
    "UNDERPOWERED",  # ★ 못 쟀다 — 표본 부족(D4) 또는 검정력 미달. **수리 가능**
    "INVALID_PROXY", # ★ 질문이 틀렸다 (D3) — IV가 그 권역에서 분산 0. 데이터를 더 모아도 소용없다
]
# ⚠️ REJECTED·UNDERPOWERED·INVALID_PROXY는 2026-07-14 신설(B02+B25).
# 구 코드는 셋을 전부 `PENDING(미검증)`으로 뭉갰다:
#     if 선행성: VERIFIED / elif 상관: PARTIAL / else: PENDING   ← else가 셋을 삼켰다
# 그래서 **p=0.8로 명확히 기각된 가설**과 **데이터가 없어 못 잰 가설**이 원장에서
# 구별되지 않았다. "미검증"이라는 말이 정직한 기각을 '아직 안 해봤다'로 위장하고,
# 못 잰 것을 '관계 없다'로 바꿔치기한다 — **후자가 B01의 정의였다.**
#
# 셋을 가르는 근거(D2위원회 8-F 진단 3분할 — 뭉개면 고칠 수 있는 것이 못 고치는 것으로
# 위장한다):
#   D1_NO_RELATION  + 검정력 충분 → REJECTED       (쟀고 관계 없었다)
#   D1_NO_RELATION  + 검정력 미달 → UNDERPOWERED   (못 잴 설계였다)
#   D4_INSUFFICIENT               → UNDERPOWERED   (표본이 없었다 — 더 모으면 된다)
#   D3_BAD_PROXY                  → INVALID_PROXY  (변수가 틀렸다 — 더 모아도 소용없다)
# 처방이 정반대이므로 이름도 달라야 한다. 상세 사유는 `diagnosis` 필드가 계속 보존한다.
VariableType = Literal["Type_A", "Type_B", "Type_C"]


@dataclass
class HypothesisSpec:
    h1: str                              # 반증 가능 형태 H1 텍스트
    h0: str                              # 귀무가설 (자동 생성)
    independent_var: str                 # 원문 독립변수 기술
    dependent_var: str                   # 원문 종속변수 기술
    control_vars: list[str] = field(default_factory=list)
    region_code: str | None = None       # event_archive 조회용 (독립변수 지역 X)
    dependent_region: str | None = None  # [B4] 사건→사건: 종속 지역 Y (event_archive)
    ticker: str | None = None            # 시장/지표 시계열 조회용
    var_type: VariableType = "Type_A"    # 변수 유형 3분류 (P1)
    proxy_suggestions: list[str] = field(default_factory=list)  # Type_C 대리변수 제안
    verification_status: VerificationStatus = "PENDING"
    granger_p: float | None = None
    f_statistic: float | None = None   # Granger F-통계량 (§22-A H1 스키마)
    best_lag: int | None = None
    n_obs: int = 0
    error: str | None = None
    # ── 학술 정합성 재설계 (인과추론 사다리) ──────────────────────────────
    inference_grade: str = "기술적"      # 기술적 → 상관 → 선행성 → 준실험 → 실험
    inference_caveat: str = ""           # Granger 한계·교란 미통제 등 정직한 단서
    # [Granger 대리변수 치환 게이트 위원회 2026-07-11] PARTIAL 판정 근거 3진입구 —
    # verification_status="PARTIAL"의 어의(정의) 자체는 불변, 이 필드는 "왜 PARTIAL인지"만
    # 부가 정보로 얹는다. TREND_P15(p<0.15 경향) / FDR_FAILED(다중검정 강등) /
    # EXTREME_ONLY(P90 극단 전용 승격) 세 값 중 하나, 해당 없으면 None.
    partial_basis: str | None = None
    theory_grounded: bool = False        # 종속변수 쌍에 문헌상 인과 메커니즘 존재 여부
    granger_q: float | None = None       # 다중검정 FDR 보정 q값 (Benjamini-Hochberg)
    differenced: bool = False            # 정상성 보정(1차 차분) 적용 여부
    controlled: bool = False             # B3 통제변수(VIX) 조건부 Granger 적용 여부
    achieved_power: float | None = None  # 달성 검정력 (B25) — UNDERPOWERED 판정 근거. None=미계산
    control_name: str | None = None      # 사용된 통제변수명
    # ── [B8] P90 극단 이벤트 보조 검정 ──────────────────────────────────────
    extreme_granger_p: float | None = None   # P90 극단 시리즈 Granger p값 (보조)
    extreme_granger_f: float | None = None   # P90 극단 시리즈 F-통계량 (보조)
    # ── [8-gate] 선형검정 적합성 게이트 (비선형 체제 변수 제외) ──────────────
    # False면 선형 Granger 트랙 진입 금지 → 구조적 논증으로 분류 (verifier에서 단락).
    # 체제·임계 변수를 선형검정에 강제 투입하던 범주오류 + null→비선형 승격 방지.
    linear_testable: bool = True             # 선형 Granger 적합 여부
    testability_reason: str = ""             # 부적합 사유 (감사용 — 출력 노출)
    # ── [9-P-2] D3·등급 분리 — theory_grounded는 등급 판정 전용 ──────────────
    # theory_grounded=False가 D3(대리변수 오류)와 등급(상관 상한)을 동시에 결정하던
    # 단일실패점 해소. is_proxy_pair는 D3 진단 전용 (8-F negative_result_triage에서 사용).
    # theory_grounded: 이론 문헌상 인과 메커니즘 화이트리스트 일치 여부 (등급 판정 유지)
    # is_proxy_pair:   화이트리스트 밖 대리변수 쌍 사용 여부 (D3 진단 전용, 등급과 무관)
    is_proxy_pair: bool = False              # D3 진단 전용 — 대리쌍 오류 가능성 마커
    # ── [Granger 대리변수 치환 게이트 위원회 2026-07-11] ──────────────────────
    # 라우터가 표면 DV(원 가설의 종속변수)를 region/sector 기본 지표로 치환했는가 —
    # 쌍의 이론성(theory_grounded)과 직교. 화이트리스트 안 쌍이어도 표면 DV가 다른
    # 것이면 치환이다(실측: hormuz→CL=F는 화이트리스트 안이라 is_proxy_pair=False였지만
    # 실제 표면 DV는 "베르베라 항 물류 비중(TEU)"이었음 — 대리 자체는 있었으나
    # is_proxy_pair 축엔 잡히지 않음). is_proxy_pair는 정상 Type_A 경로에서 미계산·
    # 발화율 0%로 기능 정지돼 있었다(위원회 실측) — 이 필드가 그 공백을 메운다.
    is_substituted_target: bool = False
    # ── [9-P-3] 라우팅 판정 근거 — "성공해도 틀린 방법" 사후 점검 기반 ──────
    # 9-0 Method Router 착수 전 현재 분기 구조의 판정 근거를 남겨둔다.
    # routing_method: 실제 선택된 분석 경로 ID
    # routing_confidence: 방법 적합성 신뢰도 (HIGH/MEDIUM/LOW)
    # routing_alternatives: 데이터 시그니처상 적용 가능한 대안 방법 (9-0 라우터 힌트)
    routing_method: str = ""                 # 선택 방법 ID (감사용)
    routing_confidence: str = ""            # HIGH / MEDIUM / LOW
    routing_alternatives: list[str] = field(default_factory=list)  # 대안 방법 힌트
    # ── [9-0] Method Router — 데이터 시그니처 + MethodResult ────────────────
    # source_query: 원본 사용자 쿼리 — H1/H0에 없는 시그니처 키워드 보완용
    # data_signature: router가 채우는 데이터 모양 분류
    # method_result:  granger_adapter 등이 채우는 공통 스키마 결과 (JSON 직렬화용 dict)
    source_query: str = ""              # 원본 쿼리 (intel_query에서 주입)
    data_signature: str = ""             # DataSignature 값 (router 결정)
    method_result: dict = field(default_factory=dict)  # MethodResult 직렬화
    # ── [9-P-4] 출력 2계층화 — 표면(비전공자 판독) / 펼침(전체 진단) ──────────
    # surface_summary: 한 줄 결론 — 라우팅 방법·검정 결과를 자연어로 요약
    # confidence_word: 신뢰 한 단어 — "높음"/"보통"/"낮음"/"검정불가"
    surface_summary: str = ""               # 표면 — 한 줄 결론
    confidence_word: str = ""              # 표면 — 신뢰 한 단어
    # ── [9-Q 우선순위 2] 인식론 모드 — HARKing(데이터→가설) 방어 ──────────────
    # exploratory=True: 데이터를 본 뒤 가설을 생성(탐색) → 같은 데이터 검정은 순환.
    #   헤드라인 등급을 '상관'에서 상한 + [탐색적] 라벨. 원본 추정치는 보존(칸만 강등).
    # exploratory=False: 사용자가 데이터 보기 **전** 가설을 직접 선언(확증) → 캡 없음.
    #
    # ⚠️ **기본값 True (fail-safe). 2026-07-13 세탁 버그 수리로 뒤집었다.**
    #
    # 구판 기본값은 False(=확증)였고 주석은 "직접 호출(테스트)은 기존 동작 유지"라고
    # 적혀 있었다. 즉 **깜빡하면 캡이 열리는** fail-open 기본값이었다. 그리고 실제로
    # 열렸다 — 예측 974건 중 157건이 "확증형"으로 기록됐는데 **진짜 사전등록은 0건**이고,
    # 157건 전부가 쿼리에 "검증"·"근거"·"확인" 같은 단어가 들어갔다는 이유만으로
    # 확증 판정을 받았다(entity_parser의 verify 키워드 → mode → exploratory=False).
    #
    # **이 클래스의 인스턴스는 `extract_hypotheses()`가 LLM 출력 마크다운에서 파싱한다.**
    # 그 마크다운은 데이터 컨텍스트를 보고 생성된 것이다 — **구성상 전부 HARKing이다.**
    # 따라서 추출기가 만든 spec은 예외 없이 exploratory=True여야 한다.
    #
    # exploratory=False가 정당한 유일한 경우: 사용자가 엔진을 돌리기 **전에** H1을 직접
    # 선언하고 그 spec을 주입하는 사전등록 경로. **그 경로는 아직 존재하지 않는다**
    # (9-Q 잔여 — 준실험 칸 도달의 유일한 전제).
    # 판례: geo-os/wiki/decisions/20260713-downstream-contamination-committee.md
    exploratory: bool = True

    # 사전등록 증거 — 사용자가 데이터 보기 전 선언한 가설임을 표시한다.
    # extract_hypotheses()는 이 값을 **절대 True로 만들지 않는다**(구성상 불가능).
    # 이 플래그 없이 exploratory=False인 spec은 세탁이다 — _apply_epistemic_cap이 막는다.
    preregistered: bool = False


# ── [P1] 변수 유형 3분류 ──────────────────────────────────────────────────────
# Type_A: 금융 ticker 직접 매핑 가능 (유가, 주가, 환율, 반도체 등)
# Type_B: ACLED 이벤트 집계로 측정 가능 (도발, 공격, 프록시 활동 빈도 등)
# Type_C: 직접 측정 불가 → proxy 변수 제안 (의지, 역량, 신뢰성 등)

_TYPE_C_KEYWORDS: list[str] = [
    "의지", "역량", "신뢰성", "결속", "비중", "가능성", "위험도",
    "영향력", "취약성", "안정성", "응집력", "피로도", "의존도",
]

_TYPE_B_KEYWORDS: list[str] = [
    "도발", "공격", "분쟁", "충돌", "프록시", "proxy", "사이버 공격 빈도",
    "이벤트 빈도", "군사 행동", "테러", "민병대", "교전", "활동 빈도",
    "incident", "빈도", "건수",
]

# Type C 대리변수 제안 맵
_TYPE_C_PROXY_MAP: list[tuple[str, list[str]]] = [
    ("대응 의지",   ["성명 강경도 (ACLED 이벤트 유형)", "군사훈련 빈도", "Kiel 지원 규모"]),
    ("프록시 비중", ["ACLED 해당 행위자 이벤트 건수", "CSIS 사이버 귀속 건수"]),
    ("억지 신뢰성", ["주한미군 배치 규모", "연합훈련 빈도", "무기 지원 금액"]),
    ("역량",        ["SIPRI 국방비 %GDP", "ACLED 이벤트 심각도 평균"]),
    ("취약성",      ["EIA 에너지 의존도", "ACLED 민간 피해 건수"]),
    ("신뢰성",      ["COW 동맹 준수 이력", "SIPRI 무기 이전 데이터"]),
]
_TYPE_C_DEFAULT_PROXY = ["ACLED 이벤트 건수", "SIPRI 국방비", "COW 동맹 데이터"]


# ── [8-A] 측정 가능 변수 카탈로그 (measurable_variables.yaml) ─────────────────

@lru_cache(maxsize=1)
def _load_measurable() -> dict:
    """measurable_variables.yaml 로드 (1회 캐시). 실패 시 빈 구조."""
    try:
        with open(_MEASURABLE_YAML, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {"market_indicators": [], "conflict_series": {}}


def build_measurable_menu() -> str:
    """
    [8-A] yaml → Gemini 프롬프트용 측정가능 변수 메뉴 텍스트 생성.
    intel_query._build_prompt가 H1 규칙에 주입해 종속변수 강제 선택에 사용.
    """
    data = _load_measurable()
    lines: list[str] = ["■ 시장·지표 (종속변수로 즉시 검정 가능):"]
    for v in data.get("market_indicators", []):
        aliases = ", ".join(v.get("aliases", [])[:4])
        lines.append(f"  - {v['name']} ({v.get('unit', '')}) — 키워드: {aliases}")
    cs = data.get("conflict_series", {})
    if cs:
        lines.append(
            "■ ACLED 지역 분쟁 건수 (독립변수 권장 / 종속이면 '다른 지역'을 명시해야 검정 가능):"
        )
        lines.append("  - " + ", ".join(cs.get("regions", [])))
    return "\n".join(lines)


def _classify_variable_type(dependent_var: str) -> tuple[VariableType, list[str]]:
    """
    종속변수 텍스트를 결정론적으로 Type_A / Type_B / Type_C로 분류한다.

    Returns:
        (var_type, proxy_suggestions)
        proxy_suggestions는 Type_C일 때만 비어있지 않음.
    """
    text = dependent_var.lower()

    # [8-A] 측정 가능 우선: 종속변수가 시장 지표 ticker로 매핑되면 Type_A.
    #   Type_C/B 키워드가 섞여 있어도(예: '유가 의존도'의 '유가') 검정 가능하므로 구제.
    #   _match_ticker 실패 시에만 기존 Type_C → Type_B → Type_A 순으로 판별
    #   (측정 불가 변수를 억지 Type_A로 만들지 않음 — 정직성 가드).
    if _match_ticker(text):
        return "Type_A", []

    # Type_C 우선 판별 (추상 변수는 ticker도 ACLED도 직접 매핑 불가)
    for kw in _TYPE_C_KEYWORDS:
        if kw in text:
            for trigger, suggestions in _TYPE_C_PROXY_MAP:
                if trigger in text:
                    return "Type_C", suggestions
            return "Type_C", _TYPE_C_DEFAULT_PROXY

    # Type_B: ACLED 이벤트 기반 측정 가능한 행동 변수
    for kw in _TYPE_B_KEYWORDS:
        if kw in text:
            return "Type_B", []

    # Type_A: 금융 ticker (기본값)
    return "Type_A", []


# ── [8-gate] 선형검정 적합성 — 비선형 체제 변수 탐지 ──────────────────────────
# 체제·임계 변수는 임계점·체제전환(regime shift)으로 작동하므로 선형 Granger가
# 구조적으로 부적합하다(선형검정 실패 = 거짓 음성). 선형 트랙에 넣지 않고
# '구조적 논증'으로 분류한다. 보수적 셋으로 시작 — 명백한 체제/임계 어휘만 등록해
# 오탐(시장·공급망 '구조' 같은 단조 변수 오제외)을 피한다. (미탐 > 오탐 우선)
_NONLINEAR_REGIME_KEYWORDS: list[str] = [
    "체제", "정당성", "응집", "내구성", "결의",
    "임계", "체제전환", "정권 붕괴", "정권 생존", "지속 의지", "전쟁 지속",
    "regime", "legitimacy", "cohesion", "resilience", "threshold",
]


def _classify_linear_testability(
    independent_var: str, dependent_var: str
) -> tuple[bool, str]:
    """
    [8-gate] 독립·종속변수가 비선형 체제 변수인지 판정한다.

    독립·종속 중 **하나라도** 체제/임계 어휘에 걸리면 선형검정 부적합으로 본다.
    var_type(측정가능성)과 독립적인 축 — 측정 가능해도 비선형이면 선형검정 제외.

    Returns:
        (linear_testable, reason)  — 부적합이면 (False, 사유), 적합이면 (True, "")
    """
    combined = f"{independent_var} {dependent_var}".lower()
    for kw in _NONLINEAR_REGIME_KEYWORDS:
        if kw.lower() in combined:
            return False, (
                f"비선형 체제·임계 변수('{kw}') 포함 — 임계점·체제전환 구조라 "
                f"선형 Granger 부적합"
            )
    return True, ""


# ── region 키워드 매핑 ────────────────────────────────────────────────────────
# independent_var 텍스트에서 지역/행위자를 식별해 event_archive region_code로 변환

# 각 지역의 region_code 리터럴("bab_el_mandeb" 등)도 키워드에 포함한다 —
# H1/쿼리에 코드가 언더스코어 그대로 박히는 실측 형태가 있는데, 공백 기반
# 키워드("bab el"·"middle east")는 언더스코어 리터럴과 부분문자열 매치가 안 돼
# dependent_region이 비고 B4 사건→사건 경로가 차단됐다 (위원회 실측 2026-07-09:
# hormuz_redsea_contagion·middle_east_hormuz_contagion 2건이 이 버그로 pending_typeB 낙하).
# 〔권역위 2026-07-14 수리 — 사용자 승인〕 이 표는 **가설층의 어휘**이고, 적재층(`services/region.py`
# ::region_for_event → config/regions.yaml)이 **저장층의 어휘**다. 둘이 갈라져 있었다:
#
#   ① `eastern_europe` → event_archive에 **0행**. 실재 코드는 `ukraine`(88,431행).
#      correlation.py가 사설 `_REGION_ALIAS`로 몰래 보정하고 있었다 — 그래서 예측 160건이 우연히 살았다.
#      다른 소비자는 그 다리가 없어 빈손으로 돌아갔다. 원천을 고치고 파생 패치를 지운다(geo-os 1-A).
#   ② "북한"·"dprk" → `korean_peninsula`. 그런데 그 권역에 **북한 이벤트는 0건**이다(98.8% South Korea).
#      적재층은 계약대로 북한을 `north_korea`에 넣는다(engine.py:66-67 · 판례 20260709-nk-region-bbox-contamination
#      — 구 bbox가 서울을 물어 남한 3,136건이 오염된 것을 고친 구조다). **적재는 옳았고 가설이 misroute됐다.**
#      실측 2026-07-14: 북한 언급 예측 72건 중 71건이 korean_peninsula로 라우팅 → 23건이 Granger 실행
#      → **폭력 이벤트 2건짜리 시계열에 대고**. 14건이 '상관' 등급을 받았다.
#      ⚠️ "조선"은 제거 — 조선업(shipbuilding) 오탐이 실측됐다. "조선민주주의"로 좁힌다.
#   ③ "남중국해" → `taiwan_strait`. `south_china_sea`(681행)는 검정층이 도달할 수 없었다. 명백한 오배선.
#
# **first-match이므로 순서가 계약이다** — 더 좁은 권역이 넓은 권역보다 위에 와야 한다
# (north_korea > korean_peninsula · south_china_sea > taiwan_strait).
_REGION_MAP: list[tuple[list[str], str]] = [
    (["우크라이나", "ukraine", "러시아", "russia", "동유럽", "eastern europe", "eastern_europe"], "ukraine"),
    # north_korea는 korean_peninsula보다 **먼저** — "북한 도발"이 남한 시위 버킷으로 새는 것을 막는다
    (["북한", "dprk", "조선민주주의", "north korea", "north_korea", "김정은", "평양"], "north_korea"),
    (["한반도", "korean", "남한", "south korea", "korean_peninsula"], "korean_peninsula"),  # 남한: 골드셋 v2가 검출한 공백
    # south_china_sea는 taiwan_strait보다 **먼저** — 둘은 다른 권역이고 둘 다 실재한다
    (["남중국해", "south china", "스프래틀리", "spratly", "구단선", "south_china_sea"], "south_china_sea"),
    (["대만", "taiwan", "반도체", "tsmc", "taiwan_strait"], "taiwan_strait"),
    (["호르무즈", "hormuz", "이란", "iran", "걸프", "gulf", "페르시아"], "hormuz"),
    (["동중국해", "east china", "센카쿠", "senkaku", "일본", "japan", "자위대", "jsdf", "east_china_sea"], "east_china_sea"),
    (["홍해", "red sea", "바브엘만데브", "bab el", "예멘", "후티", "houthi", "bab_el_mandeb"], "bab_el_mandeb"),
    (["수에즈", "suez", "이집트", "egypt"], "suez"),
    (["중동", "middle east", "이스라엘", "israel", "팔레스타인", "middle_east"], "middle_east"),
    (["말라카", "malacca", "동남아", "southeast asia"], "malacca"),
    (["사헬", "sahel", "아프리카", "africa", "말리", "niger"], "sahel"),
]


def _assert_region_map_grounded() -> None:
    """G1 (권역위 2026-07-14) — 가설층 어휘가 저장층에 실재하는 코드만 쓰는지 import 시점에 검사.

    왜 import-time인가: 이 불일치는 **조용히** 빈 시계열이 되고, 빈 시계열은
    "관계 없음"으로 읽힌다. 런타임에 터지면 이미 예측이 발행된 뒤다.
    `eastern_europe`가 정확히 그렇게 살았다 — 0행짜리 코드로 예측 160건.
    """
    from services.region import _load_regions  # 순환 import 회피 — 함수 내부에서 로드

    defined = {k for k, v in _load_regions().items() if isinstance(v, dict)}
    used = {code for _, code in _REGION_MAP}
    orphans = used - defined
    if orphans:
        raise ImportError(
            f"_REGION_MAP이 regions.yaml에 없는 권역을 가리킵니다: {sorted(orphans)}. "
            f"검정층 어휘는 저장층(config/regions.yaml)에 종속됩니다 — "
            f"없는 코드로 조회하면 빈 시계열이 나오고, 그것이 '관계 없음'으로 위조됩니다. "
            f"regions.yaml에 등재하거나 _REGION_MAP에서 제거하십시오."
        )


_assert_region_map_grounded()

# ── ticker 키워드 매핑 ────────────────────────────────────────────────────────
# dependent_var 텍스트에서 지표를 식별해 correlation.py 호환 ticker로 변환

_TICKER_MAP: list[tuple[list[str], str, str]] = [
    # (키워드 목록, ticker, 설명)
    # AR-2: 구체 종속변수 우선 매칭 — 일반 'oil'보다 먼저 배치 (first-match)
    (["brent", "브렌트"], "BZ=F", "Brent 원유 선물"),
    (["kospi", "코스피"], "^KS11", "KOSPI 지수"),  # 골드셋 v2 A4 — 한국 중심 엔진의 기본 DV
    (["대만 달러", "대만달러", "타이완 달러", "twd", "usd/twd", "신타이완달러"], "TWD=X", "대만 달러 환율"),
    (["위안", "위안화", "cny", "rmb", "런민비", "인민폐"], "CNY=X", "위안/달러 환율"),
    (["엔화", "엔/달러", "jpy", "달러엔", "엔달러"], "JPY=X", "엔/달러 환율"),
    (["wti", "원유", "유가", "crude", "oil"], "CL=F", "WTI 원유 선물"),
    (["천연가스", "natural gas", "가스", "lng", "ng=f"], "NG=F", "천연가스 선물"),
    (["tsmc", "tsm", "반도체", "semiconductor", "파운드리"], "TSM", "TSMC 주가"),
    (["원달러", "usd/krw", "krw", "원화", "환율", "usd_krw", "달러원"], "KRW=X", "원/달러 환율"),
    (["밀", "wheat", "소맥", "곡물", "grain"], "ZW=F", "밀 선물"),
    (["금", "gold", "gld", "귀금속"], "GLD", "금 ETF"),
    (["방산", "defense", "무기", "ita", "군비"], "ITA", "방산 ETF"),
    (["soxx", "반도체etf", "semiconductor etf", "chips"], "SOXX", "반도체 ETF"),
    # VIX는 통제변수(교란) 전용 — 종속변수로 매핑하면 조건부 Granger가 퇴화하므로 제외
]

# ── 정규식 ────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# ── [채택③ 2026-07-08] 논평 분리 — 자기비평 섹션·메타판정 문장은 가설이 아니다 ──
# 실측(latest.json 65가설): 12건이 '### [동사 자기검열]' 섹션의 "- H1: ... → 판정" 재인용
# 불릿에서 유령 포집됨(그중 1건은 VERIFIED 등급까지 취득 = 등급 세탁). 실 H1은 [가설] 블록에
# 별도로 살아 있어 섹션 제거는 손실 0·오탐 0 (정상 53건 전부 비-자기검열 유래 실증).
_RE_SECTION_HEADER = re.compile(r'^#{1,6}\s')
_RE_BLOCK_BOUNDARY = re.compile(r'^(#{1,6}\s|\[[가-힣]+\s*\d*\]|---)')
# 심층방어 가드 — 화살표+메타판정 어휘 '동시' 존재만 기각 (단독 신호 금지:
# 실측에서 '**'·'수준' 단독 필터는 정상 H1을 오탐했다 — 위원회 오탐 0 조건).
_RE_META_COMMENTARY = re.compile(
    r'인과 동사|상관 수준|선행성 수준|표현으로|동사[는가]|사용 불가|정당함|자기검열'
    r'|상관적|인과적 표현|수준에 부합|표현.{0,4}적절|언어로')


def _strip_self_censor_sections(text: str) -> str:
    """'### [동사 자기검열]' 류 자기비평 섹션을 통째 제거 — H1 재인용 유령 포집 원천 차단."""
    out, skip = [], False
    for ln in text.split('\n'):
        if skip:
            if _RE_BLOCK_BOUNDARY.match(ln) and '자기검열' not in ln:
                skip = False
            else:
                continue
        if _RE_SECTION_HEADER.match(ln) and '자기검열' in ln:
            skip = True
            continue
        out.append(ln)
    return '\n'.join(out)


# H1 가설 추출 패턴 — insight/verify 모드 모두 지원
# 예1: [가설] H1: "X가 증가할 때..."             (insight 모드, 같은 줄)
# 예2: [가설]\nH1: "X가 증가할 때..."             (insight 모드, 다음 줄)
# 예3: [단계 3] ... **H1 (주장 지지)**: ...       (verify 모드)
# 예4: H1: "..."  (헤더 없이 단독)
# [9-P-1] \[가설\]\n 다음 줄에 H1: 이 오는 경우 H1: 접두사도 소비 (IV에 H1: " 잔류 방지)
_RE_H1 = re.compile(
    r'(?:'
    r'\[가설\]\s*(?:\n\s*)?(?:H1\s*[:：]\s*)?'  # [가설](다음줄) + 선택적 H1: 소비
    r'|\*\*H1[^*]*\*\*\s*[:：]\s*'
    r'|(?<!\w)H1\s*[:：]\s*'
    r')'
    r'[""""]?(.+?)[""""]?\s*$',
    re.MULTILINE | re.IGNORECASE,
)

# (통제변수: X, Y) 추출
_RE_CONTROL = re.compile(
    r'통제변수\s*[:：]\s*([^\n\)]+)',
    re.IGNORECASE,
)

# "X가 증가할 때 Y가" 구조에서 독립/종속변수 추출
# [9-P-1] 확장: 될/되면/될수록 어미 + 높아지·심화·격화 등 복합 어간 추가
_RE_WHEN_THEN = re.compile(
    r'(.+?)\s*(?:가|이)?\s*'
    r'(?:증가|상승|강화|확대|악화|발생|감소|하락|심화|격화|확산|축소|개선|증대|약화'
    r'|높아지|낮아지|강해지|약해지|커지|작아지|늘어나|줄어들)'
    r'(?:할\s*때|될\s*때|\s*시|하면|되면|할\s*수록|될\s*수록'
    r'|함에\s*따라|됨에\s*따라|\s*때)'
    r'\s*[,，]?\s*'
    r'(.+?)\s*(?:가|이)?\s*'
    r'(?:통계적|유의|증가|감소|상승|하락|변화|높아|낮아|커지|작아|늘어|줄어|나타)',
    re.IGNORECASE,
)

def _normalize_h1_surface(text: str) -> str:
    """H1 표면 잔재의 결정론 정규화 — 내용 무손실 (빈 괄호·고아 따옴표·공백만).

    [밤샘 사이클 1, 2026-07-12 새벽] E2 F2 관찰 결함의 원인 분해 실측:
    빈 괄호 '한다 ().'는 생성 결함이 아니라 _RE_CONTROL.sub("")가 괄호 속만 비우고
    껍데기를 남긴 파서 자해다 — 베이스라인 20/30가설, gemini 산출에도 존재(provider
    무관 확증), result_md 본문에는 0. 고아 따옴표 '한다 ()".'는 _RE_H1의 끝 따옴표
    스트립이 '따옴표 뒤 마침표' 순서를 못 다루는 사각지대. 속이 있는 괄호(hormuz)·
    부속절(단, …)은 건드리지 않는다.
    """
    text = re.sub(r"\s*\(\s*\)", "", text)
    # 문장 끝의 따옴표·마침표·공백 혼합 꼬리: 따옴표가 섞여 있을 때만 정규화
    tail = re.search(r'[\s."“”]+$', text)
    if tail and any(q in tail.group(0) for q in '"“”'):
        text = text[: tail.start()] + ("." if "." in tail.group(0) else "")
    text = re.sub(r"  +", " ", text).strip()
    return text


# 경계 마커 기반 폴백 — 정규식 실패 시 조건절 경계로 IV·DV 분리
# 질/을 때: 높아질 때, 작아질 때 (ㄹ 받침 복합 동사)
# [위원회 20260712 집행①] "을수록" 형태소 커버리지 공백 수리 — 실측석 원인 특정:
# 기존엔 "질/할/될+수록"만 등록돼, 받침 있는 형용사 어간(낮-, 많-, 적-)에 직접
# 붙는 "을수록"(낮을수록·많을수록·적을수록)이 NO MATCH였다("낮아질수록"만 우회 매치).
# 수록형 미식별 17건의 실원인 — 재현: "낮을수록"→매치, "낮아질수록"→기존에도 매치.
_RE_CONDITION_BOUNDARY = re.compile(
    r'(?:할\s*때|될\s*때|질\s*때|을\s*때'
    r'|할\s*수록|될\s*수록|질\s*수록|을\s*수록'
    r'|하면|되면|함에\s*따라|됨에\s*따라)'
    r'\s*[,，]?\s*',
    re.IGNORECASE,
)
# IV 끝에 붙는 조사+동사 어간 제거용 (경계 마커 폴백 전용)
# 경계 분리 후 before에 잔여 어간(높아, 강해 등)이 남을 수 있어 추가
# [집행①] "을수록" 분리 후 남는 받침형 형용사 어간(낮·많·적·높)도 제거 대상에 추가
_RE_IV_VERB_TAIL = re.compile(
    r'\s*(?:이|가)?\s*'
    r'(?:증가|상승|강화|확대|악화|발생|감소|하락|심화|격화|확산|축소|개선|증대|약화'
    r'|높아지|낮아지|강해지|약해지|커지|작아지|늘어나|줄어들'
    r'|높아|낮아|강해|약해|커|작아|늘어|줄어'
    r'|낮|많|적|높)'  # "을수록" 분리 후 잔여 받침형 형용사 어간 (낮을수록 등)
    r'(?:[하되][^,，때시면수록]*)?$',
    re.IGNORECASE,
)
# DV 서술어 시작 위치 탐지 (결과절에서 명사구 이후 부분)
_RE_DV_PRED = re.compile(
    r'\s*(?:이|가|은|는)\s*'
    r'(?:통계적으로\s*유의하게\s*|통계적\s*)?'
    r'(?:증가|감소|상승|하락|변화|높아|낮아|커지|작아|늘어|줄어|나타|확대|악화|강화|심화|상실|발생)',
    re.IGNORECASE,
)

# [위원회 20260712 집행②] 상관형 대칭 정규식 — "A가 B와 (통계적으로) 유의(미)하게
# 상관한다/상관관계" 형태. _RE_WHEN_THEN(인과 서술)·_RE_CONDITION_BOUNDARY(조건절
# 경계) 둘 다 실패한 뒤의 3차 폴백으로만 배선한다. 상관은 방향 없는 대칭 관계이므로
# 여기서 direction을 추정하지 않는다 — '상관/공변' 동사는 prediction_instrument의
# _UP_TOKENS/_DOWN_TOKENS에 미등록이라 기존 로직이 자연히 unclear로 남긴다.
# IV 그룹을 탐욕적(greedy)으로 둔 이유: "이벤트"처럼 어휘 내부에 조사와 동형인 음절
# ("이")이 섞여 있을 때 비탐욕(.+?)이 그 앞에서 조기 절단되는 오분리를 피하기 위함 —
# 탐욕 매칭은 역추적으로 "와/과" 직전의 *마지막* 조사를 찾아 실제 주어 경계에 수렴한다.
_RE_CORRELATION = re.compile(
    r'(.+)(?:가|이|는|은)\s*(.+?)\s*(?:와|과)\s*'
    r'통계적으로\s*(?:유의(?:하게|미하게|한|미한)?\s*)?'
    r'(?:상관|공변)(?:한다|관계(?:를\s*(?:가진다|보인다|나타낸다))?)',
    re.IGNORECASE,
)
# 어순 반대형 — "A와 B는 (통계적으로) 유의하게 상관한다" (A·B 순서만 뒤바뀐 동형 표현,
# 실측 89건 표본에 실존: "…증가와 …증가는 통계적으로 상관한다"). 대칭 관계라 어느 쪽을
# IV·DV로 잡아도 무방하므로 등장 순서(먼저 나온 쪽=IV)를 그대로 따른다.
# "유의(미)하게"는 실측 표본에 생략형("통계적으로 상관한다")도 존재해 선택으로 두되,
# "통계적으로"는 이 코퍼스 전역 프롬프트 규약(§19-B)상 상관 서술에 항상 동반되는
# 고정 어휘라 필수로 남겨 오탐(순수 서술문의 '상관' 단어 오포착)을 억제한다.
_RE_CORRELATION_REV = re.compile(
    r'(.+?)\s*(?:와|과)\s*(.+)(?:는|은|가|이)\s*'
    r'통계적으로\s*(?:유의(?:하게|미하게|한|미한)?\s*)?'
    r'(?:상관|공변)(?:한다|관계(?:를\s*(?:가진다|보인다|나타낸다))?)',
    re.IGNORECASE,
)

# [위원회 20260712 집행③] _RE_H1 캡처 후 기각 필터 — 3종 비가설 패턴.
# 전건 logger.info 로깅 의무(기존 494행 "[extract] 논평 폐기" 관행과 동일 — 실 H1을
# 포식하지 않는지 감사 가능해야 한다).
# ① 변수정의 불릿: "- X = 드론 공격 건수 (...)" — 가설 문장이 아니라 변수 나열
_RE_VAR_DEF_BULLET = re.compile(r'^-\s*\S{1,20}\s*=\s*')
# ② 트렁케이션 조각: 여는 괄호(반각/전각)로 끝나고 짝이 맞는 닫는 괄호가 없음 — 캡처가
# 문장 중간에서 잘렸다는 신호("…이벤트 건수 ("류, 실측 캡처 오염 사례)
_RE_TRUNCATED_TAIL = re.compile(r'[\(（][^\)）]*$')
# ③ 메타논평(표준형): 화살표 없이도 명백한 파서/생성 과정 자기서술 — "H1을 이렇게
# 처리했다"는 진술이지 가설 자체가 아니다 (": H1 작성 시도했으나…" 류)
_RE_META_STANDALONE = re.compile(
    r'재진술합니다|반증됨|전환됨\.?$|작성\s*시도했으나|H1\s*작성\s*시도'
)


def _ordered_regions(text: str) -> list[str]:
    """텍스트에 등장하는 region_code를 **등장 위치 순서대로** 반환한다 (중복 제거).

    사건→사건 방향(독립=먼저, 종속=나중) 판정에 필수.
    """
    text_lower = text.lower()
    hits: list[tuple[int, str]] = []
    for keywords, code in _REGION_MAP:
        positions = [text_lower.find(kw) for kw in keywords if kw in text_lower]
        if positions:
            hits.append((min(positions), code))
    hits.sort()
    ordered: list[str] = []
    for _, code in hits:
        if code not in ordered:
            ordered.append(code)
    return ordered


def _match_region(text: str) -> str | None:
    """텍스트에서 region_code를 추출한다 (등장 위치가 가장 빠른 지역)."""
    ordered = _ordered_regions(text)
    return ordered[0] if ordered else None


# [B4] 종속변수가 '다른 지역의 사건/분쟁'을 가리킬 때 쓰는 키워드
_EVENT_DEP_KEYWORDS: list[str] = [
    "분쟁", "사건", "충돌", "교전", "도발", "공격", "테러", "건수", "발생",
    "conflict", "incident", "clash", "attack", "event",
    # 자원배분·지원 연계 — "우크라이나 지원 규모" 등 사건→사건 경로 활성화
    "지원", "원조", "지원액", "군사지원", "지원량", "지원 규모",
    "aid", "support", "assistance", "transfer",
]


def _match_dependent_region(text: str, exclude: str | None) -> str | None:
    """
    [B4] 종속변수 텍스트에서 독립 지역과 **다른** 지역을 찾는다 (사건→사건).
    사건/분쟁 키워드가 있어야 하며(시장지표 종속과 구분), exclude 지역은 제외.
    등장 위치 순서로 첫 번째 다른 지역을 반환 (방향 정확성).
    """
    if not any(kw in text.lower() for kw in _EVENT_DEP_KEYWORDS):
        return None
    for code in _ordered_regions(text):
        if code != exclude:
            return code
    return None


def _match_ticker(text: str) -> tuple[str, str] | None:
    """텍스트에서 (ticker, 설명)을 결정론적으로 추출한다."""
    text_lower = text.lower()
    for keywords, ticker, desc in _TICKER_MAP:
        if any(kw in text_lower for kw in keywords):
            return ticker, desc
    return None


def _make_h0(h1: str) -> str:
    """H1 텍스트에서 귀무가설 H0를 자동 생성한다."""
    # "통계적으로 유의하게 변화한다" 이후 전체를 귀무가설 표현으로 대체
    h0 = re.sub(
        r'통계적으로\s*유의하게\s*(증가|감소|상승|하락|변화).*',
        '통계적으로 유의한 관계가 없다.',
        h1,
    )
    if h0 == h1:  # 패턴 미매칭 시 일반 형태
        h0 = "위의 독립변수와 종속변수 사이에 통계적으로 유의한 관계가 없다."
    return h0


def extract_hypotheses(
    text: str,
    default_regions: list[str] | None = None,
) -> list[HypothesisSpec]:
    """
    Gemini 출력 마크다운에서 HypothesisSpec 목록을 추출한다.
    인사이트 카드 2~3개에서 각각 [가설] 섹션을 파싱한다.

    default_regions: H1 텍스트 자체에 지역명이 없을 때 상속할 쿼리 지역.
        예) 쿼리가 'korean_peninsula'인데 H1이 '중국 광물 → 원/달러'처럼
        지역명을 직접 안 쓰면 region_code가 None이 되어, 검증기가 엉뚱한
        섹터 proxy(예: 사이버→ITA)와 middle_east 폴백으로 빠지는 버그 방지.
    """
    specs: list[HypothesisSpec] = []
    _default_region = default_regions[0] if default_regions else None

    # [채택③] 1차: 자기비평 섹션 구조 스트립 (노이즈 출처 정면 타격, 오탐 0 실증)
    text = _strip_self_censor_sections(text)

    for m in _RE_H1.finditer(text):
        h1_raw = m.group(1).strip()
        if not h1_raw or len(h1_raw) < 10:
            continue

        # [채택③] 2차 가드(심층방어): 섹션 밖으로 샌 논평 대비 — 복합 AND 신호만 기각.
        # 폐기는 반드시 로깅: 필터가 실 H1을 잡아먹지 않는지 감사 가능해야 한다.
        if '→' in h1_raw and _RE_META_COMMENTARY.search(h1_raw):
            logger.info("[extract] 논평 폐기(비가설): %s", h1_raw[:60])
            continue

        # [집행③-①] 변수정의 불릿 기각 — "- X = ..." 는 가설이 아니라 변수 나열
        if _RE_VAR_DEF_BULLET.match(h1_raw):
            logger.info("[extract] 변수정의 불릿 폐기(비가설): %s", h1_raw[:60])
            continue

        # [집행③-②] 트렁케이션 조각 기각 — 여는 괄호로 끝나 문장이 끊긴 캡처
        if _RE_TRUNCATED_TAIL.search(h1_raw):
            logger.info("[extract] 트렁케이션 조각 폐기(비가설): %s", h1_raw[:60])
            continue

        # [집행③-③] 메타논평(표준형) 기각 — 화살표 없이도 명백한 자기서술 패턴
        if _RE_META_STANDALONE.search(h1_raw):
            logger.info("[extract] 메타논평 폐기(비가설, 표준형): %s", h1_raw[:60])
            continue

        # 통제변수 추출 (H1 텍스트 내 또는 인근 줄)
        control_vars: list[str] = []
        ctrl_m = _RE_CONTROL.search(h1_raw)
        if ctrl_m:
            control_vars = [v.strip() for v in ctrl_m.group(1).split(",") if v.strip()]
            # 통제변수 괄호 제거한 순수 H1
            h1_clean = _RE_CONTROL.sub("", h1_raw)
        else:
            h1_clean = h1_raw
        # [밤샘 사이클 1] 표면 잔재 정규화 — 구 rstrip("()")은 문장 끝이 '.'라서
        # 무동작했고, 빈 괄호가 h1 필드에 그대로 남았다 (베이스라인 20/30가설)
        h1_clean = _normalize_h1_surface(h1_clean)

        # 독립/종속변수 추출 — 정규식 → 경계 마커 → 상관형 대칭 3단계 폴백 [9-P-1][집행②]
        wt_m = _RE_WHEN_THEN.search(h1_clean)
        if wt_m:
            independent_var = wt_m.group(1).strip()
            dependent_var = wt_m.group(2).strip()
        else:
            # 폴백①: 조건절 경계 마커(때/하면/되면/수록)로 IV·DV 분리
            boundary_m = _RE_CONDITION_BOUNDARY.search(h1_clean)
            if boundary_m:
                before = h1_clean[:boundary_m.start()].strip()
                after = h1_clean[boundary_m.end():].strip()
                # IV: before에서 동사 어간+어미 꼬리 제거
                iv_tail = _RE_IV_VERB_TAIL.search(before)
                independent_var = before[:iv_tail.start()].strip() if iv_tail else before
                # DV: after에서 서술어 이전 명사구
                dv_pred = _RE_DV_PRED.search(after)
                # [집행④] DV 추출 방어 폴백 — dv_pred가 after의 맨 앞(위치 0)에서
                # 매치하면 after[:0]="" 로 DV가 빈 문자열로 붕괴한다(after 전체가
                # 명사구 없이 서술어로 시작하는 문형에서 실측). after 전체(100자 컷)로
                # 대체하고 로깅 — DV 공백 유입 경로를 감사 가능하게 남긴다.
                if dv_pred and dv_pred.start() > 0:
                    dependent_var = after[:dv_pred.start()].strip()
                else:
                    dependent_var = after[:100].strip()
                    if dv_pred:
                        logger.info(
                            "[extract] DV 빈문자 방어 폴백(dv_pred pos=0): after=%r → dv=%r",
                            after[:60], dependent_var[:60],
                        )
            else:
                # 폴백②[집행②]: "A가 B와 (통계적으로) 유의하게 상관한다" 대칭형 —
                # 방향 없는 대칭 관계이므로 direction을 추정하지 않는다(기존 로직이
                # '상관' 계열 미등록 동사로 자연히 unclear 처리하도록 둔다).
                corr_m = _RE_CORRELATION.search(h1_clean)
                corr_rev_m = None if corr_m else _RE_CORRELATION_REV.search(h1_clean)
                if corr_m:
                    independent_var = corr_m.group(1).strip()
                    dependent_var = corr_m.group(2).strip()
                elif corr_rev_m:
                    independent_var = corr_rev_m.group(1).strip()
                    dependent_var = corr_rev_m.group(2).strip()
                else:
                    # 완전 파싱 실패 시 전체 H1을 독립변수로 유지
                    independent_var = h1_clean
                    dependent_var = ""

        # region/ticker 매핑 — 독립 지역은 독립변수 우선, 종속은 종속변수에서
        combined_text = f"{h1_clean} {independent_var} {dependent_var}"
        region_code = _match_region(independent_var) or _match_region(combined_text)
        # [버그수정] H1에 지역명이 없으면 쿼리 지역을 상속 — region=None일 때
        #   검증기가 섹터 proxy(사이버→ITA)+middle_east 폴백으로 빠지는 것 방지.
        #   예: korean_peninsula 쿼리의 '중국 광물→원/달러' H1 → KRW=X 정상 검정.
        if not region_code and _default_region:
            region_code = _default_region
        ticker_match = _match_ticker(combined_text)
        ticker = ticker_match[0] if ticker_match else None

        # [B4] 사건→사건 탐지: 종속변수가 다른 지역의 분쟁/사건을 가리키고
        #      시장 ticker로 매핑되지 않을 때 → dependent_region 설정
        dependent_region = None
        if region_code:
            dep_text = dependent_var or h1_clean
            dependent_region = _match_dependent_region(dep_text, exclude=region_code)
            # 종속이 사건→사건이면 시장 ticker는 무시 (둘 중 사건→사건 우선)
            if dependent_region:
                ticker = None

        # [P1] 변수 유형 3분류 — 종속변수 기준으로 판별
        var_type, proxy_suggestions = _classify_variable_type(dependent_var or h1_clean)

        # [8-gate] 선형검정 적합성 — IV/DV에 비선형 체제 변수가 있으면 선형검정 제외
        linear_testable, testability_reason = _classify_linear_testability(
            independent_var or h1_clean, dependent_var
        )

        spec = HypothesisSpec(
            h1=h1_clean,
            h0=_make_h0(h1_clean),
            independent_var=independent_var or h1_clean[:60],
            dependent_var=dependent_var or "미식별",
            control_vars=control_vars,
            region_code=region_code,
            dependent_region=dependent_region,
            ticker=ticker,
            var_type=var_type,
            proxy_suggestions=proxy_suggestions,
            linear_testable=linear_testable,
            testability_reason=testability_reason,
        )
        specs.append(spec)

    return specs
