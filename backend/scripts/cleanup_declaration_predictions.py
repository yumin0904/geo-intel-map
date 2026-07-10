"""큐 8 소급 정화 — 선언문 h1 오적재 행 종결 (2026-07-11, geo-os STATUS 큐 8).

"현 데이터로 검증 가능한 정량 가설 없음" 류 선언문·체크리스트 파편이 h1 자리에
적재된 행은 예측이 아니다 — v9.34.1 이전(및 scorable=0 우회 경로) 적재분 잔존 실측.
처방은 삭제가 아니라 **UNRESOLVED 종결 + 사유 스탬프 + 캘리브레이션 제외**
(v9.34.1 소급 종결 판례와 동일 수술 — 감사 추적 보존).

판별 기준은 prediction_instrument._DECLARATION_H1 재사용 — 상류 필터와 소급 정화가
한 기준을 공유해야 드리프트가 없다. 멱등: 재실행해도 이미 종결분은 건드리지 않는다.

실행: .venv/bin/python scripts/cleanup_declaration_predictions.py [--apply]
      (--apply 없으면 dry-run — 대상 목록만 출력)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.prediction_instrument import _DECLARATION_H1, _INTEL_DB  # noqa: E402

REASON = "선언문 h1 오적재 — 큐 8 소급 정화(2026-07-11), 상류 필터(_DECLARATION_H1)와 동일 기준"


def main(apply: bool) -> None:
    con = sqlite3.connect(_INTEL_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT prediction_id, status, resolve_by, scorable, h1, score_reason "
        "FROM prediction_log"
    ).fetchall()

    pending = [r for r in rows if _DECLARATION_H1.search(r["h1"] or "")
               and r["status"] == "PENDING"]
    # 이미 종결(UNRESOLVED)된 선언문 행은 상태 불변 — 사유만 정화 스탬프로 교체해
    # 인간 사후 채점 큐가 건너뛸 수 있게 한다.
    closed = [r for r in rows if _DECLARATION_H1.search(r["h1"] or "")
              and r["status"] == "UNRESOLVED" and REASON not in (r["score_reason"] or "")]

    print(f"대상: PENDING 종결 {len(pending)}건 · 기종결 사유 스탬프 {len(closed)}건")
    for r in pending:
        print(f"  [종결] 만기 {r['resolve_by']} | {(r['h1'] or '')[:70]}")
    for r in closed:
        print(f"  [스탬프] {(r['h1'] or '')[:70]}")

    if not apply:
        print("\n(dry-run — 적용하려면 --apply)")
        return

    now = datetime.now(timezone.utc).isoformat()
    for r in pending:
        con.execute(
            "UPDATE prediction_log SET status='UNRESOLVED', scored_at=?, "
            "score_reason=?, eligible_for_calibration=0 WHERE prediction_id=?",
            (now, REASON, r["prediction_id"]),
        )
    for r in closed:
        con.execute(
            "UPDATE prediction_log SET score_reason=?, eligible_for_calibration=0 "
            "WHERE prediction_id=?",
            (REASON, r["prediction_id"]),
        )
    con.commit()
    print(f"\n적용 완료: 종결 {len(pending)} · 스탬프 {len(closed)}")


if __name__ == "__main__":
    main("--apply" in sys.argv)
