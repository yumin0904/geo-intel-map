"""
tests/test_hypothesis_extractor_upstream_repair.py

[위원회 20260712 집행⑦] 미식별 89건 상류 수리 회귀 테스트.

대상: services/hypothesis_extractor.py — 을수록 형태소 커버리지 수리(집행①),
상관형 대칭 정규식 신설(집행②), _RE_H1 캡처 기각 필터 강화(집행③),
DV 빈문자 방어 폴백(집행④). 실측 표본(exports/qualitative_triage.json
unidentified 89건)에서 직접 채록한 문장으로 검증한다.

실행: cd backend && .venv/bin/python -m pytest tests/test_hypothesis_extractor_upstream_repair.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.hypothesis_extractor import extract_hypotheses  # noqa: E402


def _extract_one(h1_body: str):
    """단일 H1 본문을 캡처 마커와 함께 파싱해 첫 HypothesisSpec을 반환 (없으면 None)."""
    specs = extract_hypotheses(f"H1: {h1_body}")
    return specs[0] if specs else None


# ── 집행① "을수록" 형태소 커버리지 ──────────────────────────────────────────

def test_을수록_받침형_어간_매치():
    """실측 확정 결함: '낮을수록'은 구 정규식(질/할/될+수록만 등록)에서 NO MATCH였다."""
    spec = _extract_one(
        "국가 거버넌스 지수(정치안정 WGI)가 낮을수록, 북극항로 통제를 위한 AI 기반 "
        "해상 감시 시스템의 인력 감축률(%)이 통계적으로 유의하게 증가한다."
    )
    assert spec is not None
    assert spec.dependent_var != "미식별"
    assert "인력 감축률" in spec.dependent_var
    assert "WGI" in spec.independent_var or "거버넌스" in spec.independent_var


def test_을수록_많을수록_적을수록_매치():
    """위원회 명시 예시 커버리지 확인 — 많을수록·적을수록도 동일 계열."""
    for stem, iv_kw in [("많을수록", "지원국"), ("적을수록", "예산")]:
        spec = _extract_one(f"{iv_kw} 수가 {stem}, 분쟁 지속 기간이 통계적으로 유의하게 증가한다.")
        assert spec is not None, f"{stem} 매치 실패"
        assert spec.dependent_var != "미식별", f"{stem} DV 미회수"


def test_기존_질수록_할수록_불변():
    """기존 커버리지(질/할/될+수록)가 을수록 추가로 깨지지 않았는지 회귀 확인."""
    spec = _extract_one(
        "미국의 對중 반도체 수출 통제가 강화될수록, 중국의 자체 파운드리 투자가 "
        "통계적으로 유의하게 증가한다."
    )
    assert spec is not None
    assert spec.dependent_var != "미식별"


# ── 집행② 상관형 대칭 정규식 ────────────────────────────────────────────────

def test_상관형_A가_B와_회수():
    """실측 표본: "A가 B와 통계적으로 유의미하게 상관한다" 정순."""
    spec = _extract_one(
        "bab_el_mandeb 지역의 ACLED 분쟁 이벤트 월별 건수 증가는 미국의 대테러 예산 "
        "감소율(%) 및 CPI 상승률(%)과 통계적으로 유의미하게 상관한다."
    )
    assert spec is not None
    assert spec.dependent_var != "미식별"
    assert "대테러 예산" in spec.dependent_var


def test_상관형_A와_B는_어순반대_회수():
    """실측 표본: "A와 B는 통계적으로 상관한다" 역순(유의 생략형)."""
    spec = _extract_one(
        "대만해협 분쟁 이벤트 빈도 증가와 AI 기반 사이버 공격의 초보자 완료율 증가는 "
        "통계적으로 상관한다."
    )
    assert spec is not None
    assert spec.dependent_var != "미식별"
    assert "대만해협" in spec.independent_var


def test_상관형_direction_추정_금지():
    """대칭 관계이므로 방향 토큰이 없어 direction 판정은 extractor 소관 밖(unclear로
    남아야 함) — prediction_instrument._detect_direction이 '상관' 미등록 동사로
    자연히 unclear 처리하는지는 별도 모듈 책임이라 여기서는 IV/DV 회수만 검증한다."""
    spec = _extract_one(
        "중국의 인도네시아 니켈 광산 지분 인수율 증가가 중국 해군력 투자 비중(%GDP)과 "
        "통계적으로 유의하게 상관한다."
    )
    assert spec is not None
    assert "니켈" in spec.independent_var
    assert "해군력" in spec.dependent_var


# ── 집행③ _RE_H1 캡처 기각 필터 ─────────────────────────────────────────────

def test_변수정의_불릿_기각():
    assert _extract_one("- X = 드론 공격 건수 (월별, CSIS/IISS 추정 데이터 기반)") is None


def test_트렁케이션_조각_기각():
    assert _extract_one("사헬 지역의 ACLED 분쟁 이벤트 건수 (") is None


def test_메타논평_표준형_기각():
    assert _extract_one("사용자가 제시한 주장을 정량화하여 재진술합니다.") is None
    assert _extract_one("섹션은 H1 대신 **과정추적 질문**으로 전환됨.") is None
    assert _extract_one(
        ": H1 작성 시도했으나 데이터 부재로 '정량 가설 없음' 또는 '검증 불가' 명시: ✅"
    ) is None


def test_정상_H1은_기각필터에_안걸림():
    """캡처 필터 강화가 정상 가설을 오탐하지 않는지 확인 (오탐 0 조건, 기존 494행 관행과 동일)."""
    spec = _extract_one(
        "미국 CPI가 증가할 때 Kiel Tracker 월별 지원액이 통계적으로 유의하게 감소한다 "
        "(통제변수: 선거 주기)."
    )
    assert spec is not None
    assert spec.dependent_var != "미식별"


# ── 집행④ DV 빈문자 방어 폴백 ──────────────────────────────────────────────

def test_dv_빈문자_방어_폴백():
    """경계 마커 매치 후 DV 서술어가 after 맨 앞(위치 0)에서 매치해 dependent_var가
    빈 문자열로 붕괴하는 경로 — after 전체(100자 컷)로 폴백해야 한다."""
    # after가 명사구 없이 곧장 서술어로 시작하는 인위적 문형으로 dv_pred.start()==0 유도
    spec = _extract_one("전쟁 강도가 심화될 때, 증가한다.")
    assert spec is not None
    # 빈 문자열이 아니라 after 전체(또는 그 일부)로 채워져야 한다 — "미식별" 강등 방지
    assert spec.dependent_var != ""
