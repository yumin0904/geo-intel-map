"""이중적재 재발 그물 — **두 테이블 전부**.

B01위원회(2026-07-14 오전)가 `event_archive`의 ×1.9 이중적재를 디듑했다. 그리고 재발
감시식을 만들었다. **그 감시식은 `event_archive`만 봤다.**

그날 밤 실측: `events`에 이중적재가 **53,951행(18.1%) 그대로 살아 있었다.** 아침 디듑도
archive만 청소했고, 감시식도 archive만 봐서 **아무도 못 봤다.** 그동안 `events`를 읽는
발행 표면(api/stats·api/layers·cascade/engine)이 부풀린 숫자를 내보내고 있었다 —
너울 라이브 정문의 "수집·정규화한 지정학 이벤트 **296,885**"(정직한 값 243,469).

**교훈(패턴 H, 7번째): 가드가 무엇을 보는지가 아니라 무엇을 *안 보는지*를 물어라.**
테이블을 하나라도 빼면 그 테이블이 병의 은신처가 된다. 그래서 이 테스트는 테이블 목록을
하드코딩하지 않고 **적재 대상 테이블 전수를 순회**한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests.conftest import intel_db

DB = intel_db()  # 검증기가 GEO_INTEL_DB로 백업을 물릴 수 있다

# 이벤트 행을 담는 테이블 전수. 새 테이블이 생기면 여기 추가한다 —
# 빠뜨리면 그 테이블이 다음 은신처다.
EVENT_TABLES = ("events", "event_archive")

# B23 감시식과 같은 정본 키. 키가 다르면 답도 다르다.
KEY = "timestamp || severity || COALESCE(title,'') || COALESCE(description,'') || payload"

# 월별 허용 상한. 1.05를 넘으면 재적재를 의심한다(정상 수집은 1.00~1.01).
MAX_DUP = 1.05


@pytest.mark.parametrize("table", EVENT_TABLES)
def test_no_double_loading(table: str) -> None:
    """어떤 달도 중복비 1.05를 넘지 않는다."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        bad = con.execute(
            f"""
            SELECT strftime('%Y-%m', timestamp) AS m,
                   COUNT(*) AS n,
                   ROUND(CAST(COUNT(*) AS REAL) / COUNT(DISTINCT {KEY}), 3) AS dup
              FROM {table}
             GROUP BY 1
            HAVING dup > {MAX_DUP}
             ORDER BY dup DESC
            """
        ).fetchall()
    finally:
        con.close()

    assert not bad, (
        f"{table}에 이중적재 재발: "
        + " · ".join(f"{m} {n:,}행 dup={d}" for m, n, d in bad)
        + f"\n→ scripts/dedup_events_table.py 로 디듑하고 적재 경로의 멱등성을 확인할 것"
    )


def test_guard_covers_every_event_table() -> None:
    """가드의 사정권 자체를 검사한다 — 이벤트 테이블이 새로 생겼는데 목록에 없으면 실패.

    이것이 이 파일의 진짜 요점이다. B23 감시식은 문법적으로 옳았고 `event_archive`에서
    정직하게 1.0을 뱉었다. **틀린 것은 사정권이었다.** 가드가 자기 사정권을 검사하지 않으면
    다음 테이블에서 같은 일이 반복된다.
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        names = {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        # 이벤트 행의 서명: timestamp·severity·payload를 모두 가진 테이블
        event_like = set()
        for t in names:
            cols = {c[1] for c in con.execute(f"PRAGMA table_info({t})")}
            if {"timestamp", "severity", "payload"} <= cols:
                event_like.add(t)
    finally:
        con.close()

    missed = event_like - set(EVENT_TABLES)
    assert not missed, (
        f"이벤트 테이블인데 이중적재 감시 밖: {sorted(missed)}\n"
        f"→ EVENT_TABLES에 추가하라. 빠진 테이블이 병의 은신처가 된다(패턴 H)."
    )
