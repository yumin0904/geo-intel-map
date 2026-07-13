"""
services/methods/base.py  (9-0)

공통 스키마 — 방법 무관 결과 계약.

사다리 칸은 "식별전략 강도"로 방법에 무관한 공통 축이다.
각 어댑터(Granger·EventStudy·PanelReg·...)가 이 스키마를 구현하면
grader는 방법 종류와 무관하게 최강 유효 칸을 선택한다.

DataSignature: 데이터 모양으로 적합 방법을 사전 선언 (결과 보기 전 결정).
  순차 fallback("안 되면 다른 걸 돌려보자") 금지 — method-level p-해킹 차단.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── 인과추론 사다리 ────────────────────────────────────────────────────────────
# 칸은 식별전략 강도 순서. 삼각측량 수렴은 신뢰도만 올리고 칸은 승격 안 함.
RUNG_DESCRIPTIVE   = "기술적"    # 검정 불가/미실행
RUNG_CORRELATIONAL = "상관"      # 통계 유의하나 교란 미통제
RUNG_PRECEDENCE    = "선행성"    # Granger 예측 선행 (교란 완화)
RUNG_QUASI_EXP     = "준실험"    # 이벤트스터디·합성통제·패널FE 등

RUNG_ORDER: dict[str, int] = {
    RUNG_DESCRIPTIVE: 0,
    RUNG_CORRELATIONAL: 1,
    RUNG_PRECEDENCE: 2,
    RUNG_QUASI_EXP: 3,
}

# ── 데이터 시그니처 ────────────────────────────────────────────────────────────
# 쿼리 직후 데이터 모양으로 결정 — 결과 보기 전에 방법집합을 고정.
DataSignature = Literal[
    "UNQUANTIFIABLE",    # 비선형·체제 변수 → 과정추적 스캐폴딩 (9-Q 우선순위 3)
    "SINGLE_SHOCK",      # 특정 날짜·명명 사건 → 9-A 이벤트스터디
    "CROSS_SECTION",     # 국가간 비교·시간축 없음 → 9-B 횡단/패널회귀
    "NONLINEAR",         # 임계·체제 변수(정량화 가능) → 9-C 비선형
    "NETWORK_DIFFUSION", # 전이·확산 프레임 → 9-D 네트워크/공간
    "COUNTERFACTUAL",    # 단일 단위 반사실 → 9-E 합성통제
    "PAIRED_TIMESERIES", # 짝지은 정상 시계열 → Granger (기본)
]

# 시그니처별 적용 가능 방법 집합 (사전 선언, 순서 = 주 방법 우선)
SIGNATURE_METHOD_MAP: dict[str, list[str]] = {
    "UNQUANTIFIABLE":    ["process_tracing"],  # [9-Q 우선순위 3] 거절→과정추적 스캐폴딩
    "SINGLE_SHOCK":      ["event_study", "granger"],      # 삼각측량: 국소·전역
    "CROSS_SECTION":     ["panel_regression", "granger"], # 삼각측량: 단위간·lead-lag
    "NONLINEAR":         ["nonlinear_test"],               # 9-C (데이터 누적 후)
    "NETWORK_DIFFUSION": ["network_model"],                # 9-D
    "COUNTERFACTUAL":    ["synthetic_control"],            # 9-E
    "PAIRED_TIMESERIES": ["granger"],
}


@dataclass
class MethodResult:
    """
    방법 무관 공통 결과 스키마 (9-0).

    각 어댑터가 이 스키마를 채우면 grader가 방법 종류와 무관하게 처리한다.
    assumptions_met=False인 결과는 등급 자격 박탈 (method-type laundering 차단).
    """
    method: str                          # "granger" | "event_study" | "panel_regression" | ...
    signature: str                       # 어떤 시그니처에서 선택됐는지

    # 핵심 추정치
    effect_estimate: float | None = None # 방법 핵심 추정치 (CAAR·coef·gap·Granger-F)
    effect_size_label: str = ""          # [②] 실질 유의성 — "무시/작음/중간/큼"
    significance: float | None = None   # 유의 지표 (p값·placebo-p·t통계량)

    # 불확실성 구간 [③]
    ci_low: float | None = None
    ci_high: float | None = None

    # 사다리 등급
    reachable_rung: str = RUNG_DESCRIPTIVE  # 가정 충족 시 도달 가능 칸
    actual_rung: str = RUNG_DESCRIPTIVE     # 실제 달성 칸 (assumptions_met 게이트 후)

    # 정직성 핵심 — 가정 자가검증
    assumptions_met: bool = False
    assumption_caveat: str = ""

    # 내부 강건성 [④]
    robustness: dict = field(default_factory=dict)  # 윈도우·이상치·대체프록시 민감도

    # 신뢰도 (칸 안에서의 강도)
    confidence_within_rung: int = 0      # 0~100

    # 원본 결과 보존 (거짓동등 방지 — 칸으로 뭉개지 않음)
    native_stats: dict = field(default_factory=dict)

    # 탐색형 플래그 (8-F 가드)
    # [세탁 버그 수리 2026-07-13] 기본값 False → True. 구판은 fail-open이었다 —
    # 깜빡하면 확증형(캡 면제)이 됐고, event_study·panel_regression이 실제로
    # exploratory=False를 하드코딩하고 있었다. 캡의 진실원은 spec.exploratory라
    # 라이브 피해는 없었으나(grader가 이 필드를 안 읽는다) 지뢰였다.
    # 확증 자격은 spec.preregistered로만 얻는다 — 방법 어댑터가 부여할 수 없다.
    exploratory: bool = True


@dataclass
class TriangulationResult:
    """
    삼각측량 종합 결과 — 방법집합 전체 실행 후 grader가 반환.

    수렴(convergence): 다른 식별가정 방법들이 같은 결론 → 강건성↑
    발산(divergence): 엇갈리면 발산 자체가 발견 (해석 필요)
    """
    headline_rung: str                   # 집합 내 가장 강한 유효 칸
    headline_method: str                 # 헤드라인 칸을 결정한 방법
    convergence: bool | None = None      # True=수렴, False=발산, None=단일방법
    convergence_note: str = ""
    all_results: list[MethodResult] = field(default_factory=list)
    fdr_applied: bool = False
