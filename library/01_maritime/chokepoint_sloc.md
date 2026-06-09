---
asset_type: theory
era: cold_war
geopol_region: bab_el_mandeb
instrument_of_power: military
level_of_analysis: systemic
regions:
- bab_el_mandeb
- hormuz
- malacca
- suez
sector_tag: maritime
strategic_posture: status_quo
summary: 해상 교통로(SLOC)와 그 병목인 초크포인트를 통제하는 국가가 글로벌 무역·에너지 흐름을 좌우한다. 평시엔 항행의 자유, 위기 시엔
  봉쇄 카드로 전환된다.
temporal_era: cold_war
theorists:
- Alfred Thayer Mahan
- Nicholas Spykman
- Geoffrey Till
theory_id: maritime_chokepoint_sloc
title: SLOC 통제 이론 (Chokepoint & Sea Lines of Communication)
year: 1944
independent_var: "초크포인트 통과 위협 강도 (도발·나포·기뢰 부설 건수, ACLED/해상 인시던트)"
dependent_var: "글로벌 무역·에너지 흐름 교란 (해상 운임·보험료·유가 변동 %)"
conditions:
  - "우회로 부재 또는 고비용 (희망봉 우회 = 수에즈 대비 +10~14일)"
  - "통과 물동량 집중 (호르무즈 = 글로벌 원유 해상수송 약 20%)"
  - "통제 주체의 봉쇄 의지·역량 (해군 투사력 또는 비대칭 거부 수단)"
falsifiable_prediction: "초크포인트 위협 강도 증가 시 운임·유가 단기 급등 (통제: 비축유 방출·대체 운송로·완충 재고)"
known_counterexample: "후티의 홍해 공격에도 유가 급등이 제한적이었던 2024~2025 — 미국 전략비축유 방출·OPEC+ 여유 생산능력·우회 항로 흡수로 전이 차단. 초크포인트 위협이 자동으로 가격 충격이 되지 않음 (위협 인식 ≠ 실제 봉쇄)"
rival_theories:
  - "Resource Weaponization (초크포인트는 물리 통제가 아니라 자원 무기화 수단)"
  - "Command of the Commons (미 해군의 압도적 제해권이 초크포인트 봉쇄를 무력화)"
  - "Self-deterrence / Insurance Markets (실제 봉쇄보다 보험·자기억지 인식이 교란을 결정)"
---

## 핵심 주장

**SLOC(Sea Lines of Communication)**은 국가 간 무역·에너지·군수 물자가 오가는
해상 고속도로다. Spykman은 이 항로들이 수렴하는 지점, 즉 **초크포인트**를
지배하는 자가 세계 경제의 스위치를 쥔다고 주장했다.

세계 5대 전략 초크포인트:

| 초크포인트 | 일일 통과량 | 핵심 위협 |
|---|---|---|
| 호르무즈 해협 | 원유 2,100만 배럴/일 (전세계 20%) | 이란 봉쇄 위협 |
| 말라카 해협 | 원유 1,600만 배럴/일 | 해적, 중국-인도 대결 |
| 바브엘만데브 | 원유 600만 배럴/일 | 후티 공격 |
| 수에즈 운하 | 세계 해상무역 12% | 예멘발 미사일 |
| 파나마 운하 | 세계 해상무역 5% | 기후변화(수위 저하) |

봉쇄의 논리: 초크포인트는 **폭이 좁아 소수 전력으로 차단 가능**하며,
우회로(희망봉·케이프 혼)는 수천km 추가 항행을 요구해 물류비용을 폭증시킨다.

## 주요 학자 및 저작

이 이론의 핵심 기여자와 대표 저작:

- Spykman, N. (1944). *The Geography of the Peace*. Harcourt, Brace.
- Till, G. (2018). *Seapower: A Guide for the 21st Century*. Routledge.
- EIA (2024). "World Oil Transit Chokepoints." U.S. Energy Information Administration.
- 박영준 (2020). "해양 초크포인트와 한국의 에너지 안보." *국방연구*, 63(1).

> "초크포인트를 지배하는 자는 전쟁 없이도 적국을 굴복시킬 수 있다."
> — Nicholas Spykman, *The Geography of the Peace* (1944)

## 현대 지정학과의 연결

### 후티의 홍해 작전 (2023~)
예멘 후티는 바브엘만데브 해협에서 드론·미사일로 상선을 공격하여
세계 컨테이너 운임을 600% 이상 급등시켰다.
비국가 행위자가 초크포인트 위협만으로 글로벌 공급망을 교란한 교과서적 사례다.
많은 선사가 수에즈 경유를 포기하고 희망봉으로 우회하여
아시아-유럽 항로 2주가 추가되었다.

### 호르무즈 봉쇄 위협
이란은 대미 갈등 시 "호르무즈 봉쇄" 카드를 반복 사용한다.
실제 봉쇄보다 **위협만으로도** 유가가 즉각 반응한다는 것이
초크포인트의 심리적 지렛대 효과다.

### 말라카 딜레마와 중국
중국 에너지 수입의 80%가 말라카를 통과한다.
분쟁 시 미 해군이 말라카를 통제하면 중국 경제는 마비된다.
이것이 중국이 미얀마·파키스탄 경유 육상 파이프라인(CPEC)을 추진하는 이유다.

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 바브엘만데브 공격 (severity ≥ 50) | 유가(CL=F) 상승 | `bab_el_mandeb_tension_to_oil` |
| 수에즈 긴장 고조 | 해운 운임(ZIM) 상승 | `suez_tension_to_shipping` |
| 호르무즈 봉쇄 위협 | 원유 선물 급등 | `hormuz_tension_to_oil` |

## 학습 노트

> "초크포인트를 지배하는 자는 전쟁 없이도 적국을 굴복시킬 수 있다."
> — Nicholas Spykman, *The Geography of the Peace* (1944)

지도에서 AIS 선박 밀도 레이어와 초크포인트(Chokepoints) 레이어를 동시에 켜보자.
바브엘만데브·호르무즈·말라카 주변에 선박이 얼마나 밀집되어 있는지,
그리고 분쟁 이벤트 레이어의 ACLED 점들이 그 바로 옆에 찍혀있는지 확인하라.
숫자가 아닌 공간으로 초크포인트의 의미를 이해하는 것이 핵심이다.

## 참고 자료

- Spykman, N. (1944). *The Geography of the Peace*. Harcourt, Brace.
- Till, G. (2018). *Seapower: A Guide for the 21st Century*. Routledge.
- EIA (2024). "World Oil Transit Chokepoints." U.S. Energy Information Administration.
- 박영준 (2020). "해양 초크포인트와 한국의 에너지 안보." *국방연구*, 63(1).