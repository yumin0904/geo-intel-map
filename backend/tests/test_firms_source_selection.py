"""
test_firms_source_selection.py — FIRMS 위성 소스 선택 회귀 그물 (2026-07-13).

무엇을 막는가:
    이 잡은 _SOURCE="VIIRS_SNPP_NRT" 고정이었고, 그 데이터셋이 2026-07-10에 멈췄다.
    NASA는 죽은 데이터셋에도 HTTP 200 + **헤더 줄만** 돌려준다. 잡은 그것을
    "화재 0건"으로 읽고 정상 종료했고, sensor_snapshots는 계속 0행이었다 —
    검증 퍼널 Stage 3(물리 센서 결합)이 빈 테이블을 대조하고 있었다.

    엔진이 이미 아는 병이다: **stale(소스가 죽음)을 sparse(사건이 없음)로 오진**하는 것.
    correlation.py의 fill_value=0과 같은 계열이다.

    그래서 이 테스트는 "0건을 반환하지 않고 던지는가"를 지킨다.

원문: geo-os/ARCHITECTURE.html B05 · 로스터 firms 항목
"""
from datetime import date

import pytest

from jobs.firms_sensor_job import parse_availability, select_source

_TODAY = date(2026, 7, 13)


def test_stale_source_is_skipped_for_live_one():
    """구 기본값(SNPP)이 뒤처졌으면 건너뛰고 살아 있는 소스를 고른다.

    2026-07-13 실측된 NASA 가용성 표 그대로.
    """
    avail = {
        "VIIRS_SNPP_NRT":   date(2026, 7, 10),   # 3일 뒤처짐 — 이게 사고의 원인
        "VIIRS_NOAA20_NRT": date(2026, 7, 13),
        "VIIRS_NOAA21_NRT": date(2026, 7, 13),
        "MODIS_NRT":        date(2026, 7, 13),
    }
    assert select_source(avail, _TODAY) == "VIIRS_NOAA21_NRT"


def test_preference_order_is_honored():
    """선호 1순위가 죽으면 2순위로 내려간다 (건너뛰기지 포기가 아니다)."""
    avail = {
        "VIIRS_NOAA21_NRT": date(2026, 7, 1),    # 죽음
        "VIIRS_NOAA20_NRT": date(2026, 7, 13),   # 살아 있음
    }
    assert select_source(avail, _TODAY) == "VIIRS_NOAA20_NRT"


def test_one_day_lag_is_tolerated():
    """NRT는 수 시간 단위 갱신이라 하루 랙까지는 정상으로 본다."""
    avail = {"VIIRS_NOAA21_NRT": date(2026, 7, 12)}
    assert select_source(avail, _TODAY) == "VIIRS_NOAA21_NRT"


def test_all_stale_raises_instead_of_returning_zero():
    """★ 핵심 불변식 — 잴 위성이 없으면 조용히 0건이 아니라 실패다.

    이 한 줄이 없으면 사고가 그대로 재현된다: 소스가 전부 죽어도 잡은 성공으로
    끝나고, 하류는 '분쟁 지역에 화재가 없었다'는 거짓 사실을 먹는다.
    """
    avail = {
        "VIIRS_SNPP_NRT":   date(2026, 6, 1),
        "VIIRS_NOAA20_NRT": date(2026, 6, 2),
        "VIIRS_NOAA21_NRT": date(2026, 6, 3),
        "MODIS_NRT":        date(2026, 6, 4),
    }
    with pytest.raises(RuntimeError, match="갱신되는 NRT 위성 소스가 없다"):
        select_source(avail, _TODAY)


def test_unknown_source_table_raises():
    """가용성 표 자체가 비었으면(응답 깨짐) 그것도 실패다 — 빈 표는 '화재 없음'이 아니다."""
    with pytest.raises(RuntimeError):
        select_source({}, _TODAY)


def test_parse_availability_reads_nasa_table():
    """NASA 가용성 CSV 파싱 — 실제 응답 형식 그대로."""
    text = (
        "data_id,min_date,max_date\n"
        "MODIS_NRT,2026-03-01,2026-07-13\n"
        "VIIRS_SNPP_NRT,2026-04-28,2026-07-10\n"
        "BA_MODIS,2000-11-01,2026-04-01\n"
    )
    avail = parse_availability(text)
    assert avail["VIIRS_SNPP_NRT"] == date(2026, 7, 10)
    assert avail["MODIS_NRT"] == date(2026, 7, 13)


def test_parse_availability_survives_garbage_rows():
    """깨진 줄이 섞여도 파서가 죽지 않는다 (부분 파싱 허용)."""
    text = "data_id,min_date,max_date\nGOOD_NRT,2026-01-01,2026-07-13\n쓰레기줄\nBAD,notadate,notadate\n"
    avail = parse_availability(text)
    assert avail == {"GOOD_NRT": date(2026, 7, 13)}
