---
asset_type: theory
era: multipolar
geopol_region: eastern_europe
instrument_of_power: informational
level_of_analysis: state_domestic
regions:
- eastern_europe
- taiwan_strait
- korean_peninsula
- hormuz
sector_tag: cyber
strategic_posture: revisionist
summary: 사이버 공격의 배후를 특정 국가·행위자에게 귀속하는 귀속(Attribution)은 사이버 억지와 외교적 대응의 전제 조건이다. 다이아몬드 모델과 킬 체인 분석이 귀속 증거의 표준 프레임워크를 제공한다.
temporal_era: us_china_rivalry
theorists:
- Thomas Rid
- Ben Buchanan
- Sergio Caltagirone
theory_id: cyber_apt_attribution_theory
title: APT 귀속 이론 (APT Attribution Theory)
year: 2015
independent_var: "귀속 증거 강도 (다이아몬드 모델 4요소 충족도 0~4: 대적자·능력·인프라·피해자)"
dependent_var: "공개 귀속 성명 후 동일 행위자 재공격 빈도 변화율 (CSIS Significant Cyber Incidents DB, 6개월 전후 비교)"
conditions:
  - "기술적 귀속 증거 확보: 악성코드 서명·C2 인프라·TTP 패턴 일치"
  - "국가 귀속 정치적 결정: 기술 증거 + 외교·정보 기관 판단"
  - "공개 귀속의 전략적 가치가 귀속 노출 비용(정보원 소진)을 초과"
falsifiable_prediction: "다이아몬드 모델 4요소 모두 충족한 공개 귀속 성명 이후 6개월 내 동일 APT 그룹의 동일 표적 재공격 빈도 감소 (통제: 제재·외교 압박 동반 여부, CSIS 데이터)"
known_counterexample: "미국의 중국 OPM 해킹 귀속(2015): 오바마-시 사이버 합의 후 일시적 경제스파이 감소 — 귀속 + 외교 압박의 부분 성공; 미국의 러시아 SolarWinds 귀속 선언(2021): 귀속 이후에도 Cozy Bear·Fancy Bear 작전 지속 — 귀속만으로 억지 불충분 실증"
rival_theories:
  - "Cyber Deterrence Theory (Libicki) — 귀속보다 전반적 억지 체계가 우선"
  - "Cyber Offense-Defense Balance (Lynn) — 귀속 자체가 공격자의 비용 구조를 바꾸지 못함"
  - "Cognitive Warfare — 귀속 의도가 기술 특정보다 내러티브 구성에 있음"
---

## 핵심 주장

Rid & Buchanan(2015)은 귀속을 단순 기술 문제가 아닌 **정치적·전략적 결정**으로 재정의했다:

> "귀속은 과학이 아니라 예술이다 — 완전한 확실성은 없으며, 결정은 언제나 정치적이다."

### 다이아몬드 모델 (Caltagirone et al., 2013)

사이버 침해 분석의 표준 프레임워크:

```
        대적자 (Adversary)
           /         \
      능력         피해자
  (Capability)    (Victim)
           \         /
        인프라 (Infrastructure)
```

4요소 간 관계 매핑으로 캠페인 전체 그림 구성 → 귀속 근거 강화.

### 킬 체인 분석 (Lockheed Martin, 2011)

공격 단계별 탐지·대응:
1. 정찰(Reconnaissance) → 2. 무기화 → 3. 전달 → 4. 익스플로잇 → 5. 설치 → 6. C2 → 7. 행동

각 단계에서 흔적(IOC: Indicator of Compromise) 확보 → 귀속 증거 누적.

### 귀속의 3단계 (기술→국가→공개)

1. **기술 귀속**: 악성코드 서명·TTP(전술·기법·절차) 분석 → APT 그룹 특정
2. **국가 귀속**: APT 그룹과 국가 연계 판단 (정보·외교 채널 종합)
3. **공개 귀속**: 정치적 결정 — 증거 일부 공개 vs 정보원 소진 딜레마

### 공개 귀속의 전략 효용

- 동맹국 집결·외교 압박 강화
- 피해 기업·국민의 위협 인식 제고
- 국내 정치 지지 획득 (사이버 안보 예산 확보)

## 현재 사례 연결

- **Volt Typhoon(2023~2024)**: 미국 5Eyes 공동 귀속 → 중국의 미 핵심 인프라 사전 침투 공개 — 최고 수준 다자 귀속의 전형
- **Lazarus Group**: 북한 국가 귀속 APT → WannaCry·Axie 해킹 귀속 → 제재 연계
- **Sandworm (GRU Unit 74455)**: 러시아 군 정보국에 귀속, 우크라이나 전력망 공격

## 주요 학자 및 저작

- Rid, T. & Buchanan, B. (2015). "Attributing Cyber Attacks." *Journal of Strategic Studies*, 38(1–2).
- Caltagirone, S., Pendergast, A. & Betz, C. (2013). "The Diamond Model of Intrusion Analysis." *CTIA Technical Report*.
- Hutchins, E. et al. (2011). "Intelligence-Driven Computer Network Defense." *Lockheed Martin*.
- Mandiant (2013). *APT1: Exposing One of China's Cyber Espionage Units*. Mandiant Corporation.

## 이론의 한계

- 귀속 증거 공개 시 수집 방법·정보원 노출 → 미래 정보 수집 역량 소진 딜레마
- AI 기반 딥페이크 귀속 조작: 타국 TTP 모방으로 거짓 귀속 유도 가능 (False Flag 작전)
- 국가-민간 경계 모호: APT가 국가가 허용한 범죄 조직일 때 국가 귀속 논란

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 주요 인프라 사이버 공격 귀속 선언 | 사이버 안보 기업 ETF 급등 | (신규 후보) |
| 대만 관련 APT 공격 탐지 | 대만해협 긴장 → TSM 하락 | `taiwan_strait_to_tsm` |
