---
asset_type: theory
era: multipolar
geopol_region: taiwan_strait
instrument_of_power: economic
level_of_analysis: systemic
regions:
- taiwan_strait
- eastern_europe
- hormuz
- korean_peninsula
sector_tag: indo_pacific
strategic_posture: status_quo
summary: X의 과거값이 Y를 통계적으로 예측할 때 "X가 Y를 Granger 인과한다"고 한다 — 지정학 이벤트와 시장·동맹 지표 간 시계열 인과관계 검증의 핵심 방법론.
temporal_era: us_china_rivalry
theorists:
- Clive Granger
- Christopher Sims
theory_id: methods_granger_causality
title: Granger 인과분석 (Granger Causality)
year: 1969
independent_var: "지정학 이벤트 시계열 (ACLED 분쟁 건수/월)"
dependent_var: "시장·동맹 지표 시계열 (환율·주가·방산 ETF)"
conditions:
  - "시계열 정상성 (stationarity, ADF 검정 충족)"
  - "충분한 데이터 포인트 (≥24개월 월간 데이터 권장)"
  - "lag 선택의 통계적 정당성 (AIC/BIC)"
falsifiable_prediction: "지정학 이벤트 빈도 증가 시 연관 시장 지표가 lag k 이후 통계적으로 유의하게 변화 (p<0.05)"
known_counterexample: "한반도 긴장 → KRW 환율 인과는 VERIFIED(p=0.048)이지만 대만해협 → TSMC는 PARTIAL(p=0.067) — 지정학 충격이 항상 즉각 시장 전이되지 않음"
rival_theories:
  - "Structural VAR (Sims)"
  - "Cointegration Analysis (Engle-Granger)"
  - "Counterfactual Causal Inference (Rubin)"
---

## 핵심 주장

Clive Granger는 1969년 *Econometrica*에서 시계열 간 인과관계를 정의하는
통계적 기준을 제시했다.

### Granger 인과의 정의

> "X가 Y를 Granger 인과한다" ⟺
> X의 과거값이 Y의 미래값 예측에 통계적으로 유의한 기여를 한다.

**VAR(p) 모델**:
```
Y_t = α + Σ β_i Y_{t-i} + Σ γ_i X_{t-i} + ε_t

귀무가설 H0: γ_1 = γ_2 = ... = γ_p = 0 (X는 Y를 인과하지 않는다)
F-통계량으로 검정, p < 0.05 → 기각 → Granger 인과 성립
```

### IA-Engine 적용 방식

이 프로젝트에서 Granger 인과는 H1 가설 검증의 핵심 통계 도구다:

| 상태 | 기준 | 신뢰도 캡 |
|------|------|---------|
| VERIFIED | p < 0.05 | 없음 |
| PARTIAL | p < 0.15 | ≤88 |
| PENDING | p ≥ 0.15 | ≤75 |

### AIC+min-p 하이브리드 lag 선택 (v6.5.0 구현)

1차: VAR.select_order(AIC) → 최적 lag 후보
2차: maxlag 내 min-p lag → 실제 데이터에서 가장 강한 신호
→ 두 lag 중 p 값이 더 작은 쪽 선택

## 검증 결과 (v6.5.0 기준)

| 케이스 | p값 | F값 | lag | 상태 |
|--------|-----|-----|-----|------|
| 한반도 → KRW | 0.048 | 3.05 | 2개월 | ✅ VERIFIED |
| 대만 → TSMC | 0.067 | 2.389 | 3개월 | 🔶 PARTIAL |
| 우크라이나 → WTI | 0.146 | 2.123 | 1개월 | 🔶 PARTIAL |

## 주요 학자 및 저작

- Granger, C.W.J. (1969). "Investigating Causal Relations by Econometric Models." *Econometrica*.
- Sims, C. (1980). "Macroeconomics and Reality." *Econometrica*. (VAR 확장)
- Toda, H.Y. & Yamamoto, T. (1995). "Statistical Inference in VAR with Possibly Integrated Processes." *Journal of Econometrics*.

## 이론의 한계

- Granger 인과 ≠ 진정한 인과(True Causality) — 예측력이지 메커니즘이 아님
- 공통 원인(Common Cause) 존재 시 허위 인과 가능
- 비선형 관계, 구조적 단절(structural break) 처리 어려움
- 데이터 양 부족 시 과소검정(underpowered test) 문제
