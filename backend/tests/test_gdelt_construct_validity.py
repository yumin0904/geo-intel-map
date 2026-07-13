"""
tests/test_gdelt_construct_validity.py — GDELT 구성 타당도 수리 회귀 (엔진수리위 2026-07-13)

이 파일이 지키는 것은 "코드가 도는가"가 아니라 **변수가 그 이름의 뜻인가**다.

수리한 결함 3종:
  ① 잘못된 키 — Actor1CountryCode(행위자 국적)를 사건 발생지로 오독.
     "모나코의 물리적 충돌"이 세계 어디서든 모나코 행위자가 코딩되면 세어졌다.
  ② CAMEO 스포츠 오탐 — 발생지 키로 바꿔도 모나코 279건이 잔존, 열어보니 전부
     F1 그랑프리 기사("MONACO vs POLE"=폴 포지션). 행위자 유형 필터가 두 번째 자물쇠.
  ③ goldstein_avg의 전쟁 미탐지 — 우크라이나 2022-02(전면 침공) 월평균 +0.41로
     2021-11 평시(+0.02)보다 협조적. 국가-월 평균이 폭력(음수)과 격렬 외교(양수)를
     상쇄시킨다. 컬럼은 보존하되 **어떤 소비자도 읽지 않는다**(가드 3).

실행: cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_gdelt_construct_validity.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

_DB = _BACKEND / "db" / "intel.db"
_CONFIG = _BACKEND / "config"


# ── 가드 1: FIPS→ISO3 매핑 config 무결성 ──────────────────────────────────────

def test_fips_map_integrity() -> None:
    """매핑은 코드가 아니라 config/에 산다 (헌법 §7). 그 내용이 온전한가."""
    data = yaml.safe_load((_CONFIG / "fips_iso3.yaml").read_text(encoding="utf-8"))
    m = data["fips_to_iso3"]

    # YAML 1.1 불리언 함정: 따옴표 없는 NO(노르웨이)는 False로 파싱된다.
    assert all(isinstance(k, str) and len(k) == 2 for k in m), \
        f"2자리 문자열이 아닌 키: {[k for k in m if not isinstance(k, str)]}"
    assert m["NO"] == "NOR", "FIPS 'NO'(노르웨이)가 불리언으로 삼켜졌다"

    # 실측으로 확정한 핵심 매핑 (틀리면 국가가 통째로 사라지거나 뒤바뀐다)
    assert m["MN"] == "MCO" and m["VT"] == "VAT" and m["LU"] == "LUX"
    assert m["IS"] == "ISR" and m["UP"] == "UKR"      # FIPS는 ISO2와 다르다
    assert m["KS"] == "KOR" and m["KN"] == "PRK"      # KS=남한, KN=북한
    # 다대일: 이 둘 때문에 테이블 행 키가 iso3가 아니라 fips여야 한다
    assert m["GZ"] == m["WE"] == "PSE", "가자·서안 → PSE 접기 실패"
    assert m["RI"] == m["RB"] == "SRB", "세르비아 이중코드(도시급 RI·국가급 RB) 매핑 실패"
    assert len(m) >= 250


def test_actor_filter_config() -> None:
    """행위자 유형 필터도 config/. actor2에만 CVL이 있어야 한다(국가의 대민 폭력 보존)."""
    f = yaml.safe_load(
        (_CONFIG / "gdelt_actor_types.yaml").read_text(encoding="utf-8")
    )["material_conflict_filter"]
    assert "CVL" not in f["actor1_types"], "가해 행위자에 민간이 들어가면 필터가 무의미"
    assert "CVL" in f["actor2_types"], "피해 행위자에서 민간을 빼면 대민 폭력 신호가 죽는다"
    assert {"GOV", "MIL", "REB"} <= set(f["actor1_types"])


# ── 가드 2: 소비자가 올바른 컬럼을 보는가 ─────────────────────────────────────

def test_ledger_families_use_geo_key() -> None:
    """관찰 원장의 GDELT 가족은 발생지 테이블만 본다. 물리충돌은 필터 카운트."""
    from services.observation_ledger import _FAMILIES, _RETIRED_FAMILIES

    gdelt = [f for f in _FAMILIES if "gdelt" in f.name]
    assert gdelt, "GDELT 가족이 사라졌다"
    for fam in gdelt:
        assert "gdelt_geo_country_daily" in fam.sql, f"{fam.name}이 구 테이블을 본다"
        assert "gdelt_country_daily" not in fam.sql.replace("gdelt_geo_country_daily", "")
        assert "country_iso3" in fam.sql, f"{fam.name}이 iso3로 집계하지 않는다"

    conflict = next(f for f in gdelt if "material_conflict" in f.name)
    assert "n_material_conflict_pol" in conflict.sql, \
        "물리충돌이 원본 카운트를 본다 — F1 오탐이 되살아난다"

    protest = next(f for f in gdelt if "protest" in f.name)
    assert "n_protest_pol" not in protest.sql, \
        "시위에 행위자 필터를 걸면 신호가 죽는다(민간이 주체) — 원본을 봐야 한다"

    # 폐기된 가족이 스캔 목록에 되살아나지 않았는지
    assert not (set(_RETIRED_FAMILIES) & {f.name for f in _FAMILIES})


def test_panel_catalog_uses_geo_key() -> None:
    """9-B 카운트 DV도 발생지 키 + 물리충돌 필터."""
    from services.methods.panel_regression import _VAR_CATALOG

    counts = [e for e in _VAR_CATALOG if e.is_count]
    assert len(counts) >= 2
    for e in counts:
        assert "gdelt_geo_country_daily" in e.sql
        assert "country_iso3 IS NOT NULL" in e.sql, "해양·분쟁도서 지오코딩이 패널에 샌다"

    conflict = next(e for e in counts if "충돌" in e.pattern)
    assert "n_material_conflict_pol" in conflict.sql
    protest = next(e for e in counts if "시위" in e.pattern)
    assert "SUM(n_protest)" in protest.sql and "n_protest_pol" not in protest.sql


# ── 가드 3: goldstein_avg 무소비 ─────────────────────────────────────────────

def test_goldstein_avg_has_no_consumer() -> None:
    """국가-월 평균 Goldstein은 **전쟁을 탐지하지 못한다** — 아무도 읽지 않아야 한다.

    실측: 우크라이나 2022-02(전면 침공) goldstein_avg = +0.41 (2021-11 평시 +0.02보다
    *협조적*). 평균이 폭력(음수)과 그 폭력이 부른 격렬 외교(양수)를 상쇄시킨다.
    컬럼은 진단·재현용으로 보존하되(삭제 금지), 소비 지점이 생기면 이 테스트가 깨진다.

    허용 파일: 적재 스크립트(컬럼을 만든다) · 이 테스트 · 테스트 픽스처.
    ⚠️ 이벤트 단위 GoldsteinScale(gdelt_connector 등)은 대상이 아니다 —
       상쇄는 '국가-월 평균을 낼 때' 생긴다. 여기서 막는 것은 집계 평균의 소비다.
    """
    allowed = {"scripts/load_gdelt_bq.py", "tests/test_gdelt_construct_validity.py",
               "tests/test_observation_ledger.py"}
    hits: list[str] = []
    for path in _BACKEND.rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(_BACKEND).as_posix()
        if rel in allowed:
            continue
        if re.search(r"goldstein_avg", path.read_text(encoding="utf-8", errors="ignore")):
            hits.append(rel)
    assert not hits, (
        "goldstein_avg 소비자 발견: %s — 국가-월 평균 Goldstein은 전쟁을 탐지하지 "
        "못한다(UKR 2022-02 = +0.41). 긴장·분쟁 지표로 쓰지 마라." % hits
    )


# ── 가드 4: 적재된 데이터가 실제로 결함을 고쳤는가 (DB 있을 때만) ──────────────

@pytest.mark.skipif(not _DB.exists(), reason="intel.db 없음")
def test_loaded_table_kills_sports_noise() -> None:
    """재적재된 실데이터에서 소국 잡음이 죽고 전쟁국 신호가 사는가 (2026-06 실측)."""
    con = sqlite3.connect(str(_DB))
    try:
        tbl = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='gdelt_geo_country_daily'"
        ).fetchone()
        if not tbl:
            pytest.skip("발생지 테이블 미적재")
        rows = dict(con.execute(
            "SELECT country_iso3, "
            "1.0 * SUM(n_material_conflict_pol) / NULLIF(SUM(n_material_conflict),0) "
            "FROM gdelt_geo_country_daily WHERE substr(day,1,7)='2026-06' "
            "AND country_iso3 IN ('MCO','LUX','VAT','UKR','ISR') GROUP BY 1"
        ).fetchall())
    finally:
        con.close()
    if not rows:
        pytest.skip("2026-06 데이터 없음")
    # 소국: 필터가 99%+ 를 걷어낸다 (스포츠·의례 기사)
    for iso3 in ("MCO", "LUX", "VAT"):
        if iso3 in rows and rows[iso3] is not None:
            assert rows[iso3] < 0.05, f"{iso3} 잔존율 {rows[iso3]:.1%} — 잡음이 안 죽었다"
    # 전쟁국: 신호가 남는다 (0이 되면 필터가 과한 것)
    for iso3 in ("UKR", "ISR"):
        if iso3 in rows and rows[iso3] is not None:
            assert rows[iso3] > 0.01, f"{iso3} 잔존율 {rows[iso3]:.1%} — 필터가 전쟁을 지웠다"
