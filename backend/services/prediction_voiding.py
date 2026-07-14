"""예측 회수·표시의 **단일 경로** — B33 구조 수리.

## 왜 이 파일이 생겼나

`voided_reason`과 `eligible_for_calibration`은 **독립 플래그**였다. 회수를 집행하는 코드가
`services/`·`jobs/` 어디에도 없고, **회수할 때마다 일회성 스크립트를 손으로 짰다.**
그래서 이런 일이 생겼다:

  · `scripts/triage_qualitative_predictions.py` — `voided_reason`은 쓰는데
    `eligible_for_calibration`은 **한 번도 안 건드린다.**
  · 결과: 회수 판정을 받은 예측 **144건이 `eligible=1`로 남았고**, 그중 1건
    (`d4d30294`·CL=F·HIT, IV가 **따옴표 한 글자**)이 **간판 위에 올라 있었다.**
    정직한 간판은 42.9%가 아니라 40.0%였다(2026-07-14 반박석 적발).

**기억에 의존하는 불변식은 불변식이 아니다.** 다음 회수도 똑같이 잊는다.

## 회수(retraction) vs 표시(marking) — 뭉개면 안 된다

07-13 판례: `diluted_iv`는 *"회수하지 않고 표시만"*이다(진짜 무력분쟁이 실재하므로).
`grade_demoted`도 등급 강등이지 회수가 아니다.

**전부를 `eligible=0`으로 밀면 회수 아닌 것까지 죽인다** — 2026-07-14에 실제로 그럴 뻔했고
(반박석의 일괄 권고), 의장이 144건을 회수 137 / 표시 7로 갈라서 막았다.

그래서 이 모듈은 두 가지를 **이름으로 가른다**:
  `void()`  — 회수. `eligible_for_calibration = 0`
  `mark()`  — 표시. eligible 불변. 사유만 기록한다.

불변식은 `tests/test_voiding_invariant.py`가 감시한다 — **회수 사유가 붙은 행에
`eligible=1`이 남아 있으면 실패한다.** 스크립트를 손으로 짜도 이 그물에 걸린다.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

# 회수 사유 접두어 — 이 계열이 붙으면 track record 분모에서 뺀다.
# 새 사유를 만들면 **여기 등재하라.** 등재를 잊으면 invariant 테스트가 잡지 못한다
# (그 자체가 패턴 H다 — 가드의 사정권을 넓혀둔다).
RETRACTION_KEYS: tuple[str, ...] = (
    "fabricated_input",
    "construct_invalid_iv",       # _narrative 포함 (부분일치)
    "epistemic_laundering",
    "unquantifiable",
    "antecedent_unverified",
    "antecedent_undecidable",
    "정직한 무가설 선언",
    "캡처 필터 비가설 조각 기각",
)

# 표시 사유 — 회수가 **아니다**. eligible을 내리지 않는다 (07-13 판례).
MARKING_KEYS: tuple[str, ...] = (
    "diluted_iv",
    "grade_demoted",
)


def is_retraction(voided_reason: str | None) -> bool:
    """이 사유가 회수인가(=간판에서 빼야 하는가)."""
    if not voided_reason:
        return False
    return any(k in voided_reason for k in RETRACTION_KEYS)


def _append(con: sqlite3.Connection, pid: str, reason: str) -> None:
    row = con.execute(
        "SELECT voided_reason FROM prediction_log WHERE prediction_id = ?", (pid,)
    ).fetchone()
    prev = row[0] if row else None
    if prev and reason in prev:
        return  # idempotent — 같은 사유를 두 번 적지 않는다
    merged = f"{prev} | {reason}" if prev else reason
    con.execute(
        "UPDATE prediction_log SET voided_reason = ? WHERE prediction_id = ?", (merged, pid)
    )


def void(con: sqlite3.Connection, prediction_ids: Iterable[str], reason: str) -> int:
    """회수 — 사유를 기록하고 **간판에서 뺀다**(`eligible_for_calibration = 0`).

    `scorable`은 건드리지 않는다: 채점 기록은 보존한다("회수는 삭제 아님" 판례).
    행 삭제도 하지 않는다 — 오염된 IV가 70% 맞았다는 사실 자체가 증거다.
    """
    if not is_retraction(reason):
        raise ValueError(
            f"회수 사유가 아니다: {reason[:40]!r}\n"
            f"  · 회수라면 RETRACTION_KEYS에 등재하라(그래야 invariant 테스트가 지킨다).\n"
            f"  · 표시라면 mark()를 써라 — eligible을 내리지 않는다."
        )
    n = 0
    for pid in prediction_ids:
        _append(con, pid, reason)
        con.execute(
            "UPDATE prediction_log SET eligible_for_calibration = 0 WHERE prediction_id = ?",
            (pid,),
        )
        n += 1
    return n


def mark(con: sqlite3.Connection, prediction_ids: Iterable[str], reason: str) -> int:
    """표시 — 사유만 기록한다. **간판에서 빼지 않는다.**

    `diluted_iv`처럼 "인용 시 구성비를 동봉하라"는 경고이지 회수가 아닌 경우다(07-13 판례).
    """
    if is_retraction(reason):
        raise ValueError(
            f"회수 사유를 mark()로 쓸 수 없다: {reason[:40]!r}\n"
            f"  회수라면 void()를 써라 — 그래야 간판에서 빠진다."
        )
    n = 0
    for pid in prediction_ids:
        _append(con, pid, reason)
        n += 1
    return n


def leaked(con: sqlite3.Connection) -> list[str]:
    """불변식 위반 — 회수 사유가 붙었는데 아직 간판에 남은 행."""
    return [
        r[0]
        for r in con.execute(
            "SELECT prediction_id, voided_reason FROM prediction_log "
            "WHERE voided_reason IS NOT NULL AND eligible_for_calibration = 1"
        )
        if is_retraction(r[1])
    ]
