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
| 5 | south_china_sea_to_defense | 남중국해 → ITA ↑ | ✅ 활성 (2026-05-22) |
| 6 | south_china_sea_to_lng | 남중국해 → NG=F ↑ | ✅ 활성 (2026-05-22) |
| 7 | north_korea_missile_to_krw | 북한 도발 → KRW=X ↑ | ❌ ACLED 북한 데이터 희박 |
| 8 | suez_tension_to_shipping | 수에즈 → ZIM ↑ | ✅ 활성 (2026-05-22) |
| 9 | ukraine_conflict_to_wheat | 우크라이나 → ZW=F ↑ | ✅ 활성 (2026-05-22) |
| 10 | middle_east_conflict_to_gold | 중동 → GLD ↑ | ✅ 활성 (2026-05-22) |
| 11 | korean_tension_to_kospi | 한반도 → ^KS11 ↓ | ❌ ACLED sev<40 (시위 위주) |

추가된 regions: `south_china_sea`, `north_korea`, `suez`, `ukraine`, `middle_east`, `korean_peninsula`
이론 커버리지: Weaponized Interdependence, A2/AD, Gray Zone, SLOC, Food Security, Safe Haven, Korea Discount

### ✅ 2번째 Cascade Rule 동작 — ukraine_conflict_to_wheat (2026-05-22)

**우크라이나 분쟁 → 밀 선물(ZW=F) 상승** 인과 연쇄 3개 링크 생성.

| trigger 날짜 | sev | ZW=F 반응 | score |
|---|---|---|---|
| 2025-04-30 | 100 | +1.88% | 0.63 |
| 2025-05-01 | 70  | +2.63% | 0.88 |
| 2025-05-02 | 70  | +2.18% | 0.73 |

진단·수정 내용:
- 원인 ①: `_TRIGGER_COUNTRIES`에 ukraine 키 없어 ACLED 조회 건너뜀
- 원인 ②: severity 상위 8개(4/22~25)가 ZW=F 무반응 기간에 집중
- 수정: ukraine 매핑 추가 + 평가 전략 → 날짜별 최고심각도 1개 샘플링
  (`_MAX_TRIGGERS_PER_RULE`: 8→15, 30일 창 균일 탐색)

관련 이론: Food Security as Geopolitical Weapon (Patel & Moore 2009)

### ✅ _TRIGGER_COUNTRIES 전수 점검 + 신규 3개 룰 활성화 (2026-05-22)

전수 진단 결과 (11개 룰):

| region | ACLED 30일 | bbox 내 | sev≥60 | 결론 |
|---|---|---|---|---|
| bab_el_mandeb | 1453 | 652 | 179 | ✅ 이미 활성 |
| ukraine | 1500 | 1500 | 1462 | ✅ 이미 활성 |
| middle_east | 1500 | 1062 | 294 | ✅ 신규 활성 |
| south_china_sea | 338 | 69 | 5 | ✅ 신규 활성 (sev≥40 기준) |
| suez | 199 | 9 | 1 | ✅ 신규 활성 |
| hormuz | 1500 | 17 | 0 | ❌ bbox 내 고강도 분쟁 없음 |
| taiwan_strait | 265 | 93 | 0 | ❌ 군사 도발만, ACLED 전투 없음 |
| north_korea | 11 | 11 | 0 | ❌ 데이터 극도 희박 |
| korean_peninsula | 607 | 354 | 0 | ❌ 남한 시위 위주 (sev≤20) |

**전체 Cascade 링크: 24개 (6개 룰 활성)**

acled.py: `MIDDLE_EAST_COUNTRIES`, `SOUTH_CHINA_SEA_COUNTRIES`, `SUEZ_COUNTRIES` 상수 추가  
engine.py: 신규 3개 region 매핑 + 비활성 region 사유 주석

비활성 3개 판단: 버그 아님, 데이터 소스 한계
- `hormuz` — ACLED bbox 내 고강도 분쟁 없음 → AIS 도입 시 자동 동작
- `taiwan_strait` — 군사 도발은 ACLED에 전투 이벤트 없음 → ADS-B 도입 시 자동 동작
- `north_korea` — ACLED 데이터 극도 희박(11건, sev<40) → Phase 3 NCNK 데이터 도입 시 활성화

### ✅ Cascade Engine 단계별 Trace (2026-05-22)

`bab_el_mandeb_tension_to_oil` 룰에 후티 공격 이벤트가 통과하는 5단계 게이트 확인:
1. source_type == "conflict" 체크
2. `_TRIGGER_COUNTRIES["bab_el_mandeb"]` → Yemen·Djibouti·Eritrea ACLED 조회
3. `region_for_point(lat, lon)` 지오펜스 통과
4. severity >= 60 임계치
5. `evaluate_response()` — 48h 내 CL=F 1.5% 이상 상승 → `CascadeLink` 생성

correlation_score 계산식: `min(1.0, abs(pct_change) / (threshold_pct × 2))`  
(임계치 정확히 맞으면 0.5, 2배 변동 시 1.0)

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

### ✅ TimelineView 완성 + Cascade 24개 링크 복구 (2026-05-22)

**문제**: TimelineView에 1개 링크만 표시됨 (24개 예상).

**원인 진단**:
- `build_cascade()`가 룰당 개별 ACLED HTTP 호출 → 6회 중 1회만 성공(rate-limit 추정)
- south_china_sea_to_defense + south_china_sea_to_lng가 동일 국가셋으로 2회 호출
- 서버 캐시(1h)가 1개 링크 결과를 고정시켜 TimelineView에 반영됨

**수정 내용** (`backend/services/cascade/engine.py`):
- `_fetch_conflict_triggers(rule)` → `_fetch_region_events(region)` + `_sample_triggers(events, sev_min)` 분리
- `build_cascade()`: unique region 추출 → `asyncio.gather()` 병렬 fetch → 룰별 재사용
- ACLED HTTP 호출: 6회 → 5회 (unique region 수 기준)
- 서버 재시작 후 API 24개 링크 정상 반환 확인

**TimelineView 현황**:
- 6개 룰 × 시간순 range 바 (시작=trigger, 끝=response)
- 그룹별 표시 (rule_id 기준), ticker + 등락률 + 상관도 레이블
- 아이템 클릭 → TheoryPanel 연동 (trigger 이벤트의 theory_tags 기반)

### ✅ TimelineView UI 개선 (2026-05-22)

- 패널 높이: 고정 216px → **30vh** (화면 비례)
- **드래그 리사이즈**: 패널 상단 핸들(6px)로 높이 자유 조절, 닫기/열기 시 복원
- **날짜 이동 툴바**: 년/월/일 select + "이동" 버튼 → `moveTo()` 애니메이션
- **아이템 클릭 → 날짜 이동**: 선택한 링크의 trigger 날짜 중앙으로 자동 이동
- **"📅 데이터 보기" 버튼**: 전체 링크 구간으로 `fit()` (애니메이션 400ms)
- 그룹 영역 `overflow-y: auto` 적용
- `_OVERHEAD = 72` 상수로 header+toolbar 높이 일원화

구현 파일: `frontend/src/views/TimelineView.js`, `frontend/styles/main.css`, `frontend/index.html`

### ✅ theory_tags 다차원 분류 로직 구현 (2026-05-22)

**문제**: 미얀마 ACDF 매복 사건에 `conventional_warfare + A2AD` 오배정.

**원인**: `_THEORY_TAGS["Battles"]` = event_type만으로 배정 → 지역·행위자 무관.

**수정** (`backend/connectors/acled.py`):
- `_THEORY_TAGS` dict 제거 → `_build_theory_tags(event_type, sub_event_type, inter1, inter2, region_code)` 함수
- inter1/inter2: ACLED API가 문자열로 반환("External/Other forces") → `_INTER_CODE` + `_inter_code()` 로 정수 변환 (대소문자 무관)
- `region_for_point()` import: normalize 시점에 region_code 즉시 결정 + Event에 저장

**배정 기준 (3계층)**:

| 계층 | 조건 | 태그 |
|------|------|------|
| inter1/inter2 | 1 vs 1 (국가군) | `conventional_warfare` |
| inter1/inter2 | 1 vs 2 또는 2 vs 1 | `insurgency, asymmetric_warfare` |
| inter1/inter2 | 2 vs 2 (반군) | `civil_war` |
| sub_event_type | "Ambush" | `guerrilla_tactics` |
| sub_event_type | "Air/drone strike" + inter1=2 | `gray_zone` |
| sub_event_type | shelling/artillery/missile | `conventional_warfare` |
| region | taiwan_strait, south_china_sea | `A2AD` |
| region | bab_el_mandeb, suez, hormuz | `SLOC_disruption` |
| region | hormuz | `resource_weaponization` |

**Myanmar ACDF 사건 before/after** (inter1=2, sub="Ambush"):
- BEFORE: `['conventional_warfare']`
- AFTER (vs 군부 inter2=1): `['asymmetric_warfare', 'guerrilla_tactics', 'insurgency']`
- AFTER (vs 반군  inter2=2): `['civil_war', 'guerrilla_tactics']`

### ✅ Study Mode 1단계 — 이론 태그 뱃지 토글 (2026-05-22)

- 좌측 사이드바 하단 `STUDY MODE` 버튼 추가 (`LayerPanel.js`)
- 클릭 시 `body.study-mode` CSS 클래스 토글 → 마커 재렌더링 없이 뱃지 표시/숨김
- 분쟁 이벤트 마커 DivIcon에 `.conflict-tags` 포함 (`buildIcon` 확장)
- `body.study-mode .conflict-tags { display: flex }` CSS로 on/off 처리

구현 파일: `frontend/src/layers/ConflictEventsLayer.js`, `frontend/src/panels/LayerPanel.js`, `frontend/styles/main.css`

---

### 🔜 다음 작업 (Phase 2)

**대기 중**:
- 실시간 레이어 (ADS-B / AIS / FIRMS) — 대기 중인 룰들이 자동 활성화
- CascadeGraphView (Cytoscape) — 인과 그래프 뷰
- Study Mode 2단계 — 노트 입력창 상시 표시

**Phase 3 예정**:
- **GDELT 실시간 데이터 파이프라인 (3단계 교차 검증)**

  배경: ACLED 데이터 한계(2025년 5월까지) 보완, 실시간성 확보하되 노이즈 필터링 필수

  아키텍처 (3-Stage Funnel):
  1. GDELT 자체 필터링 (QuadClass 3/4, GoldsteinScale ≤-5, NumMentions ≥20)
  2. 외부 뉴스 RSS/NewsAPI 교차 검증 (24h 내 2개 이상 매체)
  3. confidence_score 산출 (0.0~1.0)

  데이터 모델 변경:
  - Event 모델에 `confidence_score`, `is_verified` 필드 추가
  - ACLED=1.0, 미검증 GDELT=0.5, 교차검증 GDELT=0.8

  신규 모듈:
  - `backend/connectors/gdelt_verifier.py`
  - `backend/connectors/news_cross_validator.py`

  프론트엔드:
  - `confidence_score < 0.8` → 점선 테두리, 60% 투명도
  - "⚠️ 실시간 속보 (교차 검증 중)" 뱃지

  착수 조건 (게이트):
  - Phase 2 완료 후
  - 실시간 레이어 (ADS-B/AIS/FIRMS) 구현 이후
  - 시스템 프롬프트 Phase 2 11번(시장 지표) 다음 우선순위

  알려진 리스크:
  - GDELT 좌표 부정확성 → cascade region 매칭 false positive 우려
  - NewsAPI 무료 티어 일 100건 제한
  - Event 모델 변경 시 cascade engine/frontend 광범위 영향

---

## Phase 로드맵

- ✅ Phase 0: 기반 (FastAPI + Leaflet + 군사기지)
- ✅ Phase 1: MVP (5개 레이어 + LayerManager)
- 🔄 Phase 2: 핵심 차별화 — 첫 Cascade Rule 동작 ✅ / 실시간 레이어·룰 확장 진행 예정
- ⬜ Phase 3: 학습 도구 완성
