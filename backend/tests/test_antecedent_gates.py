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

import pytest

# ⚠️ **회귀 테스트는 고장난 코드 위에서도 돌아야 한다**(패턴 V). 새 심볼을 무조건 import하면
#    수리 전 커밋에서 **수집 단계가 죽고**(ImportError), 그러면 증명 등급이 ABSENT로 나온다 —
#    「결함 수리」가 아니라 「어휘 신설」로 오분류된다. 2026-07-14 실측: B30이 그렇게 걸렸다.
#    수리 전에 없던 것은 **없어도 돌게** 하고, 그 테스트만 skip한다.
import services.prediction_instrument as _pi

_is_tautological = getattr(_pi, "_is_tautological", None)
_iv_extraction_failed = getattr(_pi, "_iv_extraction_failed", None)


import services.theory_comparator as _tc
from services.theory_comparator import _get_fred_for_theories   # 수리 전에도 있던 이름

# 수리로 **생긴** 상수 — 없어도 모듈이 뜨게 한다. 그래야 «구 코드가 낡은 FRED를 뱉는다»는
# **행동**을 구 커밋 위에서 실제로 잴 수 있다(그게 BEHAVIORAL 증명이다).
_FRED_MAX_STALE_DAYS = getattr(_tc, "_FRED_MAX_STALE_DAYS", None)

# **테스트가 계약을 선언한다. 구현의 상수를 읽지 않는다.**
# 구현 상수를 읽으면 구현이 그걸 99999로 바꿔도 테스트가 통과한다 — 동어반복이고,
# 그러면 이 테스트는 게이트가 아니라 거울이다. (2026-07-14 자기 검토)
_CONTRACT_MAX_STALE_DAYS = 120


# ─── ③ 동어반복 게이트 ────────────────────────────────────────────────

def test_tautology_caught__iv_is_the_target_itself():
    """DB 실측 오염 IV(8건)를 잡는다 — IV가 곧 target인 가격 자기예측."""
    if _is_tautological is None:
        pytest.skip("_is_tautological 없음 — 수리 전 코드")
    for iv, target in [
        ("WTI 유가(USD/배럴)", "CL=F"),
        ("WTI 유가 (USD/배럴) 가 10%", "CL=F"),
        ("유럽 TTF 천연가스 가격(USD/MMBtu)이 10% 이상 급등", "NG=F"),
        ("Brent Crude Oil Price(USD/barrel) 상승", "BZ=F"),
    ]:
        assert _is_tautological(iv, target), f"놓침: {target} ← {iv}"


def test_tautology_does_not_fire_on_real_geopolitical_iv():
    """음성 테스트 — 정상 지정학 전건을 죽이면 가드가 아니라 흉기다."""
    if _is_tautological is None:
        pytest.skip("_is_tautological 없음 — 수리 전 코드")
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
    if _iv_extraction_failed is None:
        pytest.skip("_iv_extraction_failed 없음 — 수리 전 코드")
    h1 = "이란전 개전 이후 WTI 유가(USD/배럴) 상승률이 미국의 CPI 상승률(%)과 동반하여 증가할 때, 미국 국방비가 늘어난다"
    iv = "이란전 개전 이후 WTI 유가(USD/배럴) 상승률이 미국의 CPI 상승률(%)과 동반하여"
    assert _iv_extraction_failed(iv, h1)


def test_extraction_failure_does_not_fire_on_isolated_iv():
    """짧고 분리된 IV는 통과 — 추출이 제 일을 한 경우다."""
    if _iv_extraction_failed is None:
        pytest.skip("_iv_extraction_failed 없음 — 수리 전 코드")
    h1 = "중동 분쟁이 늘면 유가가 오른다"
    assert not _iv_extraction_failed("중동 분쟁 이벤트 건수(middle_east ACLED)", h1)
    assert not _iv_extraction_failed("", h1)


def test_two_diseases_stay_separate():
    """②와 ③을 뭉개지 않는다(폐기 #36).

    H1을 삼킨 IV는 후행절(WTI)까지 텍스트에 품고 있어 동어반복 검사에 걸린다 — 그러나
    그 행의 진짜 전건은 bab_el_mandeb 분쟁이지 WTI가 아니다. 추출 결함을 먼저 거르지
    않으면 정상 지정학 가설이 '동어반복'이라는 틀린 이름으로 죽는다.
    """
    if _iv_extraction_failed is None:
        pytest.skip("_iv_extraction_failed 없음 — 수리 전 코드")
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
    fred = _get_fred_for_theories(["hormuz", "eastern_europe", "taiwan_strait"])
    today = date.today()
    for sid, d in fred.items():
        stale = (today - date.fromisoformat(d["latest_date"])).days
        assert stale <= _CONTRACT_MAX_STALE_DAYS, (
            f"{sid}가 {stale}일 낡았는데 «최근 추세»라며 주입됐다"
            f"(계약 {_CONTRACT_MAX_STALE_DAYS}일)"
        )
        # "최근 추세"라 부르는 구간의 실제 시작점을 숨기지 않는다
        assert "span_from" in d


def test_implementation_cannot_loosen_the_contract():
    """구현이 임계를 몰래 늘리지 못한다 — **가드의 가드.**

    위 테스트가 계약(120일)을 스스로 선언하므로, 구현이 `_FRED_MAX_STALE_DAYS`를 늘려도
    그 테스트는 여전히 잡는다. 이 테스트는 **의도를 명시**한다: 구현 상수는 계약 이내여야 한다.
    """
    if _FRED_MAX_STALE_DAYS is None:
        pytest.skip("_FRED_MAX_STALE_DAYS 없음 — 수리 전 코드")
    assert 0 < _FRED_MAX_STALE_DAYS <= _CONTRACT_MAX_STALE_DAYS, (
        f"구현이 임계를 {_FRED_MAX_STALE_DAYS}일로 늘렸다 — 계약은 {_CONTRACT_MAX_STALE_DAYS}일이다"
    )


# ─── ①-B **살아 있는** FRED 주입 경로 (B30 재수리, 2026-07-14) ──────────────

def test_the_live_prompt_path_does_not_inject_stale_fred():
    """★ **B30의 첫 수리는 죽은 경로를 막았다.**

    18-①위원회가 오염원으로 지목한 `theory_comparator._get_fred_for_theories`는
    **수리 전에도 빈 dict를 반환했다**(cc2a0af 실측 0개). 게이트를 달아도 막을 게 없었다.
    그런데 계통도는 B30을 **`fixed`**로 찍어놨고, **두 달 가까이 «고쳤다»는 말이 틀려 있었다.**

    **살아 있는 주입 경로는 `intel_analyzer._get_fred_data`다** —
    `build_intel_context`(intel_analyzer:2196)가 불러 **LLM 프롬프트에 넣는다.**
    2026-07-14 실측: `Brent Crude Oil Price · 2024-01-01 · 80.22` **12행 반환.**
    위원회가 인용한 바로 그 줄이다.

    ⚠️ 재는 것은 "오늘 주입이 0건이다"가 아니라 **불변식**이다 —
    FRED가 최신화되면 주입이 되살아나야 **맞다.**
    """
    import services.intel_analyzer as ia
    from tests.conftest import intel_db

    # ⚠️ **실 DB를 물린다.** worktree(구 커밋)엔 `db/`가 없어서(gitignore) 그냥 두면
    #    빈 DB를 읽고 **0행 → 루프 미실행 → 공허한 통과**가 된다. 그러면 이 테스트는
    #    "결함이 없다"를 증명하는 게 아니라 **아무것도 증명하지 않는다.**
    #    2026-07-14: 이 함정에 두 번 빠졌다 — 「엉뚱한 이유로 딴 초록불」.
    ia._INTEL_DB = str(intel_db())

    rows = ia._get_fred_data(["middle_east"], ["energy"])
    today = date.today()
    for r in rows:
        stale = (today - date.fromisoformat(r["date"])).days
        assert stale <= _CONTRACT_MAX_STALE_DAYS, (
            f"{r['series_id']}({r['date']})가 {stale}일 낡았는데 **LLM 프롬프트에 주입됐다** "
            f"— «실측 · 최근 추세»라며. 계약 {_CONTRACT_MAX_STALE_DAYS}일"
        )
