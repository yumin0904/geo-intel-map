"""간판 VOID + 회수 플래그 전파 + event_series 파이프 차단.

18-① 위원회 (2026-07-14 저녁, 3석 병렬) 판정 · 사용자 승인.

## 안건이 뒤집혔다
질문은 "채점기가 independent_var를 읽게 만들 것인가"였다. 실측 답: **읽을 IV가 없다.**
  · IV는 명제가 아니라 명사구다. DV는 정량 4필드(target·direction·threshold_pct·
    horizon_days)인데 IV는 TEXT 한 칸 — 방향도 문턱도 창도 없다. 참·거짓을 물을 대상이 없다.
  · 전건 판정 가능성 = 0/21. (a)ACLED 원장형 10건 → ACLED는 2025-07-14에 끝나고 채점창
    (2026-06-30~07-13)에 0행 (b)외부데이터형 6건 → FRED는 2020~2024 연간 5행, CPI 부재
    (c)동어반복·파손 5건 → IV가 곧 target(WTI로 CL=F 예측), IV 하나는 따옴표 한 글자
  · 검증층은 순환이다. hypothesis_extractor.py:121이 자백해뒀다 — "진짜 사전등록 0건,
    구성상 전부 HARKing". IV는 LLM이 데이터를 보고 쓴 문장이다. 같은 데이터로 검증하면
    구성상 참 → 통과율 ~100%의 no-op에 "조건절을 검증합니다"라는 없는 엄밀성이 붙는다.

## 세 가지를 집행한다

**① 회수 플래그 전파 (버그 수리)**
    voided_reason과 eligible_for_calibration이 독립 플래그라 회수가 간판에 전파되지 않았다.
    회수 판정을 받고도 eligible=1로 남은 행이 144건. 그중 1건(d4d30294, CL=F·HIT·8.461,
    IV=따옴표 한 글자)은 이미 채점돼 **간판 위에 있었다** — 정직한 간판은 42.9%가 아니라
    40.0%(8H/12M)였다.
    ⚠️ diluted_iv·grade_demoted는 **회수가 아니라 표시**다(07-13 판례: "회수하지 않고
    표시만"). 전파 대상에서 제외한다 — 통째로 걸면 회수 아닌 것까지 죽인다.

**② 간판 VOID → 0/0 (사용자 결정)**
    전건 판정 가능성이 0/21이므로 21건 전부 antecedent_undecidable. 사유는 "전건 미발생"이
    아니라 **"전건 판정 불능"**이다 — 잴 계기가 없다.
    비대칭 해소이기도 하다: 결과를 모르는 76건은 동결하고 결과를 아는 21건은 간판에 남기면,
    의도가 아니어도 구조는 결과 기준 선별이다. 같은 코호트·같은 생성기·같은 IV 병리이고
    갈린 기준은 만기 도래 여부 하나뿐이었다.
    그리고 공표를 멈추는 것만으로는 부족하다 — collect 잡(09/21시)이 하루 두 번
    cumulative_skill_summary를 돌려 0.429를 재제조한다. **분모에서 빼야 사라진다.**

**③ event_series 53건 파이프 차단 (내 동결이 놓친 것)**
    freeze_unverified_antecedent.py의 SELECT가 target_kind='market' 한정이었다. 그래서
    영수증 "잔여 0건 ← 정상"의 **분모가 market뿐**이었다(패턴 H — 가드의 분모를 재라).
    실측: _count_events()는 `SELECT COUNT(*) FROM event_archive WHERE region_code=?`,
    즉 **적재 행 수**다. B01위원회가 fabricated_input으로 사살한 바로 그 변수가 DV로
    부활해 있었다. "지정학 수량이라 판단이 다르다"는 의장 진단은 틀렸다.
    53건 중 채점 가능한 20건의 16건(80%)이 이미 회수된 예측이다 → 2026-10-01에
    **회수된 예측이 간판에 오를 참이었다.**

기록은 전부 보존한다(scorable 불변, 행 삭제 0) — "회수는 삭제 아님" 판례.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# 회수 사유 — eligible=0으로 전파한다
RETRACTION_KEYS = (
    "fabricated_input",
    "construct_invalid_iv",  # _narrative 포함 (LIKE 부분일치)
    "epistemic_laundering",
    "unquantifiable",
    "antecedent_unverified",
    "캡처 필터 비가설 조각 기각",
    "정직한 무가설 선언",
)
# 표시 사유 — 회수가 아니다. 절대 전파하지 않는다 (07-13 판례)
MARKING_ONLY = ("diluted_iv", "grade_demoted")

UNDECIDABLE = (
    "antecedent_undecidable:2026-07-14:18-①위원회 — 전건 판정 불능(미발생이 아니라 잴 계기 부재). "
    "IV는 명제가 아니라 명사구다(DV는 정량 4필드, IV는 TEXT 1칸 — 방향·문턱·창 없음). "
    "전건 판정 가능성 0/21: ACLED 원장형은 채점창에 0행(ACLED가 2025-07-14 종료)·"
    "외부데이터형은 FRED가 2020~2024 연간 5행(CPI 부재)·나머지는 IV가 곧 target인 동어반복. "
    "게다가 IV는 LLM이 데이터를 보고 쓴 문장이라(사전등록 0건, HARKing) 같은 데이터로 검증하면 "
    "구성상 참 — 검증층은 순환 no-op이다. 채점 기록은 보존하되 track record에서 제외. "
    "엔진의 track record는 나쁜 것이 아니라 아직 존재하지 않는다."
)


def _stamp(con: sqlite3.Connection, pid: str, prev: str | None, reason: str) -> None:
    merged = f"{prev} | {reason}" if prev else reason
    con.execute(
        "UPDATE prediction_log SET eligible_for_calibration = 0, voided_reason = ? "
        "WHERE prediction_id = ?",
        (merged, pid),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    def is_retraction(vr: str | None) -> bool:
        if not vr:
            return False
        return any(k in vr for k in RETRACTION_KEYS)

    # ① 회수 플래그 전파
    prop = [
        r for r in con.execute(
            "SELECT prediction_id, voided_reason, status FROM prediction_log "
            "WHERE voided_reason IS NOT NULL AND eligible_for_calibration = 1"
        )
        if is_retraction(r["voided_reason"])
    ]
    # 표시사유만 있고 회수사유는 없는 행 = 진짜 제외 대상.
    # (둘 다 가진 행은 회수가 이긴다 → prop에 들어간다. 그런 행을 여기서 또 세면
    #  분모가 부풀어 "몇 건이 남아야 정상"을 틀리게 만든다 — 패턴 H, 오늘 배운 것.)
    skipped = sum(
        1 for r in con.execute(
            "SELECT voided_reason FROM prediction_log "
            "WHERE voided_reason IS NOT NULL AND eligible_for_calibration = 1"
        )
        if any(m in r["voided_reason"] for m in MARKING_ONLY) and not is_retraction(r["voided_reason"])
    )

    # ② 간판 VOID (채점 완료 · eligible=1)
    board = list(con.execute(
        "SELECT prediction_id, voided_reason FROM prediction_log "
        "WHERE eligible_for_calibration = 1 AND status IN ('HIT','MISS')"
    ))

    # ③ event_series 파이프
    evs = list(con.execute(
        "SELECT prediction_id, voided_reason FROM prediction_log "
        "WHERE target_kind = 'event_series' AND status = 'PENDING' "
        "AND scorable = 1 AND eligible_for_calibration = 1"
    ))

    print(f"① 회수 플래그 전파 대상 : {len(prop):>3}건  (표시사유 제외분 {skipped}건 — diluted_iv·grade_demoted)")
    print(f"② 간판 VOID 대상         : {len(board):>3}건")
    print(f"③ event_series 파이프    : {len(evs):>3}건")

    if not args.apply:
        print("\n[dry-run] --apply 로 실집행")
        return 0

    for r in prop:
        # 이미 사유가 있으므로 새 스탬프 없이 플래그만 내린다
        con.execute(
            "UPDATE prediction_log SET eligible_for_calibration = 0 WHERE prediction_id = ?",
            (r["prediction_id"],),
        )
    for r in board:
        _stamp(con, r["prediction_id"], r["voided_reason"], UNDECIDABLE)
    for r in evs:
        _stamp(con, r["prediction_id"], r["voided_reason"], UNDECIDABLE)
    con.commit()

    # 검증
    def q(sql: str) -> int:
        return con.execute(sql).fetchone()[0]

    board_left = q(
        "SELECT COUNT(*) FROM prediction_log "
        "WHERE eligible_for_calibration=1 AND status IN ('HIT','MISS')"
    )
    leaked = q(
        "SELECT COUNT(*) FROM prediction_log "
        "WHERE voided_reason IS NOT NULL AND eligible_for_calibration=1"
    )
    inflow = q(
        "SELECT COUNT(*) FROM prediction_log "
        "WHERE status='PENDING' AND scorable=1 AND eligible_for_calibration=1"
    )
    print("\n=== 검증 ===")
    print(f"  간판(eligible=1 & HIT/MISS)         : {board_left}건  ← 0이어야 정상")
    print(f"  회수했는데 eligible=1 잔존           : {leaked}건  ← 표시사유 {skipped}건만 남아야 정상")
    print(f"  간판 유입 가능(PENDING·scorable·elig): {inflow}건  ← 0이어야 정상 (kind 무관)")
    print(f"  행 수 (삭제 0 확인)                  : {q('SELECT COUNT(*) FROM prediction_log')}건  ← 974")
    print(f"  scorable 총합 (불변 확인)            : {q('SELECT SUM(scorable) FROM prediction_log')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
