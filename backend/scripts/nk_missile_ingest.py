#!/usr/bin/env python3
"""
scripts/nk_missile_ingest.py — CNS 북한 미사일 발사 DB → event_archive 적재.

목표(데이터 수집 루프, 2026-07-06): data_gap 원장이 지목한 최상위 갱 — "북한 미사일 도발"을
검정할 구조화 이벤트 시계열. ACLED는 폐쇄국가 북한을 커버 못 해 7호에서 korean_peninsula
이벤트가 남한 시위 98%였다. CNS(James Martin Center for Nonproliferation Studies)가
1984년부터 모든 발사를 큐레이션한 Excel을 NTI가 공개 — 이를 Event로 정규화한다.

출처: CNS North Korea Missile Test Database (NTI 호스팅).
  https://www.nti.org/analysis/articles/cns-north-korea-missile-test-database/
라이선스: 학술·연구 인용. payload.source에 출처 명시.

핵심 태깅(구성타당도 게이트 통과 목적): payload.country="North Korea" ·
source_type="missile_test" — 이래야 iv_construct 프로브가 "북한 도발" 쿼리에서
North Korea를 인식하고, 후속 actor 필터(A-1)가 순수 북한 도발 시계열을 뽑는다.

실행: cd backend && .venv/bin/python scripts/nk_missile_ingest.py [--file 로컬.xlsx]
멱등: id 기반 INSERT OR REPLACE (재실행 안전).
"""
from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import openpyxl

_BACKEND = Path(__file__).resolve().parents[1]
_DB_PATH = _BACKEND / "db" / "intel.db"
_SRC_URL = "https://www.nti.org/wp-content/uploads/2021/10/north_korea_missile_test_database.xlsx"
_SOURCE = "CNS North Korea Missile Test Database (NTI)"

# 미사일 종류 → severity (사거리·위협도 기반, 0~100). 헌법 §8 severity 정규화.
_SEV_BY_TYPE = {
    "ICBM": 95, "IRBM": 80, "SLBM": 78, "MRBM": 65, "SLV": 60,
    "SRBM": 50, "CRBM": 45, "Unknown": 40,
}
_THEORY_TAGS = ["missile_proliferation", "gray_zone", "deterrence"]


def _download(url: str) -> bytes:
    r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (research)"},
                  timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.content


def _parse(xlsx_bytes: bytes) -> list[dict]:
    """CNS xlsx → 발사 이벤트 dict 목록. 헤더는 2번째 행, 데이터는 3번째부터."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[1]
    idx = {h: i for i, h in enumerate(hdr) if h}

    def g(row, col):  # 안전 접근
        i = idx.get(col)
        return row[i] if i is not None and i < len(row) else None

    events = []
    for n, row in enumerate(rows[2:], start=1):
        date = g(row, "Date")
        if not date:
            continue
        # openpyxl datetime 또는 문자열
        ts = date.isoformat() if hasattr(date, "isoformat") else str(date)
        mtype = str(g(row, "Missile Type") or "Unknown").strip()
        mname = str(g(row, "Missile Name") or "Unknown").strip()
        facility = str(g(row, "Facility Name") or "Unknown").strip()
        loc = str(g(row, "Facility Location") or "").strip()
        outcome = str(g(row, "Test Outcome") or "").strip()
        lat = g(row, "Facility Latitude")
        lng = g(row, "Facility Longitude")
        try:
            lat = float(lat); lng = float(lng)
        except (TypeError, ValueError):
            lat = lng = None

        payload = {
            "country": "North Korea",          # ★ 구성타당도 게이트 인식 핵심
            "actor1": g(row, "Launch Agency/Authority") or "North Korea",
            "event_type": "missile_test",
            "missile_name": mname,
            "missile_type": mtype,
            "facility": facility,
            "facility_location": loc,
            "test_outcome": outcome,
            "apogee": g(row, "Apogee"),
            "distance_km": g(row, "Distance Travelled"),
            "data_source": "CNS",
            "source": _SOURCE,
        }
        events.append({
            "id": f"cns_nk_missile_{n:04d}_{ts[:10]}",
            "timestamp": ts,
            "source_type": "missile_test",
            # north_korea = 행위자형 region (미사일 도발 주체 기준) — north_korea_missile_to_krw
            # 룰의 데이터원. korean_peninsula 하드코딩이던 것을 판례 20260709 위원회가 재라우팅.
            "region_code": "north_korea",
            "severity": _SEV_BY_TYPE.get(mtype, 40),
            "title": f"[CNS] 북한 {mname} ({mtype}) 발사 — {facility}",
            "description": f"{outcome} · {loc}".strip(" ·"),
            "lat": lat, "lng": lng,
            "payload": payload,
        })
    return events


def _load(events: list[dict]) -> tuple[int, int]:
    con = sqlite3.connect(_DB_PATH)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ins = 0
    for e in events:
        con.execute(
            """
            INSERT OR REPLACE INTO event_archive
                (id, timestamp, source_type, region_code, severity,
                 confidence_score, importance_score, title, description,
                 payload, theory_tags, archived_at, archive_reason)
            VALUES (?, ?, ?, ?, ?, 1.0, 0.6, ?, ?, ?, ?, ?, 'cns_missile')
            """,
            (e["id"], e["timestamp"], e["source_type"], e["region_code"], e["severity"],
             e["title"], e["description"], json.dumps(e["payload"], ensure_ascii=False),
             json.dumps(_THEORY_TAGS), now),
        )
        ins += 1
    con.commit()
    n_total = con.execute(
        "SELECT COUNT(*) FROM event_archive WHERE source_type='missile_test'"
    ).fetchone()[0]
    con.close()
    return ins, n_total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", default="", help="로컬 xlsx 경로 (없으면 NTI에서 다운로드)")
    args = ap.parse_args()

    if args.file:
        data = Path(args.file).read_bytes()
        print(f"로컬 파일: {args.file}")
    else:
        print(f"다운로드: {_SRC_URL}")
        data = _download(_SRC_URL)
    print(f"  {len(data):,} bytes")

    events = _parse(data)
    print(f"파싱: {len(events)}건 발사 이벤트")
    if events:
        print(f"  범위: {events[0]['timestamp'][:10]} ~ {events[-1]['timestamp'][:10]}")

    ins, total = _load(events)
    print(f"✅ 적재 {ins}건 → event_archive (source_type=missile_test 누적 {total}건)")
    print("   country=North Korea 태깅 — 구성타당도 게이트가 북한 도발 쿼리에서 인식")
    return 0


if __name__ == "__main__":
    sys.exit(main())
