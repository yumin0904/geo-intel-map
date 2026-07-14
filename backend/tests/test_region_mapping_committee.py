"""권역 매핑 위원회 (2026-07-14) 회귀 그물.

〔무엇이 있었나〕 엔진은 권역을 세 층에서 각자 다르게 정의하고 있었다:
  저장층  config/regions.yaml + region_for_event  (좌표·행위자·국가 → 코드)
  검정층  hypothesis_extractor._REGION_MAP        (문장 키워드 → 코드)
  보정층  correlation._REGION_ALIAS               (둘 사이의 다리 — 항목 1개)
다리가 하나뿐이라 우크라이나만 건너왔다. 북한·남중국해는 못 건너왔고, 그 결과:
  · "북한"·"dprk" → korean_peninsula (북한 이벤트 **0건**인 권역) → 예측 71건이 misroute,
    23건이 Granger 실행 — **폭력 이벤트 2건짜리 시계열에 대고**. 14건이 '상관' 등급을 받았다.
  · "남중국해" → taiwan_strait. south_china_sea(681행)는 검정층이 도달할 수 없었다.
  · eastern_europe는 event_archive에 **0행**인데 예측 160건이 발행됐다(alias가 우연히 구제).

〔더 아래에 있던 것 — 오늘의 최대 결함〕
  D4 게이트가 `n_obs >= 40`으로 데이터 충분성을 판정하는데, `n_obs`는 **달력 칸 수**다.
  그리고 sparse 가드가 비제로 10일 미만인 계열을 **주간 리샘플**로 접는다 → 411일이 59주 →
  `59 >= 40` → **"데이터 충분" 통과**. **얇아서 접은 계열이, 접었다는 이유로 충분해졌다.**
  가드의 분모가 정보가 아니라 달력이었다(패턴 H).

〔채점기〕 `score_prediction`은 `independent_var`를 **한 번도 읽지 않는다** — HIT/MISS가
  100% 티커 등락으로 결정된다. 그래서 UNQUANTIFIABLE 가설(엔진이 스스로 "못 잰다"고 선언한
  것)이 GLD·KRW=X에 물려 자동 채점 대기 중이었다(43건, 8/15 만기 — 전건 동결).
"""
from __future__ import annotations

from datetime import date

import pytest
import yaml

from services.cascade.correlation import (
    _IV_KINDS,
    _MIN_INFORMATIVE_DAYS,
    InsufficientCoverageError,
    InsufficientInformationError,
    _load_event_series,
)
from services.hypothesis_extractor import _REGION_MAP, _assert_region_map_grounded
from services.region import _load_regions

# 정직한 검정 창 — ACLED 랙(365일)이 정한 오른쪽 끝. 2025-07-15부터는 수집 구멍이다.
WIN_START, WIN_END = date(2024, 5, 31), date(2025, 7, 14)


def _route(text: str) -> str | None:
    """_REGION_MAP의 first-match 라우팅 재현 (hypothesis_extractor 내부 로직과 동형)."""
    t = text.lower()
    for keywords, code in _REGION_MAP:
        if any(k.lower() in t for k in keywords):
            return code
    return None


# ── G1: 검정층 어휘가 저장층에 종속되는가 ─────────────────────────────────────

def test_g1_region_map_is_grounded_in_regions_yaml():
    """검정층이 뱉는 모든 권역 코드는 regions.yaml에 실재해야 한다.

    `eastern_europe`가 정확히 이걸 어겼다 — event_archive 0행짜리 코드로 예측 160건.
    """
    defined = {k for k, v in _load_regions().items() if isinstance(v, dict)}
    used = {code for _, code in _REGION_MAP}
    assert used <= defined, f"regions.yaml에 없는 권역을 검정층이 가리킨다: {sorted(used - defined)}"


def test_g1_negative_orphan_code_raises_import_error():
    """음성 테스트 — 가드가 자기 표적에 실제로 발화하는가(패턴 E)."""
    import services.hypothesis_extractor as he

    he._REGION_MAP.append((["가짜키워드"], "atlantis"))
    try:
        with pytest.raises(ImportError, match="atlantis"):
            _assert_region_map_grounded()
    finally:
        he._REGION_MAP.pop()  # 오염 원복


def test_sahel_is_registered():
    """sahel은 스크립트가 DB에 직접 UPDATE한 코드였다(regions.yaml 밖) →
    region_for_event가 영원히 부여 못 해 신규 이벤트가 NULL로 증발했다(200행 실측)."""
    assert "sahel" in _load_regions(), "sahel이 regions.yaml에서 사라졌다 — 신규 사헬 이벤트가 다시 증발한다"


# ── 라우팅: 가설이 옳은 권역으로 가는가 ───────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("북한의 미사일 도발 빈도", "north_korea"),
    ("평양의 핵실험 재개", "north_korea"),
    ("북한 라자루스 그룹의 암호화폐 탈취", "north_korea"),
    ("한반도 긴장이 KOSPI에 미치는 영향", "korean_peninsula"),
    ("남한 시위 건수", "korean_peninsula"),
    ("남중국해 스프래틀리 충돌", "south_china_sea"),
    ("대만해협 긴장과 TSMC", "taiwan_strait"),
    ("우크라이나 전선 격화", "ukraine"),
    ("러시아의 동유럽 압박", "ukraine"),
])
def test_hypothesis_routing(text, expected):
    assert _route(text) == expected, f"'{text}' → {_route(text)} (기대 {expected})"


def test_routing_does_not_leak_shipbuilding_to_north_korea():
    """'조선'은 조선업(shipbuilding) 오탐이 실측됐다 — '조선민주주의'로 좁혔다."""
    assert _route("조선업계 수주 증가") != "north_korea"


def test_no_phantom_eastern_europe():
    """eastern_europe는 event_archive에 0행이다. 검정층이 다시 뱉으면 안 된다."""
    assert _route("우크라이나 전선") == "ukraine"
    assert "eastern_europe" not in {code for _, code in _REGION_MAP}


# ── G2: 정보량 게이트 — 오늘의 핵심 ───────────────────────────────────────────

@pytest.mark.parametrize("region", ["north_korea", "korean_peninsula", "taiwan_strait"])
def test_g2_thin_series_raises_not_returns_zeros(region):
    """정보량 미달 권역은 **던져야** 한다 — 조용히 계열을 돌려주면 p>=0.05가 되고
    그것이 "관계 없음"(D1)으로 위조된다. 이것은 '측정 불가'(D4)다.

    실측(창 411일, violence_count): taiwan_strait 1건/1일 · north_korea 7건/6일 ·
    korean_peninsula 2건/2일. 구 게이트는 이걸 주간으로 접어 n=59로 만들고 통과시켰다.
    """
    with pytest.raises(InsufficientInformationError):
        _load_event_series(region, WIN_START, WIN_END, None, "violence_count")


def test_g2_routes_to_d4_not_d1():
    """상위 러너 3곳이 InsufficientCoverageError를 잡아 D4_INSUFFICIENT로 라우팅한다.
    새 예외가 그 계보에 있어야 '못 쟀다'로 분류된다 — 상속이 끊기면 D1로 오분류된다."""
    assert issubclass(InsufficientInformationError, InsufficientCoverageError)


@pytest.mark.parametrize("region", ["ukraine", "middle_east", "sahel", "hormuz", "south_china_sea"])
def test_g2_negative_healthy_regions_still_pass(region):
    """음성 테스트 — 가드가 정상 권역까지 물면 그건 가드가 아니라 재갈이다."""
    series = _load_event_series(region, WIN_START, WIN_END, None, "violence_count")
    nonzero = int((series.dropna() > 0).sum())
    assert nonzero >= _MIN_INFORMATIVE_DAYS


def test_g2_threshold_is_config_driven():
    """문턱은 매직넘버가 아니라 config가 원천이어야 한다(헌법 §7)."""
    thr = yaml.safe_load(
        (__import__("pathlib").Path(__file__).resolve().parents[1]
         / "config" / "granger_thresholds.yaml").read_text(encoding="utf-8")
    )
    assert thr["min_informative_days"] == _MIN_INFORMATIVE_DAYS


# ── provocation_count: 북한을 검정 가능하게 만든 제3 IV ────────────────────────

def test_provocation_count_is_declared():
    assert "provocation_count" in _IV_KINDS


def test_provocation_count_makes_north_korea_testable():
    """violence_count로는 7건/6일(측정 불가)이던 북한이, 도발 신호로는 91건/76일이 된다.

    룰 이름은 `north_korea_missile_to_krw`인데 IV는 전투를 세고 있었다 —
    **룰이 묻는 질문과 엔진이 재는 것이 달랐다**(패턴 I: 구성 타당도는 질문에 상대적이다).
    """
    series = _load_event_series("north_korea", WIN_START, WIN_END, None, "provocation_count")
    nonzero = int((series.dropna() > 0).sum())
    assert nonzero >= _MIN_INFORMATIVE_DAYS, f"북한 도발 IV가 다시 얇아졌다(비제로 {nonzero}일)"
    assert "weekly" not in (series.name or ""), "주간 전환됐다면 정보량이 부족하다는 뜻"


def test_provocation_count_is_actor_typed_only():
    """actor_match 없는 권역엔 적용 불가 — 이 IV는 '누가 신호를 보냈나'를 센다."""
    for region in ("ukraine", "middle_east"):
        with pytest.raises(ValueError, match="행위자형"):
            _load_event_series(region, WIN_START, WIN_END, None, "provocation_count")


def test_provocation_count_is_not_a_volume_proxy():
    """패턴 N — D2가 의무화한 대조. **처방도 재라.**

    〔측정 방법이 결과를 바꿨다 — 이것 자체가 발견이다〕
    같은 IV를 세 번 재서 세 값이 나왔다: 0.85(처방석) · 0.698(raw SQL 조인) ·
    **0.922**(검정 계열). raw SQL은 사건 있는 날만 뽑아 인덱스가 어긋나고 커버리지 NaN이
    빠져 **상관을 과소평가한다**. 패턴 N은 **검정에 실제 들어가는 계열**로만 잰다.

    〔문턱의 근거〕 0.95는 은퇴한 severity(1.000)와 violence_count(0.994)를 잡는 선이다.
    provocation_count의 0.922는 그 아래지만 **낮지 않다** — 공표 대상이며, D2가 violence_count
    에 건 조건(단독 결론 시 부피 동행 동봉)을 똑같이 받는다.

    〔진짜 대조군은 사망자다〕 부피 상관은 north_korea 권역의 구조(적재분 대부분이 SD)에서
    어느 정도 불가피하다. 병이 **옮겨 심어졌는지**를 가르는 신호는 사망자와의 직교성이다 —
    r(사망자)가 0.5를 넘으면 이 IV는 fatalities의 대리물이 된 것이고, 2종 병기가 무너진다.
    """
    import sqlite3

    import pandas as pd

    from services.cascade.correlation import _DB_PATH

    iv = _load_event_series("north_korea", WIN_START, WIN_END, None, "provocation_count")

    con = sqlite3.connect(_DB_PATH)
    rows = pd.read_sql_query(
        """SELECT DATE(timestamp) day, COUNT(*) n FROM event_archive
           WHERE region_code='north_korea' AND DATE(timestamp) BETWEEN ? AND ?
           GROUP BY day""",
        con, params=(WIN_START.isoformat(), WIN_END.isoformat()), parse_dates=["day"],
    ).set_index("day")["n"]
    con.close()

    joined = pd.concat([iv.rename("iv"), rows], axis=1).fillna(0)
    r_volume = joined["iv"].corr(joined["n"])
    assert r_volume < 0.95, (
        f"provocation_count가 적재 행 수의 대리물로 변질됐다(r={r_volume:.4f} ≥ 0.95). "
        f"구 severity IV의 병(r=1.000)이 옮겨 심어진 것이다 — 수집 파이프라인을 의심하라."
    )

    # 진짜 대조군 — 사망자와 직교해야 2종 병기가 성립한다.
    # ⚠️ 여기서 `_load_event_series(..., "fatalities")`를 쓸 수 없다 — **G2가 거부한다**.
    #    north_korea는 사망자가 거의 0이라 비제로일이 문턱 미만이기 때문이다. 그 사실 자체가
    #    이 IV의 존재 이유를 확증한다: **북한에서 검정 가능한 IV는 provocation_count 하나뿐**이고,
    #    도발은 '사람이 안 죽는 신호 행위'라서 사망자 IV로는 원리상 안 잡힌다.
    #    대조군 검사는 검정용이 아니라 상관 확인용이므로 raw 계열로 잰다.
    con = sqlite3.connect(_DB_PATH)
    fatal = pd.read_sql_query(
        """SELECT DATE(timestamp) day,
                  SUM(COALESCE(CAST(json_extract(payload,'$.fatalities') AS INT),0)) f
           FROM event_archive
           WHERE region_code='north_korea' AND DATE(timestamp) BETWEEN ? AND ?
           GROUP BY day""",
        con, params=(WIN_START.isoformat(), WIN_END.isoformat()), parse_dates=["day"],
    ).set_index("day")["f"]
    con.close()

    r_fatal = pd.concat([iv.rename("iv"), fatal], axis=1).fillna(0).corr().loc["iv", "f"]
    assert abs(r_fatal) < 0.5, (
        f"provocation_count가 사망자의 대리물이 됐다(r={r_fatal:.4f}). "
        f"도발 신호는 '사람이 안 죽는 행위'를 세는 것이 존재 이유다 — 대조군이 무너졌다."
    )


# ── 채점기: UNQUANTIFIABLE이 티커로 채점되지 않는가 ───────────────────────────

def test_unquantifiable_hypotheses_are_not_auto_scorable():
    """엔진이 '정량화 불가'로 분류한 가설에 ticker가 물리면 scorable=True가 됐다.
    그리고 `score_prediction`은 independent_var를 **읽지 않는다** — 금값이 오르면 HIT다.

    "북한 내 AI 접근성 → GLD" 같은 가설 43건이 8/15 만기로 대기 중이었다(전건 동결).
    헌법 §18-A.2가 이미 명령한 것의 집행이다 — 이 파일 docstring(L16-17)이 규칙을
    선언해 놓고 지키지 않았다(패턴 E).
    """
    from services.prediction_instrument import build_prediction

    class _Spec:
        h1 = "북한 내 AI 접근성이 증가하면 금값이 상승한다"
        independent_var = "북한의 AI 기술 접근성(UNVERIFIED)"
        dependent_var = "금 ETF"
        ticker = "GLD"
        data_signature = "UNQUANTIFIABLE"
        region_code = "north_korea"
        inference_grade = "기술적"
        exploratory = False
        theory_grounded = False
        controlled = False
        best_lag = None
        method_result = {}

    rec = build_prediction(_Spec(), "북한 AI 접근성과 금값")
    assert rec is not None, "기록 자체는 남아야 한다 — 삭제가 아니라 채점 제외다"
    assert rec.scorable is False, (
        "UNQUANTIFIABLE 가설이 자동 채점 대상으로 남았다 — "
        "선행절을 관측하지 못한 채 티커 등락으로 HIT를 준다."
    )
