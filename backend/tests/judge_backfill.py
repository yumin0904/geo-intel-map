"""48케이스 combined 런 judge 백필 — 순차 후처리 (병렬 포화 후 채점 소실 회복)."""
import json, sys, time, glob
sys.path.insert(0, '.')
from tests.eval_insight import _judge_quality
latest = 'tests/eval_results/latest.json'
arch = sorted(glob.glob('tests/eval_results/20260708_*.json'))[-1]
d = json.load(open(latest)); ok = 0
for i, r in enumerate(d['results']):
    t = r.get('full_text', '')
    if not t or r.get('error'):
        continue
    q = _judge_quality(t)
    if q: r['quality'] = q; ok += 1
    print(f"[{i+1}/{len(d['results'])}] {r['id']}: {'OK' if q else 'FAIL'}", flush=True)
    time.sleep(2)
for p in (latest, arch):
    json.dump(d, open(p, 'w'), ensure_ascii=False, indent=2)
print(f"백필 완료 judged {ok} → {arch}")
