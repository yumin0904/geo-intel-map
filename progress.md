# 개발 진행 기록

## Phase 1 — MVP (완료)

### 완료된 레이어 (5/5)

| # | 레이어 | 파일 | 상태 |
|---|--------|------|------|
| 1 | 분쟁 이벤트 (ACLED) | `connectors/acled.py`, `ConflictEventsLayer.js` | ✅ |
| 2 | 군사기지 & 자산 | `MilitaryBasesLayer.js` | ✅ |
| 3 | 에너지 파이프라인 | `EnergyPipelinesLayer.js` | ✅ |
| 4 | 해상 초크포인트 | `ChokepointsLayer.js` | ✅ |
| 5 | 해저 광케이블 | `SubmarineCablesLayer.js` | ✅ |

### 주요 구현 내용
- ACLED API 연결 + Event 정규화 (`backend/connectors/acled.py`)
- 7일/30일 분쟁 이벤트 필터 토글 (789개 차이 확인)
- LayerManager + LayerPanel UI (토글 연동)
- 해저케이블 날짜변경선 수정 (태평양 경계 버그 해결)
- 마커 1,000+ 처리: MarkerCluster + Canvas 렌더링

---

## Phase 2 — 핵심 차별화 (진행 중)

### ✅ 첫 Cascade Rule 동작 (2026-05-21)

**바브엘만데브 긴장 → 유가** 인과 연쇄가 실제 데이터로 동작.
- 후티 공격(ACLED sev76, 2025-05-01) → WTI 원유(CL=F) +1.77% 실제 매칭
- 호르무즈 룰은 룰북에 유지(현재 강 안 고강도 분쟁 없어 0건, 해군 데이터 도입 시 자동 동작)

구현 파일:
- `backend/config/regions.yaml` + `services/region.py` — 좌표→region_code 판정
- `backend/models/cascade.py` — CascadeRule / CascadeLink
- `backend/config/cascade_rules.yaml` — 룰북 (bab_el_mandeb, hormuz)
- `backend/services/cascade/rule_loader.py` — YAML 로드+검증
- `backend/connectors/yfinance_adapter.py` — CL=F 유가 시계열 (yfinance)
- `backend/connectors/acled.py` — fetch()에 countries 옵션 추가 (걸프 조회)
- `backend/services/cascade/engine.py` — 룰 평가 엔진
- `backend/api/cascade.py` — `GET /api/cascade/links` (1시간 캐시)
- `frontend/src/layers/CascadeLayer.js` — 점선 화살표(원인→결과) + 이론 팝업

관련 이론: SLOC Interdiction(Mahan) / Resource Weaponization(Hirschman 1945)

✅ 시각 확인 완료 — 노랑 점선 화살표(weight 7.5px, 3배), 도착점 "유가 +1.77%" 레이블, 팝업 헤드라인 개선

### ✅ Cascade Rule Book 11개 확장 (2026-05-22)

| # | 룰 ID | 요약 | 상태 |
|---|-------|------|------|
| 1 | bab_el_mandeb_tension_to_oil | 바브엘만데브 → CL=F ↑ | ✅ 활성 (동작 확인) |
| 2 | hormuz_tension_to_oil | 호르무즈 → CL=F ↑ | ⏳ 해군 데이터 대기 |
| 3 | taiwan_strait_to_tsm | 대만해협 → TSM ↓ | ⏳ ADS-B 도입 시 활성 |
| 4 | taiwan_strait_to_soxx | 대만해협 → SOXX ↓ | ⏳ |
| 5 | south_china_sea_to_defense | 남중국해 → ITA ↑ | ⏳ |
| 6 | south_china_sea_to_lng | 남중국해 → NG=F ↑ | ⏳ |
| 7 | north_korea_missile_to_krw | 북한 도발 → KRW=X ↑ | ⏳ ACLED 북한 포함 시 |
| 8 | suez_tension_to_shipping | 수에즈 → ZIM ↑ | ⏳ |
| 9 | ukraine_conflict_to_wheat | 우크라이나 → ZW=F ↑ | ⏳ |
| 10 | middle_east_conflict_to_gold | 중동 → GLD ↑ | ⏳ |
| 11 | korean_tension_to_kospi | 한반도 → ^KS11 ↓ | ⏳ |

추가된 regions: `south_china_sea`, `north_korea`, `suez`, `ukraine`, `middle_east`, `korean_peninsula`
이론 커버리지: Weaponized Interdependence, A2/AD, Gray Zone, SLOC, Food Security, Safe Haven, Korea Discount

### ✅ Theory Panel 완성 (2026-05-22)

- `frontend/src/panels/TheoryPanel.js` 신규 — 이론 DB 14개 내장
- 마커 클릭 → 우측 슬라이드인 패널 (transition 0.25s)
- theory_tags 기반 이론 카드: 이론명·학자·한 줄 요약·설명·추천 자료 링크
- **좌표 기반 Cascade Rule 필터링**: 이벤트 좌표가 rule trigger region bbox 안에 있을 때만 표시
  - 미얀마 내전 → cascade rule 없음 ✓ (A2AD/대만해협 룰 오표시 수정)
  - 바브엘만데브 → `bab_el_mandeb_tension_to_oil` 자동 연결 ✓
- 실제 확인된 cascade 링크(CL=F +1.77%)는 ⛓ 배지로 표시
- MilitaryBasesLayer도 eventBus 연동 — 군사기지 마커 클릭 시 이론 패널 동작
- ESC / ✕ 버튼으로 닫기

### 🔜 다음 작업 (Phase 2)
- **TimelineView** — vis-timeline 기반 시간순 이벤트 배열
- **Study Mode** — 이론 태그 강조 + 노트 입력창 상시 표시
- 실시간 레이어 (ADS-B / AIS / FIRMS) — 대기 중인 룰들이 자동 활성화
- CascadeGraphView (Cytoscape) — 인과 그래프 뷰

---

## Phase 로드맵

- ✅ Phase 0: 기반 (FastAPI + Leaflet + 군사기지)
- ✅ Phase 1: MVP (5개 레이어 + LayerManager)
- 🔄 Phase 2: 핵심 차별화 — 첫 Cascade Rule 동작 ✅ / 실시간 레이어·룰 확장 진행 예정
- ⬜ Phase 3: 학습 도구 완성
