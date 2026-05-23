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

### ✅ Study Mode 2단계 — 노트 입력창 (2026-05-22)

- Study Mode 켜지면 TheoryPanel 하단에 노트 입력창 슬라이드인
- 이벤트 id(UUID) 기준 SQLite 자동 저장 (1초 debounce), "저장됨 ✓" 피드백
- Study Mode 꺼지면 CSS `display:none` 토글 (재렌더링 없음)
- 기존 저장된 노트는 패널 열 때 자동 불러오기

구현 파일:
- `backend/api/study.py` — `GET/PUT /api/study/notes/{event_id}`, SQLite upsert
- `backend/db/study.db` — 자동 생성 (notes 테이블)
- `frontend/src/panels/NotebookPanel.js` — 노트 UI + fetch 저장
- `frontend/src/panels/TheoryPanel.js` — `setNotebook()` + `.notebook-slot` 삽입
- `frontend/index.html` — NotebookPanel import + wire-up
- `frontend/styles/main.css` — `.notebook` 스타일 + Study Mode CSS 토글

### ✅ Study Mode 1단계 — 이론 태그 뱃지 토글 (2026-05-22)

- 좌측 사이드바 하단 `STUDY MODE` 버튼 추가 (`LayerPanel.js`)
- 클릭 시 `body.study-mode` CSS 클래스 토글 → 마커 재렌더링 없이 뱃지 표시/숨김
- 분쟁 이벤트 마커 DivIcon에 `.conflict-tags` 포함 (`buildIcon` 확장)
- `body.study-mode .conflict-tags { display: flex }` CSS로 on/off 처리

구현 파일: `frontend/src/layers/ConflictEventsLayer.js`, `frontend/src/panels/LayerPanel.js`, `frontend/styles/main.css`

---

### ✅ CascadeGraphView (Cytoscape.js) — 인과 그래프 뷰 (2026-05-23)

- `frontend/src/views/CascadeGraphView.js` 신규 — 집계 양분 그래프(region→ticker)
- Cytoscape.js `breadthfirst directed` 레이아웃 — 원인(좌) → 결과(우) 배치
- 17개 elements: 분쟁 지역 5개(타원·빨강) + 시장 지표 6개(다이아몬드·황금) + 엣지 6개
- `cascade:loaded` EventBus 재사용 (API 이중 호출 없음)
- 분쟁 마커 클릭 → 해당 region 노드 하이라이트 + 패널 자동 열기
- **전체화면 토글** (⛶/✕): `100vw×100vh`, z-index 9999, setTimeout 300ms 1회 fit()
- **전체화면 내부 이론 패널** (70% 그래프 + 30% 이론): Cytoscape 노드 클릭 시
  글로벌 TheoryPanel 대신 내부 우측 패널에 theory-card 렌더 (기존 CSS 재사용)
  - `TheoryPanel.js`: `THEORY_DB`, `RULE_LABEL` export 추가
  - `_buildMiniCard()`: 이론 카드 + 활성 cascade rule 배지 + 추천 자료 + 도서관 팁
  - 일반 모드 노드 클릭 → 글로벌 TheoryPanel 동작 유지

### ✅ NASA FIRMS 화재/열점 레이어 (2026-05-23)

- `backend/connectors/nasa_firms.py` — VIIRS S-NPP NRT 커넥터
  - 분쟁 지역 9개 bbox 병렬 조회 (`asyncio.gather`)
  - FRP(MW) + 신뢰도(h/n/l) → severity 0-100 산출
  - 겹치는 bbox 중복 열점 `source_id` 기준 제거
- `backend/api/layers.py` — `GET /api/layers/fire` (10분 캐시)
- `frontend/src/layers/FireHotspotsLayer.js` — circleMarker, severity→색상/크기, TheoryPanel 연동
- `frontend/index.html` — 레이어 패널 🔥 토글 추가 (`defaultVisible: false`)

**열점 색상 체계**: 노랑(소규모 <10 MW) → 주황 → 딥오렌지 → 빨강(극대 200+ MW)

관련 이론: Resource Weaponization (Hirschman 1945), Food Security (Patel & Moore 2009), Gray Zone Strategy

### ✅ AIS 선박 실시간 레이어 (2026-05-23)

- `backend/connectors/aisstream.py` — AISStream.io WebSocket 커넥터
  - 45초 수집 창 (`asyncio.timeout`), MMSI 기준 최신 위치 dedup
  - PositionReport + ShipStaticData 병합 (선박명·유형·IMO·목적지)
  - severity: 선박 유형(군함70·LNG65·유조선50·화물선35) × 지역 가중치 × 정박 상태
- `backend/api/layers.py` — `GET /api/layers/naval` (5분 캐시)
- `frontend/src/layers/NavalLayer.js` — ▲삼각형 마커(COG 방향 회전), MarkerCluster
  - 선박 유형별 색상: 군함(빨강)·LNG(파랑)·유조선(주황)·화물선(녹색)·미분류(회색)
  - 클릭 → 팝업(속력·침로·목적지·IMO) + TheoryPanel 연동
- `frontend/index.html` — `⚓ 선박 (AIS)` 레이어 토글 (`defaultVisible: false`)
- `frontend/styles/main.css` — `.ship-marker` / `.ship-cluster` 스타일

**AISStream 무료 티어 실측 커버리지 (2026-05-23 진단)**:

| 해역 | 수신 | 비고 |
|------|------|------|
| 말라카 | ✅ 27척/15초 | 싱가포르 지상국 밀집 |
| 대만해협 | ✅ 2척/15초 | 동아시아 지상국 커버 |
| 호르무즈 | ❌ 0척/30초 | 걸프만 = 위성 AIS 필요 ($29+/월) |
| 바브엘만데브 | ❌ 0척/20초 | 홍해 = 위성 AIS 필요 |
| 남중국해 | ❌ 0척/20초 | 지상국 없음 |

**대응 조치**:
- `_NAVAL_REGIONS`: malacca + taiwan_strait 2개로 축소 (나머지 주석 처리)
- `cascade_rules.yaml` — hormuz 룰 `source_type: conflict` 복원 (ACLED 대용 유지)
- 미커버 3개 해역은 유료 업그레이드 시 주석 해제만으로 즉시 활성화 가능

관련 이론: Mahan 해양력(SLOC 통제), Weaponized Interdependence (말라카 딜레마)

### ✅ ADS-B 군용기 레이어 — OpenSky Network (2026-05-23)

- `backend/connectors/opensky.py` 신규 — OpenSky REST API 군용기 커넥터
  - 대만해협·남중국해·동중국해 bbox 병렬 조회 (`asyncio.gather`)
  - ICAO24 블록(AE0000-AFFFFF 미군 블록) + 콜사인 접두사로 군용기 필터링
  - severity 산출: ISR(QUID/JAKE 등, +20) · 폭격기(FORTE/B-52, +25) · 급유기(+8) + 대만해협 ×1.2
  - icao24 기준 중복 제거 (복수 bbox 경계 포함 항공기)
  - Event 정규화: `source_type: "military_flight"`, `theory_tags: ["A2AD", ...]`

- `backend/config/cascade_rules.yaml` — taiwan_strait 두 룰 source_type 교체
  - `taiwan_strait_to_tsm`: `conflict` → `military_flight` (활성화)
  - `taiwan_strait_to_soxx`: `conflict` → `military_flight` (활성화)

- `backend/services/cascade/engine.py` — military_flight 룰 지원 추가
  - `conflict_rules` / `military_rules` 분리 처리
  - `_fetch_military_events()`: OpenSky 커넥터 호출 (미설정 시 graceful skip)
  - `_pick_military_trigger()`: region+severity_min 필터 후 최고심각도 1개 선택
  - 트리거 timestamp 소급 (지금 - window_hours) → yfinance 최근 시장 변동 평가

**단위 테스트 결과**:
- QUID01 (RC-135) 군용기 판별: ✅ (ICAO24 AE1234)
- severity (QUID + taiwan_strait): 84 → severity_min=50 즉시 트리거
- FORTE01 (B-52) severity: 90
- UAL123 민항기 판별: ✅ False (필터 정상)
- military_flight 룰 2개 로드 확인: taiwan_strait_to_tsm, taiwan_strait_to_soxx

### ✅ ADS-B 프론트엔드 레이어 + API 엔드포인트 (2026-05-23)

- `backend/api/layers.py` — `GET /api/layers/adsb` 추가 (5분 캐시)
- `frontend/src/layers/AdsbLayer.js` 신규
  - ✈ 마커 + `rotate(track - 45)deg` COG 방향 회전
  - 임무 유형별 색상: ISR(빨강)·폭격기(보라)·급유기(주황)·초계(딥오렌지)·공수(청색)·VIP(금색)
  - 클러스터: 사각형 적색 (선박 원형 청색과 시각적 구분)
  - 툴팁: callsign·유형·고도·속도 / 팝업: 국적·고도·속도·침로·스쿼크·위치소스·severity
  - zoom ≤ 5에서 severity ≥ 60만 표시 (고성능 유지)
  - EventBus `marker:click` → TheoryPanel 연동
- `frontend/styles/main.css` — `.adsb-marker` 유형별 색상 + `.adsb-cluster` 추가
- `frontend/index.html` — import + `new AdsbLayer()` + `register('adsb', ...)` 추가
- `main.py` 변경 없음 — `layers_router`에 `/api/layers/adsb` 자동 포함

---

## Phase 2 최종 완료 (2026-05-23)

| 항목 | 상태 | 비고 |
|------|------|------|
| Cascade Rule 6개 활성 (24링크) | ✅ | bab_el_mandeb·ukraine·middle_east·south_china_sea·suez + military_flight 2개 |
| Theory Panel | ✅ | 이론 DB 14개, 좌표 기반 룰 필터링 |
| TimelineView | ✅ | 드래그 리사이즈, 날짜 이동 툴바 |
| Study Mode | ✅ | 이론 태그 뱃지 + 노트 저장 (SQLite) |
| CascadeGraphView | ✅ | Cytoscape.js, 전체화면, 내부 이론 패널 |
| FIRMS 화재/열점 | ✅ | NASA VIIRS S-NPP NRT, 10분 캐시 |
| AIS 선박 | ✅ | 말라카·대만해협 (공해상 3개 해역 유료 한계) |
| ADS-B 군용기 | ✅ | OpenSky Network, ✈ COG 방향 회전 마커 |

**실시간 레이어 커버리지 한계 (무료 티어)**:

| 레이어 | 동작 해역 | 미커버 이유 |
|--------|-----------|------------|
| AIS 선박 | 말라카·대만해협 | 호르무즈·바브엘만데브·남중국해 = 위성 AIS 필요 ($29+/월) |
| ADS-B 군용기 | 지상국 인근 | 공해 상공 군용기는 지상국 없으면 미수신 — 실제 통과 시 자동 감지 |
| FIRMS 열점 | 전 지역 | 커버리지 제한 없음 (위성) |

---

## Phase 3 계획 (검토 중)

**다음 세션 시작 전 확인 필요**:
- [ ] 시스템 프롬프트(CLAUDE.md) Phase 3 항목 재검토
- [ ] ACLED 데이터 한계(2025-05까지) → GDELT 도입 타당성 재확인
- [ ] Event 모델 변경(confidence_score 추가) 파급 범위 사전 평가

**Phase 3 후보 작업 (우선순위 미확정)**:

1. **GDELT 실시간 데이터 파이프라인** (난이도 ★★★★)
   - 배경: ACLED는 현재 ~2025-05까지만 제공, 이후 실시간 보완 필요
   - 아키텍처 (3-Stage Funnel):
     1. GDELT 자체 필터링 (QuadClass 3/4, GoldsteinScale ≤-5, NumMentions ≥20)
     2. 뉴스 RSS/NewsAPI 교차 검증 (24h 내 2개 이상 매체)
     3. confidence_score 산출 (ACLED=1.0, 미검증=0.5, 교차검증=0.8)
   - 신규 파일: `connectors/gdelt_verifier.py`, `connectors/news_cross_validator.py`
   - 프론트엔드: `confidence_score < 0.8` → 점선 테두리 + ⚠️ 뱃지
   - 알려진 리스크: GDELT 좌표 부정확 (cascade false positive), NewsAPI 일 100건 제한

2. **CII 국가 불안정성 지수** (난이도 ★★★★)
   - V-Dem 데이터 + 자체 가중 계산
   - 레이어 패널 별도 항목, 코로플레스(Choropleth) 지도 표시

3. **Case Study Library** (난이도 ★★)
   - 대표 사례 사전 저장 (펠로시 대만 방문 2022, 홍해 후티 2023~)
   - 클릭 시 해당 시점으로 지도 시간 이동 + cascade 자동 표시

4. **노트 마크다운 내보내기** (난이도 ★)
   - Study Mode 노트 → `.md` 파일 export

5. **Cascade 통계적 상관분석** (난이도 ★★★★★)
   - Granger 인과분석 (Phase 3 `services/cascade/correlation.py`)
   - 최소 6개월치 이벤트 데이터 누적 후 착수

---

## Phase 로드맵

- ✅ Phase 0: 기반 (FastAPI + Leaflet + 군사기지)
- ✅ Phase 1: MVP (5개 레이어 + LayerManager)
- ✅ Phase 2: 핵심 차별화 — 3-View ✅ / Study Mode ✅ / 실시간 레이어 3개 ✅
- 🔜 Phase 3: 학습 도구 완성 (GDELT · CII · Case Study Library · Granger 분석)

---

## Phase 3 — 학습 도구 완성 (시작: 2026-05-23)

### 구현 순서 (확정)
1. ✅ backend/services/library/md_indexer.py
2. ✅ backend/services/library/deep_link.py + theory_library.yaml
3. ✅ backend/api/library.py
4. ✅ frontend/src/core/StateStore.js (library 슬라이스)
5. ✅ frontend/src/views/TheoryLibraryView.js
6. ✅ backend/services/cascade/sandbox_solver.py
7. ✅ frontend/src/views/SandboxLabView.js
8. [ ] GDELT/RSS/Sanctions

### ✅ 이론 라이브러리 뷰 완성 (2026-05-23)

**구현 파일:**
- `backend/services/library/md_indexer.py` — `get_db_theory()` / `list_db_theories()` 헬퍼 추가
- `backend/api/library.py` 신규 — 6개 엔드포인트
  - `GET /api/library/theories` (sector 필터), `GET /api/library/theories/{id}` (본문 포함)
  - `GET /api/library/theories/{id}/focus` (MapFocusTarget)
  - `GET /api/library/search?q=...` (FTS5 전문 검색)
  - `GET /api/library/region-index` ({ region_code: [theory_id, ...] })
  - `POST /api/library/reindex` (library/ 디렉토리 재스캔)
- `backend/main.py` — `library_router` 등록
- `frontend/src/core/StateStore.js` 신규 — 경량 반응형 상태 저장소 (library 슬라이스)
- `frontend/src/views/TheoryLibraryView.js` 신규
  - 우측 슬라이드인 패널 (380px, z-index 1002)
  - 5대 섹터 탭 필터 + 검색 (300ms debounce)
  - 이론 카드 목록: sector 배지·이론가·요약·권장 레이어·"지도에서 보기" 버튼
  - "지도에서 보기" → `map.flyTo()` + 권장 레이어 자동 활성화
- `frontend/src/panels/LayerPanel.js` — `📚 이론 라이브러리` 토글 버튼 추가 (library:toggle emit)
- `frontend/index.html` — `#library-panel` div + import + `new TheoryLibraryView()` init
- `frontend/styles/main.css` — `.library-panel` / `.lib-card` 스타일 추가

**데이터 흐름:**
- theory_library.yaml(권위 소스) + library/ .md FTS5 인덱스(SQLite) 병합
- SQLite 비어있어도 기본 정보 반환 (graceful degradation)
- region_index API → TheoryPanel에서 O(1) 이론 조회 (향후 통합)

version.json: 3.0.0 → 3.1.0

### ✅ Sandbox Lab 완성 (2026-05-23)

**구현 파일:**
- `backend/services/cascade/sandbox_solver.py` 신규
  - `verify_sandbox_hypothesis()`: 사용자 캔버스 가설을 cascade_rules과 비교
  - BFS 그래프 매칭: trigger 지역 노드 → response 지표 노드 경로 탐색
  - 점수 산출: 경로 길이 패널티 + 이론 태그 오버랩
  - 빠진 노드 진단: 룰에는 있지만 사용자 그래프에 없는 중간 단계 제안
- `backend/api/sandbox.py` 확장
  - `POST /api/sandbox/canvases/{canvas_id}/verify` 엔드포인트 추가
  - 요청: SandboxCanvasFull(노드+엣지)
  - 응답: total_score, num_matches, confidence_level, gaps, all_matches
- `frontend/src/views/SandboxLabView.js` 신규
  - Cytoscape.js 기반 인터랙티브 노드·엣지 캔버스
  - 기능: 노드 추가(modal), 엣지 그리기(shift+drag), 레이아웃 정렬(cose)
  - 가설 검증 버튼 → 서버 검증 결과를 우측 패널에 표시
  - 결과 UI: 점수 원형 게이지, 최고 매칭 규칙, 개선 제안, 전체 매칭 목록
- `frontend/index.html`
  - `#sandbox-panel` div 추가, SandboxLabView import + 초기화
- `frontend/src/panels/LayerPanel.js`
  - `🔬 분석실` 버튼 추가 (sandbox:toggle emit)
- `frontend/styles/main.css`
  - `.sandbox-panel` 슬라이드인 우측 500px 패널 (z-index 1001)
  - `.cytoscape-container` 그래프 렌더링 영역
  - `.verification-panel` 검증 결과 표시 영역
  - `.modal`, `.modal-overlay` 노드 추가 다이얼로그

**작동 흐름:**
1. LayerPanel "🔬 분석실" 클릭 → `sandbox:toggle` → SandboxLabView 우측 슬라이드
2. "+ 새로 만들기" → SandboxCanvas 생성 (title, id auto-generated)
3. "+ 노드" → 모달: label + type 입력 → POST /api/sandbox/canvases/{id}/nodes
4. Shift+drag → 엣지 연결 (Cytoscape 기본 동작)
5. "✓ 검증" → GET /api/sandbox/canvases/{id} → POST /verify → 점수 + 매칭 규칙 표시

**점수 산출 알고리즘:**
- BFS로 trigger region 노드에서 indicator 노드까지 경로 탐색
- 각 경로마다: depth_penalty(1.0 → 0.85 → 0.7) × theory_overlap(0.7 + 0.3×IOU)
- 상위 3개 규칙 평균 = total_score
- 신뢰도: high(2개+ 규칙 ∧ score≥0.7) / medium(1개 ∨ score≥0.5) / low

version.json: 3.1.0 → 3.2.0

---

## Phase 3 — 오늘 완료 (2026-05-23)

### ✅ Steps 1-7 완료, 학습 도구 기반 구축 완료

**오늘 구현:**
- Step 6: `sandbox_solver.py` — BFS 그래프 매칭으로 사용자 가설을 cascade_rules과 검증
- Step 7: `SandboxLabView.js` — Cytoscape.js 인터랙티브 캔버스 (노드 추가·엣지 연결·가설 검증)
- 추가: `gemini_translator.py` 스켈레톤 — on-demand 이벤트 번역 (Gemini API, SQLite 캐시)

**현재 Phase 3 상태:**
- Theory Library: ✅ 5대 섹터 탭 + 검색 + 지도 deep-link (step 1-5)
- Sandbox Lab: ✅ 노드·엣지 기반 가설 구성 + 규칙 매칭 검증 (step 6-7)
- 다음: Step 8 GDELT/RSS/Sanctions 파이프라인 (미시작)
