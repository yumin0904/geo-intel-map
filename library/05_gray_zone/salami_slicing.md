---
asset_type: theory
era: multipolar
geopol_region: south_china_sea
instrument_of_power: military
level_of_analysis: state_domestic
regions:
- south_china_sea
- east_china_sea
- taiwan_strait
- bab_el_mandeb
sector_tag: gray_zone
strategic_posture: revisionist
summary: 경쟁자의 개별 대응 임계치 아래에서 점진적이고 가역적인 소규모 조치를 반복해 전략적 목표를 달성한다. 각 단계는 전쟁 빌미가 되기에 너무 작지만, 누적 효과는 현상 변경을 완성한다.
temporal_era: us_china_rivalry
theorists:
- Oriana Skylar Mastro
- M. Taylor Fravel
- Robert Haddick
theory_id: gray_zone_salami_slicing
title: 살라미 전술 / 점진적 현상 변경 (Salami Slicing Strategy)
year: 2014
independent_var: "개별 조치의 자극 수준 (에스컬레이션 임계 대비 %, ACLED 강도 0~100)"
dependent_var: "누적 영토·행동 변화량 (점유 지역·기지화 면적 증가, CSIS AMTI 데이터)"
conditions:
  - "각 조치가 대응 임계(escalation threshold) 아래 설계"
  - "행위자의 현상 변경 의지와 시간 인내 (장기 전략 필요)"
  - "경쟁자의 개별 조치에 대한 대응 비용이 수용 비용 초과"
falsifiable_prediction: "개별 조치 강도가 낮을수록(임계 50% 이하) 경쟁자 군사 대응 확률 감소 + 누적 점유 면적 증가 (통제: 국내 정치·동맹 압박)"
known_counterexample: "중국 남중국해 인공섬(2013~2015): 미국이 FONOP으로 대응했으나 점유 역전 실패 — 살라미 전술이 FONOP으로 저지되지 않음을 역설적으로 확인; 러시아 크림(2014): 신속한 점령(최초 1주) → 살라미보다 기습에 가까워 순수 살라미 이론 적용 한계"
rival_theories:
  - "Gray Zone Strategy (Mazarr) — 살라미는 회색지대 전략의 하위 전술"
  - "Coercive Diplomacy (Schelling) — 가시적 위협이 점진적 침식보다 효과적 강압"
  - "FONOP / Sea Control — 항행의 자유로 살라미를 역전 가능 (논쟁)"
related:
  - "[[gray_zone_strategy]]"
  - "[[fonop]]"
  - "[[lawfare]]"
---

## 핵심 주장

살라미 전술의 핵심은 **인식의 분절화(perception fragmentation)** 다:

> "상대가 각 행동을 개별적으로 평가하는 한, 전체 전략의 누적 효과를 보지 못한다."

### 남중국해 적용 (Fravel, Mastro)

중국의 남중국해 점진적 기지화 5단계:
1. 어민 보호 명목 초계 강화
2. 저조지(low-tide elevation) 임시 구조물 설치
3. 인공섬 토대 건설 (준설)
4. 활주로·레이더 시설 설치
5. 방공미사일·대함미사일 배치

각 단계에서 미국·ASEAN의 군사 대응 임계를 밑돌면서 기정 사실화(fait accompli).

### Fait Accompli (기정 사실화)

살라미의 최종 형태 — 점령 완료 후 상대가 현상 회복 비용 > 수용 비용 인식:
- 크림반도(2014): 24시간 내 점령 완료 → NATO 군사 반격 비용 현실화 불가
- 남중국해 인공섬: 이미 군사 기지화 완료 → 미국이 역파괴하려면 전쟁 필요

### Haddick의 '작은 막대기 정책' 비판

미국의 점진적 대응(경고·성명·FONOP)이 살라미를 저지 못하는 이유:
- 각 미국 대응도 임계 아래 → 억지 신호 모호
- 해결책: 비대칭 대응(살라미 1단계에 과잉 대응) — 그러나 에스컬레이션 위험

## 현재 사례 연결

- **대만 ADIZ 침범**: 중국의 일상화된 군용기 침범 → 개별 1건은 전쟁 빌미 불가, 누적으로 ADIZ 무력화
- **동중국해 센카쿠**: 중국 해경 순시선 정례화 → 일본의 대응 비용 누적
- **후티 홍해 공격**: 개별 공격은 전면전 아니지만 누적으로 홍해 항행 봉쇄 효과

## 주요 학자 및 저작

- Mastro, O.S. (2017). "Why Chinese Assertiveness Is Here to Stay." *Washington Quarterly*, 38(4).
- Fravel, M.T. (2011). "China's Strategy in the South China Sea." *Contemporary Southeast Asia*, 33(3).
- Haddick, R. (2014). *Fire on the Water: China, America, and the Future of the Pacific*. Naval Institute Press.
- Mazarr, M. (2015). "Mastering the Gray Zone." *U.S. Army War College Strategic Studies Institute*.

## 이론의 한계

- "임계치 아래" 설계가 실패하면 기대치 않은 에스컬레이션 발생 가능
- 저항하는 쪽의 임계치가 시간에 따라 하락 — "레드라인 피로" 역전 가능
- 민주주의 체제: 여론이 점진적 수용을 거부하면 정부 강경화 압박

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 중국 ADIZ 침범 빈도 급증 | 대만해협 긴장 → TSM 하락 | `taiwan_strait_to_tsm` |
| 남중국해 해경 활동 강화 | 방산 ETF 수혜 | `south_china_sea_to_defense` |
