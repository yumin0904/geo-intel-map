---
asset_type: theory
era: multipolar
geopol_region: south_china_sea
instrument_of_power: diplomatic
level_of_analysis: state_domestic
regions:
- south_china_sea
- east_china_sea
- taiwan_strait
- hormuz
sector_tag: gray_zone
strategic_posture: revisionist
summary: 법적 주장·국제법·사법 절차를 군사 대안으로 활용해 전략적 목표를 달성한다. 적의 법적 취약성 공략, 아군의 행동 합법화, 국제 여론 조작을 동시에 수행한다.
temporal_era: us_china_rivalry
theorists:
- Charles Dunlap Jr.
- Orde Kittrie
- Jerome Cohen
theory_id: gray_zone_lawfare
title: 법전쟁 (Lawfare)
year: 2001
independent_var: "국제법적 주장의 강도·범위 (UNCLOS·ICJ 청구 건수, 역사적 권원 주장 명시도)"
dependent_var: "경쟁자의 물리 행동 제약 효과 (FONOP 빈도 변화·점유 지역 역전 성공률)"
conditions:
  - "국제 규범·제도에 대한 경쟁자의 의존도 (평판 비용 취약)"
  - "자국의 법적 주장에 대한 국내·국제 청중 지지 가능성"
  - "직접 군사 대결 비용이 법적 경쟁 비용 초과"
falsifiable_prediction: "국제법정 청구 승소 시 피청구국의 해당 행동 제약 강화 (통제: 집행 메커니즘 존재 여부)"
known_counterexample: "2016년 상설중재재판소(PCA) 남중국해 판결: 필리핀 승소, 중국 9단선 불법 확인 → 중국이 판결 무시, 점유 계속 — 법적 승리가 물리적 현상 변경 역전 실패 실증; 이란 ICJ 제소: 미국 제재 위법 결정에도 미국 미준수"
rival_theories:
  - "Sea Control (실효 지배가 법적 주장보다 우선)"
  - "FONOP — 항행의 자유 실증으로 법적 주장에 물리적 반박"
  - "Salami Slicing — 법적 주장과 병행되는 물리적 점진 침식"
related:
  - "[[fonop]]"
  - "[[gray_zone_strategy]]"
  - "[[salami_slicing]]"
---

## 핵심 주장

Dunlap(2001)은 **법전쟁(Lawfare)** 을 "법을 군사 목표 달성의 무기로 사용하는 것"으로 정의했다.

### Lawfare의 3개 공격 벡터

**1. 적의 행동 제약**
적이 법적 제약(IHL·UNCLOS·ROE) 때문에 군사 행동을 자제하도록 강제.  
→ 민간인 방패 전술: 적의 공격이 법적·여론적 비용을 초래하게 만듦

**2. 아군 행동 합법화**
자국 행동을 역사적 권원·기존 조약·자위권 조항으로 정당화.  
→ 중국 9단선: 역사적 관행 + 내부해(internal waters) 주장으로 UNCLOS 우회

**3. 국제 여론·제도 조작**
국제 포럼·언론을 통해 법적 정당성 경쟁 → 제3국의 지지 확보.  
→ 러시아 "나토 확장은 협정 위반" 주장: 법적 근거 약하나 글로벌 사우스 일부 설득

### Kittrie의 '공세적 법전쟁' 개념

공세적 lawfare = 법을 선제적으로 활용해 경쟁자에게 법적 딜레마 생성:
- 남중국해 역사적 권원 주장 → UNCLOS 비참여국(미국) 상대로 법적 우위 주장
- 화웨이·TikTok 사안: 중국이 WTO 분쟁 제소로 미국 기술 통제에 반격

## 현재 사례 연결

- **남중국해 PCA 판결(2016)**: 법적 승리가 물리적 현상 변경에 무력함을 실증 — lawfare 한계 확인
- **이란 핵 협정 해석 분쟁**: JCPOA 탈퇴 후 양측 모두 법적 준수 주장 → 법적 프레이밍 경쟁
- **대만 FONOP vs 중국 직선 기선**: 미국은 UNCLOS 기준 항행의 자유 주장, 중국은 중국 내해 주장 → 법적 프레임 전쟁

## 주요 학자 및 저작

- Dunlap, C.J. (2001). "Law and Military Interventions." *Harvard Kennedy School Working Paper*.
- Kittrie, O. (2016). *Lawfare: Law as a Weapon of War*. Oxford University Press.
- Cohen, J. (2012). "China's 'Lawfare' in the South China Sea." *Asia Policy*, 13.
- Schmitt, M. (ed.) (2013). *Tallinn Manual on the International Law Applicable to Cyber Warfare*. Cambridge UP.

## 이론의 한계

- 국제법 집행 메커니즘 부재: 판결을 무시해도 제재 수단 제한적
- 국내 정치가 법적 준수를 override — 여론·국익이 판결보다 우선
- 법전쟁 과용 시 법적 정당성 자체의 신뢰성 훼손 (법률 무기화의 역설)

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID 후보 |
|---|---|---|
| 남중국해 국제 중재 판결 | 중국 군사 강경화 → 방산 ETF 수혜 | `south_china_sea_to_defense` |
| 미국 기술 수출통제 WTO 제소 | 반도체 공급 불확실성 → TSM 변동 | `taiwan_strait_to_tsm` |
