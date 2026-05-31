---
asset_type: theory
title: "확장억제 (Extended Deterrence)"
theory_id: indo_pacific_extended_deterrence
sector_tag: indo_pacific
summary: 핵보유 강대국(미국)이 동맹국에게 핵우산을 제공하는 안보 보장. 북한 핵 위협에 맞선 한미·미일 동맹의 핵심 개념. 억제가 실패할 때의 비용(연루)과 포기(방기)의 딜레마를 내포한다.
geopol_region: korean_peninsula
temporal_era: cold_war
level_of_analysis: state_domestic
instrument_of_power: military
strategic_posture: status_quo
theorists:
- Thomas Schelling
- Glenn Snyder
- Victor Cha
year: 1966
regions:
- korean_peninsula
- taiwan_strait
- east_china_sea
---

## 핵심 주장

**Thomas Schelling (1966)**: 억제(Deterrence)는 공격 비용을 올리는 것이다.
**확장억제(Extended Deterrence)**: 핵보유국이 제3국(동맹)의 방어에 자국 핵을 사용하겠다는 공약.

핵심 신뢰성 문제: "뉴욕이 서울을 위해 불탈 것인가?"
적이 이 공약을 믿지 않으면 억제는 실패한다.

## 한반도 적용

**한미상호방위조약(1953)**: 북한의 침략 시 미국 자동 개입.
**확장억제공약(Extended Deterrence Commitment)**: 핵우산, 재래식 타격, 미사일방어 3요소.

**전술핵 vs 확장억제의 대체 논쟁 (2023~)**:
한국 여론의 자체 핵무장 지지(60%+) → 미국의 확장억제 신뢰도 의문 신호.
한국이 독자 핵을 갖지 않고 미국에 의존하는 것은 Snyder의 "방기 위험" 수용이다.

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 |
|---|---|---|
| 북한 미사일 발사 (sev≥70) | KRW=X 상승 (원화 약세) | `north_korea_missile_to_krw` |
| 한반도 긴장 고조 | KOSPI 하락 | `korean_tension_to_kospi` |
| 한반도 분쟁 (sev≥35) | KRW=X 상승 | `korean_peninsula_to_krw` |

억제가 **실패**하면 연루-방기 딜레마가 즉각 시장에 반영된다.
미국의 개입 여부 불확실성 → KRW 약세 → KOSPI 하락 경로.

## 코리아 디스카운트와의 연결

확장억제의 신뢰도 불확실성은 **코리아 디스카운트**의 구조적 원인 중 하나다.
지정학 리스크 프리미엄 = 억제 공약의 불확실성이 자산 가격에 반영된 것.

→ `korea_discount` 항목과 함께 학습할 것.

## 참고 자료

- Schelling, T. (1966). *Arms and Influence*. Yale University Press.
- Cha, V. (2002). "Korea's Place in the Axis." *Foreign Affairs*, 81(3).
- 국방부 (2023). "확장억제 강화 방안." 한미안보협의회의(SCM) 공동성명.
