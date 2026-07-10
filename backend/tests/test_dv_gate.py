"""DV 출처 게이트 회귀 테스트 (개선위 P4).

핵심 계약: 감사 실증 결함형(구성개념 서로소·근거 없는 수치)은 강등하고,
모범 케이스(호르무즈 실물 판정 라인)는 절대 건드리지 않는다 — 오탐이 미탐보다 나쁘다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.dv_gate import apply_gate, check  # noqa: E402

# 전수 감사가 모범(결함 0)으로 확정한 실물 판정 라인 — 절대 강등 금지
HORMUZ_OK = (
    "판정: 열세 — 예측 '분쟁 증가→유가 상승' vs 실측 '분쟁 609 건 지속에도 "
    "유가 -18.6% 하락' — 방향 불일치 (편차 -18.6%)"
)
HORMUZ_CTX = "ACLED 분쟁 609건 · WTI 변화율 -18.6% (사전계산)"

# 감사 결함형: 기술 확산 사안의 판정에 테러 통계를 실측 DV로 사용 (DV 프록시 오용)
DRONE_BAD = (
    "판정: 우세 — 예측 '드론 기술 확산으로 비국가 행위자 역량 강화' vs "
    "실측 '미국 내 테러 1170건 발생' — 방향 일치"
)


def test_모범케이스_불강등():
    text, actions = apply_gate(HORMUZ_OK, HORMUZ_CTX)
    assert actions == []
    assert text == HORMUZ_OK


def test_구성개념_서로소_강등():
    text, actions = apply_gate(DRONE_BAD, "미국 내 테러 1170건 (사전계산)")
    assert [a["code"] for a in actions] == ["dv_mismatch"]
    assert "판정: 전제충족(DV 미검증)" in text
    assert "판정: 우세" not in text
    # 증거 텍스트는 보존 (원본 결과 보존 원칙)
    assert "테러 1170건" in text


def test_이론프로파일_폴백():
    # 예측 구간이 무클래스('제해권 확립') → 앞 창의 이론명으로 dv_classes 폴백.
    # 해상 통제 이론(shipping_sloc)의 판정에 테러 통계(conflict_event) — 호환 그룹도 없음 → 강등
    text = (
        "대안 이론 A: 코르벳 제한적 제해권 이론 (Corbett's Limited Sea Control) — 통상 보호.\n"
        "판정: 우세 — 예측 '제해권 확립' vs 실측 '미국 내 테러 1170건' — 방향 일치"
    )
    acts = check(text)
    assert [a["code"] for a in acts] == ["dv_mismatch"]


def test_호환그룹_양극단_불강등():
    # '양보 증가'(policy) vs '대응 강화(훈련)'(military) — 같은 '대상국 반응' 차원의 양극 → 정당한 열세 판정 보존
    text = "판정: 열세 — 예측 '양보 증가' vs 실측 '대응 강화 (방산 지출 상승, 군사 훈련)' — 방향 불일치"
    assert check(text) == []


def test_출처없는_수치_강등():
    # 실측 숫자가 context에 없음 → provenance_missing (크로스케이스 실측 재사용 차단)
    _, actions = apply_gate(HORMUZ_OK, "관련 없는 context — 숫자 없음")
    assert [a["code"] for a in actions] == ["provenance_missing"]


def test_출처_반올림_허용():
    # context 수치와 2% 이내면 통과 (표기 반올림 흡수)
    _, actions = apply_gate(
        "판정: 우세 — 예측 '유가 상승' vs 실측 '유가 18.5% 상승'",
        "WTI 변화율 +18.6% (사전계산)",
    )
    assert actions == []


def test_전제충족판정은_미대상():
    text = "판정: 전제충족 (DV 미검증) — 실측 부재로 방향성 검증 불가"
    assert check(text, "아무 context") == []


def test_context_없으면_provenance_생략():
    # eval 사후 점검 모드 — 구성개념 검사만 수행
    assert check(HORMUZ_OK, None) == []
