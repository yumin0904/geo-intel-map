---
asset_type: theory
era: cold_war
geopol_region: bab_el_mandeb
instrument_of_power: military
level_of_analysis: non_state
regions:
- bab_el_mandeb
- hormuz
- eastern_europe
- south_china_sea
sector_tag: gray_zone
strategic_posture: revisionist
summary: 강대국이 직접 충돌 위험 없이 목표를 달성하기 위해 제3의 비국가·약소국 행위자를 도구화한다. 지원국은 비용·책임·에스컬레이션 위험을 프록시에 전가한다.
temporal_era: us_china_rivalry
theorists:
- Andrew Mumford
- Eli Berman
- Daniel Byman
theory_id: gray_zone_proxy_war_theory
title: 대리전 이론 (Proxy War Theory)
year: 2013
independent_var: "후원국의 프록시 지원 수준 (무기·자금·훈련 제공량, SIPRI Arms Transfer)"
dependent_var: "프록시 충돌 강도·지속 기간 (ACLED 이벤트 건수·HIIK 분쟁 강도)"
conditions:
  - "직접 충돌의 비용·위험이 지원국에 과도 (핵 억지·국제 여론)"
  - "지역 내 취약 행위자 존재 (무장·훈련 가능한 비국가 집단)"
  - "지원국의 부인가능성(plausible deniability) 확보 가능"
falsifiable_prediction: "후원국 지원 규모 증가 시 프록시 분쟁 강도 증가 + 직접 충돌 빈도 감소 (통제: 지역 취약성 지수)"
known_counterexample: "러시아-우크라이나(2022~): Wagner 사용에도 결국 정규군 투입 — 프록시로 목표 미달성 시 직접 개입 전환 실증; 이란 축(Axis of Resistance): 후티·헤즈볼라·하마스 동시 활성화에도 이스라엘·미국에 전략적 패배 미부과 — 프록시 효과 과대평가 위험"
rival_theories:
  - "Gray Zone Strategy (Mazarr) — 프록시는 회색지대의 한 도구, 전략 전체가 아님"
  - "Hybrid Warfare (Hoffman) — 정규·비정규 동시 사용, 프록시는 비정규의 부분집합"
  - "Coercive Diplomacy (Schelling) — 직접 위협이 더 신뢰성 높은 강압 수단"
---

## 핵심 주장

Mumford(2013)는 프록시 전쟁을 **간접 전략의 핵심 수단**으로 정의했다:

> "프록시 전쟁: 제3자가 주요 당사자의 이익을 위해 싸우도록 사주·지원·지시하는 분쟁"

### 프록시 관계의 3유형

| 유형 | 지원국 통제 | 프록시 자율성 | 사례 |
|------|-----------|------------|------|
| **도구형** | 高 | 低 | 소련 → 쿠바 앙골라 파병 |
| **파트너형** | 中 | 中 | 이란 → 헤즈볼라 |
| **기회형** | 低 | 高 | 미국 → 시리아 쿠르드(YPG) |

### Byman의 프록시 딜레마

지원국은 프록시 통제력을 유지하기 위해 지원을 늘려야 하지만,
지원이 많아질수록 프록시의 자율성도 증가 → **꼬리가 개를 흔드는(tail wags the dog)** 역전 가능.

### 이란의 '저항의 축'(Axis of Resistance)

헤즈볼라(레바논) + 하마스(가자) + 후티(예멘) + 이라크 시아파 민병대:
- 각 프록시가 독자 의제 보유 → 이란이 일부만 통제
- 2023 10·7 하마스 공격: 이란 사전 승인 여부 불확실 → 프록시 자율 행동 사례

## 현재 사례 연결

- **후티 홍해 공격(2023~)**: 이란의 후티 지원 → 바브엘만데브 통항 위협 → 유가·해운비 상승
- **우크라이나 vs 러시아**: Wagner PMC(민간군사기업) = 현대 프록시, 러시아 부인 가능성 활용
- **사헬 위기**: 러시아 Wagner → 말리·부르키나파소·니제르 군사 지원 → 프랑스 배제

## 주요 학자 및 저작

- Mumford, A. (2013). *Proxy Warfare*. Polity Press.
- Byman, D. (2005). *Deadly Connections: States That Sponsor Terrorism*. Cambridge University Press.
- Groh, T.L. (2019). *Proxy War: The Least Bad Option*. Stanford University Press.
- Berman, E. (2009). *Radical, Religious, and Violent: The New Economics of Terrorism*. MIT Press.

## 이론의 한계

- 프록시가 독자 의제 추구 시 후원국 이익과 충돌 (Byman의 '테일 왝')
- 귀속 불확실성이 억지 실패 유발 — 후원국이 응보를 피함
- 지원 중단 후 프록시가 독자 무장 세력으로 잔존 → 후원국 골칫거리 전환 (아프가니스탄 무자헤딘)

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 후티 홍해 공격 강도 상승 | 해운 보험료 급등 → 유가 상승 | `bab_el_mandeb_to_oil` |
| Wagner 사헬 확장 | 분쟁 강도 상승 → 원자재 불안 | (신규 후보) |
