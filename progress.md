# 개발 진행 기록

## 완료된 Phase (요약)

### Phase 0 — 기반 ✅
FastAPI + Leaflet 헬로월드, Event 모델 + SQLite 스키마 확정, 군사기지 GeoJSON 정적 표시.

### Phase 1 — MVP ✅
5개 레이어 완성 (ACLED 분쟁·군사기지·에너지파이프라인·해상초크포인트·해저케이블).
LayerManager + LayerPanel 토글 UI, 1,000+ 마커 MarkerCluster+Canvas 처리.

### Phase 2 — 핵심 차별화 ✅
- **Cascade Engine**: 11개 룰 정의, 6개 활성 (24링크). bab_el_mandeb·ukraine·middle_east·south_china_sea·suez + military_flight 2개.
- **실시간 레이어 3개**: FIRMS 화재/열점(NASA), AIS 선박(말라카·대만해협), ADS-B 군용기(OpenSky).
- **3-View 시스템**: MapView(Leaflet 점선 화살표) + TimelineView(vis-timeline, 드래그 리사이즈) + CascadeGraphView(Cytoscape.js, 전체화면).
- **Study Mode**: 이론 태그 뱃지 토글 + 이벤트별 노트 저장(SQLite).
- **Theory Panel**: 이론 DB 14개, 좌표 기반 cascade 룰 필터링.

---

## Phase 3 — 학습 도구 완성 ✅ (2026-05-29 완료, v4.0.0)

**주요 구현 (v3.x ~ v4.0.0)**
- `md_indexer.py` / `api/library.py` / `TheoryLibraryView.js` — 이론 라이브러리 풀스크린 뷰 (FTS5, marked.js, Gemini SSE)
- `sandbox_solver.py` / `SandboxLabView.js` — BFS 가설 검증 + Granger 검증 탭
- `gdelt_connector.py` / `gdelt_pipeline.py` — GDELT 3-Stage Funnel (15분 주기, confidence 0.5→0.8)
- `sanctions.yaml` + `SanctionsLayer.js` — 15개 제재 레짐 버블 마커
- `cameo_mapper.py` / `intelligence.py` — CAMEO → 7대 축 결정론적 매핑 (Token-Zero)
- `verification_funnel.py` — 3단계 팩트체커 (ACLED+0.1 / RSS+0.2 / 센서+0.1)
- `archive_manager.py` / `schema.sql` — 계층형 TTL (핫 72h / event_archive 영구)
- `acled_bulk_ingest.py` 실행 → **252,409건** event_archive 적재 (41개국, 12개월)
- `cascade_rules.yaml` 15→21룰, 다단계 체인 3단계 (대만→TSM→SOXX→ITA), 44개 cascade links
- `services/reasoning/` — 8단계 추론 엔진 (case_studies.yaml·alliance_graph.yaml·FRED·sanctions)
- `ReasoningPanelView.js` — 우측 슬라이드인, 8단계 순차 표시
- `api/stats.py` / `TopBarView.js` — 3단 상단바 (긴장도·피자지수·마켓·뉴스 티커)
- `CountryLayer.js` / `CountryPanelView.js` — 국가 클릭 → 5탭 패널 (기본정보·거시지표·무역의존도·제재·이론)
- `correlation.py` — Granger 인과분석 8/8룰 검증 (korean_peninsula→KRW p=0.047 유의)
- GDELT 24h 누적 파이프라인 + 15분 스케줄러 자동 등록
- 이론 라이브러리 14개 완비, 7대 축 메타데이터 전면 이식


---

## Phase 4 — 데이터 확충 & 적재 기반 강화 ✅ (2026-05-31 완료, v4.8.0)

| # | 항목 | 버전 |
|---|------|------|
| P4-0 | `country_geopolitics.yaml` — 15개국 지정학 프로파일 (Waltz·Snyder·DIME) | v4.1.0 |
| P4-1 | `reliefweb.py` — UN OCHA RSS 커넥터, 30분 잡 | v4.2.0 |
| P4-2 | `gdelt_gkg.py` — GKG V2 테마·톤 결정론적 매핑 (Token-Zero), 파이프라인 통합 | v4.3.0 |
| P4-3 | `GET /api/stats/quality` — 승격률·GKG조인율 배지, TopBarView 연동 | v4.4.0 |
| P4-4 | `cascade_rule_draft.py` — Granger 82개 후보 스캔 → 2건 승인 (22룰) | v4.6.0 |
| 부록 | 이론 라이브러리 29→40개 (case_study 8 + concept 4 추가) | v4.7.0 |
| 부록 | `md_indexer` briefing 타입 허용 + INSS 7건 적재, Stage 3 briefing_refs 연동 | v4.8.0 |


---

---

## Phase 5 — 추론 지능화 (착수)

### ✅ [P5-5] Stage 5 명분·의도 구현 (2026-06-01) — v5.0.0

**구현 내용**
- `backend/services/reasoning/stages.py` — `stage5_justification_intent()` 실구현
  - `_THEME_INTENT_MAP`: GKG 테마 접두사 18종 → aggression/coercion/deterrence/negotiation/ambiguous 결정론적 매핑 (Token-Zero)
  - `_resolve_actor_posture()`: `country_geopolitics.yaml` 조회 — 각 ISO3의 strategic_posture + instrument_of_power
  - `_infer_intent_from_themes()`: 우선순위 기반 의도 추론 (aggression > coercion > deterrence > negotiation)
  - `_tone_label()`: GKG 톤 → 5단계 한국어 레이블 (극단적 적대 / 강한 적대 / 경미 / 중립 / 우호)
  - ACLED 이벤트 fallback: GKG 없을 때 event_type(battle/explosion/protest) → 의도 추정
  - 에스컬레이션 위험 판정: revisionist 행위자 + tone≤-4.0 + aggression/coercion 복합 조건
- `backend/services/reasoning/engine.py` — `stage5_intent_placeholder` → `stage5_justification_intent` 교체, `actors` 인자 전달, executor 병렬 실행
- `frontend/src/panels/ReasoningPanelView.js` — Stage 5 요약(`의도·톤·⚠️`) + 상세(posture/이론/에스컬레이션) 렌더링, `isPhase4` 분기 제거 → 모든 단계 ✅

**버그 수정 (검증 과정 발견)**
1. `event_type` 누락: GeoJSON `**e.payload` 스프레드 구조를 처리 못함 → `props.get("event_type") or payload.get("event_type")` 으로 수정
2. Actor ISO3 불일치: Stage 1이 `"Military Forces of Russia (2000-)"` 원문 반환 → `_resolve_actor_posture()`가 ISO3 못 찾는 버그. `_actor_to_iso3()` 모듈 레벨 함수 신설로 해결
3. Stage 8 내부 `_NAME_TO_CODE` / `_extract_country` 중복 → 모듈 레벨 통합 (`_ACTOR_NAME_TO_CODE`, `_actor_to_iso3`)

**실측 결과 (버그 수정 후)**
- ACLED Russia Battle (우크라이나): `공세적 행동 · 강한 적대 · escalation_risk=True | RUS=revisionist, UKR=status_quo` ✅
- ACLED Protest (이란/호르무즈): `외교·협상 · 중립 · escalation_risk=False` ✅ (revisionist이지만 tonality 조건 미충족 = 올바른 비위험 판정)
- 8단계 전체 에러 없음, elapsed 0.047s ✅

**주의사항**: 현재 DB GDELT 368개 이벤트 전부 `gkg_tone: None` → Stage 5가 항상 ACLED fallback 경로. GKG 파이프라인 조인 점검 필요.

**이론 연결**: Snyder 동맹 딜레마(revisionist 포지션 측정) × Farrell & Newman Weaponized Interdependence(강압 의도 분류) × Mearsheimer 공격적 현실주의(수정주의 판정)

### 현재 버전
`version.json`: **5.0.0** | phase: 5

---

### ✅ [P5-6] 추론 체인 자기검증 (2026-06-01) — v5.1.0

**구현 내용**
- `backend/services/reasoning/chain_verifier.py` (신규) — BFS 가설·반증 루프
  - 4종 주장(Claim) 추출: CascadeClaim(cascade_rules 대조) / IntentClaim(의도-포지션 일관성) / AllianceClaim(동맹 확산 경로) / HistoryClaim(역사 선례)
  - `verify_chain(stages, region_code)` → `chain_confidence: float` + `verdict: supported/contested/unsupported`
  - `_INTENT_POSTURE_DELTA`: 의도-포지션 8가지 조합 → delta 테이블 (Snyder 동맹 딜레마 계량화)
  - BFS 탐색: 지역별 cascade_rules 인덱스 → 실제 발화 여부·방향 일관성 대조
  - `chain_confidence` 계산: 기본 0.5 + Claim별 delta 합산 → [0.1, 0.95] 클리핑
  - verdict 기준: ≥0.70=supported / ≥0.45=contested / <0.45=unsupported
- `backend/services/reasoning/engine.py` — `chain_verifier.verify_chain()` 통합
  - 8단계 병렬 완료 후 executor로 자기검증 실행
  - 반환 딕셔너리에 `chain_verification` 키 추가
  - 로그에 `confidence=X.XX` 추가
- `frontend/src/panels/ReasoningPanelView.js` — `_renderChainVerification()` 추가
  - 8단계 순차 표시 완료 후 "체인 검증" 섹션 동적 삽입
  - 신뢰도 바(progress bar) + 판정 뱃지 + 지지/반증/미검증 Claim 목록
- `frontend/styles/main.css` — `.chain-verify`, `.cv-claim--*`, `.cv-bar` 스타일 추가

**실측 결과**
- 우크라이나 Battle (RUS revisionist + aggression): `confidence=0.90, supported=5건` ✅
- 한반도 역설 케이스 (status_quo + aggression): `confidence=0.40, refuted=1건, unsupported` ✅
- 실제 API 통합 (ukraine, 0건 cascade_chain): `confidence=0.57, contested, 0.061s` ✅

**이론 연결**: Snyder 동맹 딜레마(포지션-의도 일관성) × BFS 반증 탐색 = 추론 투명성 강화

### ✅ cascade_links DB 저장 + 신뢰도 필터 (2026-06-01) — v5.1.1

**문제**: cascade_links가 메모리에서만 계산되고 소멸 → reasoning API에 항상 빈 배열 전달 → chain_confidence 항상 0.57 고착

**수정**
- `backend/db/schema.sql` — `cascade_links` 테이블 추가 (id·score·depth·rule_name·evidence 등)
- `backend/services/cascade/engine.py` — `_persist_links()` 신설
  - `_MIN_PERSIST_SCORE = 0.6` (threshold × 1.2배 이상 = pct_change / (threshold×2) ≥ 0.6)
  - `score < 0.6`: 노이즈 가능성 → 저장 제외
  - `score ≥ 0.6`: DB 저장, 점수 높아지면 UPDATE
  - `build_cascade()` 반환 시 `saved_to_db`, `skipped_low_confidence` 메타데이터 추가
- `backend/api/reasoning.py` — `_resolve_cascade_links()` 쿼리에 `depth`, `rule_name` 필드 추가, `ORDER BY correlation_score DESC`

**실측**: 35개 링크 평가 → 32건 저장(score 0.62~1.00, 평균 0.94) / 3건 제외
누적 76건 (첫 호출 후), chain_confidence가 실제 cascade 발화 기록 반영 시작

### 현재 버전
`version.json`: **5.1.1**

## 다음 세션 우선순위

**Phase 5 잔여 항목**

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 5 | Stage 5 명분·의도 구현 | `stages.py` | ✅ v5.0.0 |
| 6 | 추론 체인 자기검증 (BFS 반증 루프) | `chain_verifier.py` / `engine.py` | ✅ v5.1.0 |
| 6b | cascade_links DB 저장 + 신뢰도 필터 | `schema.sql` / `engine.py` | ✅ v5.1.1 |
| 7 | 멀티에이전트 섹터별 추론 병렬 | `services/reasoning/agents/` 신규 | ⬜ |
| 8 | LLM 종합 브리핑 계층 | `api/briefing.py` importance≥0.7 게이트 | ⬜ |

### ✅ §17 Diffusion_Score + §16 Stage 3 센서 누락 보완 (2026-06-01) — v5.2.0

**§17 Stage 8 Diffusion_Score 구현**
- `alliance_graph.yaml` — 16개 동맹에 `pact_intensity` 필드 추가 (NATO=1.0, us_rok=0.90, CSTO=0.90, us_philippines=0.85 등 §17 기준값 준수)
- `alliance_graph.yaml` — `country_memberships` 34개국으로 확장 (BLR·KAZ·KGZ·TJK·ARM·PHL·QAT·TUR 등 누락국 추가)
- `stages.py` — `_calc_diffusion_score()` 신설
  - 공식: 가장 강한 동맹 pact_intensity × 80 + 나머지 × 0.5 × 80, max 100
  - involvement_factor: 양쪽 멤버=1.0, 한쪽만=0.6
  - 판정: ≥80 🔴Entrapment / <50 🟡Abandonment / else 🟢정상
- `stages.py` — `_ACTOR_NAME_TO_CODE`에 15개국 추가 (Belarus·Kazakhstan·NZ·Canada 등)
- `stages.py` — Stage 8 반환값에 `diffusion_score`, `alliance_risk`, `alliance_risk_ko` 추가
- `engine.py` — region을 stage1 결과에서 우선 읽도록 수정 (geofence 역조회 보정 반영)
- `api/reasoning.py` — `_load_event_from_db()` fallback 추가 (LIMIT에 걸린 이벤트 DB 직접 조회)

**§16 Stage 3 센서 (FIRMS) 구현**
- `jobs/firms_sensor_job.py` (신규) — NASA FIRMS NRT → sensor_snapshots 저장
  - 5대 섹터 6개 지역 bbox, FRP≥10 필터
  - `run_firms_sensor_batch()` 동기 래퍼 (APScheduler용)
- `main.py` — FIRMS 잡 6시간마다 등록

**실측 결과**
- CHN vs USA (대만해협): diffusion_score=100, 🔴Entrapment ✅
- BLR vs UKR (우크라이나): diffusion_score=56, 🟢정상 (우크라이나 NATO 미가입 반영) ✅
- ETH 시위: diffusion_score=0, 🟡Abandonment ✅

### ✅ 브리핑 대량 적재 (2026-06-01) — v5.2.0 유지

**CSIS 보고서 7건 추가 등록 (총 14개)**

| # | theory_id | 요약 |
|---|-----------|------|
| 8 | `briefing_20260601_csis_missile_inventory_rebuild` | 이란전 소진 → 서태평양 취약 창 (~2030) |
| 9 | `briefing_20260526_csis_jado_africa_battlelab` | 아프리카 JADO 배틀랩, 모로코 우선 (Jensen) |
| 10 | `briefing_20260500_csis_economic_warfare_military_power` | 전환함수 표적화, 희토류 91%, CIPS 성장 (Jensen) |
| 11 | `briefing_20260600_csis_global_terrorism_assessment_2026` | 이란전 프록시 재활성화, 사헬 지하디스트 수도권 위협 |
| 12 | `briefing_20260526_csis_pacific_islands_security_voice` | 태평양 안보 정의 미스매치, 심해 광물·솔로몬 분기점 |
| 13 | `briefing_20260526_csis_gulf_states_iran_mou` | 카타르 LNG 20% 파괴, 방위 다변화, 황금 다리 전략 |
| 14 | `briefing_20260522_csis_maritime_power_economic_link` | 미국 조선 0.1% vs 중국 50%, Mahan 사슬 현대 실증 (Jensen) |

**Benjamin Jensen 4부작 완성** (5.22·5.26·5.26·6.01):
재고(단기) → 교리(중기) → 경제전(장기) → 조선/병참(구조)

**핵심 교차 인사이트 (브리핑 간 연쇄)**:
- CSIS 3부작: 이란전 소진 → 비대칭 보완(드론) → 전환함수 구조 차단
- 걸프 MOU: 미사일 재고 공백 → GCC 방어 실패 → LNG 20% 파괴 실증
- 태평양: `hormuz_tension_to_oil` 룰의 실전 역방향 검증 가능

**라이브러리 현황**: 54개 (concept 17 + norm 15 + case_study 8 + briefing 14)

---

## 다음 세션 우선순위

**Phase 5 잔여 항목**

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 5 | Stage 5 명분·의도 구현 | `stages.py` | ✅ v5.0.0 |
| 6 | 추론 체인 자기검증 (BFS 반증 루프) | `chain_verifier.py` / `engine.py` | ✅ v5.1.0 |
| 6b | cascade_links DB 저장 + 신뢰도 필터 | `schema.sql` / `engine.py` | ✅ v5.1.1 |
| 6c | §17 Diffusion_Score + §16 FIRMS 센서 | `stages.py` / `firms_sensor_job.py` | ✅ v5.2.0 |
| 7 | 멀티에이전트 섹터별 추론 병렬 | `services/reasoning/agents/` 신규 | ⬜ |
| 8 | LLM 종합 브리핑 계층 | `api/briefing.py` importance≥0.7 게이트 | ⬜ |

**다음 작업**: P5-7 멀티에이전트 섹터별 추론 병렬

항목 8: §14 Token-Zero 위반 아님 — 사용자 명시 요청 기반 LLM 호출은 허용 범위.
병행 과제: 브리핑 지속 적재 (INSS, CSIS, RAND 등) — 현재 14개, 목표 30개

---

## Phase 6 — 브리핑 지식 그래프 & 교차 분석 (대기 중)

**착수 조건**: Phase 5 완료 + 아래 브리핑 품질 게이트 충족

### 브리핑 품질 게이트 (숫자 30 → 다차원 조건으로 재정의, 2026-06-01)

단순 숫자(30개)는 근거가 약하므로 교차 분석의 실질적 품질을 보장하는 조건으로 대체한다.

#### 조건 1: 총량 목표 — **50개 이상**
현재 14개. 규모가 커야 행위자 네트워크·지역 클러스터링이 통계적으로 의미 있음.

#### 조건 2: 6대 섹터 균형 (CLAUDE.md §1 기준)

| 섹터 | `sector_tag` | 최소 건수 | 현재 | 부족 |
|------|-------------|---------|------|------|
| 해양 & SLOC | `maritime` | 5건 | 1건 | **4건** |
| 에너지 지정학 | `energy` | 5건 | 1건 | **4건** |
| 기술 패권 | `techno` | 5건 | 1건 | **4건** |
| 인도-태평양 | `indo_pacific` | 8건 | 3건 | **5건** |
| 회색지대 | `gray_zone` | 8건 | 3건 | **5건** |
| 사이버 & 인지전 | `cyber` | 5건 | **3건** | 2건 |

> ※ `cyber` 섹터 신설 (2026-06-01). INSS 844호(이란전 사이버전)가 현재 1건.

#### 조건 3: 출처 다양성 — **4기관 이상**

| 기관 | 현재 | 목표 후보 |
|------|------|---------|
| INSS (이스라엘) | 7건 ✅ | — |
| CSIS (미국) | 7건 ✅ | — |
| RAND Corporation | 0건 ❌ | 우선 추가 |
| IISS / Chatham House | 0건 ❌ | 우선 추가 |
| Brookings / CFR | 0건 ❌ | 선택 추가 |

#### 조건 4: 시간 범위 — **2025년 이전 사례 최소 3건 이상**
현재 전체가 2026년 편중. 역사적 선례(2022~2024)가 있어야 before/after 비교 가능.

#### 조건 5: 지역 균형 — **5대 분쟁 지역 각 최소 2건**

| 지역 | `geopol_region` | 현재 | 목표 |
|------|----------------|------|------|
| 대만해협 | `taiwan_strait` | 3건 | 5건+ |
| 호르무즈 | `hormuz` | 2건 ✅ | — |
| 우크라이나·동유럽 | `eastern_europe` | 1건 | 3건+ |
| 바브엘만데브·사헬 | `bab_el_mandeb` | 2건 ✅ | — |
| 한반도 | `korean_peninsula` | 2건 ✅ | — |

**현재 충족**: 2개 / 5개 조건

현재 브리핑: **17개** (2026-06-02 기준) / 목표 50개

### ✅ 브리핑 추가 적재 (2026-06-02)

**cyber 섹터 신설 + md_indexer 허용값 업데이트**
- `CLAUDE.md §1`: 5대 → 6대 섹터 (`cyber` 추가)
- `md_indexer.py`: `ALLOWED_SECTOR_TAGS`에 `cyber` 추가

**수집러 구현 (1단계 자동화)**
- `backend/scripts/briefing_collector.py` — RSS fetch + 60일 날짜 필터 + 섹터 키워드 필터
- `backend/config/briefing_sources.yaml` — RAND·War on the Rocks·ECFR·Foreign Affairs RSS
- `backend/config/briefing_queue.yaml` — 현재 63개 대기 중
- `backend/config/briefing_done.yaml` — 완료 목록 (중복 수집 방지)

**Phase 6 게이트 재정의** — 숫자(30) → 5개 다차원 조건 (총량 50개 + 섹터 균형 + 출처 다양성 + 시간 범위 + 지역 균형)

**War on the Rocks Cyber 3부작 등록** (사이버 취약 구조 완전한 그림)

| # | theory_id | 요약 |
|---|-----------|------|
| 15 | `briefing_20260520_wotr_salt_typhoon_machine_overmatch` | 기계 압도: 솔트 타이푼 — 중국 데이터 중심 정보전 |
| 16 | `briefing_20260514_wotr_cyber_ops_speed_trilemma` | 사이버 속도 트릴레마 — 조직 설계 결함, AI 민주화 |
| 17 | `briefing_20260422_wotr_cyber_resilience_capacity_flaw` | 역량 없는 회복탄력성 — CISA 공동화, 전략 자기모순 |

**Cyber 3부작 교차 인사이트**:
- 중국 공세(Salt Typhoon) ↔ 미국 공격 조직 결함(트릴레마) ↔ 미국 방어 역량 공동화(CISA)
- 세 보고서가 미국 사이버 취약성의 공세·방어 양면을 동시에 드러내는 완전한 그림

**라이브러리 현황**: 57개 (concept 17 + norm 15 + case_study 8 + briefing 17)

설계 배경: 7개 브리핑 교차 분석에서 아래 3가지 가치 창출 경로 확인됨.
브리핑 표본 부족으로 즉시 구현보다 데이터 선적재 후 착수 결정.

**P6 구현 항목 (CLAUDE.md §11 Phase 6 참조)**
1. 브리핑 연쇄 그래프 뷰 (BriefingGraphView.js) — series_ref Cytoscape 시각화
2. 행위자 네트워크 자동 추출 — event_refs 집계 → 공통 노드 생성
3. Cascade 엔진 커버리지 갭 트리거 3종 (cyber / defense_policy / economic_coercion)
4. 교차 인사이트 자동 생성 (briefing_graph.py)
5. 브리핑 타임라인 뷰 (BriefingTimelineView.js)

**현재 확인된 교차 인사이트 (데이터 쌓이면 자동 도출 목표)**
- 한국 전략 공간 이중 압박: 382호(북한) × 일본 국가행동분석의 동시 작동 구조
- 외교 도미노 타임라인: 중러(845) → 북중(848) → 다극(382) → 핵잠(849) 10일 연쇄
- Cascade 엔진 맹점 3유형: 사이버·정책선언·경제강압 미포착 영역 지도화
- CSIS 3부작 인과 체인: 이란전 소진 → 드론 비대칭 보완 → 전환함수 구조 차단 (Jensen 4부작)
- 걸프 MOU 실증: 미사일 재고 공백 → GCC 방어 실패 → LNG 20% 파괴 (hormuz 룰 역검증)
- 태평양-인도양 연결: 솔로몬 분기점(심해 광물) × 희토류 91%(경제전) × Mahan 사슬(조선)

---

## 2026-06-03 (브리핑 적재 세션 — 18~38번째)

### 완료 항목

**Cyber 카테고리** (4/5 완료, 1개 영구보류)
- [x] `briefing_20260318_rand_gamification_narrative_cognitive_warfare` — [Cyber 4/5] 게임 언어의 무기화: 풀뿌리 인지전과 서사 수확 작전 (RAND, 18번째)
- [ ] Cyber 5/5 — Synthetic Biology 팟캐스트 → `status: permanent_defer` (텍스트 추출 불가)

**Energy 카테고리** (3/5 완료, 2개 보류)
- [ ] Energy 1/5 — Does OPEC Still Matter? → `status: permanent_defer` (정보밀도 부족)
- [x] `briefing_20260515_ecfr_postwar_uae_gulf_politics` — [Energy 2/5] 전후 UAE와 걸프 정치의 재편 (ECFR, 19번째)
- [x] `briefing_20260522_ecfr_imec_wartime_redesign` — [Energy 3/5] IMEC 전시 재설계 (ECFR, 20번째)
- [x] `briefing_20260508_wotr_russia_hormuz_playbook_baltic` — [Energy 4/5] 러시아의 호르무즈 플레이북 (WotR, 21번째)
- [x] `briefing_20260519_rand_hormuz_mine_clearing` — [Energy 5/5] 호르무즈 소해 작전 (RAND, 22번째)

**Gray Zone 카테고리** (2/4 완료, 2개 보류)
- [x] `briefing_20260519_wotr_somaliland_recognition_red_sea` — [Gray Zone 1/4] 소말릴란드 승인의 문제 (WotR, 23번째)
- [ ] Gray Zone 2/4 — Western Withdrawal, Jihadist Expansion: Sahel → `status: deferred`
- [x] `briefing_20260514_wotr_kremlin_battlefield_home` — [Gray Zone 3/4] 크렘린의 진짜 전장은 국내다 (WotR, 24번째)
- [x] `briefing_20260529_wotr_glass_jaw_economic_fragility` — [Gray Zone 4/4] 유리 턱: 미국 경제 취약성 (WotR, 25번째)

**Maritime 카테고리** (5/5 완료 ✅)
- [x] `briefing_20260528_wotr_sea_control_revolution` — [Maritime 1/5] 제해권 혁명 (WotR, 26번째)
- [x] `briefing_20260527_wotr_leading_in_dark_submarine_command` — [Maritime 2/5] 어둠 속 지휘: 잠수함 지휘관이 불확실성 하에서 생각하는 법 (WotR, 27번째)
- [x] `briefing_20260505_wotr_india_ssbn_nuclear_deterrence` — [Maritime 3/5] 억지는 연습이 필요하다: 인도의 해양 핵 도전 (WotR, 28번째)
- [x] `briefing_20260515_wotr_skorea_drone_warriors_hollow` — [Maritime 4/5] 한국의 50만 드론 전사는 공허한 전력이 될 것이다 (WotR, 29번째)
- [x] `briefing_20260529_ecfr_europe_defence_digital_layer` — [Maritime 5/5] 코드·클라우드·위성: 유럽이 외주해선 안 될 방산 레이어 (ECFR, 30번째)

**Techno 카테고리** (4/5 완료, 1개 영구보류)
- [ ] Techno 1/5 — `status: permanent_defer`
- [x] `briefing_20260421_wotr_gan_silicon_mistake_gallium` — [Techno 2/5] 갈륨나이트라이드 공급망 취약성 (WotR, 31번째)
- [x] `briefing_20260500_fa_china_ai_heist` — [Techno 3/5] 중국의 AI 절도 — 유통 패권 (FA, 32번째)
- [x] `briefing_20260528_rand_uk_aisi_ai_cyber_uplift` — [Techno 4/5] 프런티어 AI 공세 사이버 업리프트 (RAND/UK AISI, 33번째)
- [x] `briefing_20260528_wotr_china_mineral_indonesia_control` — [Techno 5/5] 소유 없는 통제: 인도네시아 광물 (WotR, 34번째)
- [ ] RAND Lithography 방법론 → `status: permanent_defer` (위협 정보 아님)

**Indo-Pacific 카테고리** (4/5 완료, 1개 재방문)
- [x] `briefing_20260518_wotr_missiles_not_strategy_pacific_air` — [Indo-Pacific 1/5] 미사일은 전략이 아니다 (WotR, 35번째)
- [ ] Indo-Pacific 2/5 — How the War with Iran Is Shaping U.S.-Chinese Competition → `status: deferred` (멤버십)
- [x] `briefing_20260513_wotr_missing_navies_hormuz_indo_pacific` — [Indo-Pacific 3/5] 사라진 해군: 호르무즈와 인도-태평양 파트너십 한계 (WotR, 36번째)
- [x] `briefing_20260421_wotr_iran_war_us_korea_alliance` — [Indo-Pacific 4/5] 이란전이 한미동맹에 의미하는 것 (WotR, 37번째)
- [x] `briefing_20260318_rand_fp_japan_sink_china_invasion_fleet` — [Indo-Pacific 5/5] 일본은 중국 침공 함대를 격침해야 한다 (RAND/FP, 38번째)

### 전체 브리핑 라이브러리 현황

| 카테고리 | 완료 | 재방문 대기 | 영구 보류 |
|----------|------|------------|----------|
| 🔵 Cyber | 4 | 0 | 1 (팟캐스트) |
| 🟡 Energy | 3 | 0 | 1 (정보밀도 부족) |
| 🟠 Gray Zone | 2 | 1 (멤버십) | 0 |
| 🔷 Maritime | 5 | 0 | 0 |
| 🟣 Techno | 4 | 0 | 2 (멤버십·방법론) |
| 🔴 Indo-Pacific | 4 | 2 (멤버십·페이월) | 0 |
| **합계** | **38개** | **3개** | **4개** |

### 다음 세션 시작점

**재방문 대기 항목 → `library/07_briefings/briefing_deferred_urls.txt` 참조**

- 재방문 권장 (3개): WOTR 이란전 5인 패널, FA Hormuz Warning, Gray Zone 2/4 Sahel
- 영구 보류 (4개): Synthetic Biology 팟캐스트, Does OPEC Still Matter, RAND Lithography, Techno 1/5

---

## 라이브러리 개편 (2026-06-04 착수)

### 목표

브리핑 38개 단일 평탄 구조 → 섹터별 분류 + 프론트 브리핑 전용 뷰 추가.

### 추진 방식: A + C 조합

**Step 1 — Option C: 프론트엔드 브리핑 모드 탭 (파일 변경 없음)**

| 항목 | 내용 |
|------|------|
| 대상 파일 | `frontend/src/views/TheoryLibraryView.js` |
| 구현 내용 | 상단에 `[이론] [사례] [제재] [브리핑]` 탭 추가. 브리핑 탭 선택 시 `sector_tag` 기준 섹터별 아코디언 그룹 + `source_org` 뱃지 표시 |
| 상태 | ⬜ |

**Step 2 — Option A: 브리핑 섹터별 하위폴더 + 번호 정정**

| 항목 | 내용 |
|------|------|
| 폴더 이동 | `07_briefings/*.md` → `07_briefings/{sector}/` |
| 번호 정정 | `04_sanctions_and_norms` → `07_sanctions_and_norms` (04 중복 해소) |
| 신규 폴더 | `06_cyber/` (CLAUDE.md §1 6대 섹터 반영) |
| 백엔드 | `md_indexer.py` 스캔 경로 재귀 탐색 확인 |
| 상태 | ⬜ |

### 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | TheoryLibraryView 브리핑 탭 UI 구현 | ⬜ |
| 2 | 섹터별 아코디언 그룹 + source_org 뱃지 | ⬜ |
| 3 | `07_briefings/` 섹터 하위폴더 생성 및 파일 이동 | ⬜ |
| 4 | `04_sanctions_and_norms` → `07_sanctions_and_norms` 번호 정정 | ⬜ |
| 5 | `06_cyber/` 폴더 신규 생성 | ⬜ |
| 6 | `md_indexer.py` 재귀 스캔 + 재인덱싱 검증 | ⬜ |
