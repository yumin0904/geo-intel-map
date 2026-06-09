---
asset_type: theory
era: cold_war
geopol_region: taiwan_strait
instrument_of_power: military
level_of_analysis: systemic
regions:
- taiwan_strait
- korean_peninsula
- east_china_sea
- eastern_europe
sector_tag: indo_pacific
strategic_posture: status_quo
summary: 방어 목적의 군사력 증강이 상대국 눈에 공격적으로 보여 군비 경쟁 나선을 유발한다. 의도의 불투명성과 공격-방어 구분 불가능성이 구조적 불안의 근원이다.
temporal_era: us_china_rivalry
theorists:
- Robert Jervis
- John Herz
- Charles Glaser
theory_id: indo_pacific_security_dilemma
title: 안보 딜레마 (Security Dilemma)
year: 1978
independent_var: "방어 목적 군비 증강 속도 (국방비 GDP% 연간 변화율, SIPRI)"
dependent_var: "경쟁국 방위비 대응 증가율 (군비 경쟁 나선 지수 — 전년도 대비 ΔmiIex)"
conditions:
  - "공격-방어 구분 불가능 (offensive-defensive indistinguishability)"
  - "의도 불투명 (상대 의도를 능력으로만 추론)"
  - "무정부 상태의 국제 체제"
falsifiable_prediction: "일국의 방위비 증가 시 주요 경쟁국의 방위비 12~24개월 내 증가 (통제: 경제성장률·국내정치 주기)"
known_counterexample: "탈냉전 단극 시기(1991~2000) 유럽 대규모 군비 감축 — 미국 압도적 우위로 균형화 인센티브 소멸, 안보딜레마 작동 정지; 노르웨이·스웨덴 — NATO 가입 전 비동맹 시기에도 군비 나선 미발생 (신뢰 구축 제도 효과)"
rival_theories:
  - "Balance of Threat Theory (Walt) — 힘 아닌 위협 인식이 군비 결정"
  - "Deterrence Theory — 군비 증강이 억지 효과로 안보 증진"
  - "Offensive Realism (Mearsheimer) — 나선이 아닌 패권 추구가 동기"
---

## 핵심 주장

Robert Jervis는 1978년 "국제정치에서 협력과 안보 딜레마"(Cooperation Under the Security Dilemma)에서 무정부 상태의 구조적 비극을 공식화했다.

### 안보 딜레마의 구조

국가 A가 방어 목적으로 군비를 증강하면:
1. 국가 B는 A의 의도를 알 수 없음
2. B는 최악 시나리오(A의 공격 의도) 가정 → 군비 대응
3. A는 B의 군비 증강을 위협으로 인식 → 추가 증강
4. **결과**: 양국 모두 더 위험해진 나선(Spiral)

### Jervis의 2×2 프레임워크

공격-방어 구분 가능성 × 방어 우위 여부로 안보딜레마 강도 결정:

| | 방어 우위 | 공격 우위 |
|---|---|---|
| **구분 가능** | 안보딜레마 약화 | 불안정하나 관리 가능 |
| **구분 불가** | 안보딜레마 심화 | 최악의 안보환경 |

### Glaser의 확장 (합리적 행위자 모델, 1997)

방어적 현실주의 관점에서 일부 군비 증강은 합리적이지만,
의도 신호(signaling)와 억제(restraint)를 통해 나선을 끊을 수 있다.

## 현재 사례 연결

- **중국 A2/AD 확장**: 중국은 "방어적 해군력"이라 주장, 미국은 공격적 역량으로 인식 → 전형적 안보딜레마
- **한반도 미사일 방어(THAAD)**: 미·한은 북한 방어용 주장, 중국은 레이더가 자국 타격 정보 수집 가능성 우려 → 공격-방어 구분 불가 사례
- **인도-태평양 해군 경쟁**: 미 해군 자유항행과 중국 해군 확장의 상호 군비 나선 — SIPRI 데이터로 계량 추적 가능

## 주요 학자 및 저작

- Jervis, R. (1978). "Cooperation Under the Security Dilemma." *World Politics*, 30(2), 167–214.
- Herz, J. (1950). "Idealist Internationalism and the Security Dilemma." *World Politics*, 2(2), 157–180.
- Glaser, C. (1997). "The Security Dilemma Revisited." *World Politics*, 50(1), 171–201.
- Glaser, C. (2010). *Rational Theory of International Politics*. Princeton University Press.

## 이론의 한계

- 순수 구조 설명 — 지도자 인식·국내 강경파·산업 이익 등 독립 변수 무시
- "방어적 의도"의 주관성: 의도 발신국이 방어적이라도 수신국 해석이 결정적
- 핵 억지가 작동하는 경우 나선 억제 효과 → 재래식 영역에서만 완전 적용

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 중국 국방비 GDP% 증가 (SIPRI) | 미·일 방위비 대응 증가 → 방위산업 수혜 | `south_china_sea_to_defense` |
| 대만해협 군사훈련 강도 상승 | TSMC 공급망 불안 → 반도체주 하락 | `taiwan_strait_to_tsm` |
