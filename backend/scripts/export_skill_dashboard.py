"""
[P3-②] skill 전광판 export — 예측 원장의 누적 성적을 read-only JSON으로 노출.

데이터효용위(2026-07-12, geo-os [[20260712-data-utility-committee]]) 채택안 P3.
877행 유휴 원장을 발행 가능 자산으로 — cumulative_skill_summary(T3 채택위 후보②,
base-rate 3기준선·Wilson CI·클러스터 캐비엇 완비)를 exports/skill_dashboard.json
으로 내보낸다. editorial 등급: "데이터 업데이트성 콘텐츠"(자동 게시+사후 검토)
자격 — 너울 소비 배선은 P4/E3 몫, 여기는 산출물만.

Goodhart 가드 (원장 코드의 기존 방어 승계):
  - 이 수치는 최적화 표적이 아니다 — 대시보드 JSON에 caveats로 명문 동봉.
  - 적중률은 '방향 실현' 빈도일 뿐 인과 입증 아님.
  - 표본 클러스터링(소수 티커 유사복제) 보정 전 잠정 — n_targets 병기.

Token-Zero(LLM 無). 실행: cd backend && .venv/bin/python scripts/export_skill_dashboard.py
배선: prediction_scoring 배치(launchd 일 2회) 말미에 편승 — 채점 갱신분이 곧 반영.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_DB = _BACKEND / "db" / "intel.db"
_OUT = _BACKEND.parent / "exports" / "skill_dashboard.json"
_VERSION = json.loads((_BACKEND / "config" / "version.json").read_text())["version"]


def build_dashboard(db_path: Path | str = _DB) -> dict:
    import sys
    sys.path.insert(0, str(_BACKEND))
    from services.prediction_scorer import cumulative_skill_summary

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        skill = cumulative_skill_summary(con)
        dist = [
            {"target_kind": r[0], "status": r[1], "n": r[2]}
            for r in con.execute(
                "SELECT target_kind, status, COUNT(*) FROM prediction_log "
                "GROUP BY 1, 2 ORDER BY 3 DESC"
            ).fetchall()
        ]
        horizon = con.execute(
            "SELECT MIN(created_at), MAX(created_at), COUNT(*) FROM prediction_log"
        ).fetchone()
        recent = [
            dict(r) for r in con.execute(
                "SELECT prediction_id, target, direction, realized_direction, "
                "       realized_pct, status, scored_at "
                "FROM prediction_log WHERE status IN ('HIT','MISS') "
                "ORDER BY scored_at DESC LIMIT 10"
            ).fetchall()
        ]
    finally:
        con.close()

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_version": _VERSION,
        "skill": skill,
        "ledger_distribution": dist,
        "ledger_span": {"first": horizon[0], "last": horizon[1], "total": horizon[2]},
        "recent_scored": recent,
        "caveats": [
            "이 수치는 최적화 표적이 아니다(런 단위값 누적 승격 금지 — T3 판례 0.526 오승격 사고 선반영).",
            "적중률은 '방향 실현' 빈도일 뿐 메커니즘·인과 입증이 아니다.",
            "표본이 소수 타깃에 클러스터링돼 유의성 해석은 클러스터 보정 전 잠정(n_targets 병기).",
            "UNRESOLVED는 실패가 아니라 '잴 데이터 없음' — 해결률 집계에 섞지 않는다.",
        ],
    }


def export(db_path: Path | str = _DB, out_path: Path | str = _OUT) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_dashboard(db_path), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return out


if __name__ == "__main__":
    p = export()
    d = json.loads(p.read_text())
    s = d["skill"]
    print(f"skill_dashboard.json → {p}")
    print(f"  n={s.get('n')} hit_rate={s.get('hit_rate')} wilson95={s.get('wilson95')} "
          f"| 판정: {s.get('verdict')}")
