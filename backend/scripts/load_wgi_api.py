"""
scripts/load_wgi_api.py

Wave-2 frozen-seed panelization fix (§ geo-os/wiki/decisions/20260709-data-audit-committee.md):
World Bank WGI(Worldwide Governance Indicators)를 API에서 전체 연도(1996~2024) 백필한다.

기존 world_bank_seed.csv 시드는 2022년 단일연도·28개국뿐이라 패널회귀(panel_regression.py)
게이트(n_units>=5 AND n_periods>=2)를 통과 못 하고 횡단(cross-section)으로만 잡혔다.
이 스크립트는 World Bank API로 전체 연도를 받아 world_bank_wgi 테이블을 패널로 채운다.

API 참고:
  국가 목록: https://api.worldbank.org/v2/country?format=json&per_page=400
    (region.value == "Aggregates" 인 항목은 세계은행 집계 리전이지 실제 국가가 아니므로 제외)
  지표 데이터: https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&per_page=20000&date=1996:2024

지표 코드 (2026-07 기준 실측 — 문서상 흔히 보이는 'PV.EST' 등 짧은 코드는
2026-07-09 확인 결과 "Invalid format/not found"로 폐기됨. 실제 유효 코드는 GOV_WGI_ 접두 버전):
  GOV_WGI_PV.EST → pv_score (Political Stability)
  GOV_WGI_CC.EST → cc_score (Control of Corruption)
  GOV_WGI_RL.EST → rl_score (Rule of Law)
  GOV_WGI_GE.EST → ge_score (Government Effectiveness)
  GOV_WGI_RQ.EST → rq_score (Regulatory Quality)
  GOV_WGI_VA.EST → va_score (Voice and Accountability)

idempotent: world_bank_wgi 는 UNIQUE(iso3, year) 이므로 INSERT OR REPLACE로 재실행해도 안전.

실행:
    /Users/kang-yumin/Projects/geo-intel-map/backend/.venv/bin/python backend/scripts/load_wgi_api.py
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _ROOT / "backend" / "db" / "intel.db"

_INDICATORS = {
    "GOV_WGI_PV.EST": "pv_score",
    "GOV_WGI_CC.EST": "cc_score",
    "GOV_WGI_RL.EST": "rl_score",
    "GOV_WGI_GE.EST": "ge_score",
    "GOV_WGI_RQ.EST": "rq_score",
    "GOV_WGI_VA.EST": "va_score",
}
_DATE_RANGE = "1996:2024"
_TIMEOUT = 30


def _fetch_valid_iso3() -> dict[str, str]:
    """세계은행 집계 리전(예: World, OECD members)을 제외한 실제 국가 iso3→국가명 맵."""
    r = requests.get(
        "https://api.worldbank.org/v2/country",
        params={"format": "json", "per_page": 400},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    countries = data[1] if len(data) > 1 and data[1] else []
    out: dict[str, str] = {}
    for c in countries:
        if c.get("region", {}).get("value", "").strip() == "Aggregates":
            continue
        iso3 = c.get("id", "")
        if iso3 and len(iso3) == 3:
            out[iso3] = c.get("name", "")
    return out


def _fetch_indicator(code: str) -> list[dict]:
    """지표 코드 하나를 전체 연도·전체 국가로 페이지네이션하며 가져온다."""
    rows: list[dict] = []
    page = 1
    while True:
        r = requests.get(
            f"https://api.worldbank.org/v2/country/all/indicator/{code}",
            params={
                "format": "json",
                "per_page": 20000,
                "date": _DATE_RANGE,
                "page": page,
            },
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            break
        meta, chunk = payload[0], payload[1]
        rows.extend(chunk)
        if page >= meta.get("pages", 1):
            break
        page += 1
    return rows


def load(con: sqlite3.Connection) -> int:
    valid_iso3 = _fetch_valid_iso3()
    logger.info("세계은행 실제 국가 %d개 확인", len(valid_iso3))

    # iso3+year → {score_col: value} 로 6개 지표를 병합
    merged: dict[tuple[str, int], dict] = {}
    for code, col in _INDICATORS.items():
        logger.info("지표 %s (%s) 다운로드 중...", code, col)
        raw = _fetch_indicator(code)
        n_kept = 0
        for rec in raw:
            iso3 = rec.get("countryiso3code") or ""
            if iso3 not in valid_iso3:
                continue
            value = rec.get("value")
            if value is None:
                continue
            try:
                year = int(rec.get("date"))
            except (TypeError, ValueError):
                continue
            key = (iso3, year)
            entry = merged.setdefault(key, {"country_name": valid_iso3[iso3]})
            entry[col] = float(value)
            n_kept += 1
        logger.info("  %s: %d개 유효 관측치", code, n_kept)
        time.sleep(0.2)  # API 예의상 페이싱

    rows = 0
    for (iso3, year), entry in merged.items():
        con.execute(
            "INSERT OR REPLACE INTO world_bank_wgi"
            " (iso3, country_name, year, pv_score, cc_score, rl_score, ge_score, rq_score, va_score)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                iso3, entry.get("country_name"), year,
                entry.get("pv_score"), entry.get("cc_score"), entry.get("rl_score"),
                entry.get("ge_score"), entry.get("rq_score"), entry.get("va_score"),
            ),
        )
        rows += 1
    con.commit()
    return rows


def main() -> None:
    con = sqlite3.connect(_DB_PATH)
    # world_bank_wgi 테이블은 load_external_data.py._ensure_tables()가 이미 생성함 —
    # 여기서는 스키마를 다시 만들지 않고 기존 테이블에 INSERT OR REPLACE만 한다.
    n = load(con)
    total, min_y, max_y, n_iso3 = con.execute(
        "SELECT COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT iso3) FROM world_bank_wgi"
    ).fetchone()
    con.close()
    logger.info("=== WGI API 백필 완료: %d행 upsert ===", n)
    logger.info("DB 현황: 총 %d행, %d~%d년, %d개국", total, min_y, max_y, n_iso3)


if __name__ == "__main__":
    main()
