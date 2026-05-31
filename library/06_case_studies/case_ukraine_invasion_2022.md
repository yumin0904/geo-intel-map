---
asset_type: case_study
title: "사례: 2022 러시아 우크라이나 전면 침공 — 자원무기화의 집대성"
theory_id: case_ukraine_invasion_2022
sector_tag: energy
summary: 2022년 2월 24일 러시아의 우크라이나 침공. 밀·해바라기유·천연가스·원유 동시 가격 충격. 자원무기화, 상호의존의 무기화, 회색지대 전략이 한 사건에서 동시에 발현된 교과서적 사례.
geopol_region: eastern_europe
temporal_era: us_china_rivalry
level_of_analysis: state_domestic
instrument_of_power: military
strategic_posture: revisionist
theorists:
- Hirschman (자원무기화)
- Farrell & Newman (상호의존 무기화)
- Mearsheimer (공격적 현실주의)
- Drezner (경제 강압)
theory_id: case_ukraine_invasion_2022
year: 2022
regions:
- ukraine
- eastern_europe
- bab_el_mandeb
- hormuz
---

## 사건 개요

2022년 2월 24일 러시아가 우크라이나를 전면 침공했다.
NATO 동방 확장에 대한 러시아의 안보 불안(Mearsheimer의 주장)과
에너지 패권·영토 팽창 논리가 복합적으로 작용했다.
이 사건은 **냉전 종식 후 유럽 최대 지상전**이자,
5대 섹터가 동시에 충격을 받은 지정학 분석의 **종합 교재**다.

## 5대 섹터 동시 충격

| 섹터 | 충격 내용 | 시장 반응 |
|------|----------|----------|
| Energy | Nord Stream 가스 공급 중단 위협 | NG=F +30~50% |
| Maritime | 흑해 봉쇄·오데사 항 미사일 공격 | 보험료 급등 |
| Techno | 러시아 인터넷 차단·사이버 공격 | 인터넷 차단 지수 |
| Indo-Pacific | 미·NATO 자원 전용 → 인태 전력 분산 우려 | ITA ↑ |
| Gray Zone | 하이브리드 전쟁 교범 적용 | — |

## Cascade 연결 — 핵심 룰

**자원무기화 경로** (`ukraine_conflict_to_wheat`):
우크라이나+러시아 = 세계 밀 수출 28%. 오데사 항 봉쇄 → ZW=F +40%(2022-03 피크).

| 룰 ID | 실측 | 이론 |
|--------|------|------|
| `ukraine_conflict_to_wheat` | ZW=F 피크 +40% | Resource Weaponization |
| `food_price_spike_to_tip` | TIP 상승 확인 | CPI 전이 |

**Granger 검증**: `ukraine_conflict_to_wheat` — 극단 이벤트(상위 25%) 방향 일치 ✅

## 상호의존의 무기화 (Farrell & Newman 2019)

유럽의 러시아 가스 의존도:
- 독일 55%, 이탈리아 40%, 오스트리아 80%

러시아는 이 의존성을 **레버리지**로 전환했다(Nord Stream 차단 협박).
Farrell & Newman 이론의 핵심: 글로벌 공급망의 **비대칭적 의존** → 강압 도구화.

그러나 역설: 러시아도 유럽 가스 수출 수입에 의존 → **상호 취약성**.
실제로 공급 차단 후 러시아도 수출 수입 급감. Drezner(2015): "제재는 양날의 검."

## 아랍의 봄 선행 패턴 (2011과 비교)

밀 가격 급등 → 중동·아프리카 식량 수입국 불안 악화.
2011 아랍의 봄도 러시아-우크라이나 밀 수출 제한(2010 가뭄) 이후 발생.
**Cascade 체인 예시**: 분쟁 → 식량가격 → 정치 불안(library: case_arab_spring).

## 학습 포인트

이 사건이 '교과서'인 이유: 이론들이 **예측한 대로** 발현됐다.
- Mearsheimer가 예측한 러시아의 안보 우려 → 현실화
- Farrell & Newman의 무기화된 상호의존 → 가스 레버리지
- Hirschman의 자원무기화 → 밀·에너지 가격 충격
- Hybrid Warfare → 정보전·사이버 공격 동시 수행

## 참고 자료

- Mearsheimer, J. (2022). "Why the Ukraine Crisis Is the West's Fault." *Foreign Affairs*.
- Economist (2022). "The consequences of Russia's war on Ukraine for food and energy markets."
- UN FAO (2022). Food Price Index 2022.
- 실증 데이터: yfinance ZW=F, NG=F 2022-02-24 전후
