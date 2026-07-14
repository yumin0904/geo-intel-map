"""cascade_links 디듑 — 발화 횟수가 아니라 재삽입 횟수였다 (B31).

## 무엇이 문제였나

`_build_response_event`가 합성 시장 이벤트에 `uuid.uuid4()` **랜덤 id**를 붙였다.
그 id가 `cascade_links.target_event_id`로 들어가는데, 테이블에는
`UNIQUE(source_event_id, target_event_id, rule_id)`가 걸려 있다.

**target이 매 런 새 랜덤값이면 이 제약은 절대 충돌하지 않는다.** 같은 트리거·같은 룰을
다시 평가할 때마다 새 행이 INSERT된다. 6월 1~17일 사이 캐스케이드가 수십 번 돌면서
같은 링크를 계속 재삽입했다.

실측(2026-07-14): **3,012행 중 진짜 링크는 315개 — 89.5%가 중복.**

    malacca_to_lng             730행 → 고유 소스 10   (×73)
    south_china_sea_to_defense 595행 → 고유 소스 11   (×54)
    hormuz_tension_to_oil       63행 → 고유 소스  1   (×63)
    taiwan_strait_to_soxx       50행 → 고유 소스  1   (×50)
    oil_spike_to_inflation      82행 → 고유 소스 82   (×1.0)  ← 트리거가 다양하면 중복 없음

## 왜 이게 위험했나 — 그 숫자가 LLM에 들어간다

`intel_analyzer._cascade_context()`가 이렇게 센다:

    SELECT rule_name, AVG(correlation_score), COUNT(*) AS fires
    FROM cascade_links GROUP BY rule_name ORDER BY fires DESC

`fires`가 **"이 룰이 730번 발화했다"**로 LLM 컨텍스트에 주입된다. 실제 발화는 10번이다.
**룰의 실적이 재실행으로 제조되고 있었다.**

B01과 같은 병이다 — *"IV는 분쟁 강도가 아니라 적재 행 수였다"* → 여기선
*"발화 횟수가 아니라 재삽입 횟수다."* 그때도 원인이 `uuid4()` 랜덤 id였다.

## 보존 규칙

`(source_event_id, rule_id)`가 같으면 **하나의 링크**다. 그중 `correlation_score`가
**가장 높은 행**을 남긴다 — 엔진의 `ON CONFLICT ... DO UPDATE WHERE excluded.score >
cascade_links.score`가 원래 그렇게 하려던 것이다(제약이 안 걸려서 못 했을 뿐).

행 삭제이므로 백업을 뜬다: `db/intel_pre_cascade_dedup.db`

## 근인 수리

`services/cascade/engine.py::_synthetic_event_id()` — uuid5(룰|트리거|티커|극값일자).
같은 시장 반응이면 같은 id → UNIQUE가 살아나 재실행이 UPDATE로 흡수된다.
회귀 그물: `tests/test_cascade_idempotency.py`
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# 같은 링크의 정의. target_event_id는 **넣지 않는다** — 그게 랜덤이라 중복이 생겼다.
KEEP = """
    SELECT id FROM cascade_links
     WHERE id NOT IN (
       SELECT id FROM (
         SELECT id,
                ROW_NUMBER() OVER (
                  PARTITION BY source_event_id, rule_id
                  ORDER BY correlation_score DESC, created_at ASC
                ) AS rn
           FROM cascade_links
       ) WHERE rn = 1
     )
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    q = lambda s: con.execute(s).fetchone()[0]

    total = q("SELECT COUNT(*) FROM cascade_links")
    uniq = q("SELECT COUNT(*) FROM (SELECT DISTINCT source_event_id, rule_id FROM cascade_links)")
    doomed = q(f"SELECT COUNT(*) FROM ({KEEP})")

    print(f"  총 행수         : {total:,}")
    print(f"  고유 (src,rule) : {uniq:,}   ← 진짜 링크 수")
    print(f"  삭제 대상       : {doomed:,}행 ({100.0 * doomed / total:.1f}%)")
    assert total - doomed == uniq, "산술 불일치 — 보존 규칙을 다시 보라"

    print("\n  룰별 '발화 횟수' 정정 (LLM 컨텍스트에 들어가던 값):")
    for rule, n, u in con.execute(
        "SELECT rule_id, COUNT(*), COUNT(DISTINCT source_event_id) "
        "FROM cascade_links GROUP BY 1 HAVING COUNT(*) > COUNT(DISTINCT source_event_id) "
        "ORDER BY COUNT(*) DESC LIMIT 6"
    ):
        print(f"    {rule:<32} {n:>4}회 → {u:>3}회  (×{n / u:.0f} 부풀림)")

    if not args.apply:
        print("\n[dry-run] --apply 로 실집행")
        return 0

    con.execute(f"DELETE FROM cascade_links WHERE id IN ({KEEP})")
    con.commit()

    after = q("SELECT COUNT(*) FROM cascade_links")
    after_u = q(
        "SELECT COUNT(*) FROM (SELECT DISTINCT source_event_id, rule_id FROM cascade_links)"
    )
    print(f"\n✅ 삭제 {total - after:,}행")
    print(f"   cascade_links   : {after:,}행   ← 정직한 발화 횟수")
    print(f"   잔여 중복       : {after - after_u}행   ← 0이어야 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
