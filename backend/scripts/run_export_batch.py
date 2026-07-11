#!/usr/bin/env python3
"""
scripts/run_export_batch.py — E2 배치 래퍼: queries_*.yaml → export_insight.py 순차 실행 → 집계 리포트.

왜 필요한가: geo-os E1이 설계한 쿼리 배치(15건, geo-os/docs/E1_QUERY_BATCH_20260711.md)를
사람이 한 건씩 export_insight.py CLI로 돌리면 재현성·재개 가능성이 없다. 이 스크립트는
YAML을 단일 입력으로 받아 export_insight.py를 쿼리마다 subprocess로 순차 호출하고(병렬
금지 — provider rate limit), completeness.ok 집계와 A그룹(재실행) 신구 비교 원자료를
report_*.json에 저장한다.

저장 격리 (E1 설계 규칙): 구 export 3건(exports/insights/*.insight.json 직하)은 기사
근거 감사추적(불변 사료) — 이 스크립트가 만드는 산출은 전부 YAML meta.out_dir 하위에만
쓴다. 직하 파일은 절대 건드리지 않는다.

경계 (geo-os Scheduler 경계 규칙): 이 스크립트 실행은 geo-intel-map 내부 소관.
geo-os는 report_*.json만 소비하고 이 스크립트를 직접 호출하지 않는다.

사용법:
    cd backend
    .venv/bin/python scripts/run_export_batch.py
    .venv/bin/python scripts/run_export_batch.py --queries ../exports/batch/queries_20260711.yaml
    .venv/bin/python scripts/run_export_batch.py --dry-run
    .venv/bin/python scripts/run_export_batch.py --only redsea-suez-transit,hormuz-iran-oil
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS_DIR.parent
_REPO = _BACKEND.parent
_VENV_PYTHON = _BACKEND / ".venv" / "bin" / "python"
_EXPORT_SCRIPT = _SCRIPTS_DIR / "export_insight.py"
_DEFAULT_QUERIES = _REPO / "exports" / "batch" / "queries_20260711.yaml"
_DEFAULT_TIMEOUT_S = 300


def _load_batch(queries_path: Path) -> dict:
    """YAML 배치 파일 로드 — meta·queries 두 최상위 키를 기대한다."""
    with queries_path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if "meta" not in doc or "queries" not in doc:
        raise SystemExit(f"배치 YAML 형식 오류(meta·queries 키 필요): {queries_path}")
    return doc


def _report_path_for(queries_path: Path) -> Path:
    """queries_20260711.yaml → report_20260711.json (같은 exports/batch/ 디렉토리)."""
    name = queries_path.stem  # "queries_20260711"
    suffix = name.split("queries_", 1)[-1] if name.startswith("queries_") else name
    return queries_path.parent / f"report_{suffix}.json"


def _build_command(item: dict, out_dir: Path) -> list[str]:
    """export_insight.py 단건 CLI 커맨드 조립 (실측 시그니처: --query --id --regions
    --sectors --provider --out — --save는 이 배치 스펙에 없어 미사용)."""
    cmd = [
        str(_VENV_PYTHON), str(_EXPORT_SCRIPT),
        "--query", item["query"],
        "--id", item["id"],
        "--provider", item["provider"],
        "--out", str(out_dir),
    ]
    regions = item.get("regions") or []
    sectors = item.get("sectors") or []
    if regions:
        cmd += ["--regions", ",".join(regions)]
    if sectors:
        cmd += ["--sectors", ",".join(sectors)]
    return cmd


def _out_file(item: dict, out_dir: Path) -> Path:
    return out_dir / f"{item['id']}.insight.json"


def _read_completeness_ok(out_file: Path) -> bool | None:
    """산출 insight.json에서 completeness.ok만 읽는다. 파싱 실패해도 배치는 중단하지
    않는다(실패 격리 원칙 — 집계 항목만 None으로 남긴다)."""
    try:
        data = json.loads(out_file.read_text(encoding="utf-8"))
        return data.get("completeness", {}).get("ok")
    except (OSError, json.JSONDecodeError):
        return None


def _load_insight(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_compare_fields(insight: dict | None) -> dict:
    """신구 비교 표용 원자료 추출 — 해석·판정 없이 필드만 나란히 뽑는다."""
    if insight is None:
        return {"found": False}
    hyps = []
    for h in insight.get("hypotheses", []):
        detail = h.get("detail", {})
        hyps.append({
            "h1": detail.get("h1", ""),
            "verification_status": detail.get("verification_status"),
            "inference_grade": detail.get("inference_grade"),
        })
    return {
        "found": True,
        "engine_version": insight.get("engine_version"),
        "confidence_score": insight.get("confidence", {}).get("score"),
        "completeness_ok": insight.get("completeness", {}).get("ok"),
        "hypotheses": hyps,
    }


def _build_rerun_compare(queries: list[dict], out_dir: Path) -> list[dict]:
    """A그룹(purpose=rerun_compare) 전용 — baseline(구 export 직하 파일)과 신 산출을
    나란히 뽑는다. gemini 고정 그룹만 대상 (provider 혼합 비교 금지, E1 규정)."""
    rows = []
    for item in queries:
        if item.get("purpose") != "rerun_compare":
            continue
        baseline_id = item.get("baseline")
        baseline_path = _REPO / "exports" / "insights" / f"{baseline_id}.insight.json"
        new_path = _out_file(item, out_dir)
        rows.append({
            "id": item["id"],
            "baseline_id": baseline_id,
            "baseline": _extract_compare_fields(_load_insight(baseline_path)),
            "new": _extract_compare_fields(_load_insight(new_path)),
        })
    return rows


def run_batch(
    doc: dict,
    repo_out_dir: Path,
    only_ids: set[str] | None,
    timeout_s: int,
    dry_run: bool,
) -> dict:
    queries = doc["queries"]
    if only_ids:
        queries = [q for q in queries if q["id"] in only_ids]

    if dry_run:
        print(f"[dry-run] {len(queries)}건 — 실제 호출 0회")
        for item in queries:
            cmd = _build_command(item, repo_out_dir)
            out_file = _out_file(item, repo_out_dir)
            exists = out_file.exists()
            print(f"[dry-run] id={item['id']} provider={item['provider']} "
                  f"purpose={item.get('purpose')} out={out_file}"
                  f"{' (SKIP-exists)' if exists else ''}")
            print("  $ " + " ".join(cmd))
        return {"dry_run": True, "planned": len(queries)}

    repo_out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for item in queries:
        qid = item["id"]
        out_file = _out_file(item, repo_out_dir)

        if out_file.exists():
            print(f"[{qid}] SKIP-exists — {out_file}")
            results.append({
                "id": qid, "provider": item["provider"], "purpose": item.get("purpose"),
                "status": "SKIP-exists",
                "completeness_ok": _read_completeness_ok(out_file),
                "duration_s": 0,
            })
            continue

        cmd = _build_command(item, repo_out_dir)
        print(f"[{qid}] START provider={item['provider']} purpose={item.get('purpose')}")
        t0 = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=str(_BACKEND), timeout=timeout_s)
            duration = round(time.monotonic() - t0, 1)
            if proc.returncode == 0 and out_file.exists():
                status = "PASS"
                ok = _read_completeness_ok(out_file)
            else:
                status = "FAIL"
                ok = None
            print(f"[{qid}] END status={status} duration={duration}s "
                  f"exit={proc.returncode}")
        except subprocess.TimeoutExpired:
            duration = round(time.monotonic() - t0, 1)
            status, ok = "FAIL", None
            print(f"[{qid}] END status=FAIL duration={duration}s (timeout {timeout_s}s)")

        results.append({
            "id": qid, "provider": item["provider"], "purpose": item.get("purpose"),
            "status": status, "completeness_ok": ok, "duration_s": duration,
        })

    pass_n = sum(1 for r in results if r["status"] == "PASS")
    total_n = len(results)
    summary = f"{pass_n}/{total_n} PASS"
    print(f"\n=== {summary} ===")

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
        "summary": summary,
        "rerun_compare": _build_rerun_compare(queries, repo_out_dir),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", default=str(_DEFAULT_QUERIES),
                    help="배치 YAML 경로 (기본: exports/batch/queries_20260711.yaml)")
    ap.add_argument("--dry-run", action="store_true",
                    help="실행할 커맨드 라인 전체를 순서대로 출력만 (호출 0회)")
    ap.add_argument("--only", default="",
                    help="쉼표 구분 id 목록 — 지정된 쿼리만 실행")
    ap.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT_S,
                    help=f"쿼리당 타임아웃 초 (기본 {_DEFAULT_TIMEOUT_S})")
    args = ap.parse_args()

    queries_path = Path(args.queries)
    if not queries_path.is_absolute():
        queries_path = (Path.cwd() / queries_path).resolve()
    if not queries_path.exists():
        raise SystemExit(f"배치 YAML 없음: {queries_path}")

    doc = _load_batch(queries_path)
    out_dir = _REPO / doc["meta"]["out_dir"]
    only_ids = {s.strip() for s in args.only.split(",") if s.strip()} or None

    result = run_batch(doc, out_dir, only_ids, args.timeout, args.dry_run)

    if args.dry_run:
        return 0

    report_path = _report_path_for(queries_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"리포트 저장: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
