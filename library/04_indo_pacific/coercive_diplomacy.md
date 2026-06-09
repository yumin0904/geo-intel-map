---
asset_type: theory
era: cold_war
geopol_region: taiwan_strait
instrument_of_power: diplomatic
level_of_analysis: state_domestic
regions:
- taiwan_strait
- hormuz
- korean_peninsula
- eastern_europe
sector_tag: indo_pacific
strategic_posture: revisionist
summary: 군사력을 실제 사용하지 않고 '사용 위협'으로 상대의 행동 변화를 강제한다(compellence). 억지(deterrence)가 행동을 막는 것이라면, 강압 외교는 이미 시작된 행동을 멈추게 하거나 새 행동을 강제하는 것이다.
temporal_era: us_china_rivalry
theorists:
- Thomas Schelling
- Alexander George
- Robert Art
theory_id: indo_pacific_coercive_diplomacy
title: 강압 외교 (Coercive Diplomacy)
year: 1966
independent_var: "강압 위협의 신뢰성 지수 (군사 전개 수준 × 과거 실행 이력 × 이익 비대칭)"
dependent_var: "강압 수용률 (요구 수락 건수 / 위협 건수, ICB 데이터셋)"
conditions:
  - "위협의 신뢰성(credibility): 실행 가능성·의지 모두 충족"
  - "이익 비대칭: 위협국 이익 > 피위협국 저항 비용"
  - "도주로(face-saving exit) 제공: 상대가 수용할 명분"
falsifiable_prediction: "군사 전개 + 최후통첩 조합 시 강압 수용률 단독 외교 위협 대비 2배 이상 (통제: 이익 비대칭·핵 지위)"
known_counterexample: "미국의 이란 핵 강압(2003~2015) — 12년간 강압에도 핵 프로그램 지속, JCPOA는 협상이지 강압 수용 아님; 쿠바 미사일 위기 — 소련의 강압 시도를 미국의 역강압으로 역전, 강압 실패 사례"
rival_theories:
  - "Compellence vs Deterrence 구분 비판 — 실제 사례에서 경계 모호"
  - "Conventional Deterrence Theory — 위협보다 실제 방어 능력이 결정적"
  - "Liberal Institutionalism (Keohane) — 제도·경제 상호의존이 강압보다 효과적"
---

## 핵심 주장

Schelling(1966)은 **강압(coercion)** 을 두 종류로 구분했다:

| 유형 | 목적 | 수단 |
|------|------|------|
| **억지(Deterrence)** | 행동 방지 | "X하면 응징" |
| **강압(Compellence)** | 행동 변화 강제 | "Y하지 않으면 응징" |

강압 외교는 **강압** 유형 — 이미 진행 중인 행동을 멈추게 하거나, 원치 않는 행동을 강제.

### George의 강압 성공 3조건

Alexander George(1991)는 역사 사례 분석에서 강압 성공 조건을 도출:

1. **동기 비대칭**: 강압국의 의지 > 피강압국의 저항 의지
2. **긴박감 창출**: 기한(deadline)·단계적 압박으로 행동 촉구
3. **도주로 제공**: 피강압국이 면피하며 수용할 명분 제공

### Art의 군사력 6기능

Art(1980)는 군사력이 억지·방어·강압·과시 등 6가지 기능을 동시 수행함을 명시.  
강압은 군사력의 정치적 활용 핵심 기제.

## 현재 사례 연결

- **대만해협 군사 훈련 (2022, 펠로시 방문 후)**: 중국의 전형적 강압 — 군사 전개로 대만의 독립 움직임에 비용 부과
- **러시아 우크라이나 국경 집결 (2021~2022)**: 군사 압박으로 NATO 확장 중단 강요 시도 → 실패 → 실제 침공 전환
- **미국 이란 제재 + 호르무즈 항모 전개**: 핵 협상 테이블 복귀를 위한 강압 → 부분 성공(JCPOA)

## 주요 학자 및 저작

- Schelling, T. (1966). *Arms and Influence*. Yale University Press.
- George, A. (1991). *Forceful Persuasion: Coercive Diplomacy as an Alternative to War*. USIP Press.
- Art, R. (1980). "To What Ends Military Power?" *International Security*, 4(4), 3–35.
- Pape, R. (1996). *Bombing to Win: Air Power and Coercion in War*. Cornell University Press.

## 이론의 한계

- 강압 성공/실패의 사후 귀인 편향 — 실패한 강압이 역사 기록에 덜 남음
- 핵보유국 간 강압: 에스컬레이션 사다리가 핵 임계를 넘을 위험 → 실행 신뢰성 저하
- 다자 강압: 연합 내부 이견이 신뢰성을 침식 (미국의 대중 기술 통제에서 동맹 이탈 현상)

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 대만해협 군사 훈련 강도 상승 | 반도체 공급 불안 → TSM 하락 | `taiwan_strait_to_tsm` |
| 미·이란 제재 강화 | 호르무즈 봉쇄 위협 → 유가 급등 | `hormuz_tension_to_oil` |
