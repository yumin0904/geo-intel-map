"""루브릭 v1↔v2 A/B 재채점 — T6 채택위 재베이스라인 절차 (2026-07-10).

동결 baseline(latest.json = 20260710_1101)의 full_text 48건을 생성 재실행 없이
루브릭 v1·v2로 각 REPEATS회 재채점한다 — 유일 변인이 루브릭이므로 순수 계측기
효과가 분리된다(splice 규약: 채점기 변경 = 동결 재채점).

방법론석 필수 통제 3종 (위원회 스펙 — 이 통제 없는 단발 재채점은 무효):
  1. 반복 채점 n>=3: judge는 정수기·temp 0.2라 셀당 +-0.5가 튄다. v1 반복이
     노이즈 플로어 대조군 — 판정은 "(v2-v1)이 v1<->v1 반복 노이즈 밴드 초과인가".
  2. 동결 미접촉: latest.json·20260710_1101.json은 읽기만. 산출은 신규 아티팩트
     (rubric_ab_<ts>.json)에만 기록.
  3. 골드 가드쌍 비대칭 이동: v2가 v2_rival_dv_absent_honest(정직 부재선언)를 올리고
     v2_rival_dv_present_engage(DV실재·판정참여)를 올리지 않아야 계측기 보정이다.
     둘 다 오르면 단순 인플레 — 발효 부적격.

발효 판정은 사용자 몫: 이 스크립트는 증거만 생산한다 (CHANGELOG 계측기 거버넌스 절).

실행: backend/.venv/bin/python tests/rubric_ab_rescore.py
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, '.')
from tests.eval_insight import _judge_quality, _JUDGE_RUBRIC, _JUDGE_RUBRIC_V2  # noqa: E402

RESULTS_DIR = Path('tests/eval_results')
# 속도 튜닝(2026-07-10 실측): PACE 2s 연사 6콜이 429 폭풍→긴 백오프 악순환(9케이스/96분).
# 정속 페이싱이 총 처리량에서 이긴다. REPEATS 2 축소 시 v1 3번째 표본은 원 baseline
# (latest.json quality — 동일 동결 텍스트·동일 계기)이 대신한다 — 리포트에 명기할 것.
REPEATS = int(os.getenv("AB_REPEATS", "3"))
PACE = int(os.getenv("AB_PACE", "2"))
BACKOFFS = (60, 300, 900, 1800)  # 모델 쿼터 가뭄(장기 429) 실측 반영 — 최장 ~51분 대기 후 포기
AXES = ("non_obviousness", "inference_honesty", "competing_rigor", "falsifiability")
GOLD_HONEST = "v2_rival_dv_absent_honest"
GOLD_ENGAGE = "v2_rival_dv_present_engage"

src = json.load(open(RESULTS_DIR / 'latest.json'))
assert src.get('timestamp') == '20260710_1101', "동결 baseline이 아님 — 대상 재확인"

# judge 신원 — provider가 다른 아티팩트에 이어붙이면 계측기 혼합 프랑켄슈타인
_PROVIDER = os.getenv("JUDGE_PROVIDER", "nim").strip().lower()

# 이어받기: AB_RESUME=<기존 아티팩트 경로> — 크래시/중단 후 완료 셀 보존 재개
resume = os.getenv("AB_RESUME")
if resume and Path(resume).exists():
    out_path = Path(resume)
    data = json.load(open(out_path))
    assert data.get("source_baseline") == src['timestamp'], "이어받기 대상의 baseline 불일치"
    assert data.get("judge_provider", "nim") == _PROVIDER, \
        f"이어받기 대상의 judge_provider({data.get('judge_provider','nim')}) ≠ 현재({_PROVIDER}) — 계측기 혼합 금지"
else:
    out_path = RESULTS_DIR / f"rubric_ab_{datetime.now().strftime('%Y%m%d_%H%M')}_{_PROVIDER}.json"
    data = {"source_baseline": src['timestamp'], "repeats": REPEATS,
            "judge_provider": _PROVIDER,
            "judge_model": src.get('judge_model'), "cells": {}}

cases = [r for r in src['results'] if r.get('full_text') and not r.get('error')
         and r['id'] not in data['cells']]
print(f"잔여 {len(cases)}건 × (v1+v2) × {REPEATS}회 = {len(cases)*2*REPEATS}콜 "
      f"(기완료 {len(data['cells'])}건 보존) → {out_path}", flush=True)


def score(text: str, rubric: str) -> dict | None:
    q = _judge_quality(text, rubric_text=rubric)
    for wait in BACKOFFS:
        if q is not None:
            return q
        print(f"  실패 → {wait}s 백오프", flush=True)
        time.sleep(wait)
        q = _judge_quality(text, rubric_text=rubric)
    return q


# 병렬화(직영 전환 후): NIM 무료 티어는 병렬이 judge를 전멸시켰으나(실측 07-08)
# DeepSeek 직영은 동시성 500 공식 허용 — 케이스 단위 병렬(케이스 내부는 v1/v2 교차
# 순차 유지, 쌍 구조 보존). AB_WORKERS=1이면 종전과 동일한 순차.
WORKERS = int(os.getenv("AB_WORKERS", "1"))
_lock = threading.Lock()
_done = [0]


def run_case(r: dict) -> None:
    cell = {"v1": [], "v2": []}
    for run in range(REPEATS):
        # v1/v2 교차 실행 — 시간대별 조건(레이트리밋·서버 상태)이 한쪽에 쏠리지 않게
        for ver, rub in (("v1", _JUDGE_RUBRIC), ("v2", _JUDGE_RUBRIC_V2)):
            q = score(r['full_text'], rub)
            cell[ver].append({a: q[a] for a in AXES} if q else None)
            time.sleep(PACE)
    with _lock:
        data['cells'][r['id']] = cell
        # 크래시 안전: 케이스마다 저장 (judge 콜이 비싸다 — 중단 시 기수집분 보존)
        json.dump(data, open(out_path, 'w'), ensure_ascii=False, indent=1)
        _done[0] += 1
        print(f"[{_done[0]}/{len(cases)}] {r['id']} 완료", flush=True)


if WORKERS > 1:
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(run_case, cases))
else:
    for r in cases:
        run_case(r)

# ── 집계 리포트 ──────────────────────────────────────────────────────────────
def axis_mean(ver: str, axis: str) -> float | None:
    vals = [s[axis] for c in data['cells'].values() for s in c[ver] if s]
    return round(sum(vals) / len(vals), 3) if vals else None

def cell_noise() -> float | None:
    """v1<->v1 반복의 셀 내 축평균 절대차 평균 = 노이즈 플로어."""
    diffs = []
    for c in data['cells'].values():
        runs = [s for s in c['v1'] if s]
        if len(runs) < 2:
            continue
        means = [sum(s[a] for a in AXES) / len(AXES) for s in runs]
        diffs += [abs(means[i] - means[j]) for i in range(len(means)) for j in range(i + 1, len(means))]
    return round(sum(diffs) / len(diffs), 3) if diffs else None

report = {"axis_means": {a: {"v1": axis_mean("v1", a), "v2": axis_mean("v2", a),
                             "delta": None} for a in AXES},
          "noise_floor_v1_repeat": cell_noise(), "gold_asymmetry": {}}
for a in AXES:
    m = report['axis_means'][a]
    if m['v1'] is not None and m['v2'] is not None:
        m['delta'] = round(m['v2'] - m['v1'], 3)

for gid in (GOLD_HONEST, GOLD_ENGAGE):
    c = data['cells'].get(gid)
    if not c:
        continue
    entry = {}
    for a in ("competing_rigor", "falsifiability"):
        v1 = [s[a] for s in c['v1'] if s]
        v2 = [s[a] for s in c['v2'] if s]
        if v1 and v2:
            entry[a] = {"v1": round(sum(v1) / len(v1), 2), "v2": round(sum(v2) / len(v2), 2),
                        "delta": round(sum(v2) / len(v2) - sum(v1) / len(v1), 2)}
    report['gold_asymmetry'][gid] = entry

data['report'] = report
json.dump(data, open(out_path, 'w'), ensure_ascii=False, indent=1)
print("\n== 리포트 ==", flush=True)
print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
print(f"\n완료: {out_path}", flush=True)
