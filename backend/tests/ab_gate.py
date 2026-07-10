"""deepseek 쿼터 게이트 — 가용성 복귀를 감지하면 A/B 재채점을 자동 재개.

원인 실측(2026-07-10 밤): 429가 deepseek-v4-pro 모델 단위(qwen·llama는 200 OK),
분당 RPM 아닌 긴 창의 쿼터 소진. 프로브는 5토큰 콜(429 거부는 비용 0) 10분 간격.
"""
import os, sys, time, subprocess
import httpx
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
KEY = os.getenv("NVIDIA_API_KEY")

def probe() -> int:
    try:
        r = httpx.post("https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {KEY}"},
            json={"model": "deepseek-ai/deepseek-v4-pro",
                  "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            timeout=60)
        return r.status_code
    except Exception:
        return -1

n = 0
while True:
    n += 1
    code = probe()
    print(f"probe {n}: HTTP {code} ({time.strftime('%H:%M')})", flush=True)
    if code == 200:
        print("쿼터 복귀 — A/B 재개", flush=True)
        break
    time.sleep(600)

env = dict(os.environ, AB_REPEATS="2", AB_PACE="30",
           AB_RESUME="tests/eval_results/rubric_ab_20260710_1530.json")
raise SystemExit(subprocess.call(
    [".venv/bin/python", "tests/rubric_ab_rescore.py"], env=env))
