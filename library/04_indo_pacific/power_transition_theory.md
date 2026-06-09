---
asset_type: theory
era: cold_war
geopol_region: taiwan_strait
instrument_of_power: military
level_of_analysis: systemic
regions:
- taiwan_strait
- korean_peninsula
- south_china_sea
- east_china_sea
sector_tag: indo_pacific
strategic_posture: revisionist
summary: 기존 패권국과 도전국의 국력 격차가 좁혀질 때 전쟁 위험이 최고조에 달한다. 도전국이 기존 질서에 불만족할수록 전이(transition) 시점의 충돌 확률이 높아진다.
temporal_era: us_china_rivalry
theorists:
- A.F.K. Organski
- Jacek Kugler
- Ronald Tammen
theory_id: indo_pacific_power_transition_theory
title: 세력전이 이론 (Power Transition Theory)
year: 1958
independent_var: "도전국 GDP의 패권국 GDP 대비 비율 (%, World Bank — 중국 vs 미국)"
dependent_var: "패권 안정성 지수 역수 (분쟁 건수·위기 빈도, COW MID 데이터)"
conditions:
  - "도전국의 상대적 성장률이 패권국 초과 (따라잡기 단계)"
  - "도전국이 현 국제 질서에 '불만족(dissatisfied)' 상태"
  - "양국 국력 격차 20% 이내 진입 (임계 구간)"
falsifiable_prediction: "중국 GDP가 미국의 80~120% 구간 진입 시 대만해협·남중국해 위기 빈도 증가 (통제: 지도자 위험 선호도)"
known_counterexample: "1970~90년대 일본의 경제 부상 — 미국 GDP 60~70% 도달에도 군사 충돌 없음 (동맹·민주주의 제도로 전이 비폭력화); EU 통합 — 여러 강대국이 동시에 수렴했으나 평화 유지 (자유주의 제도 효과)"
rival_theories:
  - "Hegemonic Stability Theory (Kindleberger) — 패권국 존재 자체가 안정, 전이 불필요"
  - "Defensive Realism (Waltz) — 구조가 전쟁 억제, 국력 격차가 아닌 균형이 핵심"
  - "Liberal Peace Theory — 민주국가 간·고상호의존 국가 간 전쟁 억제"
---

## 핵심 주장

Organski(1958)는 전통적 세력균형론과 달리 **국력 전이(Power Transition)** 가 전쟁의 핵심 원인이라 주장했다.

### 세력전이의 3단계

```
1단계 — 격차 구간: 패권국 압도적 우위 → 안정
2단계 — 추월 구간: 도전국 20% 이내 접근 → 최고 불안정
3단계 — 추월 후: 새 패권 확립 or 협상 → 재안정
```

### 불만족(Dissatisfaction) 변수의 결정적 역할

단순한 국력 추월만으로는 충분하지 않다.  
도전국이 현 국제 질서의 **규칙·제도·분배**에 불만족해야 전쟁 위험이 현실화된다.

- 일본은 경제적으로 추월에 근접했으나 **만족(satisfied)** 상태 → 전이 무해
- 중국은 추월 진행 + **불만족** (UN 거부권·IMF 지분·글로벌 남방 리더십 요구) → 위험

### Tammen의 현대화: 핵억지와 전이

핵보유국 간 전이는 전쟁 대신 **회색지대 경쟁**으로 표출.  
→ 남중국해 인공섬·FONOP·경제 강압이 핵 임계 아래 전이 경쟁의 현대판.

## 현재 사례 연결

- **중-미 GDP 격차**: 2023년 중국 GDP = 미국의 ~65% (PPP 기준 이미 추월). 전이 임계 구간 접근 중
- **대만해협**: Organski 모델에서 가장 가능성 높은 전쟁 트리거 — 중국 '불만족' + 임계 접근 시점
- **인도**: 2030년대 세력전이 2막 후보 (인도 vs 중국)

## 주요 학자 및 저작

- Organski, A.F.K. (1958). *World Politics*. Knopf.
- Organski, A.F.K. & Kugler, J. (1980). *The War Ledger*. University of Chicago Press.
- Tammen, R. et al. (2000). *Power Transitions: Strategies for the 21st Century*. Chatham House.
- Allison, G. (2017). *Destined for War: Can America and China Escape Thucydides's Trap?* Houghton Mifflin.

## 이론의 한계

- "불만족" 개념의 측정 어려움 — 지도자 의도를 사전에 알기 불가능
- 핵 억지가 존재하면 실제 전쟁 발생 확률 이론 예측치보다 낮음
- 경제력만 측정 — 기술력·소프트파워·동맹 네트워크 미반영

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 중국 GDP 미국 80% 돌파 (World Bank) | 대만해협 긴장 → TSMC 하락 | `taiwan_strait_to_tsm` |
| 남중국해 기지화 가속 | 방산주 수혜 | `south_china_sea_to_defense` |
