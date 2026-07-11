#!/bin/bash
# eval_wrapper.sh — 주기 무심판 eval 런 (예측-신뢰도 쌍 축적, 축적루틴위 2026-07-11)
#
# 목적: confidence_at_creation 쌍은 /api/intel/query 실행 시에만 쌓인다(실측 0/896).
# 주 1회 무심판(judge 없음 — 비용 0, NIM 생성만) eval 스위트를 돌려 축적한다.
#
# 가드 (위원회 판결 — 완화 금지):
#   - --no-latest-write: judge 점수 없는 리포트가 baseline 슬롯(latest.json)을 덮으면
#     "판단력 하락"으로 오독된다 (시스템석 실측 — 오염 실재).
#   - --parallel 1 순차: NIM 무료 티어 쿼터 가뭄(장기 429 실측) 회피. 심야 스케줄도 같은 이유.
#   - 서버 기실행이면 재사용하고 종료하지 않는다 (개발 세션 살해 금지).

set -u
BACKEND="/Users/kang-yumin/Projects/geo-intel-map/backend"
PY="$BACKEND/.venv/bin/python"
HEALTH="http://localhost:8000/api/health"
LOG_PREFIX="[eval_wrapper $(date '+%F %T')]"

cd "$BACKEND" || exit 1

started_server=0
if ! curl -sf "$HEALTH" > /dev/null 2>&1; then
    echo "$LOG_PREFIX 서버 기동"
    "$PY" -m uvicorn main:app --port 8000 --log-level warning &
    SERVER_PID=$!
    started_server=1
    # 헬스체크 — 최대 60초 대기
    for _ in $(seq 1 30); do
        sleep 2
        curl -sf "$HEALTH" > /dev/null 2>&1 && break
    done
    if ! curl -sf "$HEALTH" > /dev/null 2>&1; then
        echo "$LOG_PREFIX 서버 기동 실패 — eval 중단"
        kill "$SERVER_PID" 2>/dev/null
        exit 1
    fi
else
    echo "$LOG_PREFIX 기존 서버 재사용 (종료하지 않음)"
fi

echo "$LOG_PREFIX 무심판 eval 시작 (순차·latest 보호)"
"$PY" tests/eval_insight.py --no-latest-write --no-save-text --parallel 1
rc=$?
echo "$LOG_PREFIX eval 종료 (rc=$rc)"

if [ "$started_server" -eq 1 ]; then
    echo "$LOG_PREFIX 서버 종료"
    kill "$SERVER_PID" 2>/dev/null
fi

exit $rc
