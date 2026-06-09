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
sector_tag: cyber
strategic_posture: revisionist
summary: 사이버 주권론은 국가가 자국 인터넷 공간에 대해 물리적 영토와 동등한 법적·기술적 통제권을 가져야 한다고 주장한다. 서방의 '열린 인터넷' 패러다임과 직접 충돌한다.
temporal_era: us_china_rivalry
theorists:
- Ronald Deibert
- Jack Goldsmith
- Tim Wu
theory_id: cyber_cyber_sovereignty
title: 사이버 주권론 (Cyber Sovereignty Theory)
year: 2013
independent_var: "인터넷 자유 지수 역수 (Freedom House FOTN 점수 역산: 100 - FOTN 점수 = 통제 강도)"
dependent_var: "크로스보더 데이터 흐름 감소율 (OECD 디지털 서비스 무역 제한 지수 DSTRI, 국가별 연간 Δ)"
conditions:
  - "기술적 국경 통제 인프라 보유 (Great Firewall급 심층 패킷 검사 역량)"
  - "국내 대체 플랫폼 생태계 존재 (외국 플랫폼 없어도 기능 유지 가능)"
  - "국내 정치적 정당성: 국가 안보·문화 주권·경제 보호 논거 중 하나 이상"
falsifiable_prediction: "인터넷 자유 지수(FOTN) 하락 10점당 해당 국가의 디지털 서비스 수입 CAGR 통계적 유의 감소 (통제: GDP·무역 의존도, OECD DSTRI × Freedom House 교차)"
known_counterexample: "중국 Great Firewall에도 VPN·프록시로 실질 접속: 2023년 중국 VPN 이용자 추산 1억명+ — 기술 통제의 완전 차단 불가능성 실증; 러시아 RuNet 자율화 법(2019): 인터넷 분리 테스트에서 기술 불안정·자국 서비스 과부하 → 실질 구현 한계 노출"
rival_theories:
  - "Cognitive Warfare (du Cluzel) — 사이버 주권은 허위정보 통제를 위한 합리적 방어 수단"
  - "APT Attribution Theory — 주권 장벽이 귀속 증거 수집을 방해하는 이중 효과"
  - "Digital Iron Curtain — 사이버 주권은 디지털 장막의 규범적 정당화"
---

## 핵심 주장

Deibert(2013)의 *Black Code*는 인터넷이 처음부터 **규제 없는 공간이 아니었음**을 실증했다:

> "인터넷의 자유는 자연적 조건이 아니라 특정 국가(미국)의 기술·법·정치 선택의 결과다. 다른 국가들이 다른 선택을 하는 것은 이상하지 않다."

### 사이버 주권의 3가지 논거

**① 안보 논거**: 외국 플랫폼을 통한 정보전·사이버 공격 차단  
**② 문화 주권**: 자국 언어·가치관 보호 (알고리즘 편향 배제)  
**③ 경제 주권**: 데이터를 국내 자산으로 관리, 외국 플랫폼에 의한 경제 종속 방지

### 주요 구현 형태

| 국가 | 도구 | 수준 |
|------|------|------|
| 중국 | Great Firewall (GFW), 국가 인트라넷 | 최강 |
| 러시아 | RuNet 자율화, SORM 감청 | 강 |
| 이란 | 국가 인트라넷(SHOMA), 필터링 | 강 |
| 투르크메니스탄·북한 | 사실상 인터넷 차단 | 극단 |
| EU | GDPR·DSA (데이터 주권 중도) | 약~중 |

### 데이터 현지화 (Data Localization) 규범

- 자국민 데이터를 자국 서버에 저장 의무화
- 예: 러시아 데이터 현지화법(2015) → Facebook·Twitter 준수 거부 → 2022 차단
- 브라질 LGPD, 인도 PDPB, EU GDPR: 각국의 상이한 데이터 주권 모델

### 미국의 반론: 열린 인터넷 (Multi-stakeholder Model)

인터넷 거버넌스는 국가 독점이 아닌 민간·기술 커뮤니티·시민사회 공동 관리:
- ICANN(도메인 관리)·IETF(기술 표준) = 미국 주도 다중이해관계자 모델
- ITU(국제통신연합)를 통한 국가 통제 시도 = 러시아·중국 vs 서방 대립

## 현재 사례 연결

- **TikTok 금지 논란(2020~2024)**: 서방 국가들의 중국 플랫폼 사이버 주권 대응 → 보안 위협 vs 표현 자유 충돌
- **Starlink 우크라이나**: 러시아 인터넷 차단 우회 → 국가 사이버 주권 침해 vs 전시 통신 지원 논란
- **메타·트위터 러시아 차단(2022)**: RuNet 분리 전진 → 디지털 장막 실질화

## 주요 학자 및 저작

- Deibert, R. (2013). *Black Code: Inside the Battle for Cyberspace*. Signal.
- Goldsmith, J. & Wu, T. (2006). *Who Controls the Internet? Illusions of a Borderless World*. Oxford University Press.
- DeNardis, L. (2014). *The Global War for Internet Governance*. Yale University Press.
- Freedom House (annual). *Freedom on the Net (FOTN) Report*.

## 이론의 한계

- VPN·우회 기술이 물리적 장벽을 유연하게 무력화 → 완전 통제의 기술적 한계
- 글로벌 공급망·클라우드 의존이 깊은 국가는 인터넷 분리 비용이 GDP 1~3% 추산
- 디지털 권위주의 ≠ 경제 쇠퇴: 중국 디지털 경제 성장이 사이버 주권과 공존 → 서방 자유주의 논리 약화

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 주요국 외국 플랫폼 차단 선언 | 해당 플랫폼 주가 하락 + 디지털 인권 보고서 급등 | (신규 후보) |
| 인터넷 분리 시험 (러시아 RuNet) | 동맹국 디지털 협력 차단 → 에스컬레이션 | `gray_zone_escalation` |
