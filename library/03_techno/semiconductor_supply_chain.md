---
theory_id: techno_semiconductor_supply_chain
title: "반도체 공급망 집중 리스크 (TSMC 딜레마)"
sector_tag: techno
theorists:
  - Chris Miller
  - Henry Farrell
  - Abraham Newman
year: 2022
summary: "첨단 반도체 생산이 대만(TSMC)에 극도로 집중되어, 대만해협 위기 시 글로벌 기술·경제 충격이 불가피한 구조적 취약성. 지정학과 기술 공급망의 교차점."
regions:
  - taiwan_strait
  - south_china_sea
---

## 핵심 주장

Chris Miller의 2022년 저작 *Chip War*는
현대 지정학에서 반도체가 석유를 대체하는 전략 자원이 되었음을 논증했다.

**TSMC 딜레마의 구조**:
- TSMC(대만적체전로제조)는 세계 최첨단 파운드리 칩(5nm 이하)의 **90% 이상**을 생산
- 애플·AMD·엔비디아·퀄컴이 모두 TSMC 의존
- 군사 무기체계(F-35, 구축함 AEGIS, 핵잠수함 제어계)에도 TSMC 칩 사용
- 대만해협 분쟁 시 생산 중단 → 글로벌 GDP 수조 달러 손실 추정

**Farrell & Newman의 "무기화된 상호의존"** 관점에서:
- 반도체 생산 네트워크의 허브(TSMC, ASML, 삼성)를 장악한 국가는
  해당 네트워크를 통해 정보를 수집하거나 접근을 차단하는 레버리지를 획득한다

## 현대 지정학과의 연결

### 미국의 CHIPS Act (2022)
반도체 공급망의 대만 집중이 전략적 취약점임을 인식한 미국이
520억 달러를 투입해 인텔(오하이오)·TSMC(애리조나)·삼성(텍사스) 국내 팹 유치.
그러나 최첨단 공정 재현에는 10년 이상이 필요하다는 것이 전문가 중론이다.

### 중국의 반도체 굴기와 SMIC
중국은 SMIC를 통해 자체 파운드리 역량 구축을 시도하지만
ASML의 EUV 장비 수출 금지(미국 압박)로 7nm 이하 공정 진입이 차단된 상태다.
이것이 대만 침공의 경제적 동기 중 하나로 거론된다.

### 대만해협 위기와 시장 반응
PLA의 대만 주변 군사훈련(예: 2022년 펠로시 방문 직후 훈련)이 발생할 때마다
TSM(TSMC ADR) 주가와 반도체 ETF(SOXX)가 즉각 하락한다.
시장이 지정학 리스크를 반도체 공급 충격으로 실시간 반영하는 메커니즘이다.

## Cascade 연결 포인트

| 트리거 이벤트 | 연쇄 반응 | 관련 룰 ID |
|---|---|---|
| 대만해협 PLA 군용기 활동 (severity ≥ 50) | TSM 주가 하락 | `taiwan_strait_to_tsm` |
| 남중국해 군사훈련 | 반도체 공급망 불안 → 방위산업 ETF 상승 | `south_china_sea_to_defense` |

## 학습 노트

> "반도체는 21세기의 석유다. 차이점은, 석유 없으면 차가 멈추지만
> 반도체 없으면 현대 문명 자체가 멈춘다."
> — Chris Miller, *Chip War* (2022)

지도에서 ADS-B 레이어를 켜고 대만 주변 군용기를 실시간으로 보라.
RC-135 정찰기, P-8A 해상초계기, U-2 고공정찰기가 얼마나 자주 순찰하는지 확인하라.
그 비행 패턴 하나하나가 "TSMC를 둘러싼 전략적 긴장"의 공간적 표현이다.

## 참고 자료

- Miller, C. (2022). *Chip War: The Fight for the World's Most Critical Technology*. Scribner.
- Farrell, H. & Newman, A. (2019). "Weaponized Interdependence." *International Security*, 44(1).
- CSIS (2023). "Semiconductors and National Security." Center for Strategic and International Studies.
- 정인교 (2023). "반도체 공급망 재편과 한국의 전략." KIEP 연구보고서.
