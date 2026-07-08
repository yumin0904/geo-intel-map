"""
services/hypothesis_verifier.py

HypothesisSpec 목록을 받아 Granger 검정을 실행하고
verification_status (PENDING / PARTIAL / VERIFIED)를 결정한다.

기준:
  p < 0.05  → VERIFIED  (통계적 유의)
  p < 0.15  → PARTIAL   (경향성 있음)
  그 외     → PENDING   (미검증)

v6.3.0 추가:
  [P3] Type A ticker 매핑 실패 → region 있으면 Type C 대리변수 경로로 자동 강등
  [P2] Type C PROXY_DATA_MAP — ACLED 이벤트 시계열 + 지역 기본 ticker로 Granger 실행

데이터가 없거나 관측값 부족 시 PENDING 유지 + error 필드 기록.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from services.hypothesis_extractor import HypothesisSpec

# [9-P-2] 매직넘버 단일 진실 공급원 — config/granger_thresholds.yaml
_THRESHOLDS_PATH = Path(__file__).parent.parent / "config" / "granger_thresholds.yaml"
_THR: dict = yaml.safe_load(_THRESHOLDS_PATH.read_text(encoding="utf-8"))

_MIN_EVENT_OBS: int      = _THR["min_event_obs"]
_MIN_MARKET_OBS: int     = _THR["min_market_obs"]
_MIN_EVENT_EVENT_OBS: int = _THR["min_event_event_obs"]
_MIN_EXTREME_OBS: int    = _THR["min_extreme_obs"]
_P_VERIFIED: float       = _THR["p_verified"]
_P_PARTIAL: float        = _THR["p_partial"]
_P_EXTREME_VERIFIED: float = _THR["p_extreme_verified"]

logger = logging.getLogger(__name__)

# PERF-2: Granger 결과 TTL 캐시 (region·ticker·기간이 같으면 재계산 불필요)
_GrangerCache = dict[tuple, tuple[Any, float]]
_granger_spec_cache: _GrangerCache = {}
_GRANGER_SPEC_TTL = 3600   # 1시간

def _gcache_get(key: tuple) -> Any:
    entry = _granger_spec_cache.get(key)
    if entry is None:
        return None
    value, expire_at = entry
    if time.monotonic() > expire_at:
        del _granger_spec_cache[key]
        return None
    return value

def _gcache_set(key: tuple, value: Any) -> None:
    _granger_spec_cache[key] = (value, time.monotonic() + _GRANGER_SPEC_TTL)

# [P2] 지역 기본 ticker — Type C 및 Type A 실패 시 대리 종속변수로 사용
# 각 지역의 지정학적 충격이 가장 직접 전이되는 금융 지표
_REGION_DEFAULT_TICKER: dict[str, str] = {
    "eastern_europe":    "CL=F",   # 러-우: WTI 유가 (에너지 무기화)
    "taiwan_strait":     "TSM",    # 대만: TSMC 주가 (반도체 공급망)
    "hormuz":            "CL=F",   # 호르무즈: WTI 유가 (초크포인트)
    "korean_peninsula":  "KRW=X",  # 한반도: 원/달러 환율
    "east_china_sea":    "ITA",    # 동중국해(일본): 미 방산 ETF (이론근거 쌍·로컬 캐시)
    "bab_el_mandeb":     "CL=F",   # 바브엘만데브: WTI 유가
    "suez":              "CL=F",   # 수에즈: WTI 유가
    "middle_east":       "GLD",    # 중동: 금 (안전자산 도피)
    "malacca":           "CL=F",   # 말라카: WTI 유가
    "sahel":             "GLD",    # 사헬: 금 (지역 불안 프록시)
}

# [Cycle 6-B] 섹터 기본 ticker — 지역 미식별 시 섹터로 대리변수 선택
# 사이버·기술 섹터 H1은 지역 코드 없이 섹터만 식별되는 경우가 많음
_SECTOR_DEFAULT_TICKER: dict[str, str] = {
    "cyber":       "ITA",    # 사이버 공격 → 미 방산 ETF (APT 공격 → 방산투자 반응)
    "techno":      "SOXX",   # 기술 패권 → 반도체 ETF (공급망 충격 반응)
    "maritime":    "CL=F",   # 해양 → WTI 유가 (SLOC 차단 에너지 프리미엄)
    "energy":      "CL=F",   # 에너지 → WTI 유가
    "indo_pacific": "TSM",   # 인도-태평양 → TSMC (대만해협 긴장 프록시)
    "gray_zone":   "GLD",    # 회색지대 → 금 (불확실성 안전자산 도피)
}

# 분석 기간: granger_thresholds.yaml lookback_months 에서 로드
_LOOKBACK_MONTHS: int = _THR["lookback_months"]  # 18→24: 2년 데이터로 Granger 통계력 강화

# ── 인과추론 사다리 (학술 정합성 재설계) ──────────────────────────────────────
# Granger는 '선행성(precedence)'까지만 주장 가능. 인과 아님.
_LADDER_DESCRIPTIVE = "기술적"   # 검정 불가/미실행 — 서술적 근거만
_LADDER_CORRELATIONAL = "상관"   # p<0.15 or 이론근거 약한 쌍 — 시사적
_LADDER_PRECEDENCE = "선행성"    # p<0.05 + 이론근거 — Granger 예측적 선행 (인과 아님)
_LADDER_QUASI_EXP = "준실험"     # 이벤트스터디·패널FE·합성통제 (9-A~E, method_result에만 존재)

_GRANGER_CAVEAT = (
    "Granger 선행성은 예측적 선행이지 구조적 인과가 아님 · 양변량 교란 미통제"
)
_GRANGER_CAVEAT_CONTROLLED = (
    "VIX(글로벌 위험) 통제 조건부 선행성 — 공통 교란 완화했으나 여전히 구조적 인과는 아님"
)
_WEAK_PAIR_CAVEAT = (
    "이론적 인과 메커니즘이 약한 대리쌍 — 허위상관 가능성, 상관 이상 주장 불가"
)

# [B4] 문헌상 전이(contagion/spillover) 메커니즘이 정립된 (지역A → 지역B) 쌍.
# 사건→사건 Granger에서 이 쌍만 '선행성' 칸 도달 가능 (방향 있음, A→B).
_THEORY_GROUNDED_CONTAGION: set[tuple[str, str]] = {
    ("middle_east", "hormuz"),       # 이란 핵심 분쟁 → 호르무즈 도발 (프록시 에스컬레이션)
    ("middle_east", "bab_el_mandeb"),# 중동 분쟁 → 후티 홍해 공격 (이란 축)
    ("hormuz", "bab_el_mandeb"),     # 호르무즈 긴장 → 홍해 (이란-후티 연계)
    ("eastern_europe", "middle_east"),# 러-우 → 중동 (강대국 관심 분산·자원 연계)
    ("sahel", "bab_el_mandeb"),      # 사헬 지하디스트 → 홍해 회랑 (지하드 확산)
    ("middle_east", "korean_peninsula"),  # 중동 위기 → 미 자산 분산 → 한반도 기회주의
}

# 문헌상 인과 메커니즘이 정립된 (region, ticker) 쌍 — correlation.py _VALIDATION_PAIRS 기반
# 이 화이트리스트 밖의 쌍(섹터 편의 proxy)은 유의해도 '상관' 칸으로 상한
_THEORY_GROUNDED_PAIRS: set[tuple[str, str]] = {
    ("ukraine", "ZW=F"), ("ukraine", "CL=F"),
    ("eastern_europe", "ZW=F"), ("eastern_europe", "CL=F"),
    ("bab_el_mandeb", "CL=F"),
    ("hormuz", "CL=F"),
    ("middle_east", "GLD"),
    ("korean_peninsula", "KRW=X"), ("north_korea", "KRW=X"),
    ("taiwan_strait", "TSM"), ("taiwan_strait", "SOXX"),
    ("east_china_sea", "ITA"), ("south_china_sea", "ITA"),
    ("malacca", "NG=F"), ("suez", "CL=F"),
    # AR-2: 신규 일별 시계열 매핑의 문헌상 인과쌍
    ("taiwan_strait", "TWD=X"),    # 대만해협 긴장 → 대만 달러 (지정학 리스크 프리미엄)
    ("eastern_europe", "BZ=F"), ("ukraine", "BZ=F"),  # 러-우 → Brent (에너지 무기화)
    ("hormuz", "BZ=F"), ("bab_el_mandeb", "BZ=F"),    # 초크포인트 → Brent (중동 벤치마크)
}


def _classify_inference_grade(
    p_value: float | None,
    theory_grounded: bool,
    controlled: bool = False,
) -> tuple[str, str]:
    """
    Granger p값 + 이론근거 + 교란통제 → 인과추론 사다리 등급 + 단서.

    핵심 원칙 (학술 정직성):
      - 어떤 결과도 '선행성'을 넘어 인과를 주장하지 않는다.
      - '선행성'은 이론근거 + 유의 + **통제변수 조건부(B3)** 3조건 충족 시에만.
      - 이론근거 없거나 교란 미통제면 유의해도 '상관'에서 상한 (허위상관 방어).
    """
    if p_value is None:
        return _LADDER_DESCRIPTIVE, "Granger 검정 미실행/불가 — 인과 추론 근거 없음"
    if p_value < _P_VERIFIED:
        if theory_grounded and controlled:
            return _LADDER_PRECEDENCE, _GRANGER_CAVEAT_CONTROLLED
        if theory_grounded and not controlled:
            # 교란 미통제 → 선행성 주장 불가, 상관 상한
            return _LADDER_CORRELATIONAL, _GRANGER_CAVEAT + " · 교란 미통제로 선행성 주장 불가"
        # theory_grounded=False: 화이트리스트 밖 쌍 → 등급 상한(상관).
        # D3(대리변수 오류) 진단은 spec.is_proxy_pair 필드로 분리 (8-F에서 처리).
        return _LADDER_CORRELATIONAL, _WEAK_PAIR_CAVEAT
    if p_value < _P_PARTIAL:
        return _LADDER_CORRELATIONAL, _GRANGER_CAVEAT + f" · 경향성 수준(p<{_P_PARTIAL})"
    return _LADDER_DESCRIPTIVE, f"Granger 비유의(p≥{_P_PARTIAL}) — 선행성 근거 없음"


def _get_date_range() -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_MONTHS * 30)
    return start, end


# [9-P-3] 라우팅 방법 ID 상수
_ROUTE_STRUCTURAL    = "structural_arg"          # 8-gate: 비선형 체제 변수 → 구조적 논증
_ROUTE_EVENT_EVENT   = "event_to_event"          # B4: 사건→사건 Granger
_ROUTE_PENDING_B     = "pending_typeB"           # Type_B: 행동 변수, 검정 불가
_ROUTE_GRANGER_C     = "granger_typeC_proxy"     # Type_C: 대리변수 Granger
_ROUTE_GRANGER_A_DG  = "granger_typeA_downgrade" # Type_A → C 강등 후 Granger
_ROUTE_SECTOR_PROXY  = "granger_sector_proxy"    # 섹터 proxy fallback
_ROUTE_PENDING_A     = "pending_typeA_no_mapping" # Type_A 매핑 실패
_ROUTE_GRANGER_A     = "granger_typeA"           # Type_A 정상: 금융 ticker Granger
_ROUTE_NO_HYPOTHESIS = "no_quantitative_hypothesis"    # H1이 '정량 가설 없음' 선언문 — 검정 대상 아님
_ROUTE_PENDING_METHOD = "pending_method_unimplemented" # 시그니처 판정 명확, 해당 방법(9-A/9-B) 미구현
_ROUTE_CONSTRUCT_FAIL = "construct_validity_fail"       # IV가 질문 대상을 측정 못함 — 검정 미수행(2026-07-05)

# 추출기가 검정 불가를 정직하게 선언한 문장 패턴 (H1 자리에 선언문이 오는 실측 형태 2종).
# 이 선언문이 Type_A/C로 오분류되면 섹터 proxy Granger까지 흘러가 유의 결과로 '세탁'될 수 있어
# 검정 진입 전에 단락한다 (실측: 20260704 eval china_rareearth — 선언문이 PARTIAL p=0.0 획득).
_RE_NO_HYPOTHESIS = re.compile(r"(검증\s*가능한[^.]{0,30}?가설[이은는]?\s*없|정량\s*가설\s*없음)")


def _is_no_hypothesis_declaration(h1: str) -> bool:
    """H1이 실제 가설이 아니라 '검정할 가설 없음' 선언문인지 판별한다."""
    return bool(_RE_NO_HYPOTHESIS.search(h1 or ""))


def _build_surface(spec: "HypothesisSpec") -> None:
    """
    [9-P-4] 표면 2계층 — 비전공자가 읽는 한 줄 결론 + 신뢰 한 단어.

    routing_method + verification_status + routing_confidence 조합으로
    결정론적으로 생성. LLM 호출 0 (Token-Zero).
    """
    iv  = spec.independent_var or "X"
    dv  = spec.dependent_var   or "Y"
    p   = f"p={spec.granger_p:.3f}" if spec.granger_p is not None else ""
    rgn = spec.region_code or ""
    tkr = spec.ticker or ""

    m = spec.routing_method

    if m == _ROUTE_STRUCTURAL:
        # [9-Q 우선순위 3] 구조적 논증 → 과정추적 스캐폴딩으로 전환
        spec.surface_summary  = (
            f"[과정추적] {iv} → {dv} — Van Evera 4검정 스캐폴딩 제공 "
            f"(정량 검정 불가, 판정은 연구자)"
        )
        spec.confidence_word  = "검정불가"
    elif m == _ROUTE_EVENT_EVENT:
        dep = spec.dependent_region or "?"
        if spec.verification_status == "VERIFIED":
            spec.surface_summary = f"[사건→사건] {rgn}→{dep} 전이 선행성 유의 ({p})"
            spec.confidence_word = "높음"
        elif spec.verification_status == "PARTIAL":
            spec.surface_summary = f"[사건→사건] {rgn}→{dep} 경향성 ({p})"
            spec.confidence_word = "보통"
        else:
            spec.surface_summary = f"[사건→사건] {rgn}→{dep} — 통계 비유의"
            spec.confidence_word = "낮음"
    elif m == _ROUTE_PENDING_B:
        spec.surface_summary  = f"[행동변수] {dv} — 이벤트스터디 미구현, 검정 불가"
        spec.confidence_word  = "검정불가"
    elif m in (_ROUTE_GRANGER_C, _ROUTE_GRANGER_A_DG):
        proxy_note = "(대리쌍)" if spec.is_proxy_pair else ""
        if spec.verification_status == "VERIFIED":
            spec.surface_summary = f"[Granger{proxy_note}] {rgn}→{tkr} 선행성 유의 ({p})"
            spec.confidence_word = "보통" if spec.is_proxy_pair else "높음"
        elif spec.verification_status == "PARTIAL":
            spec.surface_summary = f"[Granger{proxy_note}] {rgn}→{tkr} 경향성 ({p})"
            spec.confidence_word = "낮음" if spec.is_proxy_pair else "보통"
        else:
            spec.surface_summary = f"[Granger{proxy_note}] {rgn}→{tkr} — 비유의"
            spec.confidence_word = "낮음"
    elif m == _ROUTE_SECTOR_PROXY:
        spec.surface_summary  = f"[섹터proxy] {tkr} — 지역 추정 폴백, 신뢰도 낮음"
        spec.confidence_word  = "낮음"
    elif m == _ROUTE_GRANGER_A:
        if spec.verification_status == "VERIFIED":
            spec.surface_summary = f"[Granger] {iv} → {dv} 선행성 유의 ({p})"
            spec.confidence_word = "높음"
        elif spec.verification_status == "PARTIAL":
            spec.surface_summary = f"[Granger] {iv} → {dv} 경향성 ({p})"
            spec.confidence_word = "보통"
        else:
            spec.surface_summary = f"[Granger] {iv} → {dv} — 비유의"
            spec.confidence_word = "낮음"
    elif m == _ROUTE_NO_HYPOTHESIS:
        spec.surface_summary  = "[가설없음] 검증 가능한 정량 가설 없음 — 검정 생략, 서술·이론 근거만"
        spec.confidence_word  = "검정불가"
    elif m == _ROUTE_PENDING_METHOD:
        spec.surface_summary  = (
            f"[방법대기] {iv} → {dv} — {spec.data_signature} 전용 방법(9-A/9-B) 미구현, 검정 보류"
        )
        spec.confidence_word  = "검정불가"
    else:
        # _ROUTE_PENDING_A 또는 미분류
        spec.surface_summary  = f"[검정불가] {iv} → {dv} — 데이터 매핑 실패"
        spec.confidence_word  = "검정불가"

    # routing_confidence=LOW 이면 confidence_word 하향 보정
    if spec.routing_confidence == "LOW" and spec.confidence_word not in ("검정불가", "낮음"):
        spec.confidence_word = "낮음"


def _apply_epistemic_cap(spec: "HypothesisSpec") -> None:
    """
    [9-Q 우선순위 2] 인식론 모드 캡 — HARKing(데이터→가설) 방어.

    탐색형(exploratory=True): 데이터를 본 뒤 가설을 생성 → 같은 데이터로 검정 = 순환.
      "화살 쏜 뒤 과녁 그리기"와 같음 → 강한 인과 주장(선행성·준실험) 불가.
      헤드라인 3곳(inference_grade·surface_summary·method_result.headline_rung)을
      '상관'에서 상한 + [탐색적] 라벨. 단, 원본 추정치(native_stats·all_results)는 보존 —
      칸(등급)만 강등하고 숫자는 안 지운다 (정직성: 방법 자체는 유효했음).
    확증형(exploratory=False): 사용자가 데이터 보기 전 가설을 직접 선언 → 캡 없음 + [확증].

    모든 등급 계산(FDR·_build_surface·Method Router)이 끝난 뒤 단일 패스로 적용.
    LLM 호출 0 (Token-Zero).
    """
    if not getattr(spec, "exploratory", False):
        # ── 확증형 — 캡 없음, 라벨만 (사용자 직접 선언 가설) ──
        if spec.surface_summary and not spec.surface_summary.startswith("[확증]"):
            spec.surface_summary = "[확증] " + spec.surface_summary
        return

    # ── 탐색형 — '상관' 상한 + [탐색적] 라벨 ──
    _HARK_CAVEAT = (
        "[탐색적] 데이터 관찰 후 가설 생성(HARKing) — 같은 데이터로 검정하면 순환이라 "
        "선행성·준실험 주장 불가, '상관'에서 상한. 확증하려면 가설을 데이터 보기 전 선언(검증 모드)."
    )

    # 1. 레거시 inference_grade 캡 (선행성 → 상관)
    if spec.inference_grade == _LADDER_PRECEDENCE:
        spec.inference_grade = _LADDER_CORRELATIONAL
        spec.inference_caveat = f"{_HARK_CAVEAT} · {spec.inference_caveat}".rstrip(" ·")

    # 2. Method Router headline_rung 캡 (선행성·준실험 → 상관). all_results는 보존.
    mr = spec.method_result
    if mr and mr.get("headline_rung") in (_LADDER_PRECEDENCE, _LADDER_QUASI_EXP):
        mr["epistemic_cap"] = f"[탐색적] {mr['headline_rung']}→상관 (HARKing 방어, 원본 추정치는 all_results 보존)"
        mr["headline_rung"] = _LADDER_CORRELATIONAL

    # 3. 표면 라벨 + 문구 정합 (등급이 상관인데 "선행성 유의"라 적혀 모순되지 않게)
    summary = spec.surface_summary.replace("선행성 유의", "경향성")
    if not summary.startswith("[탐색적]"):
        summary = "[탐색적] " + summary
    spec.surface_summary = summary
    if spec.confidence_word == "높음":   # 캡됐으니 '높음'은 과대 — 한 단계 하향
        spec.confidence_word = "보통"


def _check_method_fit(spec: "HypothesisSpec") -> None:
    """
    [9-P-3] 사후 점검 훅 — "성공해도 틀린 방법" 플래그.

    Granger 유의 결과가 나왔더라도 방법 선택 자체가 부적절할 수 있다.
    이 훅은 결과를 바꾸지 않고 routing_confidence를 낮추고 caveat을 보강한다.
    9-0 Method Router가 구현되면 이 훅의 진단을 라우터 로직에 흡수한다.
    """
    if spec.routing_method in (_ROUTE_GRANGER_C, _ROUTE_GRANGER_A_DG, _ROUTE_SECTOR_PROXY):
        if spec.is_proxy_pair and spec.verification_status in ("VERIFIED", "PARTIAL"):
            # 대리쌍으로 유의 결과: 화이트리스트 밖이므로 허위상관 가능성
            spec.routing_confidence = "LOW"
            spec.inference_caveat = (
                "[방법점검-P3] 화이트리스트 밖 대리쌍(is_proxy_pair=True)에서 유의 결과. "
                "허위상관 가능성 있음. 직접 DV 시계열 확보 또는 9-A 이벤트스터디 고려. "
            ) + spec.inference_caveat

    if spec.routing_method == _ROUTE_SECTOR_PROXY and spec.routing_confidence != "LOW":
        # 섹터 proxy는 지역 추정 포함 — 유의하지 않아도 MEDIUM 이하
        spec.routing_confidence = "MEDIUM"


async def _run_granger_for_spec(
    spec: HypothesisSpec,
    start: date,
    end: date,
    load_event_series,
    get_market_series,
    run_granger,
    *,
    proxy_label: str | None = None,
    get_control_series=None,
    run_conditional_granger=None,
    load_extreme_event_series=None,  # [B8] P90 극단 시리즈 로더 (선택)
) -> HypothesisSpec:
    """
    HypothesisSpec에 대해 Granger 선행성 검정을 실행한다.

    [B3] 통제변수(VIX) 로드 가능 시 **조건부 Granger** 우선 — 공통 교란 완화.
         불가 시 양변량 fallback (교란 미통제 단서 유지).
    [B8] 정규 Granger p > 0.15 시 P90 극단 시리즈로 재검정 (비선형 임계 전이 탐색).
         이론 근거: 지정학 충격의 시장 전이는 극단 이벤트에서만 발생 (Farrell & Newman 2019).
    proxy_label: Type C 대리변수 사용 시 에러 필드에 기재.
    """
    # PERF-2: 동일 지역·티커·기간 조합은 Granger 재계산 생략
    _cache_key = (spec.region_code, spec.ticker, start.isoformat(), end.isoformat())
    _cached = _gcache_get(_cache_key)
    if _cached is not None:
        logger.debug("[hypothesis] Granger cache HIT %s/%s", spec.region_code, spec.ticker)
        # 캐시된 수치 필드만 덮어쓰고 나머지(h1·h0·var 등)는 현재 spec 유지
        for _k, _v in _cached.items():
            setattr(spec, _k, _v)
        return spec

    try:
        # [A-1] 게이트가 단일 국가를 지목했으면 그 국가만 필터(순수 대상 시계열)
        _fc = getattr(spec, "_filter_country", None)
        event_series = load_event_series(spec.region_code, start, end, country=_fc)
        if event_series is None or len(event_series) < _MIN_EVENT_OBS:
            spec.error = (
                f"이벤트 데이터 부족 ({len(event_series) if event_series is not None else 0}건)"
            )
            return spec

        market_series = await get_market_series(spec.ticker, start, end)
        if market_series is None or len(market_series) < _MIN_MARKET_OBS:
            spec.error = f"시장 데이터 부족 (ticker={spec.ticker})"
            return spec

        # [B3] 통제변수 로드 (실패 시 None → 양변량 fallback)
        control_series, control_name = (None, None)
        if get_control_series is not None:
            control_series, control_name = await get_control_series(start, end)

        # sparse 이벤트 시계열(주간 집계)과 일별 시장·통제 시계열 길이 불일치 보정
        is_weekly = bool(event_series.name and "weekly" in str(event_series.name))
        if is_weekly:
            market_series = market_series.resample("W").last()
            if control_series is not None:
                control_series = control_series.resample("W").last()

        # ── [B3] 조건부 Granger 우선, 불가 시 양변량 ──────────────────────
        if control_series is not None and run_conditional_granger is not None:
            p_value, best_lag, n_obs, f_stat, meta = run_conditional_granger(
                event_series, market_series, control_series
            )
            # 조건부 검정이 표본 부족 등으로 실패하면 양변량으로 재시도
            if p_value is None:
                p_value, best_lag, n_obs, f_stat, meta = run_granger(event_series, market_series)
        else:
            p_value, best_lag, n_obs, f_stat, meta = run_granger(event_series, market_series)

        spec.n_obs = n_obs
        spec.differenced = bool(meta.get("differenced")) if meta else False
        spec.controlled  = bool(meta.get("controlled")) if meta else False
        spec.control_name = control_name if spec.controlled else None

        if p_value is None:
            spec.error = "Granger 검정 실패 (관측값 부족 또는 분산=0)"
            spec.inference_grade  = _LADDER_DESCRIPTIVE
            spec.inference_caveat = "검정 불가 — 인과 추론 근거 없음"
            return spec

        spec.granger_p    = round(p_value, 4)
        spec.f_statistic  = f_stat
        spec.best_lag     = best_lag

        # ── 이론근거 판정 + 인과추론 사다리 등급 (통제 여부 반영) ──────────
        spec.theory_grounded = (spec.region_code or "", spec.ticker or "") in _THEORY_GROUNDED_PAIRS
        spec.inference_grade, spec.inference_caveat = _classify_inference_grade(
            p_value, spec.theory_grounded, spec.controlled
        )

        # verification_status: 하위 호환용 — 사다리에서 파생 (인과 단정 어휘 배제)
        if spec.inference_grade == _LADDER_PRECEDENCE:
            spec.verification_status = "VERIFIED"   # = '선행성 유의' (UI에서 사다리로 표기)
        elif spec.inference_grade == _LADDER_CORRELATIONAL:
            spec.verification_status = "PARTIAL"
        else:
            spec.verification_status = "PENDING"

        # ── [B8] P90 극단 시리즈 보조 검정 ──────────────────────────────────
        # 정규 Granger 유의하지 않을 때(p > 0.15) 비선형 임계 전이 탐색.
        # P90 초과분 시리즈는 일상 이벤트 노이즈 제거 후 극단 신호만 포착 (고빈도 일별 유지).
        # 이 검정이 유의하면 "비선형 임계 전이" 구조로 inference_grade 승격.
        if (
            load_extreme_event_series is not None
            and spec.region_code
            and spec.granger_p is not None
            and spec.granger_p > 0.15
        ):
            try:
                ext_series = load_extreme_event_series(spec.region_code, start, end)
                if ext_series is not None:
                    mkt = await get_market_series(spec.ticker, start, end)
                    if mkt is not None and len(mkt) >= _MIN_EXTREME_OBS:
                        ep, elag, en, ef, _ = run_granger(ext_series, mkt)
                        if ep is not None:
                            spec.extreme_granger_p = round(ep, 4)
                            spec.extreme_granger_f = round(ef, 3) if ef is not None else None
                            logger.info(
                                "[hypothesis] [B8-P90] %s | region=%s p_extreme=%.4f F=%.3f lag=%d",
                                spec.h1[:50], spec.region_code, ep, ef or 0, elag or 0,
                            )
                            if ep < _P_EXTREME_VERIFIED:
                                # 극단 이벤트에서만 시장 전이 확인 → 비선형 임계 전이
                                spec.inference_grade = _LADDER_CORRELATIONAL  # 상관 단계 승격
                                spec.inference_caveat = (
                                    f"[비선형 임계 전이] P90 극단 이벤트 시계열에서 선행성 유의 "
                                    f"(p_extreme={ep:.4f}, F={ef:.3f}). "
                                    "일상 이벤트는 시장에 신호 없고 임계값 초과 사건만 전이. "
                                    "선형 Granger 유의하지 않음 → 비선형·임계 모델 필요. "
                                    "(Farrell & Newman 2019 임계 효과 실증)"
                                )
                                spec.verification_status = "PARTIAL"
            except Exception as _ext_exc:
                logger.debug("[hypothesis] [B8-P90] 극단 검정 실패: %s", _ext_exc)

        # [8-gate] 선형·극단 모두 비유의 — null을 비선형 증거로 승격하지 않는다.
        #   affirming-the-null 방지: 비유의는 4가지 원인 중 '식별 불가'일 뿐이며,
        #   비선형 주장은 적극적 비선형 검정의 양성 결과로만 가능하다.
        if (
            spec.verification_status == "PENDING"
            and spec.granger_p is not None
            and spec.extreme_granger_p is not None
            and spec.extreme_granger_p > 0.10
        ):
            spec.inference_caveat += (
                f" | [검정 비유의] 정규(p={spec.granger_p}) · 극단P90(p={spec.extreme_granger_p}) "
                "모두 비유의. 원인은 ①무관계 ②비선형 미포착 ③대리변수 오류 ④데이터 부족 "
                "중 식별 불가 — 비선형이라고 주장하지 않음. 비선형을 입증하려면 "
                "임계회귀 등 적극적 비선형 검정이 필요(검증포인트)."
            )

        if proxy_label:
            spec.error = (
                f"[대리변수 사용] {proxy_label} → {spec.ticker} "
                f"(p={spec.granger_p}, F={f_stat}, lag={best_lag}, "
                f"diff={spec.differenced})"
            )

        logger.info(
            "[hypothesis] %s | region=%s ticker=%s p=%.4f lag=%s grounded=%s diff=%s → %s%s",
            spec.h1[:50], spec.region_code, spec.ticker,
            p_value, best_lag, spec.theory_grounded, spec.differenced,
            spec.inference_grade,
            f" [{proxy_label}]" if proxy_label else "",
        )

        # PERF-2: 결과를 캐시에 저장 (수치 필드만)
        _gcache_set(_cache_key, {
            "granger_p": spec.granger_p,
            "f_statistic": spec.f_statistic,
            "best_lag": spec.best_lag,
            "n_obs": spec.n_obs,
            "differenced": spec.differenced,
            "controlled": spec.controlled,
            "control_name": spec.control_name,
            "theory_grounded": spec.theory_grounded,
            "inference_grade": spec.inference_grade,
            "inference_caveat": spec.inference_caveat,
            "verification_status": spec.verification_status,
            "extreme_granger_p": spec.extreme_granger_p,
            "extreme_granger_f": spec.extreme_granger_f,
        })
    except Exception as exc:
        spec.error = str(exc)
        logger.warning("[hypothesis] 검정 오류: %s — %s", spec.h1[:50], exc)

    return spec


async def verify_hypotheses(specs: list[HypothesisSpec]) -> list[HypothesisSpec]:
    """
    각 HypothesisSpec에 대해 Granger 검정을 실행한다.

    v6.3.0 분기 로직:
      Type_C: ACLED 이벤트 시계열 + 지역 기본 ticker → Granger 실행 (P2)
      Type_A 실패: region 있으면 Type C 경로로 자동 강등 (P3)
      Type_B: PENDING + 안내 메시지 (변화 없음)
    """
    from services.cascade.correlation import (
        _load_event_series,
        _load_extreme_event_series,  # [B8] P90 극단 이벤트 시계열
        _get_market_series,
        _run_granger,
        _get_control_series,        # [B3] 통제변수 로더
        _run_conditional_granger,   # [B3] 조건부 Granger
    )

    start, end = _get_date_range()
    results: list[HypothesisSpec] = []

    # [B3] 통제변수는 쿼리당 1회만 로드해 재사용 (yfinance 호출 절약)
    _ctl_cache: dict = {}

    async def _cached_control(s: date, e: date):
        if "v" not in _ctl_cache:
            _ctl_cache["v"] = await _get_control_series(s, e)
        return _ctl_cache["v"]

    # [B4] 사건→사건 Granger 러너 (전이 가설) — 글로벌 분쟁 baseline 통제
    from services.cascade.correlation import (
        _load_global_conflict_series, _run_conditional_granger as _cond_g,
    )

    async def _run_event_to_event(spec: HypothesisSpec) -> HypothesisSpec:
        x = _load_event_series(spec.region_code, start, end)       # 독립 지역 A
        y = _load_event_series(spec.dependent_region, start, end)  # 종속 지역 B
        if x is None or y is None or len(x) < _MIN_EVENT_EVENT_OBS or len(y) < _MIN_EVENT_EVENT_OBS:
            spec.error = (
                f"사건→사건 데이터 부족 (A={spec.region_code}:{len(x) if x is not None else 0} "
                f"B={spec.dependent_region}:{len(y) if y is not None else 0})"
            )
            spec.inference_grade = _LADDER_DESCRIPTIVE
            return spec
        z = _load_global_conflict_series(start, end, exclude=[spec.region_code, spec.dependent_region])
        p, lag, n, f, meta = _cond_g(x, y, z)
        spec.n_obs = n
        spec.differenced = bool(meta.get("differenced"))
        spec.controlled = bool(meta.get("controlled"))
        spec.control_name = "글로벌 분쟁 baseline" if spec.controlled else None
        if p is None:
            spec.error = "사건→사건 Granger 실패 (관측·분산 부족)"
            spec.inference_grade = _LADDER_DESCRIPTIVE
            return spec
        spec.granger_p = round(p, 4)
        spec.f_statistic = f
        spec.best_lag = lag
        spec.theory_grounded = (
            (spec.region_code or "", spec.dependent_region or "") in _THEORY_GROUNDED_CONTAGION
        )
        spec.inference_grade, spec.inference_caveat = _classify_inference_grade(
            p, spec.theory_grounded, spec.controlled
        )
        # 사건→사건 통제변수는 VIX가 아니라 글로벌 분쟁 baseline — 단서 라벨 교정
        if spec.controlled:
            spec.inference_caveat = spec.inference_caveat.replace(
                "VIX(글로벌 위험)", "글로벌 분쟁 baseline"
            )
        if spec.inference_grade == _LADDER_PRECEDENCE:
            spec.verification_status = "VERIFIED"
        elif spec.inference_grade == _LADDER_CORRELATIONAL:
            spec.verification_status = "PARTIAL"
        else:
            spec.verification_status = "PENDING"
        spec.error = (
            f"[사건→사건] {spec.region_code}→{spec.dependent_region} "
            f"(글로벌 분쟁 통제, p={spec.granger_p}, grounded={spec.theory_grounded})"
        )
        logger.info(
            "[hypothesis] 사건→사건 %s→%s p=%.4f grounded=%s → %s",
            spec.region_code, spec.dependent_region, p, spec.theory_grounded,
            spec.inference_grade,
        )
        return spec

    # [9-P-1] 동일 (region_code, ticker) 쌍 중복 표지
    # IV/DV 추출 실패로 두 H1이 같은 폴백 대리쌍에 매핑될 때 두 번째부터
    # [동일 대리변수쌍] 레이블 → 사용자가 추출 버그임을 인식할 수 있도록.
    # 데이터는 동일하므로 캐시 히트 후 수치만 복사 (재계산 불필요).
    _seen_pairs: set[tuple[str | None, str | None]] = set()

    # [9-Q 쿼리-우선 라우팅] 조작화(H1)를 계산하기 '전에' 질문의 논리 형태로 방법을 정한다.
    #   이론 판별형(복수 이론 비교)·해석형(왜/어떻게 — 메커니즘·귀속·역량공백) 질문은 LLM이 만든
    #   정량 H1·ticker와 무관하게 선형검정 부적합(→ 구조적 논증/과정추적)으로 확정.
    #   순서 역전(조작화→방법)을 질문→방법으로 바로잡음.
    from services.methods.router import unquantifiable_question_reason as _unq_reason

    for spec in specs:
        # ── [구성타당도 게이트] 라우팅에 앞서 공통 적용 — Granger·과정추적 등 모든 event-IV
        # 경로를 차단한다. IV가 특정 국가를 지목하는데 실제 이벤트 표본에 그 국가가 거의 없으면
        # (질문 대상 미측정) 검정을 진행하지 않는다. 예: "북한 도발" IV인데 korean_peninsula
        # 표본은 South Korea 98%·North Korea 0건(ACLED 폐쇄국가 미커버) → 큰 표본의 가짜 유의 방지.
        # (2026-07-05 목표 '확실한 변수' — geo-os/docs/ENGINE_CONSTRUCT_VALIDITY.md)
        if spec.region_code:
            try:
                from services.methods.iv_construct import probe_event_iv, assess_construct
                # 국가 추출은 IV 텍스트 + '원 쿼리'를 함께 본다 (v9.29.0 — 골드셋 검증 런 검출):
                # 생성이 IV를 "한반도 이벤트"로 패러프레이즈하면 '북한'이 IV에서 사라져
                # 게이트가 조용히 미적용되는 자연 발생 우회가 실측됨. 질문이 지목한 대상이
                # 구성타당도의 기준이다 (9-Q 쿼리-우선 원칙의 게이트판).
                _cv = assess_construct(
                    f"{getattr(spec, 'independent_var', '') or spec.h1} "
                    f"{getattr(spec, 'source_query', '') or ''}",
                    probe_event_iv(spec.region_code, start, end),
                    start=start, end=end,  # A/B 진단(DATA_ABSENT vs IV_MISROUTE)용 창
                )
            except Exception as _cv_exc:  # noqa: BLE001
                logger.warning("[구성타당도] 프로브 실패(무시): %s", _cv_exc)
                _cv = None
            if _cv is not None:
                # 감사 가능성(축 2): 무엇을 셌는지 항상 남긴다.
                spec.method_result = {**(spec.method_result or {}), "iv_construct": _cv.meta}
                if not _cv.ok:
                    spec.inference_grade = _LADDER_DESCRIPTIVE
                    spec.verification_status = "PENDING"
                    spec.error = _cv.reason
                    spec.inference_caveat = _cv.reason
                    spec.routing_method = _ROUTE_CONSTRUCT_FAIL
                    spec.routing_confidence = "HIGH"  # 표본에 대상 부재 — 판정 명확
                    spec.routing_alternatives = ["질문 대상을 커버하는 데이터 확보 후 재검정"]
                    logger.info("[구성타당도] 검정 미수행: %s (대상 %s share=%.2f)",
                                spec.h1[:50], _cv.meta.get("named_countries"),
                                _cv.meta.get("named_share", 0.0))
                    results.append(spec)
                    continue
                # [A-1] 통과 + 단일 국가 지목 → 검정에서 그 국가만 필터(순수 대상 시계열).
                # region에 섞인 타국 이벤트(예: korean_peninsula의 남한 시위) 배제.
                if _cv.filter_country:
                    spec._filter_country = _cv.filter_country
                    logger.info("[A-1] IV 국가 필터 적용: %s → country=%s (%d건)",
                                spec.h1[:40], _cv.filter_country, _cv.meta.get("named_n", 0))
                # [episodic 정책계열 — 위원회 2026-07-08] 필터 대상이 의도적 정책행위
                # 이벤트(missile_test 등)로 구성되면 선형 Granger 부적합 — linear_testable을
                # 꺼서 아래 8-gate 경로로 구조적 논증에 보낸다. construct_fail(데이터 부족)과
                # 구별되는 방법 문제: reason에 "데이터는 충분"이 명시돼 표면에서 갈린다.
                if _cv.episodic_policy and spec.linear_testable:
                    spec.linear_testable = False
                    spec.testability_reason = _cv.episodic_reason
                    logger.info("[episodic] 선형검정 제외(데이터 충분·방법 부적합): %s",
                                spec.h1[:50])

        # ── [9-Q] 쿼리-우선 veto — spec.linear_testable을 쿼리 형태로 선행 무효화 ──
        _reason = _unq_reason(getattr(spec, "source_query", ""))
        if spec.linear_testable and _reason:
            spec.linear_testable = False
            spec.testability_reason = _reason + ". 과정추적·구조적 논증 대상"
            logger.info("[hypothesis] [9-Q 쿼리-우선] → 선형검정 제외: %s",
                        (getattr(spec, "source_query", "") or spec.h1)[:60])

        # ── [8-gate] 선형검정 부적합 변수 단락 — Granger 트랙 진입 차단 ────────
        # 체제·임계 변수는 선형 Granger에 넣지 않고 '구조적 논증'으로 명시한다.
        # 대리쌍 치환·노이즈 p값 생성을 원천 차단 → 선형검정 실패를 비선형 증거로
        # 둔갑시키던 affirming-the-null 오류를 구조적으로 제거.
        if not spec.linear_testable:
            spec.inference_grade = _LADDER_DESCRIPTIVE
            spec.verification_status = "PENDING"
            spec.inference_caveat = (
                "[구조적 논증 — 설계상 선형검정 제외] " + spec.testability_reason +
                ". 통계 검증을 청구하지 않음. 비선형을 입증하려면 임계회귀(TAR)·"
                "체제전환 모델 등 적극적 비선형 검정이 필요(검증포인트)."
            )
            spec.error = "선형검정 부적합(비선형 체제 변수) — Granger 미실행"
            # [9-P-3] 라우팅 마킹
            spec.routing_method = _ROUTE_STRUCTURAL
            spec.routing_confidence = "HIGH"   # 8-gate 판정이 명확 → 방법 선택 신뢰도 高
            spec.routing_alternatives = ["9-C 비선형검정(TAR·체제전환) — 적극적 양성 증거 필요"]
            logger.info("[hypothesis] [8-gate] 선형검정 제외: %s", spec.h1[:60])
            results.append(spec)
            continue

        # ── '정량 가설 없음' 선언문 단락 — 검정 대상이 아니므로 어떤 검정 경로에도 넣지 않음 ──
        # 선언문에 var_type(Type_A/C)이 붙어 폴백·섹터 proxy Granger로 흘러가면
        # "가설 없음"이 유의 결과를 얻는 모순(laundering)이 생긴다. 선언 자체는 정직한
        # 판정이므로 routing_confidence=HIGH (UNQUANTIFIABLE 제외 규칙과 같은 논리).
        if _is_no_hypothesis_declaration(spec.h1):
            spec.inference_grade = _LADDER_DESCRIPTIVE
            spec.verification_status = "PENDING"
            spec.error = "정량 가설 없음 선언 — 검정 미실행"
            spec.inference_caveat = (
                "검정 대상 아님 — 추출기가 '검증 가능한 정량 가설 없음'을 선언. "
                "서술·이론 근거만 가능. " + (spec.inference_caveat or "")
            ).rstrip()
            spec.routing_method = _ROUTE_NO_HYPOTHESIS
            spec.routing_confidence = "HIGH"   # 선언 판정은 명확 — 방법 오선택 아님
            spec.routing_alternatives = ["필요 데이터 확보 후 H1 재추출"]
            logger.info("[hypothesis] 정량 가설 없음 선언 → 검정 생략: %s", spec.h1[:60])
            results.append(spec)
            continue

        # ── [v9.29.0 시그니처 선분류] 골드셋 v2 검증 런이 회귀 검출: 시그니처 할당이
        # 사후 계산(결과 재구성 단계)뿐이라 라우팅 중 참조하는 9-A/9-B 미구현 마킹이
        # dead code였다. 방법 선택 '전에' 데이터 모양을 알도록 여기서 선계산한다
        # (classify의 has_ts 인자는 PAIRED 꼬리에만 영향 — 선계산 안전 확인됨).
        from services.methods.router import classify_signature as _classify_sig
        spec.data_signature = _classify_sig(
            f"{getattr(spec, 'source_query', '')} {spec.h1} {spec.h0}",
            linear_testable=spec.linear_testable,
        )
        # 9-C/9-E 미구현 시그니처 — 티커 성사 여부와 '무관하게' granger 대체 금지.
        # 반사실(COUNTERFACTUAL)·임계전환(NONLINEAR) 질문을 쌍별 granger로 답하는 것은
        # 방법 치환(질문이 바뀐 채 검정) — 정직한 미구현 선언이 옳은 행동 (골드 D블록).
        # legacy 영향 0건 실측 (직전 33케이스 baseline에 두 시그니처 부재).
        if spec.data_signature in ("NONLINEAR", "COUNTERFACTUAL"):
            _mk = ("임계회귀·체제전환(9-C)" if spec.data_signature == "NONLINEAR"
                   else "합성통제(9-E)")
            spec.inference_grade = _LADDER_DESCRIPTIVE
            spec.verification_status = "PENDING"
            spec.inference_caveat = (
                f"검정 불가 — 데이터 모양({spec.data_signature})의 전용 방법 {_mk}가 "
                f"미구현. Granger로 대체하지 않음(방법 치환 방지). 서술·이론 근거만 가능."
            )
            spec.error = f"{spec.data_signature} 전용 방법 미구현 — 검정 보류"
            spec.routing_method = _ROUTE_PENDING_METHOD
            spec.routing_confidence = "HIGH"
            spec.routing_alternatives = [f"{_mk} 구현 후 검정"]
            logger.info("[hypothesis] 방법 미구현 PENDING (%s): %s",
                        spec.data_signature, spec.h1[:60])
            results.append(spec)
            continue

        # [B4] 사건→사건 전이 가설이 최우선 — 시장 경로 대신 지역B 이벤트로 검정
        if spec.dependent_region and spec.region_code:
            spec = await _run_event_to_event(spec)
            # [9-P-3] 라우팅 마킹
            spec.routing_method = _ROUTE_EVENT_EVENT
            spec.routing_confidence = "HIGH"
            spec.routing_alternatives = ["9-A 이벤트스터디 (사건 전후 비정상변동 포착)"]
            _check_method_fit(spec)
            results.append(spec)
            continue

        if spec.var_type == "Type_B":
            if not spec.region_code:
                spec.error = "Type B (행동 변수): region_code 미식별 → ACLED 검증 불가"
                spec.inference_caveat = (
                    "검정 불가 — 종속변수가 '건수·빈도'(행동 변수)이나 집계 지역이 식별되지 않음. "
                    "검정하려면 H1에 지역(예: '동중국해 분쟁 건수')과 집계 출처(ACLED/CSIS)를 명시해야 함."
                )
            else:
                spec.error = (
                    f"Type B (행동 변수): ACLED 이벤트 비교 필요 "
                    f"(region={spec.region_code}) "
                    f"→ actor_filter 기반 event study로 검증 가능 (다음 버전 구현 예정)"
                )
                spec.inference_caveat = (
                    f"검정 불가 — 종속변수가 행동 변수(건수)로 {spec.region_code} ACLED 시계열은 있으나 "
                    f"actor_filter 기반 event study 미구현. 현재는 서술·이론 근거만 가능."
                )
            # [9-P-3] 라우팅 마킹
            spec.routing_method = _ROUTE_PENDING_B
            spec.routing_confidence = "HIGH"   # Type_B 판정 자체는 명확
            spec.routing_alternatives = ["9-A 이벤트스터디 (actor_filter 기반 event study 구현 후)"]
            logger.info("[hypothesis] Type_B PENDING: %s", spec.h1[:60])
            results.append(spec)
            continue

        if spec.var_type == "Type_C":
            # [P2] 대리변수 Granger: ACLED 이벤트 시계열 + 지역 기본 ticker
            default_ticker = _REGION_DEFAULT_TICKER.get(spec.region_code or "")
            if spec.region_code and default_ticker:
                spec.ticker = default_ticker
                # [9-P-2] D3 마킹: 화이트리스트 밖 대리쌍 → is_proxy_pair=True
                spec.is_proxy_pair = (spec.region_code, default_ticker) not in _THEORY_GROUNDED_PAIRS
                proxy_label = (
                    f"ACLED {spec.region_code} 이벤트 건수"
                    f" → {default_ticker} (지역 기본 지표)"
                )
                spec = await _run_granger_for_spec(
                    spec, start, end,
                    _load_event_series, _get_market_series, _run_granger,
                    get_control_series=_cached_control,
                    run_conditional_granger=_run_conditional_granger,
                    load_extreme_event_series=_load_extreme_event_series,
                    proxy_label=proxy_label,
                )
                # [9-P-3] 라우팅 마킹
                spec.routing_method = _ROUTE_GRANGER_C
                spec.routing_confidence = "HIGH" if not spec.is_proxy_pair else "MEDIUM"
                spec.routing_alternatives = ["9-A 이벤트스터디 (SINGLE_SHOCK 시그니처)"]
                _check_method_fit(spec)
            else:
                proxy_str = ", ".join(spec.proxy_suggestions[:3]) if spec.proxy_suggestions else "대체 지표 필요"
                spec.error = f"Type C (추상 변수): region 미식별 → 권장 대리변수: {proxy_str}"
                spec.inference_caveat = (
                    f"검정 불가 — 종속변수가 추상 지표(예: 의존도·취약성·생산비)로 직접 매핑 가능한 "
                    f"시계열·ticker 없음. 권장 대리변수: {proxy_str}. "
                    f"이 대리변수의 실측 시계열이 확보돼야 Granger 검정 가능."
                )
                spec.routing_method = _ROUTE_PENDING_A
                spec.routing_confidence = "LOW"
                spec.routing_alternatives = ["직접 DV 시계열 확보 후 재검정"]
            logger.info("[hypothesis] Type_C %s: %s", spec.verification_status, spec.h1[:60])
            results.append(spec)
            continue

        # Type_A: 금융 ticker Granger 경로
        if not spec.region_code or not spec.ticker:
            # [P3] ticker 매핑 실패 → region 있으면 Type C 대리변수 경로로 자동 강등
            if spec.region_code:
                default_ticker = _REGION_DEFAULT_TICKER.get(spec.region_code)
                if default_ticker:
                    spec.var_type = "Type_C"
                    spec.ticker = default_ticker
                    # [9-P-2] D3 마킹: Type A 강등 경로도 화이트리스트 밖이면 대리쌍
                    spec.is_proxy_pair = (spec.region_code, default_ticker) not in _THEORY_GROUNDED_PAIRS
                    proxy_label = (
                        f"Type A 강등 → ACLED {spec.region_code} + {default_ticker} 대리변수"
                    )
                    spec = await _run_granger_for_spec(
                        spec, start, end,
                        _load_event_series, _get_market_series, _run_granger,
                        get_control_series=_cached_control,
                        run_conditional_granger=_run_conditional_granger,
                        proxy_label=proxy_label,
                    )
                    # [9-P-3] 라우팅 마킹 — 강등 경로는 원래 방법 신뢰도 MEDIUM
                    spec.routing_method = _ROUTE_GRANGER_A_DG
                    spec.routing_confidence = "MEDIUM"
                    spec.routing_alternatives = ["ticker 재정의 후 Type_A 정상경로 재시도"]
                    _check_method_fit(spec)
                    logger.info("[hypothesis] Type_A→C 자동강등 %s: %s", spec.verification_status, spec.h1[:60])
                    results.append(spec)
                    continue

            # [Cycle 6-B] 섹터 proxy 경로: region 미식별이지만 섹터 키워드로 ticker 결정
            sector_proxy = _get_sector_proxy(spec)
            if sector_proxy:
                proxy_ticker, proxy_label = sector_proxy
                spec.var_type = "Type_C"
                # [버그수정] 이미 정확히 추출된 ticker(예: 원/달러→KRW=X)는 보존.
                #   섹터 키워드(사이버 등)로 ITA 등 엉뚱한 ticker로 덮어쓰지 않음.
                region_fallback = False
                if not spec.ticker:
                    spec.ticker = proxy_ticker
                # region 없으면 event_archive 조회 불가 → 섹터 대표 지역 폴백(명시)
                if not spec.region_code:
                    spec.region_code = "middle_east"
                    region_fallback = True
                # [9-P-2] 섹터 proxy 경로는 항상 화이트리스트 밖 대리쌍
                spec.is_proxy_pair = True
                spec = await _run_granger_for_spec(
                    spec, start, end,
                    _load_event_series, _get_market_series, _run_granger,
                    get_control_series=_cached_control,
                    run_conditional_granger=_run_conditional_granger,
                    load_extreme_event_series=_load_extreme_event_series,
                    proxy_label=f"섹터 proxy: {proxy_label}",
                )
                # 지역을 추정 폴백한 경우 결과가 쿼리 지역과 다를 수 있음을 명시
                if region_fallback:
                    spec.inference_caveat = (
                        f"[지역 미식별 — {spec.region_code} 추정 폴백] " +
                        (spec.inference_caveat or "")
                    )
                # [9-P-3] 라우팅 마킹 — 섹터 proxy는 지역 추정 포함이라 LOW
                spec.routing_method = _ROUTE_SECTOR_PROXY
                spec.routing_confidence = "LOW"
                spec.routing_alternatives = ["H1에 지역 명시 후 Type_C/A 경로 재시도"]
                _check_method_fit(spec)
                logger.info("[hypothesis] 섹터proxy %s: %s", spec.verification_status, spec.h1[:60])
                results.append(spec)
                continue

            missing = []
            if not spec.region_code:
                missing.append("지역")
            if not spec.ticker:
                missing.append("시장 ticker")
            spec.error = f"Type A (금융 ticker): 매핑 실패 — {', '.join(missing)} 미식별"

            # 시그니처가 미구현 방법(9-A/9-B) 대상이면 매핑 실패는 '오선택 의심'이 아니라
            # '방법 미구현' — Type_B PENDING과 같은 정직 상태로 마킹한다.
            # (실측: 20260704 eval에서 CROSS_SECTION 2건·SINGLE_SHOCK 1건이 티커 경로로
            #  낙하해 LOW로 집계됐으나, 시그니처 판정 자체는 전부 옳았음)
            if spec.data_signature in ("SINGLE_SHOCK", "CROSS_SECTION"):
                _method_ko = ("이벤트스터디(9-A)" if spec.data_signature == "SINGLE_SHOCK"
                              else "횡단/패널 회귀(9-B)")
                spec.inference_caveat = (
                    f"검정 불가 — 데이터 모양({spec.data_signature})에 맞는 방법인 "
                    f"{_method_ko}가 미구현. 티커 Granger로 대체하지 않음(방법 오선택 방지). "
                    f"현재는 서술·이론 근거만 가능."
                )
                spec.routing_method = _ROUTE_PENDING_METHOD
                spec.routing_confidence = "HIGH"   # 시그니처 판정은 명확
                spec.routing_alternatives = [f"{_method_ko} 구현 후 검정"]
                logger.info("[hypothesis] 방법 미구현 PENDING (%s): %s",
                            spec.data_signature, spec.h1[:60])
                results.append(spec)
                continue

            spec.inference_caveat = (
                f"검정 불가 — {', '.join(missing)}을(를) 식별하지 못해 시계열 매핑 실패. "
                f"종속변수를 환율·유가·주가·ETF 등 측정 가능한 시장 지표로 재정의하거나, "
                f"H1에 분석 지역을 명시하면 검정 가능."
            )
            # [9-P-3] 라우팅 마킹
            spec.routing_method = _ROUTE_PENDING_A
            spec.routing_confidence = "LOW"
            spec.routing_alternatives = ["H1 재작성(지역·ticker 명시)", "Type_B(ACLED) 경로 고려"]
            logger.info("[hypothesis] Type_A PENDING (매핑 실패): %s", spec.h1[:60])
            results.append(spec)
            continue

        # Type_A 정상 경로: region + ticker 모두 있음
        # [9-P-1] 이미 처리한 대리쌍이면 [동일 대리변수쌍] 레이블 추가
        _pair_key = (spec.region_code, spec.ticker)
        if _pair_key in _seen_pairs:
            spec.inference_caveat = (
                "[동일 대리변수쌍 — IV/DV 추출 공유] "
                f"region={spec.region_code}, ticker={spec.ticker}로 앞선 가설과 동일한 "
                "시계열 데이터쌍 사용. IV/DV 텍스트는 다르나 Granger 수치는 동일."
                + (f" | {spec.inference_caveat}" if spec.inference_caveat else "")
            )
        _seen_pairs.add(_pair_key)
        spec = await _run_granger_for_spec(
            spec, start, end,
            _load_event_series, _get_market_series, _run_granger,
            get_control_series=_cached_control,
            run_conditional_granger=_run_conditional_granger,
            load_extreme_event_series=_load_extreme_event_series,
        )
        # [9-P-3] 라우팅 마킹 — Type_A 정상: theory_grounded 여부로 신뢰도 결정
        spec.routing_method = _ROUTE_GRANGER_A
        spec.routing_confidence = "HIGH" if spec.theory_grounded else "MEDIUM"
        spec.routing_alternatives = ["9-B 패널회귀 (CROSS_SECTION 시그니처)", "9-A 이벤트스터디 (단일 충격)"]
        _check_method_fit(spec)
        results.append(spec)

    # ── [B2] 다중검정 보정 (Benjamini-Hochberg FDR) ──────────────────────────
    # 한 쿼리에서 여러 가설을 검정하면 우연 유의가 누적된다.
    # 같은 쿼리 범위 내 Granger p값을 FDR 보정 → '선행성' 등급 재판정.
    tested = [s for s in results if s.granger_p is not None]
    if len(tested) >= 2:
        try:
            from statsmodels.stats.multitest import multipletests
            pvals = [s.granger_p for s in tested]
            _, qvals, _, _ = multipletests(pvals, alpha=0.05, method="fdr_bh")
            for s, q in zip(tested, qvals):
                s.granger_q = round(float(q), 4)
                # FDR 미통과 시 '선행성' → '상관'으로 정직 강등
                if s.inference_grade == _LADDER_PRECEDENCE and q >= 0.05:
                    s.inference_grade = _LADDER_CORRELATIONAL
                    s.inference_caveat = (
                        f"{_GRANGER_CAVEAT} · 다중검정 FDR 미통과(q={s.granger_q})"
                    )
                    s.verification_status = "PARTIAL"
                    logger.info(
                        "[hypothesis] FDR 강등: %s (p=%.4f q=%.4f)",
                        s.h1[:40], s.granger_p, q,
                    )
        except Exception as exc:
            logger.warning("[hypothesis] FDR 보정 실패: %s", exc)

    # [9-P-4] 표면 2계층 일괄 생성 (FDR 보정 후 최종 등급 기준)
    for s in results:
        _build_surface(s)

    # [9-0/9-A] Method Router 연결 — 시그니처 분류 + MethodResult 변환 + 삼각측량
    try:
        from services.methods.router import classify_signature, select_method_set, filter_implemented
        from services.methods.granger_adapter import from_spec as _granger_adapt
        from services.methods.event_study import from_spec as _event_study_adapt
        from services.methods.panel_regression import from_spec as _panel_reg_adapt
        from services.methods.process_tracing import process_tracing_adapt as _pt_adapt  # [9-Q 우선순위 3]
        from services.methods.grader import grade as triangulate

        # 검정을 실제로 수행하지 않은 상태(매핑 실패·방법 미구현·가설 없음)는 어댑터를
        # 호출하지 않는다. 호출하면 event_study 등이 ticker 없는 spec에 effect=None 껍데기
        # MethodResult를 만들어 소비자(export_insight 등)가 '결과 있음'으로 오독한다.
        # PENDING이면 method_result는 검정 결과를 담지 않는다 (2026-07-05 엔진 위원회 C-4
        # — method_result null 불변식). skipped 마커로 '검정 안 함'을 명시적으로 남긴다.
        _NO_TEST_ROUTES = {_ROUTE_PENDING_METHOD, _ROUTE_PENDING_A, _ROUTE_NO_HYPOTHESIS,
                           _ROUTE_CONSTRUCT_FAIL}

        for s in results:
            if getattr(s, "routing_method", "") in _NO_TEST_ROUTES:
                mr = {"skipped": True, "skip_reason": s.routing_method}
                # 구성타당도 프로브 결과(무엇을 셌는지)는 감사용으로 보존한다(축 2).
                _prev = s.method_result or {}
                if "iv_construct" in _prev:
                    mr["iv_construct"] = _prev["iv_construct"]
                s.method_result = mr
                continue
            # 시그니처 결정: 원본 쿼리 + h1 + h0 합산 — 원본에만 있는 "이벤트스터디", "패널 분석" 등 보완
            query_text = f"{getattr(s, 'source_query', '')} {s.h1} {s.h0}"
            lt = getattr(s, "linear_testable", True)
            has_ts = s.granger_p is not None or s.verification_status != "PENDING"
            sig = classify_signature(query_text, linear_testable=lt, has_paired_timeseries=has_ts)
            s.data_signature = sig

            # 방법집합 선언 (시그니처 기반 사전 선언 — 결과 주도 선택 금지)
            methods = select_method_set(sig)
            implemented, stubs = filter_implemented(methods)

            # 방법 무관 루프 — 각 구현 어댑터 호출
            method_results = []
            for method in implemented:
                try:
                    if method == "granger":
                        mr = _granger_adapt(s)
                        method_results.append(mr)
                    elif method == "event_study":
                        # 동기 어댑터 (yfinance.download는 동기)
                        mr = _event_study_adapt(s)
                        method_results.append(mr)
                    elif method == "panel_regression":
                        # 동기 어댑터 (SQLite 쿼리)
                        mr = _panel_reg_adapt(s)
                        method_results.append(mr)
                    # [9-Q 우선순위 3] process_tracing: Van Evera 4검정 스캐폴딩
                    elif method == "process_tracing":
                        mr = _pt_adapt(s)
                        method_results.append(mr)
                    # structural_arg: MethodResult 불필요 (등급 기여 없음, 레거시 경로)
                    elif method == "structural_arg":
                        pass
                except Exception as _m_exc:
                    logger.warning("[9-A] 어댑터 실패 method=%s: %s", method, _m_exc)

            # 삼각측량 (단일 방법이면 convergence=None)
            tri = triangulate(method_results)

            # 결과를 spec에 저장 (SSE에서 사용) — iv_construct 감사흔적 보존:
            # 골드셋 v2의 valid_filter 관측(Lock 2)이 이 키에 의존한다 (검수 위원 지적:
            # 기존엔 NO_TEST 경로만 보존돼 정상검정 케이스의 게이트 흔적이 소실됐음).
            _prev_ivc = (s.method_result or {}).get("iv_construct")
            s.method_result = {
                "iv_construct":     _prev_ivc,
                "headline_rung":    tri.headline_rung,
                "headline_method":  tri.headline_method,
                "convergence":      tri.convergence,
                "convergence_note": tri.convergence_note,
                "stub_methods":     stubs,
                "all_results": [
                    {
                        "method":                 r.method,
                        "signature":              r.signature,
                        "effect_estimate":        r.effect_estimate,
                        "effect_size_label":      r.effect_size_label,
                        "significance":           r.significance,
                        "ci_low":                 r.ci_low,
                        "ci_high":                r.ci_high,
                        "assumptions_met":        r.assumptions_met,
                        "assumption_caveat":      r.assumption_caveat,
                        "reachable_rung":         r.reachable_rung,
                        "actual_rung":            r.actual_rung,
                        "confidence_within_rung": r.confidence_within_rung,
                        "robustness":             r.robustness,
                        "native_stats":           r.native_stats,
                        "exploratory":            r.exploratory,
                    }
                    for r in tri.all_results
                ],
            }
            logger.debug(
                "[9-A] sig=%s headline=%s/%s stubs=%s",
                sig, tri.headline_rung, tri.headline_method, stubs,
            )
    except Exception as exc:
        logger.warning("[9-A] Method Router 연결 실패 (무시, Granger 결과 유지): %s", exc)

    # [9-Q 우선순위 2] 인식론 모드 캡 — 모든 등급 계산이 끝난 최종 단일 패스.
    #   탐색형(HARKing) → '상관' 상한 + [탐색적]. 확증형 → [확증] 라벨. (헤드라인 3곳 정합)
    for s in results:
        _apply_epistemic_cap(s)

    return results


def _get_sector_proxy(spec: "HypothesisSpec") -> tuple[str, str] | None:
    """
    [Cycle 6-B] 지역 미식별 시 섹터로 대리변수 ticker를 선택한다.
    H1 텍스트에서 섹터 키워드를 탐지해 _SECTOR_DEFAULT_TICKER로 매핑.
    반환: (ticker, proxy_label) 또는 None
    """
    h1_lower = spec.h1.lower()
    # 우선순위: 구체적(specific) → 일반(general) 순서로 배치
    sector_keywords = {
        "cyber":        ["사이버", "cyber", "apt", "해킹", "악성코드", "랜섬웨어"],
        "indo_pacific": ["대만", "taiwan", "tsmc", "인도-태평양", "indo-pacific", "a2ad"],
        "techno":       ["반도체", "semiconductor", "soxx", "chip", "희토류", "공급망"],
        "energy":       ["유가", "원유", "에너지", "lng", "가스", "oil", "호르무즈"],
        "maritime":     ["해양", "해협", "sloc", "초크포인트", "chokepoint", "선박"],
        "gray_zone":    ["회색지대", "gray zone", "하이브리드", "프록시"],
    }
    for sector, keywords in sector_keywords.items():
        if any(kw in h1_lower for kw in keywords):
            ticker = _SECTOR_DEFAULT_TICKER.get(sector)
            if ticker:
                return ticker, f"{sector} 섹터 대리변수 → {ticker}"
    return None
