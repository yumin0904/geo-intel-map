---
asset_type: theory
era: unipolar
geopol_region: hormuz
instrument_of_power: economic
level_of_analysis: state_domestic
regions:
- hormuz
- bab_el_mandeb
- eastern_europe
- south_china_sea
sector_tag: energy
strategic_posture: status_quo
summary: 국가의 에너지 안보는 '적정 가격의 안정적 공급'으로 정의된다. 공급 다변화·전략 비축·효율화·재생에너지 전환의 네 축이 에너지 안보 취약성을 감소시킨다.
temporal_era: us_china_rivalry
theorists:
- Daniel Yergin
- Jan Kalicki
- Andreas Goldthau
theory_id: energy_energy_security_theory
title: 에너지 안보론 (Energy Security Theory)
year: 1991
independent_var: "에너지 공급원 집중도 (HHI 지수 — 상위 3개 공급국 점유율, IEA 데이터)"
dependent_var: "에너지 가격 충격 민감도 (유가 10% 변동 시 GDP 성장률 변화율, World Bank)"
conditions:
  - "화석연료 수입 의존도 高 (GDP 대비 에너지 수입액)"
  - "공급 다변화 경로 부재 (파이프라인·항로 단일 의존)"
  - "전략 비축량 부족 (IEA 기준 90일 미만)"
falsifiable_prediction: "에너지 공급원 HHI 감소(다변화) 시 에너지 가격 충격 대비 GDP 변동성 감소 (통제: 재생에너지 비율·전략 비축량)"
known_counterexample: "독일의 노르드스트림 의존 전략(2000~2022): 에너지 안보론의 '다변화 원칙' 위반 → 2022년 러시아 공급 차단 시 에너지 위기 실증; 일본 1973년 오일 쇼크 이후 적극 다변화 → 이후 충격 내성 향상 — 이론 지지"
rival_theories:
  - "Resource Weaponization (Hirschman) — 에너지는 공급자의 정치적 무기, 단순 안보 이상"
  - "Rentier State Theory — 에너지 안보의 공급측 행위자(렌티어 국가)의 정치 논리"
  - "Weaponized Interdependence (Farrell & Newman) — 에너지 의존이 강압 취약성"
---

## 핵심 주장

Yergin(1991)은 *The Prize*에서 에너지 안보를 국가 생존의 핵심 변수로 규정했다.

### 에너지 안보의 4D 전략

| 전략 | 내용 | 현대 사례 |
|------|------|---------|
| **다변화(Diversify)** | 공급국·경로·연료 종류 분산 | 한국 LNG 다변화, 유럽 미국 LNG 수입 |
| **비축(Stockpile)** | 전략 비축유·가스 90일+ 유지 | 미국 SPR, 일본 국가 비축 |
| **효율화(Efficiency)** | 소비 절감으로 의존도 감소 | EU 에너지 효율 지침 |
| **전환(Transition)** | 재생에너지로 화석연료 의존 탈피 | RE100, IRA 청정에너지 |

### Goldthau의 시장-안보 딜레마

에너지 시장 자유화(IEA 권고) vs 안보 목적 국가 개입:
- 시장 자유화: 효율적이나 가격 변동 노출
- 국가 개입: 안보적이나 비효율·자원 민족주의 유발
- **딜레마**: 어느 쪽도 완전한 에너지 안보 달성 불가

### 전략 석유 비축(SPR)의 정치경제

IEA 90일 기준 비축량 = 공급 충격 완충.  
실제로는 정치적 목적으로 방출 (2022 우크라이나전 후 SPR 방출 → 유가 일시 하락).

## 현재 사례 연결

- **독일 에너지 위기(2022)**: 노르드스트림 의존 → Yergin의 다변화 원칙 위반의 결과
- **한국 에너지 안보**: LNG 수입선 카타르·호주·미국 분산 → 호르무즈 위기 대비
- **중국 에너지 안보**: 말라카 딜레마 → 파이프라인(미얀마·중앙아시아)·BRI로 우회 다변화

## 주요 학자 및 저작

- Yergin, D. (1991). *The Prize: The Epic Quest for Oil, Money & Power*. Simon & Schuster.
- Yergin, D. (2011). *The Quest: Energy, Security, and the Remaking of the Modern World*. Penguin.
- Kalicki, J. & Goldwyn, D. (eds.) (2005). *Energy and Security*. Woodrow Wilson Center Press.
- Goldthau, A. & Witte, J.M. (eds.) (2010). *Global Energy Governance*. Brookings Institution Press.

## 이론의 한계

- '적정 가격' 기준 모호 — 국가별 경제 구조에 따라 허용 가격 차이
- 재생에너지 전환 후 새로운 안보 의존(희토류·배터리 리튬)이 등장 → 에너지 안보 개념 확장 필요
- 시장 가격 메커니즘이 전략 비축 방출 시점 왜곡 가능 (정치적 방출 = 시장 신뢰 훼손)

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 호르무즈 봉쇄 위기 | 전략 비축 방출 신호 → 유가 일시 하락 후 반등 | `hormuz_tension_to_oil` |
| LNG 공급 차단 (노르드스트림 유사) | 유럽 에너지 위기 → 에너지 ETF 급등 | (신규 후보) |
