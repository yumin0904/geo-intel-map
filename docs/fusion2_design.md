# 융합2 — Token-Zero 산술 레이어 (구현 핸드오프)

> 설계: Opus (2026-06-07). 구현: Sonnet 세션용. Phase 8 두 번째 사이클.
> **목표**: 편차·변화율·격차·비율·HHI 등 모든 수치 연산을 Python으로 끌어내리고,
> Gemini는 **이미 계산된 값을 서술·인용만** 하게 한다. (LLM 산술 환각 제거)
> **측정**: 산술 오류 0. 가드: PASS율·경쟁이론 수치비교율 무회귀(이상적으론 경쟁이론엄밀↑).

---

## 0. 대상 파일

- **신규** `backend/services/arithmetic_layer.py` — 순수 산술 함수 모음 (Token-Zero 코어)
- `backend/services/theory_comparator.py` — 인라인 산술을 arithmetic_layer로 통일 + **실측값 쌍 격차 사전계산 주입**
- `backend/api/intel_query.py` — `_build_prompt()` system_role에 **산술 금지 하드룰** 추가 + 예시 교체
- 버전: `backend/config/version.json` 마이너 bump (7.9.0 → 7.10.0)

## 1. 진단 (왜 하는가)

### 1-A. Gemini가 지금 하는 산술 (= 환각 위험원)

`theory_comparator.build_theory_comparison_context()`는 실측값을 **나열만** 한다:

```
실측 — SIPRI 국방비: RUS: 5.9% GDP | UKR: 37.0% GDP   ← 격차(31.1%p)는 Gemini가 암산
실측 — 파운드리 HHI: ... | TSMC: 90% | SMIC: 5%        ← 격차(85%p)는 Gemini가 암산
```

그리고 `intel_query.py:104,108,214,218`의 카드 형식이 **"판정: 예측 X vs 실측 Y, 편차 Z"** 를
요구하고, 프롬프트 예시(`intel_query.py:113-119`)는 `45% → 8%` 를 주고 Gemini가
`-37%p` 를 직접 빼서 적게 만든다. → **모든 편차 산술이 LLM 암산.**

이것이 v7.8.9 측정의 핵심 손실 지점:
> "경쟁이론엄밀 3.43 (레이블 100% but **편차 산술 없음** — Gemini가 수치를 '말'로만 비교)"

### 1-B. 이미 Python이 계산하는 것 (= 통일 대상)

| 위치 | 현재 인라인 산술 | 통일 후 |
|------|----------------|--------|
| `_get_sipri_arms_hhi` L104 | `dominant/total*100` | `share_of()` |
| `_get_fred_for_theories` L188 | `(latest-oldest)/oldest*100` | `pct_change()` |
| `_get_trade_hhi` L560 | `sum(r²)*10000` | `hhi()` |

이들은 환각이 아니지만 **라운딩·0분모·None 처리가 제각각**이라 한 모듈로 통일해
"산술은 전부 arithmetic_layer를 거친다"는 단일 규율을 세운다(향후 8-C가 재사용).

## 2. 설계 — 3개 작업

### 2-A. `arithmetic_layer.py` 신설 (순수 함수, 부작용 0)

모든 함수는 **None-safe · 0분모-safe · 라운딩 일관**. 입력이 부적합하면 `None` 반환
(예외 던지지 않음 — 컨텍스트 조립이 한 값 때문에 깨지면 안 됨). LLM 호출 절대 금지.

```python
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
    scale_0_1=True: values가 0~1 비율 → ×10000 (0~10000 스케일)
    scale_0_1=False: values가 이미 0~100 점유율(%) → 그대로 제곱합
    빈 입력/전부 None이면 None.
    """
    nums = [_num(v) for v in (values or [])]
    nums = [v for v in nums if v is not None]
    if not nums:
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
```

> ⚠️ `_get_trade_hhi`(L560)는 현재 `sum(r²)*10000`. `hhi(values, scale_0_1=True)`와
> **동일 스케일**이 되도록 그대로 옮긴다. `_get_sipri_arms_hhi`(L104)의 `hhi_proxy_pct`는
> 사실 HHI가 아니라 **점유율**(dominant/total)이므로 `share_of()`로 매핑(라벨 유지).

### 2-B. `theory_comparator.py` — 산술 통일 + 격차 사전계산 주입

**(1) 인라인 산술 3곳을 arithmetic_layer로 교체** (출력 수치 불변 — 회귀 방지):

| 함수 | 변경 |
|------|------|
| `_get_sipri_arms_hhi` | `hhi_proxy = (dominant/total*100)` → `share_of(dominant_tiv, total)` |
| `_get_fred_for_theories` | `pct = (latest-oldest)/oldest*100` → `pct_change(oldest_val, latest_val)` |
| `_get_trade_hhi` | `hhi = sum(i²)*10000` → `hhi([i["dependency_ratio"] for i in items[:3]])` |

**(2) 실측값 쌍 격차를 Python으로 미리 계산해 텍스트에 주입** (이게 융합2의 신규 가치):

`build_theory_comparison_context()`의 `empirical_lines` 생성부에서, **두 실측값을 비교**하는
지점마다 `pct_point_gap`/`delta`/`pct_change`로 편차를 계산해 **이미 계산된 격차를 문장에 박는다**.

- **SIPRI/OWID 국방비 쌍** (mearsheimer·waltz·mahan 블록): 행위자가 2개 이상이면 최상·최하
  GDP% 격차를 사전계산:
  ```python
  from services import arithmetic_layer as A
  vals = [(iso3, v.get("gdp_pct")) for iso3, v in milex.items() if v.get("gdp_pct") is not None]
  if len(vals) >= 2:
      vals.sort(key=lambda x: -x[1])
      gap = A.pct_point_gap(vals[0][1], vals[-1][1])
      # "실측 — SIPRI 국방비 격차: RUS 5.9%p ↔ UKR 37.0%p (격차 31.1%p, 사전계산)"
      empirical_lines.append(
          f"실측 — SIPRI 국방비 격차: {vals[0][0]} {vals[0][1]}% ↔ "
          f"{vals[-1][0]} {vals[-1][1]}% (격차 {A.fmt_signed(gap, '%p')}, 사전계산)"
      )
  ```
- **semi foundry TSMC↔SMIC 격차** (weaponized_interdependence·digital_iron_curtain 블록):
  두 점유율이 있으면 `pct_point_gap`으로 "격차 85.0%p (사전계산)" 주입.
- **FRED 추세**: 이미 `pct_change` 계산값(`pct_change` 필드)을 `A.fmt_signed`로 부호 강제.
- **trade HHI**: `concentration_label(hhi)` 사용(현재 인라인 if문을 함수로).

> **포맷 규율**: 사전계산된 편차에는 반드시 **`(사전계산)` 또는 `(Python 계산)` 꼬리표**를 붙인다.
> Gemini가 "이 숫자는 내가 만든 게 아니라 제공된 값"임을 인지하고 그대로 인용하게 하는 신호.

### 2-C. `intel_query.py` — 산술 금지 하드룰 + 예시 교체

**(1) `system_role`에 새 블록 추가** (`## H1 가설 작성 규칙` 앞에 삽입):

```python
"## Token-Zero 산술 규율 (융합2) — 절대 준수\n"
"<context>의 편차·변화율·격차·HHI·비율은 **이미 Python으로 계산되어** 제공된다.\n"
"너는 그 값을 **그대로 인용만** 하라. 직접 빼기·나누기·퍼센트·평균을 계산하지 말라.\n"
"- '판정: 예측 X vs 실측 Y, 편차 Z'의 Z는 context에 '(사전계산)'/'격차'/'변화'로 "
"제공된 값을 그대로 쓴다.\n"
"- context에 그 편차가 없으면 **암산하지 말고** '[산술 미제공]'으로 표기하라.\n"
"- 두 수의 차이를 네가 머릿속으로 빼서 적으면 산술 환각으로 간주한다 — "
"context 제공값만 신뢰하라.\n\n"
```

**(2) 기존 [경쟁설명] 예시(L110-119) 교체** — 현재 예시는 Gemini가 `45→8 ⇒ -37%p`를
암산하도록 유도하므로, **"context 제공 편차를 인용"하는 형태**로 바꾼다:

```
   ★ 구체적 예시 (반드시 이 형식 준수 — 편차는 context의 (사전계산) 값 인용):
   자원무기화 (Hirschman):
     예측: 에너지 의존도 증가 시 정치적 양보 빈도 증가
     실측: EU 러시아 가스 의존도 45%→8% (변화 -37.0%p, 사전계산) [EIA/FRED]
     판정: 열세 — 예측 '의존도 증가→양보' vs 실측 '의존도 -37.0%p 급감' — 방향 불일치
   ...
   ▶ 종합 판정: 자원무기화 열세 — context 제공 편차(-37.0%p)가 예측 방향과 반대
```

> 편차 수치(`-37.0%p`)를 **예시 안에서도 "(사전계산)" 꼬리표와 함께** 두어, 모델이
> "편차는 내가 만드는 게 아니라 context에서 받는 것"이라는 패턴을 학습하게 한다.

## 3. 범위 경계 (융합2 vs 8-C) — 혼선 방지

| | 융합2 (이번) | 8-C (다음다음) |
|--|------------|---------------|
| 책임 | 산술 **인프라** + 명백한 격차(두 실측값 차이) 사전계산 | 경쟁이론 **예측 방향 부호화** + 우세 자동판정 |
| 산출 | `arithmetic_layer.py` + 격차 주입 + 프롬프트 하드룰 | 이론 프로파일에 `predicted_direction` 메타 + 예측↔실측 방향 일치판정 로직 |
| Gemini 역할 | 제공된 편차를 **서술** | (8-C 후) 제공된 판정을 **해설** |

**이번 세션은 융합2까지만.** 예측 방향 부호화·우세 자동판정은 8-C에서. (블라인드 확장 회피)

## 4. 정직성·안티패턴 가드 (필수 준수)

- **정직성 > 산술 편의** (메모리 `feedback_honesty_over_judge`): 편차를 사전계산한다고
  해서 **불리한 실측을 빼거나 유리한 쌍만 고르면 안 된다.** 격차 계산 대상은 "쿼리 주제에
  등장한 모든 행위자/지표 쌍"이며, 결론에 유리한 쌍만 선별하면 체리피킹=환각.
- 인라인 산술 교체 시 **출력 수치 불변** (FRED pct·HHI 값이 기존과 동일해야 함 — 회귀 가드).
- LLM 호출 0 (Token-Zero, CLAUDE.md §14-A).
- `arithmetic_layer` 함수는 부작용·예외 금지 — 한 값이 None이어도 컨텍스트 조립은 계속.

## 5. 검증 단계

1. `python -c "import sys; sys.path.insert(0,'backend'); import services.arithmetic_layer"` — import·문법.
2. arithmetic_layer 안전성 수동 확인(코드 리뷰): `pct_change(0, 5)`→None, `hhi([])`→None,
   `share_of(3,0)`→None, `delta(None,5)`→None 가 예외 없이 None.
3. `theory_comparator` 회귀: 동일 입력(taiwan_strait, CHN·USA·KOR)으로 호출 시
   기존 FRED pct·trade HHI 수치가 **변하지 않는지** + 새 "(사전계산)" 격차 라인이 등장하는지.
4. **골드셋 eval**: `python backend/eval_insight.py --gold --judge --fast`
   - 가드: PASS율 ≥ 12/15, 경쟁이론 수치비교 무회귀(100% [엄격] 유지).
   - 기대: 편차에 `(사전계산)` 꼬리표 등장 → 경쟁이론엄밀 점수↑(3.43 → 목표 3.7+ 신호).
   - 산술 오류 점검: 심판이 지적한 "편차 수치 틀림" 케이스 0건.
5. 통과 시 progress.md 진행현황 `[융합2] ✅` + version.json 7.10.0 + 같은 커밋.

## 6. 완료 후 다음

8-A (H1 측정가능성 강제 — `measurable_variables.yaml`). 본 문서와 독립.
산술 레이어는 8-C(경쟁이론 편차 계산)에서 다시 호출되므로 인터페이스를 안정적으로 유지할 것.
