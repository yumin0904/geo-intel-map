"""
scripts/load_vdem_api.py

Wave-2 frozen-seed panelization fix (§ geo-os/wiki/decisions/20260709-data-audit-committee.md):
V-Dem 민주주의 지수를 vdeminstitute/vdemdata GitHub 저장소에서 전체 연도 백필한다.

기존 vdem_seed.csv 시드는 2023년 단일연도·42개국뿐이라 패널회귀(panel_regression.py)
게이트(n_units>=5 AND n_periods>=2)를 통과 못 하고 횡단(cross-section)으로만 잡혔다.

acquisition 경로 (2026-07-09 실측):
  V-Dem 공식 웹사이트(v-dem.net) 다운로드는 등록/로그인 필요 — 사용 안 함.
  대신 vdeminstitute/vdemdata (V-Dem 공식 R 패키지) GitHub 저장소의
  data/vdem.RData 가 **로그인 없이 공개** 접근 가능 (raw.githubusercontent.com, 200 OK 확인).
  .RData(R 바이너리) 포맷이라 pyreadr(순수 파이썬, R 미설치)로 파싱한다.

로드 컬럼 한정 (요구사항): iso3, country_name, year, v2x_libdem, v2x_regime, v2x_polyarchy, v2x_corr
연도 제한: year >= 1990, 전체 국가.

용량 정책: 다운로드한 vdem.RData(약 33MB)는 DB 적재 후 삭제한다(디스크 절약).
이 로더 스크립트 자체는 재실행 가능하도록 남겨둔다(재다운로드 → 재적재).

idempotent: vdem_index 는 UNIQUE(iso3, year) 이므로 INSERT OR REPLACE로 재실행해도 안전.

실행:
    /Users/kang-yumin/Projects/geo-intel-map/backend/.venv/bin/python backend/scripts/load_vdem_api.py

의존성: pip install pyreadr requests (venv에 설치됨, 2026-07-09)
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _ROOT / "backend" / "db" / "intel.db"
_RDATA_URL = "https://raw.githubusercontent.com/vdeminstitute/vdemdata/master/data/vdem.RData"
_TMP_RDATA = _ROOT / "data" / "external" / "_vdem_tmp.RData"
_MIN_YEAR = 1990

_COLS = ["country_text_id", "country_name", "year", "v2x_libdem", "v2x_regime", "v2x_polyarchy", "v2x_corr"]


def _download() -> Path:
    logger.info("V-Dem RData 다운로드 중: %s", _RDATA_URL)
    r = requests.get(_RDATA_URL, timeout=120)
    r.raise_for_status()
    _TMP_RDATA.parent.mkdir(parents=True, exist_ok=True)
    _TMP_RDATA.write_bytes(r.content)
    logger.info("다운로드 완료: %d bytes", len(r.content))
    return _TMP_RDATA


def load(con: sqlite3.Connection, rdata_path: Path) -> int:
    import pyreadr  # 지연 임포트 — 이 스크립트에서만 필요

    res = pyreadr.read_r(str(rdata_path))
    df = next(iter(res.values()))
    df = df[df["year"] >= _MIN_YEAR]

    rows = 0
    for rec in df[_COLS].itertuples(index=False):
        iso3, country_name, year, libdem, regime, polyarchy, corr = rec
        if not iso3 or len(str(iso3)) != 3:
            continue
        try:
            year_i = int(year)
        except (TypeError, ValueError):
            continue

        def _f(v):
            return None if v is None or v != v else float(v)  # v!=v → NaN 체크

        def _i(v):
            return None if v is None or v != v else int(v)

        con.execute(
            "INSERT OR REPLACE INTO vdem_index"
            " (iso3, country_name, year, v2x_libdem, v2x_regime, v2x_polyarchy, v2x_corr)"
            " VALUES (?,?,?,?,?,?,?)",
            (str(iso3), country_name, year_i, _f(libdem), _i(regime), _f(polyarchy), _f(corr)),
        )
        rows += 1
    con.commit()
    return rows


def main() -> None:
    rdata_path = _download()
    con = sqlite3.connect(_DB_PATH)
    # vdem_index 테이블은 load_external_data.py._ensure_tables()가 이미 생성함.
    n = load(con, rdata_path)
    total, min_y, max_y, n_iso3 = con.execute(
        "SELECT COUNT(*), MIN(year), MAX(year), COUNT(DISTINCT iso3) FROM vdem_index"
    ).fetchone()
    con.close()

    # 대용량 원본 파일 삭제 — 로더 스크립트만 남기고 디스크 절약
    try:
        rdata_path.unlink()
        logger.info("임시 RData 파일 삭제: %s", rdata_path)
    except OSError as e:
        logger.warning("임시 파일 삭제 실패: %s", e)

    logger.info("=== V-Dem API 백필 완료: %d행 upsert ===", n)
    logger.info("DB 현황: 총 %d행, %d~%d년, %d개국", total, min_y, max_y, n_iso3)


if __name__ == "__main__":
    main()
