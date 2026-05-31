---
asset_type: case_study
title: "사례: 2022 펠로시 대만 방문 (Pelosi Taiwan Visit)"
theory_id: case_pelosi_taiwan_2022
sector_tag: indo_pacific
summary: 낸시 펠로시 미 하원의장 대만 방문(2022-08-02)으로 대만해협 긴장 최고조. TSMC 주가 하락(D1 발화), 그러나 D2 미발화 — "buy-the-dip" 현상이 체인 한계를 보여준다.
geopol_region: taiwan_strait
temporal_era: us_china_rivalry
level_of_analysis: state_domestic
instrument_of_power: diplomatic
strategic_posture: revisionist
theorists:
- Nancy Pelosi (행위자)
- PLA Eastern Theater Command
- TSMC
theory_id: case_pelosi_taiwan_2022
year: 2022
regions:
- taiwan_strait
- south_china_sea
---

## 사건 개요

2022년 8월 2~3일, 낸시 펠로시 미 하원의장이 대만을 방문했다.
25년 만의 미국 최고위급 대만 방문으로, 중국은 즉각 **대만 봉쇄 모의 훈련**을 포함한
군사훈련(8월 4~7일)으로 대응했다. PLA 미사일 5발이 일본 EEZ 안에 낙탄해
일본의 동맹 딜레마를 자극했다.

## 지정학적 해석

**Weaponized Interdependence (Farrell & Newman 2019)**:
대만 방문 직후 반도체 공급망 리스크가 시장에 즉각 반영됐다. TSMC는 단순 기업이 아니라
미-중 전략 경쟁의 **지정학적 인질**이다.

**Alliance Theory (Snyder 1984)**:
일본의 딜레마가 극명하게 드러났다. 미군 기지가 있는 오키나와에서 PLA 미사일 낙탄 →
일본이 연루되기를 원하는가? → **연루-방기 딜레마의 실시간 시험**.

## Cascade 연결 — 실증 데이터

| 룰 ID | 예측 | 실측 (72h) | 발화 |
|--------|------|-----------|------|
| `taiwan_strait_to_tsm` | TSM↓1% | **TSM -2.45%** | ✅ D1 발화 |
| `semiconductor_supply_risk_to_sector_decline` | SOXX↓ | **SOXX +0.19%** (buy-the-dip) | ❌ D2 미발화 |

**핵심 학습**: D1은 발화했지만 D2가 발화하지 않았다. 이유는?
투자자들이 **"방문 = 전쟁 아님"** 으로 빠르게 재평가했기 때문이다.
일회성 정치 이벤트는 공급망 구조 변화가 아니므로 섹터 전반 충격으로 이어지지 않았다.

## 비교 학습: Joint Sword 2023과의 차이

| 항목 | 펠로시 2022 | Joint Sword 2023 |
|------|------------|-----------------|
| 성격 | 외교 충격 | 지속 군사 압박 |
| D1 (TSM) | -2.45% ✅ | -2.14% ✅ |
| D2 (SOXX) | +0.19% ❌ | -0.52% ✅ |
| D3 (ITA) | — | +2.16% ✅ |
| 해석 | 시장이 정치 이벤트를 할인 | 군사 에스컬레이션은 섹터 전파 |

**학습 포인트**: Cascade 엔진의 "window_hours"가 왜 중요한지를 보여주는 사례.
단기 충격 vs 지속 압박의 시장 반응 패턴 차이.

## 지도에서 확인하기

- **분쟁 레이어**: 2022-08 대만 주변 ACLED 이벤트 밀도 확인
- **AIS 레이어**: 방문 직후 대만해협 상선 항로 변화
- **Cascade 레이어**: `taiwan_strait_to_tsm` D1 링크

## 참고 자료

- Sanger, D. (2022). "Pelosi Arrives in Taiwan." *NYT* 2022-08-02.
- CSIS (2022). "China's Response to Pelosi Taiwan Visit." China Power Blog.
- 실증 데이터: yfinance TSM 2022-08-01~08-05
