"""
event_countable 오분류 예측의 event_series 재분류 — 원장·룰북 정비위(2026-07-12) 안건 ①.

배경: P3 triage가 지목한 194건 중 위원회 3석 실측으로 실채점 가능은 ~30건대
(정규식 오포섭 ~73%). 이 스크립트는 **결정론 화이트리스트**로 깨끗한 부분집합만
추려 target_kind='event_series'·scorable=1·target=region으로 재분류한다.

정직성 근거 (위원회 판정):
- 대상 전건 status=PENDING·resolve_by 미래(2026-12~2027-01) — 채점 창 미개방이라
  재분류는 retrodiction이 아니라 **미래 채점 경로 수리**. eligible_for_calibration=1 유지.
- 채점은 지금 하지 않는다 — 만기 도래 시 기존 prediction_scoring 배치가 자동 채점.
- 만기 경과 행이 후보에 섞이면 제외(조기/소급 채점 차단 게이트).

화이트리스트 (전부 AND — LLM 재해석 금지):
  ① DV 텍스트에 'ACLED' 명시 (분쟁 이벤트 카운트 실측정 가능 유형만 — '사망자 수'·
     '제재 명단'·'침해 건수' 등 archive에 없는 지표는 자동 탈락)
  ② region_code가 event_archive에 실존 (eastern_europe 별칭 등 조인 불가 코드 제외 —
     별칭 수리는 별도 안건)
  ③ DV 텍스트가 다른 region을 명시하면 region_code와 일치해야 함 (지역 오염 차단)
  ④ direction ∈ {up, down} · horizon_days 존재 (채점기 필수 입력)

기본 dry-run — exports/reclassify_dryrun.json에 before/after 표 기록.
**실집행은 --execute (사용자 승인 후에만).** 판례: prediction-lifecycle 소급 규약 준용.

실행: cd backend && .venv/bin/python scripts/reclassify_event_predictions.py [--execute]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_DB = _BACKEND / "db" / "intel.db"
_OUT = _BACKEND.parent / "exports" / "reclassify_dryrun.json"


def _candidates(con: sqlite3.Connection) -> tuple[list[dict], dict]:
    archive_regions = {r[0] for r in con.execute(
        "SELECT DISTINCT region_code FROM event_archive WHERE region_code IS NOT NULL")}
    today = date.today().isoformat()

    rows = con.execute(
        "SELECT prediction_id, dependent_var, region_code, direction, horizon_days, "
        "       resolve_by, status, target, target_kind "
        "FROM prediction_log WHERE target_kind='qualitative' AND status='PENDING' "
        "AND dependent_var LIKE '%ACLED%'"
    ).fetchall()

    picked, rejected = [], {"region_not_in_archive": 0, "region_mismatch": 0,
                            "no_direction": 0, "no_horizon": 0, "resolve_by_past": 0}
    for r in rows:
        (pid, dv, region, direction, horizon, resolve_by, _status, _tgt, _tk) = r
        if not region or region not in archive_regions:
            rejected["region_not_in_archive"] += 1
            continue
        # ③ DV가 명시한 region 토큰과 region_code 일치 검증
        dv_regions = set(re.findall(
            r"\b(sahel|taiwan_strait|hormuz|bab_el_mandeb|korean_peninsula|"
            r"middle_east|ukraine|east_china_sea|south_china_sea|suez|arctic)\b", dv))
        if dv_regions and region not in dv_regions:
            rejected["region_mismatch"] += 1
            continue
        if direction not in ("up", "down"):
            rejected["no_direction"] += 1
            continue
        if not horizon:
            rejected["no_horizon"] += 1
            continue
        if resolve_by and resolve_by <= today:
            rejected["resolve_by_past"] += 1      # 만기 경과 — 소급 채점 차단
            continue
        picked.append({
            "prediction_id": pid, "dv": dv[:90], "direction": direction,
            "horizon_days": horizon, "resolve_by": resolve_by,
            "before": {"target_kind": "qualitative", "scorable": 0, "target": _tgt},
            "after": {"target_kind": "event_series", "scorable": 1, "target": region},
        })
    return picked, rejected


def main() -> None:
    ap = argparse.ArgumentParser(description="event_countable 재분류 (기본 dry-run)")
    ap.add_argument("--execute", action="store_true",
                    help="실집행 — 사용자 승인 후에만 사용")
    args = ap.parse_args()

    con = sqlite3.connect(str(_DB))
    try:
        picked, rejected = _candidates(con)
        report = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mode": "EXECUTE" if args.execute else "DRY-RUN",
            "picked": len(picked), "rejected": rejected,
            "note": ("화이트리스트: DV에 ACLED 명시 AND region archive 실존 AND "
                     "DV-region 일치 AND direction/horizon 존재 AND 만기 미래. "
                     "실집행은 사용자 승인 게이트(정비위 07-12)."),
            "rows": picked,
        }
        _OUT.parent.mkdir(parents=True, exist_ok=True)
        _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                        encoding="utf-8")

        if args.execute and picked:
            for p in picked:
                con.execute(
                    "UPDATE prediction_log SET target_kind='event_series', scorable=1, "
                    "target=?, score_reason=IFNULL(score_reason,'') || ? "
                    "WHERE prediction_id=?",
                    (p["after"]["target"],
                     " [재분류 2026-07-12 정비위 — qualitative→event_series, 승인 집행]",
                     p["prediction_id"]),
                )
            con.commit()
            print("실집행 완료: %d건 재분류" % len(picked))
        print("dry-run → %s" % _OUT)
        print("후보 %d건 · 탈락 %s" % (len(picked), rejected))
        for p in picked[:12]:
            print("  %s → target=%s dir=%s h=%sd 만기=%s" % (
                p["prediction_id"][:8], p["after"]["target"], p["direction"],
                p["horizon_days"], p["resolve_by"]))
    finally:
        con.close()


if __name__ == "__main__":
    main()
