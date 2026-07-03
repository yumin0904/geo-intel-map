#!/usr/bin/env python3
"""
collect_standalone.py — 서버 없이 수집 잡을 1회전 실행하는 단독 러너.

왜 필요한가:
    수집 스케줄러(APScheduler)는 FastAPI 서버 프로세스 안에서만 돈다.
    로컬 서버를 안 켜 두면 GDELT(TTL 3일)·FIRMS(24h) 같은 실시간 축이
    영구 손실된다 (실측: 2026-06-21~07-04 약 2주 공백).
    이 스크립트를 launchd가 하루 2회 실행하면 서버 가동 여부와 무관하게
    데이터가 누적된다.

실행:
    cd backend && .venv/bin/python jobs/collect_standalone.py

설계 원칙:
    - 잡 하나가 실패해도 나머지는 계속 실행 (부분 실패 허용, 로그로 보고)
    - LLM 호출 없음 (Token-Zero 태깅 — cameo_mapper 결정론 로직만 사용)
    - 종료 코드: 전체 실패(0건 성공)일 때만 1, 그 외 0
    - 서버가 동시에 켜져 있어도 안전: SQLite 잠금 충돌 시 해당 잡만 실패로
      기록되고 다음 주기에 재시도된다 (launchd가 매일 다시 실행하므로 자가 회복)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# backend/ 를 import 루트로 (launchd는 WorkingDirectory를 backend로 설정하지만,
# 직접 실행 시에도 동작하도록 명시)
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("collect_standalone")


def _load_env() -> None:
    """backend/.env 를 os.environ에 로드 (이미 설정된 변수는 존중)."""
    env_file = _BACKEND / ".env"
    if not env_file.exists():
        logger.warning(".env 없음 — FIRMS 등 키 필요 잡은 건너뛸 수 있음")
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    _load_env()

    # import는 .env 로드 후에 (모듈 상단에서 os.getenv 하는 코드 대비)
    from db.archive_manager import ArchiveManager
    from jobs.gdelt_job import run_gdelt_batch
    from jobs.firms_sensor_job import run_firms_sensor_batch
    from jobs.press_releases_job import (
        run_nk_press_batch,
        run_un_news_batch,
        run_policy_think_tank_batch,
        run_govinfo_batch,
    )
    from jobs.prediction_scoring_job import run_prediction_scoring_batch

    archive = ArchiveManager()
    archive.init_schema()

    # (이름, 함수) — 서버 스케줄러와 동일 구성에서 reliefweb 제외
    # (reliefweb 잡은 서버 요청용 캐시 만료라 단독 실행 의미 없음)
    jobs = [
        ("gdelt", run_gdelt_batch),                      # 실시간 첩보 (TTL 3일 — 최우선)
        ("firms", run_firms_sensor_batch),               # 위성 화재/열점
        ("nk_press", run_nk_press_batch),                # NKNews·38North
        ("un_news", run_un_news_batch),                  # UN News RSS
        ("policy_think_tank", run_policy_think_tank_batch),
        ("govinfo", run_govinfo_batch),                  # 대통령 성명 (1차 사료)
        ("archive_cycle", archive.run_full_cycle),       # TTL 이관·삭제
        ("prediction_scoring", run_prediction_scoring_batch),  # Phase 10-2 만기 예측 채점
    ]

    ok, failed = [], []
    t0 = time.time()
    logger.info("=== 수집 1회전 시작 (%s) ===", datetime.now().isoformat(timespec="seconds"))
    for name, fn in jobs:
        t = time.time()
        try:
            fn()
            ok.append(name)
            logger.info("[%s] 완료 (%.1fs)", name, time.time() - t)
        except Exception as e:  # 부분 실패 허용 — 다음 잡 계속
            failed.append(name)
            logger.error("[%s] 실패: %s", name, e)

    logger.info(
        "=== 수집 1회전 종료: 성공 %d / 실패 %d (%.1fs) %s ===",
        len(ok), len(failed), time.time() - t0,
        ("실패목록=" + ",".join(failed)) if failed else "",
    )
    return 1 if not ok else 0


if __name__ == "__main__":
    sys.exit(main())
