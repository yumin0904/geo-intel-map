"""
tests/test_region.py  (region 배정 회귀 — 2026-07-09)

실행: cd backend && PYTHONPATH=. .venv/bin/python tests/test_region.py

배경: north_korea bbox 남위 경계(37.5N)가 서울을 물어 남한 시위 3,136건이
'북한 도발' 버킷에 섞였던 오염의 재발 방지 (geo-os 판례
20260709-nk-region-bbox-contamination). bbox·배정 로직 자체를 검정하는
첫 테스트 — 기존 테스트들은 region_code를 픽스처 값으로만 사용했다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.region import region_for_event, region_for_point  # noqa: E402


def _check_bbox_fallback() -> list[str]:
    """좌표만 있는 소스(FIRMS·AIS 등)의 bbox 판정 — 서울이 north_korea면 안 된다."""
    fails = []
    cases = [
        ("서울시청(오염 진원)", 37.5665, 126.9780, "korean_peninsula"),
        ("여의도권(오염 최빈 2,863건)", 37.5223, 126.9075, "korean_peninsula"),
        ("평양", 39.03, 125.75, "north_korea"),
        ("부산", 35.18, 129.08, "korean_peninsula"),
    ]
    for name, lat, lon, expected in cases:
        got = region_for_point(lat, lon)
        if got != expected:
            fails.append(f"{name}: 기대 {expected}, 실제 {got}")
    return fails


def _check_actor_country_priority() -> list[str]:
    """행위자·발생국 신호가 좌표 bbox를 이겨야 하는 케이스."""
    fails = []
    # 판문점 북한군(37.9559N, 남측 좌표) — ACLED가 접촉점에 좌표코딩하는 관행
    got = region_for_event(
        37.9559, 126.6769,
        country="South Korea",
        actors=("Military Forces of North Korea (2011-)", ""),
    )
    if got != "north_korea":
        fails.append(f"판문점 NK 행위자: 기대 north_korea, 실제 {got}")

    # 개성(37.97N, 새 bbox 밖) — 발생국 North Korea로 구제
    got = region_for_event(37.97, 126.55, country="North Korea")
    if got != "north_korea":
        fails.append(f"개성 country=NK: 기대 north_korea, 실제 {got}")

    # 제주(33.4998N — korean_peninsula bbox 하한 33.5 밖 0.0002도, 실측 오염 171건)
    got = region_for_event(33.4998, 126.5316, country="South Korea")
    if got != "korean_peninsula":
        fails.append(f"제주 경계 갭: 기대 korean_peninsula, 실제 {got}")

    # 독도(경도 131.87 — bbox 경도 상한 130.5 초과)
    got = region_for_event(37.2417, 131.8656, country="South Korea")
    if got != "korean_peninsula":
        fails.append(f"독도 경도 초과: 기대 korean_peninsula, 실제 {got}")

    # 서울 시위(남한 행위자·발생) — north_korea 혼입 절대 금지
    got = region_for_event(
        37.5223, 126.9075,
        country="South Korea",
        actors=("Protesters (South Korea)", ""),
    )
    if got != "korean_peninsula":
        fails.append(f"서울 시위: 기대 korean_peninsula, 실제 {got}")

    # 신호 없으면 bbox 폴백과 동일 (회귀 가드)
    if region_for_event(48.5, 31.0) != region_for_point(48.5, 31.0):
        fails.append("신호 없는 이벤트가 bbox 폴백과 불일치")
    return fails


def main() -> int:
    fails = _check_bbox_fallback() + _check_actor_country_priority()
    if fails:
        print("❌ region 배정 회귀 위반:")
        for f in fails:
            print("  -", f)
        return 1
    print("✅ region 배정 회귀 통과 (서울↛north_korea + 판문점 행위자 우선 + 제주·독도 경계 갭 보완)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
