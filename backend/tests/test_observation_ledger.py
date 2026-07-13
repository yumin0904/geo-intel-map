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

  ⑦ [엔진수리위 2026-07-13] GDELT 물리충돌 관찰은 **행위자 유형 필터 카운트**
     (n_material_conflict_pol)를 본다 — 원본 카운트가 폭증해도 필터 카운트가
     평평하면 관찰되지 않는다. '모나코 물리적 충돌 +76%'의 실체가 F1 그랑프리
     기사였던 사고의 회귀 봉쇄 (CAMEO 코더의 스포츠 오탐).
  ⑧ 시위 관찰은 **원본 카운트**(n_protest)를 본다 — 시위 주체는 민간(CVL)이라
     행위자 필터를 걸면 신호 자체가 죽는다. 구성개념마다 자물쇠가 다르다.
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
    # 발생지 키 테이블 (2026-07-13 수리본) — 원본·필터 카운트 병기
    con.execute("""
        CREATE TABLE gdelt_geo_country_daily (
            day TEXT, fips TEXT, country_iso3 TEXT,
            n_total INTEGER, n_protest INTEGER,
            n_material_conflict INTEGER, n_verbal_conflict INTEGER,
            mentions INTEGER, goldstein_avg REAL,
            n_total_pol INTEGER, n_protest_pol INTEGER,
            n_material_conflict_pol INTEGER, n_verbal_conflict_pol INTEGER)
    """)

    def put_month(region: str, ym: str, n: int) -> None:
        con.executemany(
            "INSERT INTO event_archive VALUES (?,?,?,?)",
            [(region, "acled", 3.0, f"{ym}-15T00:00:00Z")] * n,
        )

    def put_gdelt(iso3: str, ym: str, *, protest: int = 0, mat_raw: int = 0,
                  mat_pol: int = 0) -> None:
        """국가-월 카운트를 그 달 1일 1행에 넣는다 (스캔은 월 SUM만 본다)."""
        con.execute(
            "INSERT INTO gdelt_geo_country_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"{ym}-01", iso3[:2], iso3, mat_raw + protest, protest, mat_raw, 0,
             0, 0.0, 0, 0, mat_pol, 0),
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

    # E) 모나코형(불변식 ⑦): 원본 물리충돌은 200→600으로 폭증하나 그 전부가 스포츠
    #    오탐이라 행위자 필터 카운트는 평평(2건). → **관찰되면 안 된다.**
    for m in range(1, 6):
        put_gdelt("MCO", f"2026-0{m}", mat_raw=200, mat_pol=2)
    put_gdelt("MCO", "2026-06", mat_raw=600, mat_pol=2)

    # F) 전쟁국형(불변식 ⑦ 대칭): 필터 카운트가 실제로 급변 → 관찰돼야 한다.
    for m in range(1, 6):
        put_gdelt("WAR", f"2026-0{m}", mat_raw=1000, mat_pol=100)
    put_gdelt("WAR", "2026-06", mat_raw=1000, mat_pol=300)

    # G) 시위형(불변식 ⑧): 시위는 원본을 본다 — 필터 카운트가 0이어도 관찰돼야 한다.
    for m in range(1, 6):
        put_gdelt("PRO", f"2026-0{m}", protest=100)
    put_gdelt("PRO", "2026-06", protest=300)

    con.commit()
    con.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "test.db")
        _mk_db(db)

        s1 = run_scan(db, now_ym=NOW_YM, force=True)
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT family, series_key, bucket, value, runs_confirmed "
            "FROM observation_ledger ORDER BY series_key"
        ).fetchall()
        observed = {(r[1], r[0]) for r in rows}

        # ①~④: event_archive는 spike_region만
        assert ("spike_region", "event_archive_region") in observed, rows
        for dead in ("gap_region", "tiny_region", "flat_region"):
            assert not any(r[1] == dead for r in rows), f"{dead}가 관찰됨: {rows}"
        spike = next(r for r in rows if r[1] == "spike_region")
        assert spike[2] == "2026-06" and spike[3] == 300 and spike[4] == 1, spike
        assert s1["candidates"] >= 2, "flat도 후보에는 들어야 함(가드 통과, BH 탈락)"

        # ⑦ 모나코형: 원본 물리충돌 3배 폭증에도 필터 카운트가 평평 → 관찰 금지
        assert not any(r[1] == "MCO" for r in rows), (
            f"스포츠 오탐(원본 카운트) 계열이 관찰로 새어 나감: {rows}")
        # ⑦ 대칭: 필터 카운트가 실제로 급변한 전쟁국형은 관찰돼야 함
        assert ("WAR", "gdelt_geo_material_conflict_pol") in observed, rows
        # ⑧ 시위는 원본 카운트 — 필터 카운트 0이어도 관찰됨
        assert ("PRO", "gdelt_geo_protest") in observed, rows

        n_rows = len(rows)

        # ⑤: 재실행 — 행 수 불변, runs_confirmed 증가
        s2 = run_scan(db, now_ym=NOW_YM, force=True)
        cnt, max_rc = con.execute(
            "SELECT COUNT(*), MAX(runs_confirmed) FROM observation_ledger"
        ).fetchone()
        assert (cnt, max_rc) == (n_rows, 2), f"증식 방지 실패: {(cnt, max_rc)}"
        assert s2["inserted"] == 0 and s2["updated"] == n_rows

        # ⑥: report-only — 스캔이 만드는 테이블은 2개뿐 (은퇴 테이블은 스캔이 안 만든다)
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if r[0] != "sqlite_sequence"}  # AUTOINCREMENT 내부 테이블 제외
        assert tables == {"event_archive", "gdelt_geo_country_daily",
                          "observation_ledger", "observation_runs"}, tables
        con.close()

    print(f"OK — 관찰 원장 불변식 8종 통과 (관찰 {n_rows}행)")
    return 0


def test_observation_ledger_invariants() -> None:
    """pytest 진입점 — 스크립트 실행(main)과 같은 불변식을 검사한다."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
