"""eval 원장 judge 백필 — 순차 후처리 (병렬 포화 후 채점 소실 회복).

2026-07-10 수리 (구버전 결함 2건 — qwen3.5 신 baseline 백필 전패 사후 부검):
  1. 아카이브 대상이 '20260708_*' 글롭 하드코딩 → latest.json의 timestamp 필드로
     대응 아카이브를 특정한다. (구버전은 07-10 원장을 07-08 파일에 덮어써 구원장
     클로버 — git의 latest.json 이력(e09a2d7)에서 복구했음.)
  2. 429(레이트리밋) 무대응 → 지수 백오프 재시도 3회(60/120/240s). NIM 무료 티어는
     풀런 직후 judge 연타에 429를 던진다(실측 2026-07-10).

  안전 규약: judged 0이면 파일을 쓰지 않는다 (무의미 재기록 + 클로버 위험 차단).

실행: backend/.venv/bin/python tests/judge_backfill.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, '.')
from tests.eval_insight import _judge_quality  # noqa: E402

RESULTS_DIR = Path('tests/eval_results')
BACKOFFS = (60, 120, 240)   # 429 재시도 대기(초)
PACE = 5                    # 케이스 간 기본 간격(초) — RPM 여유

latest_path = RESULTS_DIR / 'latest.json'
d = json.load(open(latest_path))

# 대응 아카이브 = latest의 timestamp (없으면 latest만 갱신)
ts = d.get('timestamp', '')
arch_path = RESULTS_DIR / f'{ts}.json'
targets = [latest_path] + ([arch_path] if arch_path.exists() else [])
print(f"대상: {[str(p) for p in targets]}", flush=True)

ok = 0
for i, r in enumerate(d['results']):
    t = r.get('full_text', '')
    # 기채점 스킵: 재실행 시 성공분 재채점 방지 (쿼터 절약 + 429 재유발 차단)
    if not t or r.get('error') or r.get('quality'):
        continue
    q = _judge_quality(t)
    for wait in BACKOFFS:
        if q is not None:
            break
        print(f"[{i+1}/{len(d['results'])}] {r['id']}: 실패 → {wait}s 백오프", flush=True)
        time.sleep(wait)
        q = _judge_quality(t)
    if q:
        r['quality'] = q
        ok += 1
    print(f"[{i+1}/{len(d['results'])}] {r['id']}: {'OK' if q else 'FAIL(백오프 소진)'}", flush=True)
    time.sleep(PACE)

if ok == 0:
    print("judged 0 — 파일 미기록 (쿼터 소진 추정, 나중에 재실행)")
    sys.exit(1)
for p in targets:
    json.dump(d, open(p, 'w'), ensure_ascii=False, indent=2)
print(f"백필 완료 judged {ok} → {[str(p) for p in targets]}")
