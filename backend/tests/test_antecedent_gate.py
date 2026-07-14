"""전건 게이트 음성 회귀 — B28.

**«X가 증가하면 Y가 오른다»에서 X가 안 일어났으면 그 예측은 참도 거짓도 아니다.**

그런데 `prediction_scorer`는 **X를 한 번도 안 읽었다.** 자기 주석에 자백해 놨다:

    "채점된 예측 전건(independent_var)의 발생 여부를 판정할 계기가 없다."

그래서 「호르무즈 긴장 → 유가 상승」 예측이 **호르무즈에서 아무 일도 없었는데**
유가가 올랐다는 이유로 **HIT**가 됐다. **적중률 59.8%가 그렇게 만들어졌고,
채점된 82건(HIT 49 · MISS 33)이 전부 무효가 됐다. 간판 = 0/0.**

## 왜 ACLED로는 못 고치나 (실측 2026-07-14)

    ACLED                   랙 365일  → **만기의 전건 창에 데이터가 아예 없다**
    GDELT geo_country_daily 랙  1일   → 그러나 r(분쟁, 보도총량) = **0.959**(IRN)
                                        r(GDELT 분쟁, ACLED 실제 폭력) = **0.019**(IRN)
                                        → **보도량이지 분쟁이 아니다.** severity IV와 같은 병
    BP 북한 도발             랙 11일  → **사람이 코딩한 «사건»**. 유일하게 쓸 수 있다

**전건도 신선하고 DV(KRW·^KS11·ITA)도 신선한 쌍은 북한뿐이다.**

⚠️ 이 파일은 DB를 읽는다 — `conftest.intel_db()`(`VERIFY_REAL_ROOT` 존중).
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

# ⚠️ **증명 등급 ABSENT를 정직하게 받는다** (2026-07-14).
# `antecedent.py`는 **새 모듈**이다 — 구 코드엔 없다. 엔진에 **전건을 말할 단어가 없었다.**
# 그건 「어휘 신설」이지 「결함 수리」가 아니다(B02/B25와 같은 종류).
# **하류 귀결이 다르다: 기존 974건은 소급 재분류할 수 없다.** 새 예측부터 적용된다.
#
# 그래도 import는 방어한다 — 구 코드 위에서 **수집이 죽으면 다른 테스트까지 못 돈다**(패턴 V).
pytest.importorskip("services.antecedent", reason="antecedent 없음 — 수리 전 코드(어휘 신설)")

from services import antecedent as A  # noqa: E402
from tests.conftest import intel_db  # noqa: E402


@pytest.fixture
def con():
    c = sqlite3.connect(f"file:{intel_db()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ─── 파서 ────────────────────────────────────────────────────────────────

def test_noun_phrase_is_not_an_antecedent():
    """★ **명사구로는 참·거짓을 물을 수 없다.**

    이게 병의 뿌리다 — DV는 정량 7필드인데 IV는 TEXT 한 칸이었다.
    """
    for iv in ("WTI 유가", "미국의 억지 의지", "한국 부사관 충원율 (X, %)"):
        assert A.parse(iv, "hormuz") is None, f"명사구가 전건으로 통과했다: {iv!r}"


def test_a_measurable_antecedent_parses():
    """계량 + 방향 + (임계|기준선)이 있으면 전건이다."""
    a = A.parse("호르무즈 지역의 ACLED 분쟁 건수가 월간 100 건 이상", "hormuz")
    assert a is not None
    assert (a.metric, a.direction, a.threshold, a.window_days) == ("violence_count", "up", 100.0, 30)

    b = A.parse("북한 미사일 발사 건수 (월별) 증가", "north_korea")
    assert b is not None and b.metric == "provocation_count" and b.mode == "baseline"


def test_metrics_are_a_closed_catalog():
    """**닫힌 목록이다.** LLM이 계량을 지어내도 목록 밖이면 IV가 아니다.

    `severity` 합은 은퇴했다 — r(SUM(severity), 행수)가 0.984였고, **IV의 정체가
    「적재 행 수」**였다. 목록을 열어두면 그 병이 다시 들어온다.
    """
    assert set(A._IV_METRICS) == {"violence_count", "fatalities", "provocation_count"}
    assert A.parse("severity 합계가 증가", "hormuz") is None
    assert A.parse("GDELT 물리충돌 보도 건수 증가", "hormuz") is None  # 보도량 ≠ 분쟁


# ─── 판정 ────────────────────────────────────────────────────────────────

def test_missing_data_is_undecidable_not_zero(con):
    """★ **«수집이 없다»를 «사건이 0이다»로 바꿔치기하지 않는다.**

    `fill_value=0`이 저지른 짓이 바로 그것이다(B01 — 수집 공백을 «전쟁 없음»으로 위조).
    그리고 ACLED는 **365일 늦다** — 오늘 기준 전건 창에 데이터가 없다.
    """
    a = A.Antecedent("violence_count", "hormuz", "up", 30, 100.0)
    verdict, obs = A.verify(con, a, date.today())
    assert verdict == "UNDECIDABLE", (
        f"ACLED 랙 365일인데 «{verdict}»로 판정했다 — 데이터가 없는데 답을 지어냈다"
    )
    assert obs is None


def test_the_only_fresh_antecedent_actually_decides(con):
    """★ **북한 도발은 오늘 판정된다** — 전건도 신선하고 DV도 신선한 유일한 쌍.

    이게 track record 0/0을 깨는 유일한 길이다(실측: ACLED 365일 · GDELT는 보도량).
    """
    a = A.Antecedent("provocation_count", "north_korea", "up", 30, 1.0)
    verdict, obs = A.verify(con, a, date.today())
    assert verdict in ("MET", "NOT_MET"), f"북한 도발도 판정 못 했다: {verdict}"
    assert obs is not None, "도발 관측값이 없다 — BP 커넥터가 죽었나"


# ─── 채점기 게이트 (★ 핵심) ────────────────────────────────────────────────

def test_the_scorer_refuses_to_score_when_the_antecedent_did_not_happen():
    """★★ **전건이 안 일어났으면 DV를 채점하지 않는다.**

    구 채점기는 `independent_var`를 **한 번도 안 읽었다.** 그래서 전건이 안 일어났어도
    Y만 보고 HIT/MISS를 매겼다 — **공허하게 참인 예측에 적중을 줬다.**

    이 테스트는 그 행동을 직접 잡는다: 전건이 `NOT_MET`이면 상태가
    `ANTECEDENT_NOT_MET`이어야 하고, **적중으로도 오답으로도 세지 않는다.**
    """
    from services import prediction_scorer as ps

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE bp_provocations (id INTEGER PRIMARY KEY, event_date TEXT)"
    )
    # 창(30일) 안에 도발 0건 · 직전 창에는 3건 → "증가"는 **일어나지 않았다**
    c.executemany(
        "INSERT INTO bp_provocations (event_date) VALUES (?)",
        [("2026-05-20",), ("2026-05-25",), ("2026-06-01",)],
    )
    row = {
        "prediction_id": "p1", "iv_metric": "provocation_count", "iv_region": "north_korea",
        "iv_direction": "up", "iv_threshold": None, "iv_window_days": 30,
    }
    gate = ps._antecedent_gate(c, row, date(2026, 7, 14))
    assert gate is not None, "전건이 안 일어났는데 채점을 통과시켰다 — 공허한 참에 적중을 준다"
    assert gate[0] == "ANTECEDENT_NOT_MET", f"상태가 틀렸다: {gate}"


def test_an_unstructured_antecedent_cannot_be_scored():
    """전건이 구조화 안 됐으면 **채점하지 않는다** — 「모른다」를 「일어났다」로 안 바꾼다."""
    from services import prediction_scorer as ps

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    row = {"prediction_id": "p2", "iv_metric": None, "iv_region": None,
           "iv_direction": None, "iv_threshold": None, "iv_window_days": None}
    gate = ps._antecedent_gate(c, row, date(2026, 7, 14))
    assert gate is not None and gate[0] == "UNRESOLVED"
