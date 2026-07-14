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
    """실 DB, 또는 검증기가 지정한 백업."""
    override = os.environ.get("GEO_INTEL_DB")
    if not override:
        return _DEFAULT_DB
    p = Path(override)
    return p if p.is_absolute() else Path(__file__).resolve().parents[1] / p
