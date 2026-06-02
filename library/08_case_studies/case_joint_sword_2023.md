---
asset_type: case_study
title: "사례: 2023 Joint Sword 군사훈련 — 3단계 Cascade 전체 발화"
theory_id: case_joint_sword_2023
sector_tag: indo_pacific
summary: 2023년 4월 중국 PLA Joint Sword 훈련 — D1(TSM↓)→D2(SOXX↓)→D3(ITA↑) 3단계 체인 전체 발화 확인. Cascade 엔진 실증의 핵심 사례.
geopol_region: taiwan_strait
temporal_era: us_china_rivalry
level_of_analysis: state_domestic
instrument_of_power: military
strategic_posture: revisionist
theorists:
- PLA Eastern Theater Command
- Farrell & Newman
- Eisenhower (군산복합체)
theory_id: case_joint_sword_2023
year: 2023
regions:
- taiwan_strait
- south_china_sea
---

## 사건 개요

2023년 4월 5~10일, 중국 PLA는 **Joint Sword 합동군사훈련**을 실시했다.
대만 전역을 포위하는 방식으로 6개 해역에서 동시에 진행됐으며,
항모 산둥함, 구축함, 전략폭격기가 참가했다.
트리거: 차이잉원 대만 총통의 미국 경유 방문(케빈 매카시 하원의장 면담, 4-5).

## Cascade 3단계 완전 발화 — 실증 데이터

이 사건은 **Cascade 엔진 설계 타당성을 실증한 핵심 사례**다.

| 단계 | 룰 ID | 예측 | 실측 | 윈도우 |
|------|--------|------|------|--------|
| D1 | `taiwan_strait_to_tsm` | TSM↓1% | **TSM -2.14%** ✅ | 24h |
| D2 | `semiconductor_supply_risk_to_sector_decline` | SOXX↓ | **SOXX -0.52%** ✅ | 48h |
| D3 | `semiconductor_sector_decline_to_defense` | ITA↑ | **ITA +2.16%** ✅ | 168h (1주) |

**D3 발화 지연 이유**: 방산주(ITA)는 기술 공급망 위기 → 국방 자립 정책 기대로 이어지는
정책 형성 시간이 필요하다. 72h 이내 반응 없음 → 168h에 발화. window_hours=168h 설정의 근거.

## 지정학적 해석

**Weaponized Interdependence**: TSMC 개별주 하락(D1)이 섹터 전체(D2), 나아가
방산-기술주 재편(D3)으로 전파되는 전형적 **공급망 집중 취약성** 메커니즘.

**군산복합체 (Eisenhower 1961)**: D3(ITA↑)는 "반도체 위기 → 기술 자립 → 방산 수주 증가"
기대가 1주 내에 가격에 반영됐음을 보여준다. 위기가 방산업체의 기회가 되는 구조.

## 펠로시 2022와의 결정적 차이

2022 펠로시: D1 발화, D2 미발화 (buy-the-dip). 이유: **일회성 외교 이벤트**.
2023 Joint Sword: D1→D2→D3 전체 발화. 이유: **지속적 군사 에스컬레이션**.

시장은 "방문 같은 외교 이벤트"와 "실제 군사 포위 훈련"을 다르게 평가한다.
이것이 Cascade 룰의 `severity_min` 파라미터가 존재하는 이유다.

## Cascade 연결 포인트

- `taiwan_strait_to_tsm` → `semiconductor_supply_risk`
- `semiconductor_supply_risk_to_sector_decline` → `semiconductor_sector_decline`
- `semiconductor_sector_decline_to_defense` → `us_defense_response` (체인 종점)
- **병렬 발화**: `semiconductor_sector_decline_to_qqq_drop` → `tech_sector_selloff`

## 지도에서 확인하기

- **ADS-B 레이어**: 2023-04 대만 주변 군용기 밀도 급증
- **Cascade 그래프**: 3단계 노드 트리 (황금→갈색→진갈색)
- **분석실 (SandboxLab)**: `2023 Joint Sword` 가설 검증 실행

## 참고 자료

- Reuters (2023). "China launches military exercises around Taiwan." 2023-04-08.
- CSIS (2023). "Joint Sword: China's Coercive Signal." China Power Blog.
- 실증 데이터: yfinance TSM/SOXX/ITA 2023-04-05~04-12 (v3.15.3 검증)
