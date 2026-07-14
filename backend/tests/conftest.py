"""테스트 공통 픽스처.

## `GEO_INTEL_DB` — 검증기가 백업 DB를 물릴 수 있게 하는 문

`geo-os/tools/verify_repair.py`가 **"이 테스트는 수리 전에는 실패했다"**를 증명하려면
같은 테스트를 **수리 전 DB 백업**에 대고 돌려야 한다. 그래서 DB 경로를 하드코딩하지 않고
환경변수로 뚫어둔다.

    GEO_INTEL_DB=db/intel_pre_events_dedup.db pytest tests/test_no_double_loading.py
      → 실패해야 정상 (그게 "수리 전엔 병이 있었다"의 증거다)

⚠️ 기본값은 실 DB다. 환경변수를 안 주면 평소처럼 돈다 — 이 문은 **검증기 전용 출입구**이지
   테스트의 의미를 바꾸는 스위치가 아니다.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"


def intel_db() -> Path:
    """실 DB, 또는 검증기가 지정한 백업.

    ## worktree엔 `db/`가 없다 (2026-07-14 실측)

    `verify_repair --pre`는 구 커밋을 **worktree로 체크아웃**하는데, `db/`는 gitignore라
    **거기 없다.** 그대로 두면 테스트가 **빈 DB를 읽고 0행 → 루프 미실행 → 공허한 통과**가
    되고, 검증기는 그걸 *"수리 전에도 통과했다 = 결함의 증거가 없다"*로 읽는다.

    **B30이 그 함정에 두 번 빠졌다.** 실제로는 구 코드가 낡은 FRED 12행을 LLM 프롬프트에
    먹이고 있었는데, 테스트는 «문제 없음»을 뱉었다. **엉뚱한 이유로 딴 초록불이 가장 위험하다.**

    → `VERIFY_REAL_ROOT`(검증기가 주입)가 있으면 **실 저장소의 DB**를 문다.
      우선순위: `GEO_INTEL_DB`(--pre-db 백업) > `VERIFY_REAL_ROOT`(실 DB) > 로컬 기본값.
    """
    override = os.environ.get("GEO_INTEL_DB")
    if override:
        p = Path(override)
        return p if p.is_absolute() else Path(__file__).resolve().parents[1] / p

    real_root = os.environ.get("VERIFY_REAL_ROOT")
    if real_root:
        return Path(real_root) / "geo-intel-map" / "backend" / "db" / "intel.db"

    return _DEFAULT_DB
