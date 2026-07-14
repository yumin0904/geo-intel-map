"""D2 위원회 회귀 그물 (2026-07-14) — IV 교체가 되돌아가지 않게 막는다.

무엇을 지키는가:
  1. 은퇴한 IV(SUM(severity))가 검정층에 다시 기어들어오지 않는다.
  2. 커버리지 분모가 IV의 출처와 일치한다 (전역 분모 = 18일치 위조).
  3. 미선언 IV는 검정에 못 들어간다 (결과 보고 IV 고르기 = p-해킹).
  4. "못 쟀다"(D4)와 "관계 없다"(D1)와 "질문이 틀렸다"(D3)가 뭉개지지 않는다.

⚠️ 각 가드에 **음성 테스트**를 짝지었다 — 표적을 넣었을 때 정말 걸리는지 확인한다.
폐기 원장 패턴 E: "가드를 만들면 반드시 음성 테스트. 자기 표적을 놓치는 가드를 5번 만들었다."
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from services.cascade.correlation import (
    _ACLED,
    _IV_KINDS,
    _VIOLENT_TYPES,
    InsufficientCoverageError,
    _coverage_days,
    _load_event_series,
    apply_coverage,
)

_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# ACLED가 연속으로 존재하는 유일한 창. 이 밖은 315일 수집 구멍(2025-07-15~2026-05-25)이라
# 검정에 못 쓴다 — 창을 넓히면 커버리지 게이트가 정직하게 던진다.
_WIN_START, _WIN_END = date(2024, 5, 31), date(2025, 7, 14)


# ── 1. 은퇴한 IV가 돌아오지 않는다 ────────────────────────────────────────────

def test_retired_iv_is_unreachable():
    """은퇴한 IV(`event_severity`)는 이름으로도 불러낼 수 없다.

    severity = _SEVERITY_BASE[event_type] + min(30, fatalities) — 위해 척도가 아니라
    사건유형 순서코드다. 하루치를 합산하면 일건수가 지배한다(r=0.98~1.00).
    """
    assert "event_severity" not in _IV_KINDS
    assert "severity" not in _IV_KINDS
    with pytest.raises(ValueError, match="미선언 IV"):
        _load_event_series("ukraine", _WIN_START, _WIN_END, None, "event_severity")


def test_fatalities_is_not_a_volume_proxy():
    """사망자 IV는 적재 부피의 대리물이 아니다 — **이것이 2종 병기의 존재 이유다.**

    ⚠️ 정직하게 기록한다: `violence_count`는 부피 문제를 **완전히 벗어나지 못했다.**
    실측(ukraine, 정직한 창):
        r(SUM(severity),  적재 행 수) = 0.9972   ← 구 IV (은퇴)
        r(violence_count, 적재 행 수) = 0.9941   ← 신 IV. **거의 같다.**
        r(fatalities,     적재 행 수) = 0.1318   ← 신 IV. 진짜로 다르다.

    왜 violence_count가 여전히 부피를 닮았나: 우크라이나에서는 ACLED 이벤트가 거의 전부
    폭력이라, "폭력을 센 것"과 "행을 센 것"이 수치상 수렴한다. violence_count가 고친 것은
    **무엇을 세는가**(시위를 안 센다)이지 **세는 행위 자체**가 아니다. 전장에서 그것은
    여전히 수집 강도와 함께 움직인다.

    그러므로:
      - violence_count 단독 결론은 **부피 동행(r≈0.99)을 반드시 공표**해야 한다.
      - fatalities가 그 대조군이다. 둘이 **수렴하면** 강건성이 올라가고, **발산하면**
        그 발산 자체가 발견이다(수집 강도 ≠ 위해).
      - 어느 하나만 쓰면 이 대조가 사라진다. 그래서 둘 다 돌리고 둘 다 보고한다.
    """
    con = sqlite3.connect(_DB)
    try:
        raw = pd.read_sql_query(
            "SELECT DATE(timestamp) AS day, COUNT(*) AS rows_ FROM event_archive "
            "WHERE region_code='ukraine' AND DATE(timestamp) BETWEEN ? AND ? GROUP BY day",
            con, params=(_WIN_START.isoformat(), _WIN_END.isoformat()),
            parse_dates=["day"],
        ).set_index("day")
    finally:
        con.close()

    fat = _load_event_series("ukraine", _WIN_START, _WIN_END, None, "fatalities").dropna()
    joined = raw.join(fat.rename("iv"), how="inner").dropna()
    r_fat = abs(float(joined["iv"].corr(joined["rows_"])))

    assert r_fat < 0.5, (
        f"사망자 IV가 적재 행 수와 r={r_fat:.3f}로 동행한다 — 부피 대리물이 됐다. "
        f"2종 병기의 대조군이 무너졌다는 뜻이다. 수집 파이프라인을 의심하라 "
        f"(B01의 ×1.9 이중적재 같은 사고가 재발했을 수 있다)."
    )


def test_declared_ivs_are_the_only_ones():
    """사전선언 집합 밖의 IV는 거부된다 — 결과 보고 IV를 고르면 p-해킹이다."""
    with pytest.raises(ValueError, match="미선언 IV"):
        _load_event_series("ukraine", _WIN_START, _WIN_END, None, "event_severity")

    # 음성 테스트: 선언된 IV는 통과해야 한다(가드가 전부를 막으면 그것도 고장이다)
    for iv in _IV_KINDS:
        s = _load_event_series("ukraine", _WIN_START, _WIN_END, None, iv)
        assert s.name == iv, f"IV 이름이 내용과 다르다: {s.name} != {iv}"


# ── 2. 커버리지 분모가 IV 출처와 일치한다 ─────────────────────────────────────

def test_coverage_is_source_aware():
    """ACLED IV에는 ACLED 커버리지를 쓴다 — 전역 분모는 위조를 만든다.

    GDELT는 2026-07-13까지 신선한데 ACLED는 2026-05-26에서 멈춘다(랙 49일). 전역
    COUNT(*)로 '수집 정상'을 판정하면, GDELT만 들어온 날의 ACLED 0건이 '진짜 0 —
    아무도 안 죽었다'로 주조된다. 분모와 분자의 출처가 다르면 가드가 위조를 만든다(패턴 H).

    ⚠️ 창 선택 주의: 2024~2025 구간은 ACLED가 사실상 유일 소스라 전역 커버리지와 ACLED
    커버리지가 **같은 게 정상이다**. 두 분모가 갈라지는 곳은 GDELT만 신선한 **꼬리 구간**이다.
    (초판 테스트가 정직한 창에서 부등호를 요구해 자기 오탐을 냈다 — 그 교훈을 남겨둔다.)
    """
    # 부분집합 관계는 어느 창에서나 참이어야 한다 (ACLED ⊂ 전체)
    acled_w = _coverage_days(_WIN_START.isoformat(), _WIN_END.isoformat(), _ACLED)
    glob_w = _coverage_days(_WIN_START.isoformat(), _WIN_END.isoformat(), None)
    assert acled_w <= glob_w, "ACLED 수집일이 전역 수집일보다 많다 — 산술적으로 불가능."

    # 꼬리 구간(ACLED 정지 후 GDELT만 신선): 전역은 '수집 정상'을 주장하고 ACLED는 안 한다
    tail_start, tail_end = "2026-05-27", "2026-07-14"
    acled_t = _coverage_days(tail_start, tail_end, _ACLED)
    glob_t = _coverage_days(tail_start, tail_end, None)

    assert not acled_t, (
        f"ACLED가 멈춘 꼬리 구간({tail_start}~{tail_end})에서 ACLED 커버리지가 "
        f"{len(acled_t)}일을 '수집 정상'이라 한다 — 소스 인식이 무력화됐다."
    )
    assert glob_t, (
        "전역 커버리지도 꼬리 구간에서 0일이다 — 이 테스트의 전제(GDELT는 신선하다)가 "
        "무너졌다. 데이터를 다시 재고 전제를 갱신하라."
    )


def test_gdelt_only_days_are_not_minted_as_true_zero():
    """[음성 테스트] 전역 분모를 쓰면 위조가 실제로 발생하는가 — 표적을 넣어본다.

    이 테스트가 통과한다는 것은 '전역 분모가 위험하다'는 진단이 사실이라는 뜻이고,
    동시에 우리가 그 경로를 쓰지 않는다는 뜻이다.
    """
    con = sqlite3.connect(_DB)
    try:
        rows = con.execute(
            "SELECT DATE(timestamp) d, "
            "  SUM(CASE WHEN json_extract(payload,'$.data_source')=? THEN 1 ELSE 0 END) acled, "
            "  COUNT(*) tot "
            "FROM event_archive WHERE DATE(timestamp) BETWEEN ? AND ? GROUP BY d",
            (_ACLED, "2024-06-01", "2026-07-14"),
        ).fetchall()
    finally:
        con.close()

    glob = _coverage_days("2024-06-01", "2026-07-14", None)
    # 전역 게이트가 '수집 정상'이라 했는데 ACLED는 0건인 날 = 위조가 일어날 날
    forged = [d for d, acled, _tot in rows if d in glob and acled == 0]

    assert forged, (
        "전역 분모로도 위조일이 0이다 — 이 가드의 근거가 사라졌거나 데이터가 바뀌었다. "
        "그렇다면 이 테스트를 지우지 말고 **다시 재서** 근거를 갱신하라."
    )
    # 그리고 ACLED 커버리지에는 그 날들이 없어야 한다 (우리가 쓰는 경로)
    acled_cov = _coverage_days("2024-06-01", "2026-07-14", _ACLED)
    assert not (set(forged) & acled_cov), (
        f"ACLED 커버리지가 ACLED 0건인 날을 '수집 정상'으로 확정했다: "
        f"{sorted(set(forged) & acled_cov)[:5]}"
    )


def test_coverage_gap_still_throws():
    """수집 구멍이 임계를 넘으면 검정을 성립시키지 않는다 — 0으로 메우지 않는다.

    실측: 2025-07-15 ~ 2026-05-25에 ACLED 315일 구멍. 이 구간을 포함한 창은 던져야 한다.
    '못 쟀다'를 '관계 없다'로 바꿔치기하는 것이 B01의 정의였다.
    """
    with pytest.raises(InsufficientCoverageError):
        _load_event_series("ukraine", date(2024, 6, 1), date(2026, 7, 14),
                           None, "violence_count")


def test_apply_coverage_separates_missing_from_zero():
    """수집 공백 = NaN · 수집된 날의 무사건 = 0.0. 둘은 같은 값이 아니다."""
    idx = pd.date_range("2026-01-01", "2026-01-04", freq="D")
    raw = pd.Series([5.0], index=pd.DatetimeIndex(["2026-01-01"]))
    covered = frozenset({"2026-01-01", "2026-01-02"})  # 3·4일은 미수집

    out = apply_coverage(raw, idx, covered, "테스트", max_missing_share=0.9)

    assert out.iloc[0] == 5.0            # 수집 + 사건 있음
    assert out.iloc[1] == 0.0            # 수집 + 사건 없음 = 진짜 0
    assert pd.isna(out.iloc[2])          # 미수집 = 모름 (0이 아니다)
    assert pd.isna(out.iloc[3])


# ── 3. IV가 실제로 무엇을 세는가 ──────────────────────────────────────────────

def test_violence_count_excludes_protests():
    """violence_count는 시위를 세지 않는다 — 그게 구 IV가 무너진 이유다.

    korean_peninsula 6,554건 중 6,435건(98.2%)이 Protests였고, 구 IV는 그걸 '분쟁 강도'로
    보고했다. 무력충돌을 말하려면 무력충돌을 세야 한다.
    """
    assert "Protests" not in _VIOLENT_TYPES
    assert "Strategic developments" not in _VIOLENT_TYPES
    assert set(_VIOLENT_TYPES) == {
        "Battles", "Explosions/Remote violence", "Violence against civilians",
    }

    # 라이브 대조: korean_peninsula의 violence_count는 시위 6,435건을 안 센다
    s = _load_event_series("korean_peninsula", _WIN_START, _WIN_END, None, "violence_count")
    assert float(s.dropna().sum()) < 10, (
        f"korean_peninsula violence_count가 {s.dropna().sum()}건 — 시위가 새어 들어왔다."
    )


def test_fatalities_zero_variance_regions_are_flagged_not_tested():
    """사망자 IV의 분산이 0인 권역은 D3(질문이 틀렸다)로 갈린다 — 귀무로 읽지 않는다.

    east_china_sea는 무력충돌 40일인데 사망자 0명이다. 무력이 안 쓰여서가 아니라
    사람이 안 죽어서다. 이걸 '관계 없음'으로 보고하면 거짓말이다.
    """
    for region in ("korean_peninsula", "taiwan_strait", "east_china_sea"):
        s = _load_event_series(region, _WIN_START, _WIN_END, None, "fatalities")
        observed = s.dropna()
        assert float(observed.std() or 0) == 0.0, (
            f"{region}의 사망자 분산이 0이 아니게 됐다 — 데이터가 바뀌었으면 "
            f"D3 판정 목록과 variable_catalog의 caveat를 함께 갱신하라."
        )

    # 그리고 같은 권역이 violence_count로는 살아 있어야 한다 (2종 병기의 존재 이유)
    ecs = _load_event_series("east_china_sea", _WIN_START, _WIN_END, None, "violence_count")
    assert float(ecs.dropna().std() or 0) > 0, (
        "east_china_sea가 violence_count로도 죽었다 — 사망자 단독 IV였다면 이 등록 쌍은 "
        "말없이 사라졌을 것이다. 2종 병기가 지키는 바로 그 케이스다."
    )
