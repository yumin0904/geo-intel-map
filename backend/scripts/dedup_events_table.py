"""`events` 이중적재 디듑 — B01 수리의 미완분.

## 무엇을 놓쳤나

B01위원회(2026-07-14 오전, 커밋 82324cb)가 `event_archive`의 ×1.9 이중적재를 디듑했다
(304,581 → 249,438행). **그런데 `events`는 청소하지 않았다.** 커밋 제목이 그대로 말한다 —
"event_archive 디듑". 범위 판단의 근거는 커밋 어디에도 없다(디듑 SQL이 수동 실행돼 기록이 없다).

실측(2026-07-14 밤): `events` 297,420행 중 **53,951행(18.1%)이 중복**이다.
전체 초과분의 97.9%가 2025-03·04·05 세 달에 몰려 있다 —

    2025-03  39,716 → 20,760  (dup 1.91)
    2025-04  38,136 → 20,058  (dup 1.90)
    2025-05  35,201 → 19,401  (dup 1.81)
    그 외    dup ≈ 1.00

B01이 지목한 백필 구간 그대로이고, 중복 쌍은 **같은 시각·같은 내용에 UUID만 다르다**
(당시 `uuid4()` 랜덤 id → 멱등성 방어 불가). 안정 UUID는 수리됐으므로 재발하지 않는다
(2026-07 신규 적재 dup=1.000 실측).

## 왜 이게 archive보다 위험했나

`events`는 **발행 표면이 읽는 테이블**이다:
    api/stats.py       → 카운터
    api/layers.py      → 지도 레이어
    cascade/engine.py  → 룰 발화

너울 라이브 정문이 **"수집·정규화한 지정학 이벤트 296,885"**를 띄우고 있었다.
정직한 값은 **243,469**다. 그리고 전문가 패킷 윤강현 카드의 *"정직한 변수 위에서 다시 세면
월간 최대 62건"*이 실은 **35건**이다 — **"정직하게 다시 셌다"는 그 재측정이 이중적재
위에서 이뤄졌다.**

## 그리고 감시식이 이것을 볼 수 없었다

오늘 아침 만든 B23 재발 감시식은 `FROM event_archive`만 본다. **병이 살아 있는 테이블을
가드가 구조적으로 못 본다**(패턴 H, 7번째). 이 스크립트와 함께 감시식을 두 테이블로 확장한다.

## 참조 무결성

`cascade_links.source_event_id`/`target_event_id`가 `events.id`를 참조한다(3,012행).
실측 확인:
  · 유효 source 2,686건 **전부가 보존될 행**을 가리킨다 → 이 디듑의 추가 고아 = **0**
  · ⚠️ target은 **3,012건 전부가 이미 고아**다(events·archive 어디에도 없다).
    아침 디듑 이전 백업 대조 결과 그때도 0/3,012 — **더 오래된 별건 버그**(B14 계열).
  · ⚠️ 아침 archive 디듑은 source 링크 **50건을 조용히 고아로 만들었다**(2,736 → 2,686).
    참조 무결성 검사 없이 지웠기 때문이다. 이 스크립트는 지우기 전에 센다.

보존 규칙: 정본 키가 같은 행 중 **`MIN(rowid)`만 남긴다**(가장 먼저 적재된 행).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# B23 감시식과 같은 정본 키. 키가 다르면 답도 다르다 — 하나로 통일한다.
KEY = "timestamp || severity || COALESCE(title,'') || COALESCE(description,'') || payload"

DOOMED = f"""
    SELECT id FROM events
     WHERE rowid NOT IN (SELECT MIN(rowid) FROM events GROUP BY {KEY})
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실집행 (없으면 dry-run)")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    q = lambda sql: con.execute(sql).fetchone()[0]

    total = q("SELECT COUNT(*) FROM events")
    uniq = q(f"SELECT COUNT(DISTINCT {KEY}) FROM events")
    doomed = total - uniq

    # 참조 무결성 — 지우기 전에 센다 (아침 디듑이 안 해서 50건을 조용히 잃었다)
    orphaned = q(
        f"SELECT COUNT(*) FROM cascade_links "
        f"WHERE source_event_id IN ({DOOMED}) OR target_event_id IN ({DOOMED})"
    )
    live_src = q(
        "SELECT COUNT(*) FROM cascade_links WHERE source_event_id IN (SELECT id FROM events)"
    )

    print(f"  현재      : {total:,}행")
    print(f"  고유      : {uniq:,}행")
    print(f"  삭제 대상 : {doomed:,}행 ({100.0 * doomed / total:.1f}%)")
    print(f"  이 삭제로 새로 고아가 될 cascade_links: {orphaned}행  ← 0이어야 집행")
    print(f"  (참고) 현재 유효 source 링크: {live_src}행")

    if orphaned:
        print("\n❌ 중단 — 참조 무결성이 깨진다. 링크 재매핑을 먼저 설계할 것.")
        return 1

    if not args.apply:
        print("\n[dry-run] --apply 로 실집행")
        return 0

    con.execute(f"DELETE FROM events WHERE id IN ({DOOMED})")
    con.commit()

    after = q("SELECT COUNT(*) FROM events")
    after_uniq = q(f"SELECT COUNT(DISTINCT {KEY}) FROM events")
    after_src = q(
        "SELECT COUNT(*) FROM cascade_links WHERE source_event_id IN (SELECT id FROM events)"
    )
    worst = con.execute(
        f"SELECT strftime('%Y-%m',timestamp), "
        f"ROUND(CAST(COUNT(*) AS REAL)/COUNT(DISTINCT {KEY}),3) d "
        f"FROM events GROUP BY 1 ORDER BY d DESC LIMIT 1"
    ).fetchone()

    print(f"\n✅ 삭제 {total - after:,}행")
    print(f"   events            : {after:,}행  ← 정직한 수치")
    print(f"   잔여 중복          : {after - after_uniq}행  ← 0이어야 정상")
    print(f"   최악 월 dup        : {worst[0]} = {worst[1]}  ← 1.0 근처여야 정상")
    print(f"   유효 source 링크   : {after_src}행  ← {live_src}에서 불변이어야 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
