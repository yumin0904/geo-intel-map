"""
Token-Zero 산술 레이어 (Phase 8 융합2).

경쟁이론 편차·시계열 변화율·공급망 집중도 등 인사이트에 들어가는 모든
수치 연산을 이 모듈의 결정론적 함수로 처리한다. Gemini는 여기서 계산된
값을 서술만 하고, 직접 빼기/나누기/퍼센트 계산을 하지 않는다(§14 Token-Zero).

모든 함수 규약:
  - 입력이 None이거나 숫자가 아니면 None 반환 (예외 금지)
  - 0 분모는 None 반환
  - 반환 float는 round(ndigits) 적용 — 호출부 라운딩 불필요
"""
from __future__ import annotations


def _num(x) -> float | None:
    """안전한 숫자 변환. 실패 시 None."""
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def pct_change(old, new, *, ndigits: int = 1) -> float | None:
    """변화율 % = (new-old)/|old|*100. old=0이면 None."""
    o, n = _num(old), _num(new)
    if o is None or n is None or o == 0:
        return None
    return round((n - o) / abs(o) * 100, ndigits)


def delta(a, b, *, ndigits: int = 1) -> float | None:
    """절대 편차 a-b (부호 유지)."""
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return None
    return round(x - y, ndigits)


def pct_point_gap(a_pct, b_pct, *, ndigits: int = 1) -> float | None:
    """퍼센트포인트 격차 |a-b| (두 값이 이미 % 단위일 때). 부호 없는 크기."""
    d = delta(a_pct, b_pct, ndigits=ndigits)
    return None if d is None else abs(d)


def ratio(num, den, *, ndigits: int = 2) -> float | None:
    """비율 num/den. den=0이면 None."""
    n, d = _num(num), _num(den)
    if n is None or d is None or d == 0:
        return None
    return round(n / d, ndigits)


def share_of(part, whole, *, ndigits: int = 1) -> float | None:
    """점유율 % = part/whole*100. whole=0이면 None."""
    r = ratio(part, whole, ndigits=ndigits + 4)
    return None if r is None else round(r * 100, ndigits)


def hhi(values, *, scale_0_1: bool = True, ndigits: int = 0) -> float | None:
    """
    허핀달-허쉬만 지수 = Σ(share²).

    scale_0_1=True:  values가 0~1 비율 → ×10000 (0~10000 스케일)
    scale_0_1=False: values가 이미 0~100 점유율(%) → 그대로 제곱합
    빈 입력/전부 None이면 None.
    """
    nums = [_num(v) for v in (values or [])]
    nums = [v for v in nums if v is not None]
    if not nums:
        return None
    # 입력 불변식 (개선위 2026-07-10): HHI는 '한 시장 내' 점유율 분해라 합이 1(=100%)을
    # 넘을 수 없다. 서로 다른 시장·연도의 비율을 섞어 넣으면 상한 10,000 초과 사이비
    # 수치가 나온다(실측: 25,449·30,000) — 그런 입력은 계산 거부가 정직하다.
    total = sum(nums)
    limit = 1.02 if scale_0_1 else 102          # 반올림 여유 2%
    if total > limit:
        import logging
        logging.getLogger(__name__).warning(
            "hhi(): 점유율 합=%.3f > %s — 단일 시장 입력이 아님, None 반환", total, limit)
        return None
    if scale_0_1:
        return round(sum(v ** 2 for v in nums) * 10000, ndigits)
    return round(sum(v ** 2 for v in nums), ndigits)


def concentration_label(hhi_value) -> str:
    """HHI → 한국어 집중도 레이블 (기준: >2500 독과점, >1500 집중, else 분산)."""
    h = _num(hhi_value)
    if h is None:
        return "미상"
    if h > 2500:
        return "독과점"
    if h > 1500:
        return "집중"
    return "분산"


def fmt_signed(value, unit: str = "", *, ndigits: int = 1) -> str:
    """부호 강제 표기 ('+37.0%p' / '-5.9%'). None이면 '[산술 미제공]'."""
    v = _num(value)
    if v is None:
        return "[산술 미제공]"
    return f"{v:+.{ndigits}f}{unit}"
