"""고정 텍스트 라우팅 회귀 테스트 — e2e 골드가 생성 비결정성으로 못 잡는 경로를 고정한다.

배경(골드셋 v2 3차 검증, 2026-07-08): proxy downgrade 경로는 생성 문구에 따라
3런 3행동 — 자연어 쿼리 기반 e2e 골드로는 고정 불가. 추출기 매핑 계약을 여기서 고정.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.hypothesis_extractor import extract_hypotheses


def test_downgrade_ingredients():
    """티커 무접점 DV + region 존재 = Type_A→C 강등의 결정론 재료.

    ⚠️ [권역위 2026-07-14] 기대값 `eastern_europe` → **`ukraine`**으로 정정.
    이 테스트는 낡은 계약을 고정하고 있었다 — `eastern_europe`는 **event_archive에 0행**이고
    (실재 코드는 `ukraine`, 88,431행), correlation.py가 사설 별칭으로 몰래 보정해 온 덕에
    예측 160건이 우연히 살았을 뿐이다. 검정층 어휘를 저장층(regions.yaml)에 종속시키면서
    원천을 고쳤고, G1(import-time assert)이 없는 코드의 재유입을 막는다.
    """
    sp = extract_hypotheses('[가설] H1: "글로벌 제재 강도 지수가 증가할 때 러시아에 대한 유엔총회 표결 동조율이 통계적으로 유의하게 하락한다"')[0]
    assert sp.ticker is None, f"티커 무접점이어야 함: {sp.ticker}"
    assert sp.region_code == "ukraine", f"러시아→ukraine(DB 실재 코드): {sp.region_code}"


def test_kospi_typeA():
    """KOSPI 티커 매핑 (골드셋 v2 A4가 검출한 공백의 회귀 방지)."""
    sp = extract_hypotheses('[가설] H1: "남한의 대규모 시위 건수가 증가할 때 KOSPI 지수가 통계적으로 유의하게 하락한다"')[0]
    assert sp.ticker == "^KS11" and sp.region_code == "korean_peninsula"


def test_regime_lexicon():
    """체제 어휘 → linear_testable=False (8-gate 재료)."""
    sp = extract_hypotheses('[가설] H1: "러시아 정권 생존 압박이 임계점에 도달하면 에너지 수출이 급변한다"')[0]
    assert sp.linear_testable is False


if __name__ == "__main__":
    test_downgrade_ingredients(); test_kospi_typeA(); test_regime_lexicon()
    print("✅ 라우팅 경로 회귀 3종 통과")
