#!/usr/bin/env python3
"""
scripts/retag_theory_tags.py — theory_tags 소급 재태깅 (변수 타당도 감사 2026-07-13).

왜: `_build_theory_tags`가 Explosions/Remote violence 전건에 무조건 gray_zone을
붙여, 우크라이나 미사일·포격 69,800건이 "재래식 정규전"이면서 동시에
"전쟁 문턱 아래(gray_zone)"로 태깅됐다. 커넥터는 수리됐으나 이미 적재된
304,024건은 구 태그를 그대로 갖고 있다. payload에 event_type·fatalities·
inter 코드가 100% 보존돼 있으므로 재수집 없이 소급 재태깅이 가능하다.

사용법:
    .venv/bin/python scripts/retag_theory_tags.py [--apply]
기본은 dry-run(전후 대조만 출력). --apply 시에만 UPDATE.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from connectors.acled import _build_theory_tags, _inter_code  # noqa: E402

_DB = _BACKEND / "db" / "intel.db"

# ACLED의 6개 event_type — 이 스크립트의 관할 경계.
_ACLED_EVENT_TYPES = {
    "Battles", "Explosions/Remote violence", "Violence against civilians",
    "Riots", "Protests", "Strategic developments",
}


def retag(apply: bool) -> None:
    con = sqlite3.connect(_DB)
    con.row_factory = sqlite3.Row
    changed, unchanged = 0, 0
    before, after = Counter(), Counter()
    updates: list[tuple[str, str]] = []

    for table in ("events", "event_archive"):
        rows = con.execute(
            f"SELECT id, region_code, source_type, theory_tags, payload FROM {table}"
        ).fetchall()
        for r in rows:
            try:
                pl = json.loads(r["payload"] or "{}")
            except Exception:
                continue
            et = pl.get("event_type") or ""
            # ACLED 유래분만 재태깅한다. 드라이런이 잡은 결함: source_type=missile_test
            # (CNS/BP 미사일 커넥터, 자체 태그 deterrence·missile_proliferation 보유)
            # 303건이 ACLED 태거를 통과해 unclassified로 덮어써지고 있었다.
            # 다른 커넥터의 태그 체계를 이 스크립트가 침범하지 않는다.
            if et not in _ACLED_EVENT_TYPES or r["source_type"] != "conflict":
                continue
            new_tags = _build_theory_tags(
                et,
                pl.get("sub_event_type") or "",
                _inter_code(pl.get("inter1", 0) or 0),
                _inter_code(pl.get("inter2", 0) or 0),
                r["region_code"],
                country=pl.get("country") or "",
                fatalities=int(pl.get("fatalities") or 0),
            )
            old_tags = json.loads(r["theory_tags"] or "[]")
            for t in old_tags:
                before[t] += 1
            for t in new_tags:
                after[t] += 1
            if sorted(old_tags) != sorted(new_tags):
                changed += 1
                if apply:
                    con.execute(
                        f"UPDATE {table} SET theory_tags = ? WHERE id = ?",
                        (json.dumps(new_tags), r["id"]),
                    )
            else:
                unchanged += 1

    print(f"{'적용' if apply else 'DRY-RUN'}: 변경 {changed:,}건 · 불변 {unchanged:,}건\n")
    keys = sorted(set(before) | set(after), key=lambda k: -before.get(k, 0))
    print(f"  {'태그':<24} {'전':>9} {'후':>9}  변화")
    for k in keys:
        b, a = before.get(k, 0), after.get(k, 0)
        d = a - b
        mark = "" if d == 0 else (f"  {d:+,}")
        print(f"  {k:<24} {b:>9,} {a:>9,}{mark}")
    if apply:
        con.commit()
        print("\n✅ 커밋됨")
    else:
        print("\n(--apply 없이 실행 — DB 불변)")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    retag(ap.parse_args().apply)
