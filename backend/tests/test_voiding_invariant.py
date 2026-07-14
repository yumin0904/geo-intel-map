"""회수 불변식 그물 — B33.

**회수 판정을 받은 예측이 간판에 남아 있으면 안 된다.**

이 그물이 없어서 실제로 새어 나갔다(2026-07-14 반박석 적발): `voided_reason`과
`eligible_for_calibration`이 독립 플래그이고 회수를 집행하는 코드가 없어서 **회수할 때마다
일회성 스크립트를 손으로 짰다.** 그중 `triage_qualitative_predictions.py`는 `voided_reason`만
쓰고 `eligible`을 안 내렸다 → **회수된 예측 144건이 간판 모수에 남았고, 그중 1건은
이미 채점돼 HIT로 간판 위에 있었다**(IV가 따옴표 한 글자인 행이었다).

정직한 간판은 42.9%가 아니라 40.0%였다. **기억에 의존하는 불변식은 불변식이 아니다.**
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.prediction_voiding import (
    MARKING_KEYS,
    RETRACTION_KEYS,
    is_retraction,
    leaked,
    mark,
    void,
)

from tests.conftest import intel_db

DB = intel_db()  # 검증기가 GEO_INTEL_DB로 백업을 물릴 수 있다


def test_no_retracted_prediction_remains_on_the_board():
    """실 DB 불변식 — 회수 사유가 붙은 행에 eligible=1이 남아 있지 않다."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        bad = leaked(con)
    finally:
        con.close()
    assert not bad, (
        f"회수됐는데 간판에 남은 예측 {len(bad)}건: {bad[:5]}\n"
        f"→ services.prediction_voiding.void()를 써라. 손으로 UPDATE하면 이 그물에 걸린다."
    )


def test_retraction_and_marking_are_not_conflated():
    """회수와 표시는 다른 것이다 — 뭉개면 회수 아닌 것까지 죽인다(07-13 판례).

    `diluted_iv`는 "회수하지 않고 표시만"이다. 2026-07-14에 반박석이 일괄 전파를
    권고했고, 그대로 걸었으면 표시 7건까지 죽었다.
    """
    for k in RETRACTION_KEYS:
        assert is_retraction(f"{k}:2026-01-01:테스트")
    for k in MARKING_KEYS:
        assert not is_retraction(f"{k}:2026-01-01:테스트"), f"{k}는 표시이지 회수가 아니다"


@pytest.fixture
def mem() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE prediction_log ("
        " prediction_id TEXT PRIMARY KEY, voided_reason TEXT,"
        " eligible_for_calibration INTEGER, scorable INTEGER, status TEXT)"
    )
    con.executemany(
        "INSERT INTO prediction_log VALUES (?,?,?,?,?)",
        [("p1", None, 1, 1, "HIT"), ("p2", None, 1, 1, "PENDING")],
    )
    return con


def test_void_drops_eligible_and_preserves_the_record(mem: sqlite3.Connection):
    """회수는 간판에서 빼되 **기록은 보존한다**(scorable·status 불변)."""
    n = void(mem, ["p1"], "fabricated_input:2026-07-14:테스트")
    assert n == 1
    row = mem.execute(
        "SELECT eligible_for_calibration, scorable, status, voided_reason "
        "FROM prediction_log WHERE prediction_id='p1'"
    ).fetchone()
    assert row[0] == 0, "간판에서 빠져야 한다"
    assert row[1] == 1, "scorable은 불변 — 채점 기록은 보존한다"
    assert row[2] == "HIT", "status도 불변 — 회수는 삭제가 아니다"
    assert "fabricated_input" in row[3]
    assert not leaked(mem)


def test_mark_does_not_touch_the_board(mem: sqlite3.Connection):
    """표시는 사유만 적는다 — eligible 불변."""
    mark(mem, ["p2"], "diluted_iv:2026-07-14:구성비 동봉할 것")
    row = mem.execute(
        "SELECT eligible_for_calibration, voided_reason FROM prediction_log "
        "WHERE prediction_id='p2'"
    ).fetchone()
    assert row[0] == 1, "표시는 회수가 아니다 — 간판에 남는다"
    assert "diluted_iv" in row[1]
    assert not leaked(mem), "표시는 불변식 위반이 아니다"


def test_the_two_paths_cannot_be_swapped(mem: sqlite3.Connection):
    """이름을 잘못 고르면 **터진다.** 조용히 잘못 집행되지 않는다."""
    with pytest.raises(ValueError, match="회수 사유가 아니다"):
        void(mem, ["p1"], "diluted_iv:표시인데 void로 부름")
    with pytest.raises(ValueError, match="회수 사유를 mark"):
        mark(mem, ["p1"], "fabricated_input:회수인데 mark로 부름")


def test_leak_is_actually_detected(mem: sqlite3.Connection):
    """음성 테스트 — 손으로 UPDATE해서 새면 정말 잡히는가.

    이것이 2026-07-13에 실제로 일어난 일이다: 스크립트가 voided_reason만 썼다.
    """
    mem.execute(
        "UPDATE prediction_log SET voided_reason='epistemic_laundering:손으로 씀' "
        "WHERE prediction_id='p1'"
    )  # eligible은 안 내렸다 ← 그때 그대로
    assert leaked(mem) == ["p1"], "이 누수를 못 잡으면 그물이 아니다"
