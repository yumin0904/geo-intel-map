---
asset_type: theory
era: multipolar
geopol_region: taiwan_strait
instrument_of_power: informational
level_of_analysis: systemic
regions:
- taiwan_strait
- eastern_europe
- hormuz
- korean_peninsula
sector_tag: cyber
strategic_posture: revisionist
summary: 사이버 공간은 공세가 방어보다 구조적으로 유리하다. 취약점의 비대칭적 전파, 익스플로잇 민주화, 공급망 공격 가능성이 소규모 행위자도 대국 인프라를 공격할 수 있게 만든다.
temporal_era: us_china_rivalry
theorists:
- William Lynn III
- Ben Buchanan
- Jason Healey
- Erik Gartzke
theory_id: cyber_offense_defense_balance
title: 사이버 공세-방어 균형 (Cyber Offense-Defense Balance)
year: 2010
independent_var: "공격 도구 접근 비용 (익스플로잇 개발·구매 비용 달러, 취약점 시장 데이터)"
dependent_var: "사이버 공격 성공률 (침해 성공 건수 / 시도 건수, CSIS Cyber Incidents DB)"
conditions:
  - "취약점의 비대칭적 전파 (공격자는 1개 취약점, 방어자는 전체 면적 방어)"
  - "공급망 신뢰 구조 (소프트웨어·하드웨어 공급망에 백도어 삽입 가능)"
  - "귀속 불확실성 (Attribution Problem)으로 억지 효과 제한"
falsifiable_prediction: "공격 도구 민주화(비용 하락) 시 소규모 국가·비국가 행위자의 대국 인프라 공격 성공률 증가 (통제: 방어 투자 수준)"
known_counterexample: "이스라엘 사이버 방어 체계 — Iron Dome과 병행한 집중적 방어 투자로 공세 우위 제한; CISA·NSA 방어 역량 집중 시 일부 APT 작전 조기 탐지 (단, 이는 예외적 역량)"
rival_theories:
  - "Cyber Deterrence Theory (Libicki) — 귀속 명확화로 억지 가능"
  - "Digital Iron Curtain — 네트워크 분절화로 공격 면적 축소"
  - "Security Dilemma in Cyberspace — 방어 투자가 공격 역량으로 오인"
related:
  - "[[libicki_cyber_deterrence]]"
  - "[[apt_attribution_theory]]"
  - "[[digital_iron_curtain]]"
---

## 핵심 주장

William Lynn III(미 국방부 차관)는 2010년 *Foreign Affairs* 논문에서 사이버 공간의 구조적 공세 우위를 공식화했다:

> "방어자는 모든 공격 벡터를 막아야 하지만, 공격자는 단 하나의 취약점만 찾으면 된다."

### 공세 우위의 3대 구조 요인

**1. 비대칭적 방어 부담 (Defender's Dilemma)**
- 공격자: 단 1개 취약점 = 침해 성공
- 방어자: 전체 네트워크 100% 방어 = 이론상 불가능
- 결과: 완전한 방어는 존재하지 않음

**2. 취약점 민주화 (Exploitability Democratization)**
- 제로데이 취약점 시장(Zerodium, HackingTeam): 국가급 무기 민간 유통
- AI 코딩 도구: 악성코드 작성 기술 장벽 하락
- 결과: 소규모 국가·비국가 행위자도 고급 공격 가능

**3. 공급망 공격 벡터 (Supply Chain Attack)**
- SolarWinds(2020), XZ Utils(2024): 신뢰받는 소프트웨어에 백도어 삽입
- 하드웨어 임플란트: 중국 제조 장비의 의심
- 결과: 방어 레이어 전체를 우회하는 공격 경로

### Ben Buchanan의 보완: 사이버 보안 딜레마 (2017)

공세 우위는 **안보딜레마(Security Dilemma)** 를 사이버 공간에 이식:
- 방어적 사이버 역량(취약점 탐색, 침투 테스트)이 공격 역량으로 보임
- → 경쟁국의 사이버 군비 경쟁 유발

### Jason Healey의 반론: 방어 우위 잠재력

AI 기반 위협 탐지·자동화 패치의 규모 경제로 방어 비용 하락 가능 → 장기적 균형 전환 가능성.

## 현재 사례 연결

- **Salt Typhoon (2024~2025)**: 중국이 미국 통신 인프라 18개월 지속 접근 — 공세 우위의 실증 (방어 실패)
- **Volt Typhoon**: 미 군사 인프라 사전 배치 — "공격 준비" = 공세 우위 활용 선제 포지션
- **이란전 사이버전 (2026)**: PLC(산업 제어 시스템) 공격 → 물리 피해 발생 — 사이버-물리 통합 공세의 현실화
- **러시아 우크라이나 사이버전**: Sandworm의 전력망·통신 공격 — 전시 공세 우위 실전 검증

## 주요 학자 및 저작

- Lynn, W. (2010). "Defending a New Domain." *Foreign Affairs*, 89(5), 97–108.
- Buchanan, B. (2017). *The Cybersecurity Dilemma*. Oxford University Press.
- Healey, J. (ed.) (2013). *A Fierce Domain: Conflict in Cyberspace, 1986–2012*. CCSA.
- Gartzke, E. (2013). "The Myth of Cyberwar." *International Security*, 38(2), 41–73.

## 이론의 한계

- "공세 우위" 주장은 **귀속 불확실성** 과 결합해 억지 공백 발생 — 공격 많아지지만 응보 적어짐
- AI 기반 방어 자동화로 방어 비용 하락 시 균형 역전 가능 (Healey 반론)
- 핵·물리 억지가 사이버 에스컬레이션을 제한 — 순수 사이버 전쟁의 상한선 존재
- 국가 역량 차이: 사이버 역량 하위국은 공세 우위 활용 자체가 어려움

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 대규모 사이버 공격 (인프라) | 사이버 방산주·보안 ETF 급등 | (신규 룰 후보) |
| APT 전력망 침투 탐지 | 에너지 인프라 취약성 → 유가 불안 | `hormuz_tension_to_oil` 간접 |
