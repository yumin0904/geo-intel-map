#!/usr/bin/env python3
"""
scripts/backfill_observations.py — 관찰 원장 역사 백필 (2026-07-13).

왜: `run_scan(now_ym=...)`이 임의 시점으로 되돌아갈 수 있다는 것이 실측됐다
(설계에 이미 있었다). 2015~2026 전 월을 스캔하면 수백 건의 역사적 관찰이
나오고, 그것이 **중요도 게이트의 훈련·검증 자료**가 된다 — 우크라이나 침공
(2022-02)은 중요하고 캐나다 프리덤 컨보이(같은 달, p=1e-297로 더 유의)는
우리 도메인이 아니라는 **정답이 이미 있는** 자료다.

핵심 발견(백필의 동기): p값은 "얼마나 이례적인가"를 잴 뿐 "얼마나 중요한가"를
재지 않는다. 평소 조용한 나라가 시끄러워지면 p값이 폭발한다. 그래서 유의성
게이트만으로는 캐나다 트럭시위가 전면 침공을 이긴다.

라이브 원장(observation_ledger)을 오염시키지 않는다 — 별도 테이블에 쓴다.

사용법:
    .venv/bin/python scripts/backfill_observations.py [--from 2015-07] [--to 2026-06]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.observation_ledger import _DB, _FAMILIES, _bh_pass, _scan_family  # noqa: E402

_HIST_SCHEMA = """
CREATE TABLE IF NOT EXISTS observation_history (
    scan_ym       TEXT NOT NULL,   -- 어느 시점 기준으로 스캔했는가
    family        TEXT NOT NULL,
    series_key    TEXT NOT NULL,
    bucket        TEXT NOT NULL,   -- 관측월
    metric        TEXT NOT NULL,
    value         REAL NOT NULL,
    baseline_mean REAL NOT NULL,
    delta_pct     REAL NOT NULL,
    direction     TEXT NOT NULL,
    p_value       REAL NOT NULL,
    dispersion    REAL,
    family_size   INTEGER NOT NULL,
    PRIMARY KEY (scan_ym, family, series_key, bucket)
);
CREATE INDEX IF NOT EXISTS idx_obs_hist_p ON observation_history(p_value);
"""


def months(a: str, b: str):
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    cur = ya * 12 + ma
    end = yb * 12 + mb
    while cur <= end:
        y, m = divmod(cur - 1, 12)
        yield f"{y:04d}-{m + 1:02d}"
        cur += 1


def main(frm: str, to: str) -> None:
    con = sqlite3.connect(_DB)
    con.executescript(_HIST_SCHEMA)
    total = 0
    for ym in months(frm, to):
        cands = []
        for fam in _FAMILIES:
            cands.extend(_scan_family(con, fam, ym))
        if not cands:
            continue
        passed = _bh_pass(cands)
        fsize = len(cands)
        for c in passed:
            con.execute(
                "INSERT OR REPLACE INTO observation_history "
                "(scan_ym, family, series_key, bucket, metric, value, baseline_mean,"
                " delta_pct, direction, p_value, dispersion, family_size) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ym, c.family, c.series_key, c.bucket, c.metric, c.value,
                 c.baseline_mean, c.delta_pct, c.direction, c.p_value,
                 c.dispersion, fsize),
            )
        total += len(passed)
        print(f"  {ym}: 후보 {fsize:>4} → 통과 {len(passed):>3}")
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM observation_history").fetchone()[0]
    print(f"\n✅ observation_history: {n:,}행 (이번 실행 {total:,}건)")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2015-08")
    ap.add_argument("--to", dest="to", default="2026-06")
    a = ap.parse_args()
    main(a.frm, a.to)
