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
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_INTEL_DB = os.path.join(os.path.dirname(__file__), "..", "db", "intel.db")
_FIRMS_KEY = os.getenv("FIRMS_MAP_KEY", "")
_FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
_AVAIL_URL = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{key}/ALL"

# ── 위성 소스 선택 (2026-07-13 수리) ──────────────────────────────────────────
# 배경: 이 잡은 _SOURCE="VIIRS_SNPP_NRT" 고정이었고, 그 데이터셋이 2026-07-10에
#   멈췄다. NASA는 죽은 데이터셋에도 HTTP 200 + **헤더 줄만** 돌려준다 — 그래서
#   잡은 "화재 0건"으로 읽고 정상 종료했고, sensor_snapshots는 계속 0행이었다.
#   검증 퍼널 Stage 3(물리 센서 결합, +0.1)이 빈 테이블을 대조하고 있었다.
#
#   이건 엔진이 이미 아는 병이다 — **stale(소스가 죽음)을 sparse(사건이 없음)로
#   오진**하는 것. correlation.py의 fill_value=0과 같은 계열이다.
#
# 처방: 소스 이름을 다른 위성으로 갈아끼우는 것은 같은 사고를 미루는 것뿐이다
#   (위성은 계속 은퇴한다 — SNPP는 2011년 발사체). NASA가 가용성 표를 공개하므로
#   **매 런마다 그 표를 읽고 살아 있는 소스를 고른다.** 전부 죽었으면 조용히 0을
#   반환하지 않고 **던진다**(fail-loud) — 0건은 "없다"가 아니라 "못 쟀다"이다.
_SOURCE_PREFERENCE = [
    "VIIRS_NOAA21_NRT",   # 최신 VIIRS (2022 발사)
    "VIIRS_NOAA20_NRT",   # 차순위 VIIRS
    "VIIRS_SNPP_NRT",     # 구 기본값 — 2026-07-10 정체 중, 되살아나면 자동 복귀
    "MODIS_NRT",          # 해상도는 낮으나(1km) 최후 보루
]
# 가용성 표의 max_date가 오늘로부터 이만큼 넘게 뒤처지면 죽은 소스로 본다.
# 1일: NRT 피드는 수 시간 내 갱신이 정상이라 이틀치 공백이면 이미 이상이다.
_MAX_SOURCE_LAG_DAYS = 1

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


def parse_availability(text: str) -> dict[str, date]:
    """NASA 가용성 표(CSV: data_id,min_date,max_date) → {소스명: max_date}."""
    avail: dict[str, date] = {}
    for line in text.strip().splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            avail[parts[0]] = date.fromisoformat(parts[2])
        except ValueError:
            continue
    return avail


def select_source(avail: dict[str, date], today: date,
                  max_lag_days: int = _MAX_SOURCE_LAG_DAYS) -> str:
    """선호 순서대로 훑어 **아직 갱신되는** 첫 소스를 고른다.

    순수 함수(네트워크 없음) — 회귀 테스트가 이 판정을 직접 검증한다.
    전부 뒤처졌으면 RuntimeError. 조용히 0건을 반환하지 않는 것이 요점이다:
    "화재가 없었다"와 "잴 위성이 없었다"는 다른 사실이고, 후자를 전자로
    보고하는 순간 하류(검증 퍼널 Stage 3)가 거짓 음성을 먹는다.
    """
    for src in _SOURCE_PREFERENCE:
        max_date = avail.get(src)
        if max_date and (today - max_date).days <= max_lag_days:
            return src
    detail = ", ".join(f"{s}={avail.get(s, '없음')}" for s in _SOURCE_PREFERENCE)
    raise RuntimeError(
        f"[firms_job] 갱신되는 NRT 위성 소스가 없다 (기준일 {today}, 허용 랙 "
        f"{max_lag_days}일) — {detail}. 0건 반환이 아니라 실패로 올린다."
    )


async def _resolve_source(client: httpx.AsyncClient) -> str:
    """NASA 가용성 표를 읽어 이번 런에서 쓸 소스를 결정한다."""
    resp = await client.get(_AVAIL_URL.format(key=_FIRMS_KEY))
    resp.raise_for_status()
    avail = parse_availability(resp.text)
    src = select_source(avail, datetime.now(timezone.utc).date())
    logger.info("[firms_job] 소스 선택: %s (max_date=%s)", src, avail[src])
    return src


async def run_firms_sensor_job() -> dict:
    """FIRMS NRT 화재 데이터를 조회해 sensor_snapshots에 저장한다."""
    if not _FIRMS_KEY:
        logger.warning("[firms_job] FIRMS_MAP_KEY 미설정 — 건너뜀")
        return {"saved": 0, "skipped": 0}

    saved = skipped = 0
    fail_count = 0
    async with httpx.AsyncClient(timeout=30) as client:
        # 소스 결정 실패는 삼키지 않는다 — 잴 위성이 없으면 잡이 실패해야 한다
        source = await _resolve_source(client)

        for region_code, (w, s, e, n) in _REGIONS:
            url = f"{_FIRMS_BASE}/{_FIRMS_KEY}/{source}/{w},{s},{e},{n}/1"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                rows = _parse_csv(resp.text)
                for row in rows:
                    frp = float(row.get("frp", 0))
                    if frp < _FRP_MIN:
                        skipped += 1
                        continue
                    ok = _save_snapshot(row, region_code, source)
                    if ok:
                        saved += 1
            except Exception as e:
                fail_count += 1
                logger.warning("[firms_job] %s 조회 실패: %s", region_code, e)

    logger.info("[firms_job] 완료 — 소스 %s, 저장 %d건, FRP 미달 제외 %d건",
                source, saved, skipped)

    # 판례 20260709: 전 지역 조회가 실패(예: DNS 장애)해도 saved=0을 그냥
    # 반환하면 "화재 없음"과 구분 불가 — run_firms_sensor_batch()를 거쳐
    # collect_standalone의 잡 레벨 except가 실제로 발동하도록, 일부 지역만
    # 실패했으면 그대로 반환(부분 실패 허용·집계)하고 전량 실패 시에만 던진다.
    if _REGIONS and fail_count == len(_REGIONS):
        raise RuntimeError(f"[firms_job] 전체 지역({fail_count}개) 접근 실패")

    return {"saved": saved, "skipped": skipped, "source": source}


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


def _save_snapshot(row: dict, region_code: str, source: str = "") -> bool:
    """단일 화재 포인트를 sensor_snapshots에 저장. 중복 시 무시."""
    try:
        lat = float(row.get("latitude", 0))
        lon = float(row.get("longitude", 0))
        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "0000").zfill(4)
        ts = f"{acq_date}T{acq_time[:2]}:{acq_time[2:]}:00Z"
        payload = json.dumps({
            "frp": row.get("frp"),
            # VIIRS는 bright_ti4/ti5, MODIS는 brightness — 소스마다 컬럼명이 다르다.
            # 둘 다 담아 하류가 어느 위성 산출인지 알 수 있게 한다.
            "brightness": row.get("brightness") or row.get("bright_ti4"),
            "confidence": row.get("confidence"),
            "satellite": row.get("satellite"),
            "data_source": source,   # 어느 위성이 잰 값인가 (변수 신원)
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
