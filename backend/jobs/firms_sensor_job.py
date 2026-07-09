"""
firms_sensor_job.py — NASA FIRMS 화재/열점 → sensor_snapshots 저장 잡.

6시간마다 실행. 5대 섹터 핵심 분쟁 지역 bbox를 커버.
verification_funnel.py Stage 3 (_stage3_sensor)가 이 데이터를 조회한다.

TTL: sensor_snapshots는 FIRMS 특성상 24h 이내 데이터만 유의미.
archive_manager.py가 48h 이상 된 FIRMS 스냅샷을 자동 삭제.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_INTEL_DB = os.path.join(os.path.dirname(__file__), "..", "db", "intel.db")
_FIRMS_KEY = os.getenv("FIRMS_MAP_KEY", "")
_FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
_SOURCE = "VIIRS_SNPP_NRT"

# 5대 섹터 핵심 지역 bbox (W, S, E, N)
_REGIONS: list[tuple[str, tuple[float, float, float, float]]] = [
    ("ukraine",          (22.0, 44.0, 40.0, 52.0)),
    ("middle_east",      (34.0, 28.0, 56.0, 38.0)),
    ("hormuz",           (56.0, 24.0, 62.0, 28.0)),
    ("bab_el_mandeb",    (42.0, 11.0, 46.0, 16.0)),
    ("taiwan_strait",    (118.0, 22.0, 124.0, 27.0)),
    ("south_china_sea",  (108.0, 5.0,  122.0, 22.0)),
]

# FRP (Fire Radiative Power) 임계값: 분쟁 지역 폭발·인프라 파괴 신호
_FRP_MIN = 10.0


async def run_firms_sensor_job() -> dict:
    """FIRMS NRT 화재 데이터를 조회해 sensor_snapshots에 저장한다."""
    if not _FIRMS_KEY:
        logger.warning("[firms_job] FIRMS_MAP_KEY 미설정 — 건너뜀")
        return {"saved": 0, "skipped": 0}

    saved = skipped = 0
    fail_count = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for region_code, (w, s, e, n) in _REGIONS:
            url = f"{_FIRMS_BASE}/{_FIRMS_KEY}/{_SOURCE}/{w},{s},{e},{n}/1"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                rows = _parse_csv(resp.text)
                for row in rows:
                    frp = float(row.get("frp", 0))
                    if frp < _FRP_MIN:
                        skipped += 1
                        continue
                    ok = _save_snapshot(row, region_code)
                    if ok:
                        saved += 1
            except Exception as e:
                fail_count += 1
                logger.warning("[firms_job] %s 조회 실패: %s", region_code, e)

    logger.info("[firms_job] 완료 — 저장 %d건, FRP 미달 제외 %d건", saved, skipped)

    # 판례 20260709: 전 지역 조회가 실패(예: DNS 장애)해도 saved=0을 그냥
    # 반환하면 "화재 없음"과 구분 불가 — run_firms_sensor_batch()를 거쳐
    # collect_standalone의 잡 레벨 except가 실제로 발동하도록, 일부 지역만
    # 실패했으면 그대로 반환(부분 실패 허용·집계)하고 전량 실패 시에만 던진다.
    if _REGIONS and fail_count == len(_REGIONS):
        raise RuntimeError(f"[firms_job] 전체 지역({fail_count}개) 접근 실패")

    return {"saved": saved, "skipped": skipped}


def _parse_csv(text: str) -> list[dict]:
    """FIRMS CSV 응답 파싱."""
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    result = []
    for line in lines[1:]:
        vals = [v.strip() for v in line.split(",")]
        if len(vals) == len(headers):
            result.append(dict(zip(headers, vals)))
    return result


def _save_snapshot(row: dict, region_code: str) -> bool:
    """단일 화재 포인트를 sensor_snapshots에 저장. 중복 시 무시."""
    try:
        lat = float(row.get("latitude", 0))
        lon = float(row.get("longitude", 0))
        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "0000").zfill(4)
        ts = f"{acq_date}T{acq_time[:2]}:{acq_time[2:]}:00Z"
        payload = json.dumps({
            "frp": row.get("frp"),
            "brightness": row.get("brightness"),
            "confidence": row.get("confidence"),
            "satellite": row.get("satellite"),
        })
        snap_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"firms_{lat}_{lon}_{ts}"))

        with sqlite3.connect(_INTEL_DB) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO sensor_snapshots
                    (id, source_type, timestamp, lat, lon, region_code, payload)
                VALUES (?, 'fire', ?, ?, ?, ?, ?)
                """,
                (snap_id, ts, lat, lon, region_code, payload),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.debug("[firms_job] 저장 실패: %s", e)
        return False


def run_firms_sensor_batch() -> None:
    """동기 래퍼 — APScheduler에서 호출."""
    asyncio.run(run_firms_sensor_job())
