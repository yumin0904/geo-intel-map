"""
[위원회 20260712 판정④ 소급 규약 집행] 미식별 89 실집행 — dry-run 3처분 DB 반영.

배경: geo-os wiki/decisions/20260712-qualitative-upstream-committee.md 판정④
"소급은 회수만 허용·LLM 합성 백필 금지"(retrodiction 방화벽). dry-run 결과
(exports/unidentified_reextract_dryrun.json)의 건별 3처분을 사용자 승인 후
prediction_log에 실적용한다.

3처분:
  recovered(13)              — dependent_var·independent_var를 신DV·신IV로 갱신 +
                                extraction_ok=1 + extracted_at 스탬프.
                                created_at·confidence_at_creation은 **절대 불변**
                                (retrodiction 격리 — 생성 시점 원값을 소급 변경하지 않는다).
  rejected_fragment(8) +
  declaration_no_hypothesis(35) = 마킹 43건 — DELETE 금지. v9.50.0 재분류 실집행
                                선례(reclassify_event_predictions.py)의 "기존 필드
                                append" 방식을 승계해 score_reason에 사유를 덧붙이고,
                                채점·triage 모수 제외는 신설 voided_reason 컬럼
                                (idempotent ALTER)으로 구조화 — 기존 eligible_for_calibration
                                필드는 큐 8 정화(cleanup_declaration_predictions.py)가
                                이미 다른 목적으로 36건을 선점해 재사용 시 그 결과를
                                오염시키므로 회피(교란 변수 분리).
  unresolved_qualitative(33) — 무변경 (유지).

기본 dry-run (기존 exports/unidentified_reextract_dryrun.json 재검증만) —
**실집행은 --execute (사용자 승인 후에만)**. 단일 트랜잭션.

실행: cd backend && .venv/bin/python3 scripts/apply_unidentified_reextract.py [--execute]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_DB = _BACKEND / "db" / "intel.db"
_DRYRUN = _BACKEND.parent / "exports" / "unidentified_reextract_dryrun.json"

_VOID_REASON = {
    "rejected_fragment": "캡처 필터 비가설 조각 기각 — 미식별 89 실집행(v9.52.0), 사용자 승인 07-12",
    "declaration_no_hypothesis": "정직한 무가설 선언('정량 가설 없음' 류) — 미식별 89 실집행(v9.52.0), 사용자 승인 07-12",
}
_SCORE_REASON_TAG = " [v9.52.0 미식별 89 실집행 — {bucket} 마킹, triage/채점 모수 제외, 사용자 승인 07-12]"


def _ensure_columns(con: sqlite3.Connection) -> None:
    """extraction_ok·extracted_at·voided_reason 소급 추가 (idempotent).

    extraction_ok는 prediction_instrument._ensure_table과 동일 패턴(구 행 NULL 유지,
    retrodiction 격리). extracted_at·voided_reason은 이 실집행 전용 신설 컬럼.
    """
    cols = {r[1] for r in con.execute("PRAGMA table_info(prediction_log)")}
    if "extraction_ok" not in cols:
        con.execute("ALTER TABLE prediction_log ADD COLUMN extraction_ok INTEGER")
    if "extracted_at" not in cols:
        con.execute("ALTER TABLE prediction_log ADD COLUMN extracted_at TEXT")
    if "voided_reason" not in cols:
        con.execute("ALTER TABLE prediction_log ADD COLUMN voided_reason TEXT")


def main() -> None:
    ap = argparse.ArgumentParser(description="미식별 89 dry-run 3처분 실집행 (기본 dry-run)")
    ap.add_argument("--execute", action="store_true", help="실집행 — 사용자 승인 후에만 사용")
    args = ap.parse_args()

    dryrun = json.loads(_DRYRUN.read_text(encoding="utf-8"))
    records = dryrun["records"]
    recovered = [r for r in records if r["버킷"] == "recovered"]
    rejected = [r for r in records if r["버킷"] == "rejected_fragment"]
    declaration = [r for r in records if r["버킷"] == "declaration_no_hypothesis"]
    unresolved = [r for r in records if r["버킷"] == "unresolved_qualitative"]
    marked = rejected + declaration

    print(f"회수(recovered): {len(recovered)}건 · 마킹(rejected+declaration): "
          f"{len(rejected)}+{len(declaration)}={len(marked)}건 · 유지(unresolved): {len(unresolved)}건")

    for r in recovered:
        assert (r["신DV"] or "").strip() not in ("", "미식별"), \
            f"recovered인데 신DV가 비어있음: {r['prediction_id']}"

    if not args.execute:
        print("(dry-run — 적용하려면 --execute)")
        return

    con = sqlite3.connect(str(_DB))
    try:
        con.execute("BEGIN")
        _ensure_columns(con)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1) 회수 13건 — DV·IV 갱신 + extraction_ok=1 + extracted_at 스탬프.
        #    created_at·confidence_at_creation은 SET 절에 절대 포함하지 않는다.
        for r in recovered:
            con.execute(
                "UPDATE prediction_log SET dependent_var=?, independent_var=?, "
                "extraction_ok=1, extracted_at=? WHERE prediction_id=?",
                (r["신DV"], r["신IV"], now, r["prediction_id"]),
            )

        # 2) 마킹 43건 — DELETE 금지, DV/IV/created_at/confidence_at_creation 불변.
        #    score_reason append(v9.50.0 선례 방식 승계) + voided_reason 구조화 스탬프
        #    (triage/채점 모수 제외의 기계 판별 키).
        for r in marked:
            bucket = r["버킷"]
            con.execute(
                "UPDATE prediction_log SET "
                "score_reason = IFNULL(score_reason,'') || ?, "
                "voided_reason = ? "
                "WHERE prediction_id=?",
                (_SCORE_REASON_TAG.format(bucket=bucket), _VOID_REASON[bucket], r["prediction_id"]),
            )

        # 3) 유지 33건 — 무변경 (검증용 카운트만 확인, UPDATE 없음)

        con.commit()
        print(f"실집행 완료: 회수 {len(recovered)} · 마킹 {len(marked)} · 유지 {len(unresolved)}(무변경)")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
