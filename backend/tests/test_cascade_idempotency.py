"""캐스케이드 멱등성 그물 — B31.

`cascade_links.target_event_id`가 **매 런 새 랜덤 UUID**였다(`uuid.uuid4()`).
그런데 테이블에는 `UNIQUE(source_event_id, target_event_id, rule_id)`가 걸려 있다 —
**target이 랜덤이면 이 제약은 절대 충돌하지 않는다.** 같은 트리거·같은 룰을 다시
평가할 때마다 새 행이 INSERT됐다.

실측(2026-07-14): **3,012행 중 진짜 링크는 315개 — 89.5%가 중복.**
그리고 그 숫자가 `intel_analyzer._cascade_context()`의 `COUNT(*) AS fires`로
**"이 룰이 730번 발화했다"**가 되어 LLM 컨텍스트에 주입됐다. 실제 발화는 10번이다.

**룰의 실적이 재실행으로 제조되고 있었다.** B01과 같은 병이고, 그때도 원인이
`uuid4()` 랜덤 id였다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from services.cascade.engine import _synthetic_event_id

DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"


def _fixture():
    rule = SimpleNamespace(
        id="hormuz_tension_to_oil",
        expected_response=SimpleNamespace(ticker="CL=F"),
    )
    trigger = SimpleNamespace(id="trigger-abc-123")
    result = {"extreme_date": "2026-06-17T00:00:00+00:00"}
    return rule, trigger, result


def test_same_market_reaction_gets_the_same_id():
    """같은 (룰·트리거·티커·극값일자)면 같은 id — 그래야 UNIQUE가 재삽입을 흡수한다."""
    rule, trigger, result = _fixture()
    a = _synthetic_event_id(rule, trigger, result)
    b = _synthetic_event_id(rule, trigger, result)
    assert a == b, "id가 런마다 바뀌면 UNIQUE 제약이 무력화되고 링크가 무한 증식한다"


def test_different_reactions_get_different_ids():
    """음성 테스트 — 결정론이 '전부 같은 id'로 붕괴하면 안 된다.

    (id를 상수로 만들면 test_same_...는 통과하지만 서로 다른 링크가 하나로 뭉개진다.)
    """
    rule, trigger, result = _fixture()
    base = _synthetic_event_id(rule, trigger, result)

    other_day = _synthetic_event_id(rule, trigger, {"extreme_date": "2026-06-18T00:00:00+00:00"})
    other_trigger = _synthetic_event_id(rule, SimpleNamespace(id="trigger-xyz-999"), result)
    other_rule = _synthetic_event_id(
        SimpleNamespace(id="malacca_to_lng", expected_response=SimpleNamespace(ticker="CL=F")),
        trigger,
        result,
    )
    other_ticker = _synthetic_event_id(
        SimpleNamespace(id="hormuz_tension_to_oil", expected_response=SimpleNamespace(ticker="BZ=F")),
        trigger,
        result,
    )
    assert len({base, other_day, other_trigger, other_rule, other_ticker}) == 5, (
        "네 축(룰·트리거·티커·극값일자) 중 하나라도 다르면 다른 링크다"
    )


def test_id_is_not_random():
    """`uuid4()` 회귀 감시 — 구판이 정확히 이래서 89.5%가 중복이 됐다."""
    import inspect

    from services.cascade import engine

    src = inspect.getsource(engine._build_response_event)
    assert "uuid.uuid4()" not in src, (
        "합성 시장 이벤트에 랜덤 id를 쓰면 UNIQUE(source,target,rule)가 무력화된다 — "
        "_synthetic_event_id()를 써라"
    )


def test_no_duplicate_links_in_the_ledger():
    """실 DB 불변식 — (source, rule)당 링크는 하나다.

    이것이 1을 넘으면 같은 발화가 여러 번 세어지고, 그 숫자가 LLM에게
    '이 룰이 N번 발화했다'로 전달된다.
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        bad = con.execute(
            "SELECT rule_id, source_event_id, COUNT(*) n FROM cascade_links "
            "GROUP BY 1, 2 HAVING n > 1 ORDER BY n DESC LIMIT 5"
        ).fetchall()
    finally:
        con.close()
    assert not bad, (
        "cascade_links에 중복 발화: "
        + " · ".join(f"{r}/{s[:8]} ×{n}" for r, s, n in bad)
        + "\n→ scripts/dedup_cascade_links.py 로 디듑하고 _synthetic_event_id를 확인하라"
    )
