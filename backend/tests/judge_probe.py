"""judge 고장 모드 판별 프로브 — 상태코드·지연·finish_reason·토큰·헤더를 전부 노출."""
import json, os, sys, time
import httpx
sys.path.insert(0, '.')
from tests.eval_insight import _JUDGE_RUBRIC, _JUDGE_RUBRIC_V2

key = os.getenv("NVIDIA_API_KEY")
if not key:
    from dotenv import load_dotenv; load_dotenv(); key = os.getenv("NVIDIA_API_KEY")
base = "https://integrate.api.nvidia.com/v1"
src = json.load(open('tests/eval_results/latest.json'))
text = next(r['full_text'] for r in src['results'] if r.get('full_text'))[:12000]

for name, rubric, mt in [("v1_mt4000", _JUDGE_RUBRIC, 4000), ("v2_mt4000", _JUDGE_RUBRIC_V2, 4000)]:
    t0 = time.time()
    try:
        r = httpx.post(f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "deepseek-ai/deepseek-v4-pro",
                  "messages": [{"role": "user", "content": rubric + text}],
                  "temperature": 0.2, "max_tokens": mt},
            timeout=300)
        el = time.time() - t0
        print(f"== {name}: HTTP {r.status_code} / {el:.0f}s")
        rl = {k: v for k, v in r.headers.items() if 'rate' in k.lower() or 'retry' in k.lower()}
        if rl: print("   headers:", rl)
        if r.status_code == 200:
            d = r.json(); ch = d["choices"][0]
            content = ch["message"].get("content") or ""
            print(f"   finish_reason={ch.get('finish_reason')} usage={d.get('usage')}")
            print(f"   content_len={len(content)} json_at_end={'{' in content[-400:]}")
            print(f"   tail: ...{content[-160:]!r}")
        else:
            print("   body:", r.text[:300])
    except Exception as e:
        print(f"== {name}: EXC {type(e).__name__}: {e} / {time.time()-t0:.0f}s")
    time.sleep(10)
