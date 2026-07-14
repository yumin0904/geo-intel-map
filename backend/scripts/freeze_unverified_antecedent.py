"""만기 전 동결 — 전건(independent_var) 미검증 market 예측 76건.

배경 (2026-07-14, 사용자 승인):
    prediction_scorer는 independent_var를 한 번도 읽지 않는다(실파일 대조: 참조 0건).
    조건부 예측 "IF X THEN Y"를 Y만 보고 채점하면 남는 것은 X와 무관한 티커 베팅이다.
    현 간판 21건이 이미 그 산물 — GLD HIT 4건의 realized_pct가 전부 3.7326(같은 금값
    움직임을 4번 셌다), CL=F는 4.8432가 HIT에도 MISS에도 있다(같은 유가 움직임에 반대로
    건 두 예측). 고유 실현결과는 21건 중 13개뿐이다.

    만기 도래분 중 scorable=1 & eligible=1인 market 예측 76건(2026-07-17~08-10)이
    그대로 채점되면 간판이 21→97건으로 불어난다 — 증량분 전량이 같은 병의 산물이다.
    첫 20건 만기가 07-17, 전문가 패킷 최종 점검이 07-19다.

원칙:
    결과를 보기 전에 동결하므로 forking paths가 아니다. 결과가 마음에 안 들어서 멈추는
    것이 아니라 계기가 고장 났음을 발견해서 멈추는 것이다 — 고장 난 계기로 잰 값은
    유리하든 불리하든 값이 아니다. 선별 동결도 아니다(해당 76건 전수).

집행:
    scorable=1 유지          — 채점 자체는 돌게 둔다(기록 보존, "회수는 삭제 아님" 판례)
    eligible_for_calibration=0 — track record 간판에서만 제외
    voided_reason append     — 구조화 스탬프(기존 사유가 있으면 ' | '로 이어붙임)

범위 밖 (위원회 안건으로 이월):
    event_series 53건(만기 2026-10-01~2027-01-07) — target이 티커가 아니라 지정학 수량이라
    판단이 다르다. 급하지 않다(최단 만기 10-01).

선례: apply_unidentified_reextract.py(v9.52.0) · D2위원회 construct_invalid_iv_narrative
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

REASON = (
    "antecedent_unverified:2026-07-14:채점기 전건 미검증 — "
    "prediction_scorer가 independent_var를 읽지 않는다(참조 0건). 조건부 예측의 조건절이 "
    "한 번도 확인되지 않은 채 결과변수(티커 등락)만으로 채점된다 — 전건이 발생하지 않았어도 "
    "티커가 움직이면 HIT가 된다. 현 간판 21건의 고유 실현결과는 13개뿐이고 HIT 9 중 4가 "
    "2026-07-07 금값 랠리 하나다(realized_pct 3.7326 중복). 만기 전 동결이므로 결과를 보고 "
    "고른 것이 아니다 — 해당 조건 전수(market 76건). 기록은 보존하되 track record에서 제외. "
    "채점기 수리는 18-① 위원회 소관."
)

SELECT_SQL = """
    SELECT prediction_id, voided_reason
      FROM prediction_log
     WHERE status = 'PENDING'
       AND scorable = 1
       AND eligible_for_calibration = 1
       AND target_kind = 'market'
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실집행 (없으면 dry-run)")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = list(con.execute(SELECT_SQL))

    print(f"대상: {len(rows)}건 (PENDING·scorable=1·eligible=1·market)")
    already = sum(1 for r in rows if r["voided_reason"] and "antecedent_unverified" in r["voided_reason"])
    if already:
        print(f"  이미 스탬프됨: {already}건 — 재집행해도 중복 기재 안 함 (idempotent)")

    if not args.apply:
        print("\n[dry-run] --apply 로 실집행")
        for r in rows[:5]:
            print(f"  {r['prediction_id']}")
        if len(rows) > 5:
            print(f"  … 외 {len(rows) - 5}건")
        return 0

    n = 0
    for r in rows:
        prev = r["voided_reason"]
        if prev and "antecedent_unverified" in prev:
            continue  # idempotent
        merged = f"{prev} | {REASON}" if prev else REASON
        con.execute(
            "UPDATE prediction_log "
            "SET eligible_for_calibration = 0, voided_reason = ? "
            "WHERE prediction_id = ?",
            (merged, r["prediction_id"]),
        )
        n += 1
    con.commit()

    left = con.execute(
        "SELECT COUNT(*) FROM prediction_log "
        "WHERE status='PENDING' AND scorable=1 AND eligible_for_calibration=1 AND target_kind='market'"
    ).fetchone()[0]
    board = con.execute(
        "SELECT COUNT(*) FROM prediction_log "
        "WHERE eligible_for_calibration=1 AND status IN ('HIT','MISS')"
    ).fetchone()[0]

    print(f"\n✅ 동결 {n}건")
    print(f"   잔여 (만기 시 간판 유입될 market): {left}건  ← 0이어야 정상")
    print(f"   현 간판(채점완료·eligible=1): {board}건  ← 21에서 불변이어야 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
