"""
[P3-③] 질적 예측 triage — report-only 분류 (DB 무변).

데이터효용위(2026-07-12) P3 집행분. 방치돼 온 qualitative 예측(PENDING 377 +
UNRESOLVED)을 채점 가능성별로 분류해 exports/qualitative_triage.json 으로 보고한다.
어떤 행도 수정하지 않는다 — 재분류·소급 채점은 [판단필요] (인간 승인 후 별도 집행,
prediction-lifecycle 판례의 소급 9건 전례 준용).

분류 버킷:
  event_countable  — DV가 이벤트 건수·빈도류(ACLED·HIIK·건수·빈도) → event_series
                     기계 채점으로 재지정 가능한 오분류 후보 (이번 실측의 핵심 발견)
  structural_panel — DV가 패널 카탈로그 어휘(민주주의·거버넌스·군사비·부패 등)
                     → 연간 빈티지 지평 불일치로 단기 채점 부적합, 장기 대조 후보
  market_like      — DV가 가격·환율·주가류 → market 채점 재지정 검토 후보
  human_judgment   — 서술형 질적 주장 → 큐 7 인간 사후 채점 큐의 실표본
  unidentified     — DV 미식별 → 채점 불능, 상류(10-1) 추출 품질 안건

실행: cd backend && .venv/bin/python scripts/triage_qualitative_predictions.py
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_DB = _BACKEND / "db" / "intel.db"
_OUT = _BACKEND.parent / "exports" / "qualitative_triage.json"

_RULES: list[tuple[str, re.Pattern]] = [
    ("event_countable", re.compile(
        r"ACLED|HIIK|이벤트.*건수|건수|빈도|횟수|발생.*수|사망자 수|공격.*건")),
    ("structural_panel", re.compile(
        r"민주주의|거버넌스|부패|법치|정치.*안정|군사비|국방비|GDP 대비|핵탄두|polyarchy")),
    ("market_like", re.compile(
        r"가격|주가|환율|유가|수익률|지수.*포인트|USD|KRW|프리미엄")),
]


def classify(dv: str | None) -> str:
    if not dv or dv.strip() in ("미식별", "…", ""):
        return "unidentified"
    for bucket, pat in _RULES:
        if pat.search(dv):
            return bucket
    return "human_judgment"


def triage(db_path: Path | str = _DB) -> dict:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        # [위원회 20260712 실집행] voided_reason 마킹 행(캡처 기각·무가설 선언 43건,
        # apply_unidentified_reextract.py --execute)은 DELETE 없이 보존하되 채점·triage
        # 모수에서 제외한다 — 컬럼이 없는 구 DB에서도 동작하도록 존재 여부를 먼저 확인.
        cols = {r[1] for r in con.execute("PRAGMA table_info(prediction_log)")}
        void_filter = "AND voided_reason IS NULL " if "voided_reason" in cols else ""
        rows = con.execute(
            "SELECT prediction_id, dependent_var, region_code, resolve_by, status "
            "FROM prediction_log WHERE target_kind = 'qualitative' "
            "AND status IN ('PENDING', 'UNRESOLVED') " + void_filter
        ).fetchall()
    finally:
        con.close()

    buckets: dict[str, list[dict]] = {}
    for r in rows:
        b = classify(r["dependent_var"])
        buckets.setdefault(b, []).append({
            "prediction_id": r["prediction_id"],
            "dv": (r["dependent_var"] or "")[:80],
            "region": r["region_code"], "status": r["status"],
            "resolve_by": r["resolve_by"],
        })

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(rows),
        "counts": {k: len(v) for k, v in sorted(buckets.items(),
                                                key=lambda kv: -len(kv[1]))},
        "note": ("report-only — 재분류·소급 채점은 인간 승인 후 별도 집행. "
                 "event_countable은 event_series 기계 채점 재지정 후보(오분류 발견), "
                 "human_judgment가 큐 7 인간 채점 큐의 실표본."),
        "buckets": buckets,
    }


if __name__ == "__main__":
    out = triage()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"qualitative_triage.json → {_OUT}")
    print(f"  총 {out['total']}건: " + " · ".join(
        f"{k} {n}" for k, n in out["counts"].items()))
