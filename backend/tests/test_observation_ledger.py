"""
tests/test_observation_ledger.py — P1 관찰 원장 가드·증식 방지 회귀 (데이터효용위 2026-07-12)

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/test_observation_ledger.py

불변식:
  ① 당월(진행 중)은 관측 대상이 아니다 — 완결월만.
  ② 수집 공백(비연속 월)을 낀 계열은 스킵 — 공백 건너뛴 비교는 추세 위조.
  ③ 기준선 평균 < 30(소분모)은 스킵 — '+6100%' 위조 차단.
  ④ 평평한 계열은 BH를 통과하지 못한다(허위 신호 없음).
  ⑤ 급변 계열은 1행으로 기록되고, 재실행은 행을 늘리지 않고 확인 횟수만 올린다
     (identity_key 증식 방지 — PENDING 605→807 병리의 선반영).
  ⑥ report-only — 스캔이 만드는 테이블은 observation_ledger·observation_runs 뿐.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.observation_ledger import run_scan  # noqa: E402

NOW_YM = "2026-07"  # 테스트 고정 '당월' — 2026-06까지가 완결월


def _mk_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE event_archive (
            region_code TEXT, source_type TEXT, severity REAL, timestamp TEXT)
    """)
    con.execute("""
        CREATE TABLE gdelt_country_daily (
            day TEXT, country TEXT, n_total INTEGER, n_protest INTEGER,
            n_material_conflict INTEGER, n_verbal_conflict INTEGER)
    """)

    def put_month(region: str, ym: str, n: int) -> None:
        con.executemany(
            "INSERT INTO event_archive VALUES (?,?,?,?)",
            [(region, "acled", 3.0, f"{ym}-15T00:00:00Z")] * n,
        )

    # A) 급변 계열: 1~5월 100건, 6월 300건 → 관찰 1행 기대
    for m in range(1, 6):
        put_month("spike_region", f"2026-0{m}", 100)
    put_month("spike_region", "2026-06", 300)
    # 당월(7월) 데이터 — 관측에 끼면 안 됨 (불변식 ①)
    put_month("spike_region", "2026-07", 9999)

    # B) 공백 계열: 5월 결측 — 스킵 기대 (불변식 ②)
    for m in (1, 2, 3, 4, 6):
        put_month("gap_region", f"2026-0{m}", 100)

    # C) 소분모 계열: 월 5건 → 마지막 달 40건이어도 스킵 (불변식 ③)
    for m in range(1, 6):
        put_month("tiny_region", f"2026-0{m}", 5)
    put_month("tiny_region", "2026-06", 40)

    # D) 평평한 계열: 매월 100건 — 기록 0 기대 (불변식 ④)
    for m in range(1, 7):
        put_month("flat_region", f"2026-0{m}", 100)

    con.commit()
    con.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "test.db")
        _mk_db(db)

        s1 = run_scan(db, now_ym=NOW_YM, force=True)
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT series_key, bucket, value, runs_confirmed FROM observation_ledger"
        ).fetchall()

        # ①~④: spike_region 2026-06만 기록
        assert len(rows) == 1, f"기대 1행, 실측 {len(rows)}행: {rows}"
        key, bucket, value, rc = rows[0]
        assert key == "spike_region" and bucket == "2026-06" and value == 300, rows[0]
        assert rc == 1
        assert s1["candidates"] >= 2, "flat도 후보에는 들어야 함(가드 통과, BH 탈락)"

        # ⑤: 재실행 — 행 수 불변, runs_confirmed 증가
        s2 = run_scan(db, now_ym=NOW_YM, force=True)
        rows2 = con.execute(
            "SELECT COUNT(*), MAX(runs_confirmed) FROM observation_ledger"
        ).fetchone()
        assert rows2 == (1, 2), f"증식 방지 실패: {rows2}"
        assert s2["inserted"] == 0 and s2["updated"] == 1

        # ⑥: report-only — 신설 테이블은 2개뿐
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if r[0] != "sqlite_sequence"}  # AUTOINCREMENT 내부 테이블 제외
        assert tables == {"event_archive", "gdelt_country_daily",
                          "observation_ledger", "observation_runs"}, tables
        con.close()

    print("OK — 관찰 원장 불변식 6종 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
