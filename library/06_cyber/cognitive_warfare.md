---
asset_type: theory
era: multipolar
geopol_region: eastern_europe
instrument_of_power: informational
level_of_analysis: non_state
regions:
- eastern_europe
- taiwan_strait
- korean_peninsula
- bab_el_mandeb
sector_tag: cyber
strategic_posture: revisionist
summary: 인지전은 상대 인구·의사결정자의 인식·신념·행동을 직접 표적으로 삼아 물리적 전쟁 없이 전략적 목표를 달성한다. 소셜미디어·딥페이크·내러티브 조작이 현대 인지전의 핵심 수단이다.
temporal_era: us_china_rivalry
theorists:
- François du Cluzel
- Michael Libicki
- Peter Singer
theory_id: cyber_cognitive_warfare
title: 인지전 이론 (Cognitive Warfare Theory)
year: 2020
independent_var: "가짜 정보 캠페인 규모 (허위 계정 수·콘텐츠 확산 속도, Stanford IO 관측 데이터)"
dependent_var: "표적 사회의 정책 지지율 변화 (여론 조사 분기별 변동, 신뢰도 지수)"
conditions:
  - "고속 정보 네트워크 (소셜미디어 침투율 高)"
  - "표적 사회의 인지 취약성 (양극화·미디어 리터러시 低)"
  - "귀속 불확실성 (공격자 숨기기 가능)"
falsifiable_prediction: "허위 정보 캠페인 노출 강도 증가 시 표적 집단의 정책 지지율 변화 폭 확대 (통제: 미디어 리터러시·팩트체크 접근성)"
known_counterexample: "핀란드·에스토니아: 러시아 인지전 집중 대상임에도 사회적 결속·NATO 지지 높게 유지 — '인지 회복력(cognitive resilience)'이 매개변수; 대만: 중국 허위정보 공세에도 민주주의 지지율 유지 → 수용자 회복력이 이론의 한계 조건"
rival_theories:
  - "Information Warfare (정보전) — 인지전은 정보전의 하위 범주 vs 독립 개념 논쟁"
  - "Propaganda Theory (Bernays) — 전통 선전과 본질적 차이 없음, 매체만 변화"
  - "Resilience Theory — 효과는 공격 강도가 아니라 표적 사회 회복력이 결정"
related:
  - "[[information_warfare]]"
  - "[[apt_attribution_theory]]"
  - "[[gray_zone_strategy]]"
---

## 핵심 주장

NATO가 2020년 공식화한 인지전(Cognitive Warfare) 개념은 전통 정보전을 초월한다:

> "인지전의 표적은 정보가 아니라 **인간의 뇌** — 신념·행동·의사결정 자체를 조작한다."

### 5세대 전쟁의 맥락

| 세대 | 전쟁 유형 | 주요 수단 |
|------|---------|---------|
| 1G | 선형 전선 | 보병·기병 |
| 2G | 화력 우세 | 포병·참호 |
| 3G | 기동전 | 전차·공수 |
| 4G | 비대칭·게릴라 | 비국가 행위자 |
| **5G** | **인지전** | **내러티브·딥페이크·AI** |

### du Cluzel의 인지전 3개 전선

1. **물리 뇌 조작**: 수면 교란·전자기 자극·향정신성 물질 (극단 사례)
2. **디지털 뇌 조작**: 소셜미디어 알고리즘 활용 → 에코챔버·필터버블 강화
3. **문화적 내러티브 조작**: 역사 재해석·민족 정체성 침식 → 사회 결속 약화

### Singer의 현대 사례: 러시아 허위정보 생태계

'Firehose of Falsehood' 전략:
- 대량 허위 정보 동시 발사 → 팩트체크 압도
- 상호 모순된 내용도 동시 유포 → 진실 자체에 대한 불신 조장
- 목표: 특정 허위 믿게 만들기 X → **아무것도 믿지 못하게 만들기** ✓

## 현재 사례 연결

- **우크라이나전 전후 내러티브**: "나치 정권 제거", "NATO 도발론" → 글로벌 사우스 중립화 시도
- **대만 선거 개입 (2024)**: 중국발 딥페이크·가짜 여론조사로 친중 후보 지지 유도 시도
- **이란전 사이버전 (2026)**: 사이버 공격 + 내러티브 전쟁 동시 수행 → 서방 여론 분열 공략

## 주요 학자 및 저작

- du Cluzel, F. (2020). *Cognitive Warfare*. NATO ACT Innovation Hub.
- Singer, P.W. & Brooking, E.T. (2018). *LikeWar: The Weaponization of Social Media*. Houghton Mifflin.
- Paul, C. & Matthews, M. (2016). "The Russian 'Firehose of Falsehood' Propaganda Model." *RAND PE-198*.
- Rid, T. (2020). *Active Measures: The Secret History of Disinformation and Political Warfare*. Farrar, Straus and Giroux.

## 이론의 한계

- 인과성 측정 어려움: 인지전 노출 → 태도 변화 경로의 인과 확인 불가 (다른 변수 통제 불가)
- 역효과(Backfire Effect): 가짜 정보 폭로 시 오히려 믿음 강화되는 심리 현상
- 민주주의 체제의 자유 언론이 방패인 동시에 취약점 (허위정보가 자유롭게 유통)

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 선거 개입 탐지 (허위정보 캠페인) | 사이버 방산·보안주 급등 | (신규 후보) |
| 대만 관련 딥페이크 유포 | 대만해협 긴장 → TSM 하락 | `taiwan_strait_to_tsm` |
