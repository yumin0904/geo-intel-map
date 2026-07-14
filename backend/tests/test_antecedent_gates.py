"""18-①위원회(2026-07-14) 신설 가드 3종의 회귀 그물.

안건이 뒤집힌 위원회다. 질문은 "채점기가 independent_var를 읽게 만들 것인가"였으나
실측 답은 **읽을 IV가 없다**였다 — IV는 명제가 아니라 명사구이고(DV는 정량 4필드,
IV는 TEXT 1칸), 전건 판정 가능성은 0/21이었다.

여기서 지키는 것은 그 판정의 집행물이다:
  ① FRED 신선도 게이트   — 오염의 발원지(낡은 시세를 "실측·최근 추세"로 LLM에 주입)
  ② 추출 결함 게이트     — IV가 H1 문장을 통째로 삼킨 행(전건 미분리)
  ③ 동어반복 게이트      — IV가 target 자신을 가리키는 행("IF X THEN X")

②와 ③은 **다른 병이다.** 한 이름으로 뭉개면 폐기 #36(D2 판례)을 재발시킨다 —
"'못 쟀다'·'질문이 틀렸다'·'관계 없다'는 처방이 정반대다."
"""

from __future__ import annotations

from datetime import date

from services.prediction_instrument import (
    _is_tautological,
    _iv_extraction_failed,
)
from services.theory_comparator import _FRED_MAX_STALE_DAYS, _get_fred_for_theories


# ─── ③ 동어반복 게이트 ────────────────────────────────────────────────

def test_tautology_caught__iv_is_the_target_itself():
    """DB 실측 오염 IV(8건)를 잡는다 — IV가 곧 target인 가격 자기예측."""
    for iv, target in [
        ("WTI 유가(USD/배럴)", "CL=F"),
        ("WTI 유가 (USD/배럴) 가 10%", "CL=F"),
        ("유럽 TTF 천연가스 가격(USD/MMBtu)이 10% 이상 급등", "NG=F"),
        ("Brent Crude Oil Price(USD/barrel) 상승", "BZ=F"),
    ]:
        assert _is_tautological(iv, target), f"놓침: {target} ← {iv}"


def test_tautology_does_not_fire_on_real_geopolitical_iv():
    """음성 테스트 — 정상 지정학 전건을 죽이면 가드가 아니라 흉기다."""
    for iv, target in [
        ("중동 분쟁 이벤트 건수(middle_east ACLED)", "CL=F"),
        ("북한 도발 건수(provocation_count)", "^KS11"),
        ("러시아가 우크라이나 에너지 인프라를 공격", "NG=F"),
        ("중국의 갈륨 수출 통제 강도", "TSM"),
        ("middle_east 지역의 ACLED 분쟁 이벤트 월별 건수", "GLD"),
    ]:
        assert not _is_tautological(iv, target), f"오탐: {target} ← {iv}"


# ─── ② 추출 결함 게이트 ───────────────────────────────────────────────

def test_extraction_failure_caught__iv_swallowed_the_whole_h1():
    """IV가 H1 문장을 통째로 삼킨 행 — 전건이 분리되지 않았다(실측 105건)."""
    h1 = "이란전 개전 이후 WTI 유가(USD/배럴) 상승률이 미국의 CPI 상승률(%)과 동반하여 증가할 때, 미국 국방비가 늘어난다"
    iv = "이란전 개전 이후 WTI 유가(USD/배럴) 상승률이 미국의 CPI 상승률(%)과 동반하여"
    assert _iv_extraction_failed(iv, h1)


def test_extraction_failure_does_not_fire_on_isolated_iv():
    """짧고 분리된 IV는 통과 — 추출이 제 일을 한 경우다."""
    h1 = "중동 분쟁이 늘면 유가가 오른다"
    assert not _iv_extraction_failed("중동 분쟁 이벤트 건수(middle_east ACLED)", h1)
    assert not _iv_extraction_failed("", h1)


def test_two_diseases_stay_separate():
    """②와 ③을 뭉개지 않는다(폐기 #36).

    H1을 삼킨 IV는 후행절(WTI)까지 텍스트에 품고 있어 동어반복 검사에 걸린다 — 그러나
    그 행의 진짜 전건은 bab_el_mandeb 분쟁이지 WTI가 아니다. 추출 결함을 먼저 거르지
    않으면 정상 지정학 가설이 '동어반복'이라는 틀린 이름으로 죽는다.
    """
    h1 = "bab_el_mandeb 지역의 ACLED 분쟁 이벤트 월별 건수 증가가 WTI 유가(USD/배럴)를 끌어올린다"
    iv = "bab_el_mandeb 지역의 ACLED 분쟁 이벤트 월별 건수 증가가 WTI 유가(USD/배럴)를"

    assert _iv_extraction_failed(iv, h1)      # ← 이쪽이 먼저 잡아야 한다
    assert _is_tautological(iv, "CL=F")       # ← 텍스트만 보면 여기도 걸린다(오탐)
    # build_prediction의 if/elif 순서가 이 오탐을 막는다. 순서를 뒤집으면 이 테스트의
    # 의미가 사라지므로, 순서 자체가 계약이다.


# ─── ① FRED 신선도 게이트 ─────────────────────────────────────────────

def test_stale_fred_is_not_injected():
    """낡은 시세를 "실측 — … 최근 추세 … [FRED]"로 LLM에 먹이지 않는다.

    실측(2026-07-14): fred_indicators는 시리즈당 5행·2020~2024 **연간**값이고
    2024-01-01에 멈춰 있다(925일). LLM은 그 줄을 독립변수로 되받아 썼다 — 동어반복
    8건의 발원지다. 배관을 막지 않으면 가드 ③은 증상만 잡는다.

    ⚠️ 이 테스트는 "지금 주입이 0건이다"를 재지 않는다 — 그것은 오늘의 사고(事故)이지
    계약이 아니다. FRED가 최신화되면 주입이 되살아나야 **맞다.** 재는 것은 불변식이다:
    **주입된 것은 무엇이든 임계 안쪽이어야 한다.**
    """
    assert _FRED_MAX_STALE_DAYS > 0
    fred = _get_fred_for_theories(["hormuz", "eastern_europe", "taiwan_strait"])
    today = date.today()
    for sid, d in fred.items():
        stale = (today - date.fromisoformat(d["latest_date"])).days
        assert stale <= _FRED_MAX_STALE_DAYS, (
            f"{sid}가 {stale}일 낡았는데 주입됐다(임계 {_FRED_MAX_STALE_DAYS}일)"
        )
        # "최근 추세"라 부르는 구간의 실제 시작점을 숨기지 않는다
        assert "span_from" in d
