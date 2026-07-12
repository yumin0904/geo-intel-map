"""
[위원회 20260712 집행⑥] 미식별 89건 소급 재추출 dry-run — DB 무변경.

exports/qualitative_triage.json의 unidentified 버킷(89건, prediction_id만 보유)을
DB(backend/db/intel.db)에서 h1 원문으로 역참조한 뒤, 개량된 extract_hypotheses()
(을수록 형태소 커버리지 수리·상관형 대칭 정규식·캡처 필터 강화·DV 방어 폴백)를
재적용해 회수 가능 여부를 건별로 report-only 출력한다.

**DB 쓰기 절대 금지** — 이 스크립트는 어떤 행도 UPDATE/INSERT하지 않는다. 실집행
(개선된 IV/DV를 실제로 DB에 반영)은 사용자 승인 후 별도 스크립트로 진행한다
(v9.50.0 event_countable 재분류 선례 경로 — dry-run → 사용자 승인 → 실집행).

**회수(recovery)만 다룬다, 합성(synthesis) 아님** — 원본 h1 텍스트에 개량 파서를
재적용하는 것뿐, 신규 LLM 호출로 필드를 새로 만들지 않는다(방법론석 (D) 이분 채택 —
회수는 194 선례 동형, 합성은 confidence_at_creation 불변식과 충돌해 금지).

h1 원문을 extract_hypotheses()에 먹이려면 "[가설]" 또는 "H1:" 마커가 필요하다
(_RE_H1 캡처 전제) — DB에는 이미 캡처된 h1 필드만 남아 있으므로 "H1: " 접두어를
합성해 원 캡처 조건을 재현한다. 이 접두어 자체는 파싱 대상 텍스트가 아니라 마커일
뿐이며 회수 결과(IV/DV)에 포함되지 않는다.

실행: cd backend && .venv/bin/python3 scripts/reextract_unidentified_dryrun.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from services.hypothesis_extractor import extract_hypotheses  # noqa: E402

_DB = _BACKEND / "db" / "intel.db"
_TRIAGE = _BACKEND.parent / "exports" / "qualitative_triage.json"
_OUT = _BACKEND.parent / "exports" / "unidentified_reextract_dryrun.json"

# prediction_instrument._DECLARATION_H1과 동일 어휘 — "정량 가설 없음" 류 선언문은
# 파싱 실패가 아니라 *정직한 무가설 선언*이다. 회수 대상도 아니고 캡처 오염도 아닌
# 별도 버킷으로 갈라 리포트 정확도를 높인다(원본 필터는 build_prediction 단계 전용이라
# extract_hypotheses 자체는 이를 거르지 않음 — dry-run 분류만을 위한 재사용).
_RE_DECLARATION = re.compile(r"가설\s*없음|정량\s*가설이?\s*(?:부재|불가)|작성\s*시도했으나")


def _reextract_one(h1: str) -> tuple[str, str, bool]:
    """h1 원문에 개량 파서 재적용 → (신DV, 신IV, 회수여부).

    회수여부 = 신DV가 비어있지 않고 "미식별"이 아닌 경우.
    """
    text = f"H1: {h1 or ''}"
    specs = extract_hypotheses(text)
    if not specs:
        # 캡처 필터가 기각(비가설 조각) — 회수 대상 아님, 정직하게 미회수
        return "", "", False
    spec = specs[0]
    new_dv = (spec.dependent_var or "").strip()
    new_iv = (spec.independent_var or "").strip()
    recovered = new_dv not in ("", "미식별")
    return new_dv, new_iv, recovered


def main() -> None:
    triage = json.loads(_TRIAGE.read_text(encoding="utf-8"))
    unidentified = triage["buckets"]["unidentified"]
    ids = [row["prediction_id"] for row in unidentified]

    con = sqlite3.connect(str(_DB))
    con.row_factory = sqlite3.Row
    try:
        rows = []
        for pid in ids:
            r = con.execute(
                "SELECT prediction_id, h1, dependent_var FROM prediction_log "
                "WHERE prediction_id = ?", (pid,),
            ).fetchone()
            if r:
                rows.append(dict(r))
    finally:
        con.close()

    results = []
    recovered_n = 0
    rejected_n = 0       # 캡처 필터가 기각(비가설 조각) — 정직한 미회수
    declaration_n = 0    # "정량 가설 없음" 류 — 정직한 무가설 선언(회수 대상 아님)
    unresolved_n = 0     # 파싱은 됐으나 여전히 미식별 — 정직한 잔여 질적(과정추적 등)

    for row in rows:
        old_dv = (row["dependent_var"] or "").strip()
        h1_text = row["h1"] or ""
        new_dv, new_iv, recovered = _reextract_one(h1_text)
        if recovered:
            recovered_n += 1
            bucket = "recovered"
        elif new_dv == "" and new_iv == "":
            rejected_n += 1
            bucket = "rejected_fragment"
        elif _RE_DECLARATION.search(h1_text):
            declaration_n += 1
            bucket = "declaration_no_hypothesis"
        else:
            unresolved_n += 1
            bucket = "unresolved_qualitative"
        results.append({
            "prediction_id": row["prediction_id"],
            "구DV": old_dv,
            "신DV": new_dv,
            "신IV": new_iv,
            "회수여부": recovered,
            "버킷": bucket,
        })

    n_total = len(rows)
    n_missing = len(ids) - n_total  # DB에서 못 찾은 prediction_id (있으면 이상 신호)

    out = {
        "schema_version": 1,
        "note": (
            "dry-run 전용 — DB 무변경. recovered=DV 회수 성공, "
            "rejected_fragment=캡처 필터가 비가설로 기각(정직한 미회수), "
            "declaration_no_hypothesis='정량 가설 없음' 류 정직한 무가설 선언"
            "(build_prediction._DECLARATION_H1이 이미 신규 생성분은 등재 차단 — 이 89건은"
            " 해당 필터 도입 이전 소급분), "
            "unresolved_qualitative=파싱됐으나 DV 여전히 미식별(정직한 잔여 질적/과정추적)."
        ),
        "total_unidentified": len(ids),
        "found_in_db": n_total,
        "missing_in_db": n_missing,
        "counts": {
            "recovered": recovered_n,
            "rejected_fragment": rejected_n,
            "declaration_no_hypothesis": declaration_n,
            "unresolved_qualitative": unresolved_n,
        },
        "records": results,
    }
    _OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[dry-run] 총 {len(ids)}건 중 DB 조회 {n_total}건 (누락 {n_missing})")
    print(f"[dry-run] 회수(recovered)          : {recovered_n}")
    print(f"[dry-run] 무가설 선언(declaration) : {declaration_n}")
    print(f"[dry-run] 기각(rejected_fragment)  : {rejected_n}")
    print(f"[dry-run] 잔여(unresolved_qualitative): {unresolved_n}")
    print(f"[dry-run] 결과 export: {_OUT}")


if __name__ == "__main__":
    main()
