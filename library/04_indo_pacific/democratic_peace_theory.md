---
asset_type: theory
era: cold_war
geopol_region: eastern_europe
instrument_of_power: diplomatic
level_of_analysis: state_domestic
regions:
- taiwan_strait
- eastern_europe
- korean_peninsula
sector_tag: indo_pacific
strategic_posture: status_quo
summary: 민주주의 국가들은 서로 전쟁을 하지 않는다. 민주적 규범(타협·평화적 갈등 해결)과 제도적 제약(의회 선전포고 승인)이 민주국가 간 전쟁을 구조적으로 억제한다.
temporal_era: us_china_rivalry
theorists:
- Michael Doyle
- Bruce Russett
- John Owen
theory_id: indo_pacific_democratic_peace_theory
title: 민주 평화론 (Democratic Peace Theory)
year: 1983
independent_var: "양국의 민주주의 지수 최솟값 (V-DEM 또는 Polity5 양국 중 낮은 쪽 — 'weak link' 원칙)"
dependent_var: "양국 간 무력 분쟁 발생 확률 (COW MID 데이터 — 민주국가쌍 vs 혼합·권위주의쌍 비교)"
conditions:
  - "양국 모두 절차적 민주주의 충족 (선거·법치·시민 자유)"
  - "민주적 규범의 외교 적용 (타협·제도적 갈등 해결 경험)"
  - "충분한 상호 인식: 상대를 민주국가로 인식해야 효과 발동"
falsifiable_prediction: "Polity5 기준 양국 모두 +6 이상 민주주의 점수 보유 시 해당 쌍의 전쟁 발발 확률 권위주의쌍 대비 통계적으로 유의하게 낮음 (통제: 경제 발전·동맹·지리)"
known_counterexample: "인도-파키스탄 카르길 전쟁(1999): 인도 민주주의, 파키스탄 당시 민주 정권 → 전쟁 발생 (민주 평화의 부분 예외); 미국의 민주국가 침략 지원(이란 모사데크 전복 1953, 칠레 아옌데 1973) → '민주국가가 민주국가를 공격'의 간접 형태"
rival_theories:
  - "Offensive Realism (Mearsheimer) — 민주주의보다 권력 구조가 전쟁 결정, 민주 평화는 허구"
  - "Liberal Institutionalism (Keohane) — 제도·상호의존이 민주주의보다 더 강한 평화 조건"
  - "Power Transition Theory (Organski) — 민주주의 여부보다 국력 전이·불만족이 전쟁 결정"
---

## 핵심 주장

Doyle(1983)은 Kant의 '영구 평화론'을 실증화했다: **민주주의 국가들끼리는 전쟁하지 않는다.**

### 민주 평화의 두 설명 메커니즘

**1. 규범 메커니즘 (Normative Mechanism)**
민주국가는 내부적으로 타협·협상으로 갈등 해결 → 이 규범이 외교에도 적용.  
상대를 민주국가로 인식 → 전쟁 대신 협상 선택.

**2. 제도 메커니즘 (Institutional Mechanism)**
의회 동의 필요, 선거 책임, 언론 감시 → 전쟁 비용이 유권자에게 투명.  
권위주의보다 전쟁 개시 임계치 높음.

### Russett의 통계 검증

Bruce Russett(1993) 분석: 1816~1980년 MID 데이터에서
- 민주국가 쌍: 상호 전쟁 사례 **0건** (전쟁이 아닌 낮은 수준 분쟁은 존재)
- 민주-권위주의 쌍: 정상 비율
- 권위주의 쌍: 가장 높은 전쟁 발생률

### 'Liberal Zone of Peace'와 지정학적 함의

민주국가들 사이에 형성되는 평화 지대 → NATO, EU, Quad의 민주 동맹은 이 프레임의 제도화.  
중국·러시아의 권위주의 vs 서방 민주 동맹의 충돌 = 민주 평화론의 현재 격전지.

## 현재 사례 연결

- **대만**: 민주주의 지수 높음 → 중국(권위주의)과의 충돌은 민주 평화론 범위 밖 (다른 억지 필요)
- **한국·일본**: 민주국가 쌍 → 역사 갈등에도 전쟁 억제 → 민주 평화 부분 작동
- **러시아 우크라이나**: 러시아 권위주의화(2000년 이후) + 우크라이나 민주화 → 충돌 예측 일치

## 주요 학자 및 저작

- Doyle, M. (1983). "Kant, Liberal Legacies, and Foreign Affairs." *Philosophy & Public Affairs*, 12(3/4).
- Russett, B. (1993). *Grasping the Democratic Peace*. Princeton University Press.
- Owen, J. (1994). "How Liberalism Produces Democratic Peace." *International Security*, 19(2).
- Mearsheimer, J. (1994). "The False Promise of International Institutions." *International Security*, 19(3). (반론)

## 이론의 한계

- 인과 방향 불확실: 민주주의가 평화를 만드는가, 평화가 민주주의를 만드는가
- '민주국가' 정의 논쟁: 파키스탄·헝가리 등 결함 있는 민주주의 포함 시 이론 적용 범위 확대
- 민주-권위주의 간 전쟁은 억제 안 됨 → 실제 위험한 쌍에서 효과 없음

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 대만 민주주의 지수 하락 | 중국 강압 명분 증가 → TSM 하락 | `taiwan_strait_to_tsm` |
| 동맹국 권위주의화 (Polity5 하락) | 동맹 결속 약화 → 방기 위험 증가 | (신규 후보) |
