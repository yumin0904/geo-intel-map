# 완료된 작업 히스토리 (아카이브)

> 이 파일은 progress.md에서 분리된 Phase 0~7 완료 작업 로그입니다.
> 현재 진행 중인 작업은 progress.md를 참조하세요.

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

## 라이브러리 개편 ✅ (2026-06-04 완료, v5.3.0)

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
| 1 | TheoryLibraryView 브리핑 탭 UI 구현 | ✅ b51e270 |
| 2 | 섹터별 아코디언 그룹 + source_org 필터 칩 | ✅ b51e270 |
| 3 | `07_briefings/` 섹터 하위폴더 생성 및 파일 이동 (38개) | ✅ 9020e56 |
| 4 | `04_sanctions_and_norms` → `07_sanctions_and_norms` 번호 정정 | ✅ 9020e56 |
| 5 | `06_cyber/` 폴더 신규 생성, `08_case_studies/` 번호 정정 | ✅ 9020e56 |
| 6 | `md_indexer.py` 재귀 스캔 + 재인덱싱 검증 (78개 오류 0) | ✅ 9020e56 |
| 7 | `list_db_theories` SELECT 필드 누락 버그 수정 (source_org 등 7개) | ✅ 7bd9c8c |
| 8 | source_org 부분 매칭 필터 (RAND Corporation·ECFR 변형 대응) | ✅ 7bd9c8c |

---

## 인사이트 분석실 탭 — 설계 확정 (2026-06-03)

### 결정 사항

**백엔드 LLM**: **Gemini 2.5 Flash** (단일 모델, 모드로 분기)

| 모드 | Thinking | 용도 | 비용/쿼리 |
|------|---------|------|---------|
| `fast` | OFF | 즉각 인사이트 조회, 요약 | ~$0.001 |
| `deep` | ON | 교차 분석, 발표 주제 추천, 가설 검증 | ~$0.006 |

- 기존 Gemini SSE 파이프라인 재사용 (모델명 + thinking 파라미터 변경)
- 무료 티어(1,500회/일) 범위 내 운용
- 월 예상 비용: $1~3 이하

### 구현 목표

분석실(`SandboxLabView.js`) 내 **세 번째 탭** 추가:
`[가설 빌더] [Granger 검증] [🧠 인사이트 분석]`

사용자가 자연어로 질문 → 백엔드가 다중 소스 교차 검색(결정론적) → Gemini 2.5 Flash SSE로 합성 → 인사이트 카드 + 발표 각도 반환.

### 구현 파일

```
backend/
  api/intel_query.py          POST /api/intel/query (SSE)
  services/intel_analyzer.py  멀티소스 검색 + 컨텍스트 조립
  services/entity_parser.py   결정론적 엔티티 추출 (Token-Zero)

frontend/src/views/
  InsightAnalystView.js        새 탭 UI (SandboxLabView 내 탭으로 삽입)
```

### 데이터 파이프라인

```
자연어 쿼리
  → [1] entity_parser: 지역·행위자·모드 결정론적 추출
  → [2] 병렬 멀티소스 검색 (LLM 없음)
        ├ FTS5 라이브러리 (78개 문서)
        ├ event_archive 통계 (지역·기간 필터)
        ├ cascade_links (지역 발화 실적)
        ├ country_geopolitics.yaml
        └ alliance_graph.yaml
  → [3] 컨텍스트 조립 (~3,000~5,000 tokens)
  → [4] Gemini 2.5 Flash SSE (thinking: fast=OFF / deep=ON)
  → [5] 구조화 응답: 인사이트 카드 3~5개 + 발표 각도 제안
```

### 쿼리 모드 3종

| 모드 | 트리거 키워드 | Thinking | 출력 |
|------|------------|---------|------|
| `insight` | 기본값, "분석", "교차" | OFF | 인사이트 카드 + 증거 소스 |
| `presentation` | "발표", "주제 추천", "프레젠테이션" | ON | 발표 각도 3~5개 + 슬라이드 개요 |
| `verify` | "검증", "근거", "맞아?" | ON | 지지/반증 증거 비율 + verdict |

### Phase 5 잔여 항목과의 관계

- **P5-7 멀티에이전트**: 인사이트 분석탭이 나중에 섹터별 에이전트의 프론트 진입점이 됨. 지금은 단일 파이프라인으로 구현 → P5-7에서 에이전트로 교체.
- **P5-8 LLM 브리핑 계층**: `importance≥0.7` 게이트 로직을 `intel_query.py`가 함께 활용.

### 구현 순서

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| IA-1 | 결정론적 엔티티 파서 | `services/entity_parser.py` | ✅ |
| IA-2 | 멀티소스 검색 파이프라인 | `services/intel_analyzer.py` | ✅ |
| IA-3 | SSE 엔드포인트 + Gemini 2.5 Flash 통합 | `api/intel_query.py` | ✅ |
| IA-4 | 프론트 탭 UI | `InsightAnalystView.js` | ✅ |

---

## 다음 세션 시작점

**우선순위**

| # | 항목 | 상태 |
|---|------|------|
| P5-7 | 멀티에이전트 섹터별 추론 병렬 | ✅ v5.4.0 |
| IA-1~4 | 인사이트 분석실 탭 (4단계) | ✅ v5.5.0 |
| IA-개선 | 데이터 깊이 + 저장 기능 | ✅ v5.6.0 |
| IA-엔진 | 인사이트 엔진 개선 로드맵 반영 | ✅ v5.6.0 (CLAUDE.md §19~21) |
| P5-8 | LLM 종합 브리핑 계층 | ⬜ |
| **IA-Engine-A** | **프롬프트 6단계 재설계** | **✅ v5.7.0** |
| IA-Engine-B1 | SIPRI Expenditure + COW + Kiel Tracker 적재 | ✅ v5.8.0 |
| IA-Engine-B2 | EIA Energy Stats + CSIS Cyber DB 적재 | ✅ v5.9.0 |
| IA-Engine-C | 인사이트 신뢰도 점수 모듈 | ⬜ 중기 |
| IA-Engine-D | Falsifiable Hypothesis 자동 생성 | ⬜ 중기 |

### IA 개선 내역 (v5.6.0)

**데이터 깊이**
- FTS5(한국어 0건) → LIKE 검색으로 교체 → 10건 히트
- 브리핑 body 원문 상위 3개 포함 (각 최대 3,000자)
- cascade_rules.yaml 이론 텍스트 추가
- 컨텍스트 총량: ~2,300자 → ~12,000자 (5배)

**저장 기능**
- `intel_analyses` 테이블 (id·query·mode·regions·sectors·result_md·created_at)
- `POST /api/intel/save` · `GET /api/intel/history` · `GET /api/intel/history/{id}` · `DELETE /api/intel/history/{id}`
- 분석 완료 후 💾 저장 버튼 표시
- 좌측 히스토리 패널: 클릭 시 쿼리+결과 복원, ✕로 삭제

---

## ✅ [IA-1~4] 인사이트 분석실 탭 (2026-06-03) — v5.5.0

**구현 내용**

| 파일 | 역할 |
|------|------|
| `services/entity_parser.py` | 자연어 → ParsedQuery 결정론적 추출. 지역 9개·행위자 15개·섹터 6개 별칭 매핑. Thinking ON/OFF 자동 결정 |
| `services/intel_analyzer.py` | 5개 소스 병렬 조회 (FTS5·sector filter·event_archive·cascade_links·country_geopolitics) → Gemini 컨텍스트 조립 |
| `api/intel_query.py` | POST /api/intel/query SSE. 모드별 프롬프트(insight/presentation/verify). Gemini 2.5 Flash + thinking 503 fallback |
| `InsightAnalystView.js` | SandboxLabView 세 번째 탭 `🧠 인사이트 분석`. 쿼리 입력·모드 선택·메타바·마크다운 스트리밍 렌더링 |

**Gemini API 상태**
- `gemini-2.5-flash` 모델 정상 (SSE 스트리밍 확인)
- thinking 모드: `thinkingBudget=8192` 명시 시 503 간헐 발생 → 503 감지 즉시 fast 모드로 자동 fallback 처리
- `thoughtsTokenCount` 자동 발생 확인 (모델 자체 사고 과정 내부 처리)

**실측 결과 (러시아-우크라이나 발표 주제 추천 쿼리)**
- META: mode=presentation, regions=[ukraine], sectors=[gray_zone, energy], thinking=True
- 소스: sector 6건 + event 1개지역(105,723건) + cascade 8건 + 국가프로파일 2개
- 출력: 발표 각도 3개 + 슬라이드 구성 7단계 완전 생성

---

## ✅ [P5-7] 멀티에이전트 섹터별 추론 병렬 (2026-06-03) — v5.4.0

**구현 내용**

`backend/services/reasoning/agents/` 신규 디렉토리:

| 파일 | 역할 |
|------|------|
| `base_agent.py` | `SectorAgent` 기반 클래스 — `is_relevant()` / `analyze()` 인터페이스 |
| `maritime_agent.py` | 초크포인트 근접성·SLOC 취약성·Mahan 이론 |
| `energy_agent.py` | 자원무기화·파이프라인 취약성·Stage4 매크로 재활용 |
| `techno_agent.py` | 반도체 공급망·희토류·Digital Iron Curtain |
| `indo_pacific_agent.py` | 제1열도선·A2/AD·동맹 페어·Stage8 Diffusion 재활용 |
| `gray_zone_agent.py` | 하이브리드전 단계·프록시 탐지·에스컬레이션 |
| `cyber_agent.py` | APT 귀속·공격 유형·사이버 역량 매핑 |
| `synthesizer.py` | 교차 섹터 인사이트 10종 패턴 + 위험 등급 3단계 |
| `__init__.py` | `ALL_AGENTS`, `synthesize` 등록 |

`engine.py`에 `run_reasoning_with_agents()` 신규 진입점 추가:
- 기존 8단계 실행 후, `is_relevant()` 필터로 관련 에이전트만 병렬 실행
- `synthesize()`로 교차 인사이트 + `summary_context` (Gemini 주입용) 생성

**실측 결과**

| 시나리오 | 활성 섹터 | 교차 인사이트 | 위험 등급 | elapsed |
|---------|---------|------------|---------|--------|
| 우크라이나 에너지 공격 | energy·techno·gray_zone | 2개 | 1/3 주의 | 0.062s |
| 대만해협 PLA 침범 | maritime·techno·indo_pacific·gray_zone | 4개 | 2/3 경계 | 0.041s |

**이론 연결**: Mahan 해양력 × Farrell & Newman Weaponized Interdependence × Snyder 동맹 딜레마 × Hoffman 하이브리드전 × Libicki 사이버 억지 — 6대 섹터 이론 매핑 완성

**IA 탭 연계**: `synthesis["summary_context"]`가 인사이트 분석실 Gemini 프롬프트에 직접 주입되는 구조화 컨텍스트로 사용됨

---

## 인사이트 엔진 개선 로드맵 (2026-06-03 진단)

### 현황 진단 요약

3개 인사이트 세트 평가 결과:

| 평가 차원 | 미국 전략 세트 | 이란전 세트 | 이란-러시아 연쇄 |
|---|---|---|---|
| 이론적 정확성 | 72% | 78% | 70% |
| 인과 논리 엄밀성 | **38%** | **52%** | **31%** |
| 데이터 기반 정도 | **25%** | **61%** | **44%** |
| 가설 명확성 | 55% | 45% | 35% |
| 학술 기여 가능성 | 48% | 67% | 72% |

**공통 병목**: 인과 논리 엄밀성 + 데이터 기반 정도가 최저.
현재 엔진은 **현상 기술 + 이론 레이블링**에서 멈추며 **인과 검증**으로 미진입.

### 즉시 실행 항목 (Layer A — 프롬프트 레벨, 코드 변경 없음)

- [ ] 인사이트 생성 프롬프트 6단계 구조 적용 (`api/intel_query.py` `_build_prompt`)
- [ ] 연쇄 고리별 강도 자기평가 출력 (HIGH/MEDIUM/LOW)
- [ ] MEDIUM 이하 고리 포함 연쇄에 [SPECULATIVE] 자동 태그
- [ ] 수치 근거 없는 주장에 [UNVERIFIED] 플래그

### 단기 데이터 적재 (Layer B-1 — 1~2개월)

**즉시 ROI 최대 조합**: SIPRI + COW + Kiel Tracker 3종 적재
→ 인사이트 수준 석사 중반 → 석사 후반 기대

- [ ] SIPRI Military Expenditure DB (173개국 %GDP, 무기 이전)
- [ ] COW Alliance Data (동맹 형성·해체 1816~)
- [ ] Kiel Institute Ukraine Support Tracker (서방 지원 실데이터)
- [ ] EIA International Energy Statistics (에너지 생산·소비)
- [ ] CSIS Significant Cyber Incidents DB (2006~, 사이버전 기준점)

### 중기 아키텍처 (Layer C — 3~6개월)

- [ ] 인사이트 신뢰도 점수(0~100%) 자동 산출 모듈
- [ ] Falsifiable Hypothesis (H1/H0) 자동 생성 모듈
- [ ] 이론 라이브러리 12개 이론 프로파일 구축
- [ ] 인사이트 카드 7개 필드 출력 형식 표준화 (CLAUDE.md §19-B)

### 장기 목표 (Layer C v6.0 — 6~12개월)

- [ ] 경쟁 이론 동시 적용 및 설명력 비교 엔진
- [ ] 데이터 자동 조회 → 상관 분석 파이프라인
- [ ] 박사 수준 분석 기준 충족 검증 체크리스트

### 핵심 전환 원칙

> **"무슨 일이 일어나고 있는가"(현황 기술) →
> "왜 이 설명이 경쟁 이론보다 더 타당한가"(인과 검증)를 데이터로 보여주는 도구**

---

## ✅ [IA-Engine-A] 프롬프트 6단계 재설계 (2026-06-03) — v5.7.0

**구현 내용** (`api/intel_query.py` `_build_prompt()` 전면 재설계)

| 변경 항목 | 이전 | 이후 |
|----------|------|------|
| system_role | 석사 지도 / 이론 포함 2줄 | §19-A 8개 원칙 + §19-D 신뢰도 기준 명시 |
| insight 카드 | 인사이트+근거+이론 3필드 | §19-B 8필드 카드 (헤드라인·신뢰도·관찰·주장·가설·근거·한계·경쟁설명·검증포인트·문헌공백) |
| verify 모드 | 판정+지지/반증+이론 | §19-A 6단계 완전 구조화 (관찰→변수→가설→경쟁이론→근거→고리강도) |
| presentation 모드 | 각도제목+주장+근거+이론+차별점 | 인사이트 카드 형식 통합 + 청중 훅 + 문헌 공백 |
| 공통 추가 | 없음 | [UNVERIFIED] / [SPECULATIVE] / [PROVISIONAL] 자동 레이블 지침 |
| 강점 보존 | - | §19-B-2 ①이론 반례 ②도메인 교차 경로 ③문헌 공백 탐지 3종 명시 요구 |

**진단 문제 → 해결 매핑**

| 병목 | 이전 점수 | 해결 방법 |
|------|---------|---------|
| 인과 논리 엄밀성 38~52% | 낮음 | 6단계 강제 구조 + 연쇄 고리 강도 |
| 데이터 기반 정도 25~61% | 낮음 | [UNVERIFIED] 의무 태그 + 신뢰도 점수 산출 기준 |
| 가설 명확성 35~55% | 낮음 | H1 반증 가능 형태 강제 |
| 경쟁 이론 없음 | 없음 | 경쟁 이론 1~2개 + 기각 근거 필수화 |

### 다음 세션 시작점

---

## ✅ [IA-Engine-B1] 외부 정형 데이터 적재 (2026-06-03) — v5.8.0

**P5-8 취소** — IA-Engine으로 대체됨 (§14 자동 LLM 충돌, 기능 중복)

**구현 내용**

| 파일 | 역할 |
|------|------|
| `backend/db/schema.sql` | `sipri_milex` · `cow_alliances` · `kiel_ukraine_support` 3개 테이블 추가 |
| `data/external/sipri_milex_seed.csv` | SIPRI 2019~2023, 15개국 국방비 %GDP + USD bn |
| `data/external/cow_alliances_seed.csv` | COW v4.1 기반 현재 활성 동맹 44쌍 (NATO·CSTO·미일·미한 등) |
| `data/external/kiel_ukraine_support_seed.csv` | Kiel Release 19 (2024-06) 19개 공여국 군사·재정·인도적 지원 |
| `backend/scripts/load_external_data.py` | 3개 소스 적재 + `--update` 플래그로 원본 다운로드 시도 |
| `backend/services/intel_analyzer.py` | `_get_sipri_data()` · `_get_cow_alliances()` · `_get_kiel_data()` 추가, `build_intel_context()` 병렬 gather 통합 |

**실측 결과**

| 시나리오 | SIPRI | COW | Kiel | 컨텍스트 길이 |
|---------|------|-----|------|-----------|
| 대만해협 반도체 쿼리 | CHN·USA 2국 | 33동맹 | 0 | 13,022자 |
| 우크라이나 서방지원 쿼리 | UKR·RUS 2국 | 37동맹 | 12개국 | 12,990자 |

**인사이트 품질 향상 효과**
- [관찰] 섹션: "러시아 2023년 국방비 GDP 5.9% / $109bn" 수치 직접 인용 가능 (+30점)
- [근거] 섹션: 1차 사료(SIPRI·COW·Kiel) 참조 가능 (+20점)
- §19-D 신뢰도 점수 +50점 잠재력 확보

### 다음 세션 시작점

| 항목 | 상태 |
|------|------|
| IA-Engine-B2 | EIA Energy Stats + CSIS Cyber DB 적재 | ✅ v5.9.0 |
| IA-Engine-C | 인사이트 신뢰도 점수 모듈 | ⬜ 중기 |
| IA-Engine-D | Falsifiable Hypothesis 자동 생성 | ⬜ 중기 |

---

## ✅ [IA-Engine-B2] EIA + CSIS 데이터 적재 (2026-06-03) — v5.9.0

**구현 내용**

| 파일 | 역할 |
|------|------|
| `data/external/eia_energy_seed.csv` | EIA 2023, 19개국 원유/천연가스 생산량 + 6개 초크포인트 통과량 |
| `data/external/csis_cyber_seed.csv` | CSIS 2015~2024, 20개 주요 사이버 사건 (Sandworm·Lazarus·Volt Typhoon·Salt Typhoon 등) |
| `backend/db/schema.sql` | `eia_energy` · `csis_cyber_incidents` 2개 테이블 추가 |
| `backend/scripts/load_external_data.py` | eia·csis 소스 추가, `--source eia,csis` 지원 |
| `backend/services/intel_analyzer.py` | `_get_eia_data()` · `_get_csis_incidents()` 추가, 10개 소스 병렬 gather |

**실측 결과**

| 시나리오 | EIA | CSIS | 컨텍스트 길이 |
|---------|-----|------|-----------|
| 호르무즈 유가 쿼리 | Hormuz 21Mbpd + SAU·IRN 생산량 | 이란 관련 6건 | 13,628자 |
| 이란 사이버 공격 쿼리 | IRN 에너지 프로파일 | 최신 사이버 6건 | 13,684자 |
| 대만해협 반도체 쿼리 | Malacca 16Mbpd | CHN·USA·PRK 관련 7건 | 14,147자 |

**인사이트 품질 향상**
- 에너지 섹터: "호르무즈 21Mbpd 통과 (EIA 2023)" 수치 직접 인용 가능
- 사이버 섹터: "Volt Typhoon 미국 군사 인프라 사전 배치" 등 APT 선례 참조 가능
- §19-D 신뢰도 기준 충족 항목 (수치 인용 +30, 1차 사료 +20) 모두 확보

### 다음 세션 시작점

| 항목 | 상태 |
|------|------|
| IA-Engine-C | 인사이트 신뢰도 점수 모듈 | ⬜ |
| IA-Engine-D | Falsifiable Hypothesis 자동 생성 | ⬜ |

### 현재 버전
`version.json`: **5.9.0** | phase: 5

---

## 2026-06-03 세션 요약 (IA-Engine A·B1·B2)

### 완료 항목

| 버전 | 항목 | 핵심 변경 |
|------|------|---------|
| v5.7.0 | IA-Engine-A 프롬프트 6단계 재설계 | `_build_prompt()` §19 전면 적용 — [UNVERIFIED]/[SPECULATIVE]/[PROVISIONAL] 자동 레이블, §19-B 8필드 카드, §19-D 신뢰도 기준 |
| v5.8.0 | IA-Engine-B1 SIPRI·COW·Kiel 적재 | 국방비 5년 추이 + 공식 동맹 + 우크라이나 지원액 수치 인용 |
| v5.9.0 | IA-Engine-B2 EIA·CSIS 적재 | 초크포인트 통과량 + APT 사건 선례 인용 |

**P5-8 취소** — IA-Engine으로 대체, §14 충돌 해소

### 외교부 오픈데이터 검토 결과 (미착수, 별도 판단)
- `opendata.mofa.go.kr/lod/` LOD 플랫폼: 브리핑(91건)·보도자료(983건) 국가 태그 데이터 → Phase 6 브리핑 라이브러리 확충 시 `connectors/mofa_press.py` 형태로 편입 예정
- `insight.mofa.go.kr` 글로벌 공공데이터 1,275건 → 각국 오픈데이터 포털 링크 디렉토리, 직접 지정학 데이터 아님
- 여행경보 REST API → CountryPanel "현재 위험도" 탭 보완용, Phase 4 연장선

### 인사이트 엔진 데이터 소스 현황 (10개 병렬)

| # | 소스 | 건수 | 활성화 조건 |
|---|------|------|-----------|
| 1 | 브리핑·이론 LIKE 검색 | 라이브러리 57개 | 항상 |
| 2 | 섹터 필터 | 라이브러리 57개 | 항상 |
| 3 | ACLED event_archive 통계 | 252,409건 | 지역 지정 시 |
| 4 | Cascade links + rules | 76건 | 지역 지정 시 |
| 5 | Country geopolitics | 15개국 | 행위자 지정 시 |
| 6 | SIPRI 국방비 | 80행 (15국×5년) | 행위자·지역 시 |
| 7 | COW 공식 동맹 | 44쌍 | 행위자·지역 시 |
| 8 | Kiel 우크라이나 지원 | 19개국 | ukraine 지역 시 |
| 9 | EIA 에너지·초크포인트 | 24행 | 에너지·해양 지역 시 |
| 10 | CSIS 사이버 사건 | 20건 | cyber 섹터·관련국 시 |

---

## ✅ [IA-Engine-C] 인사이트 신뢰도 점수 모듈 (2026-06-04) — v6.0.0

**구현 내용**

| 파일 | 역할 |
|------|------|
| `backend/services/confidence_scorer.py` (신규) | §19-D 5개 항목 정규식 탐지 → 0~100 점수 역산 |
| `backend/api/intel_query.py` | 스트리밍 완료 후 `{"type":"score"}` SSE 이벤트 추가 |
| `backend/api/intel_query.py` | `/save` 엔드포인트 `confidence_score` 필드 추가 |
| `backend/db/schema.sql` | `intel_analyses.confidence_score INTEGER` 컬럼 추가 |
| `backend/main.py` | lifespan에 `ALTER TABLE` 마이그레이션 (기존 DB 호환) |
| `frontend/src/views/InsightAnalystView.js` | `score` 이벤트 처리 + `_renderScore()` 메서드 |
| `frontend/styles/main.css` | `.ia__score-badge--{high/mid/low}` + `.ia__provisional-banner` |

**§19-D 탐지 항목 및 점수**

| 항목 | 탐지 방법 | 점수 |
|------|----------|------|
| 수치 데이터 직접 인용 | 숫자+단위 정규식 (%, bn, Mbpd 등) | +30 |
| 1차 사료 참조 | SIPRI·EIA·ACLED·COW·Kiel·CSIS 등 기관명 | +20 |
| 반증 가능 가설 | H1:·[가설]·통계적으로·통제변수 | +20 |
| 경쟁 이론 비교 | [경쟁설명]·대안 이론·기각 근거 | +15 |
| 연쇄 고리 강도 | HIGH/MEDIUM/LOW·고리 강도 | +15 |

**실측 결과**

| 케이스 | 점수 | provisional |
|--------|------|------------|
| 풀 충족 (SIPRI + H1 + 경쟁설명 + HIGH) | 100/100 | False |
| 중간 (EIA 수치 + HIGH, 가설·경쟁이론 없음) | 65/100 | False |
| 빈 (서술만, 수치/사료/가설 없음) | 0/100 | True |

**UX 흐름**
- 메타 바에 `신뢰도 ██████░░░░ 65점` 배지 (색상: 80↑=초록 / 60-79=주황 / 60↓=빨강)
- 60점 미만 → 결과 최상단에 ⚠️ [PROVISIONAL] 배너 자동 표시
- 저장 시 `confidence_score` DB 기록

**이론 연결**: §19-D 신뢰도 산출 기준 직접 구현 — 인사이트 생성에서 인과 검증으로의 전환 척도

### 현재 버전
`version.json`: **6.0.0** | phase: 6

---

## 인사이트 엔진 품질 평가 (2026-06-04) — 3개 세트 기반

| 평가 차원 | 업데이트 전 | 업데이트 후 | 변화 |
|---|---|---|---|
| 이론적 정확성 | 73% | 87% | +14%p |
| 인과 논리 엄밀성 | 40% | 65% | +25%p |
| 데이터 기반 정도 | 25% | **87%** | **+62%p** ← 최대 |
| 가설 명확성 | 45% | 75% | +30%p |
| 학술 기여 가능성 | 62% | 80% | +18%p |
| **종합** | **53%** | **81%** | **+28%p** |

**도달 수준**: 학부·석사 초입 → **박사 초입(81%)**

### 발견된 문제 및 처리 현황

| 우선순위 | 문제 | 처리 |
|---|---|---|
| P0 | 신뢰도 100/100 버그 — Gemini 자체 점수 출력 | ✅ 이 세션에서 수정 (프롬프트에서 제거) |
| A-2 | 시간 역전 탐지 미적용 | ✅ 이 세션에서 수정 (`[TEMPORAL_REVERSAL]` 태그 추가) |
| P1 | H1 가설 생성됐지만 예비 검증 미실행 | ⬜ IA-Engine-D 대상 |
| P2 | 경쟁 이론 기각이 수사적 수준 (예측값 편차 비교 미구현) | ⬜ v8.0 목표 |
| P4 | ACLED 대만해협 Cascade 0건 | ⬜ 다음 세션 조사 |

---

## ✅ 신뢰도 버그 픽스 + 시간 역전 탐지 (2026-06-04) — v6.0.1

**구현 내용**

| 파일 | 변경 |
|------|------|
| `api/intel_query.py` | 카드 형식에서 `신뢰도: N점/100` 줄 완전 제거 |
| `api/intel_query.py` | system_role §19-D 항목 → 자체 산출 금지 명시로 교체 |
| `api/intel_query.py` | 원칙 9번 추가: `[TEMPORAL_REVERSAL]` 시간 역전 탐지 + 재공식화 |
| `CLAUDE.md §19-B` | 카드 형식 표준 업데이트 (신뢰도 줄 제거, `[문헌공백]` 추가) |
| `CLAUDE.md §19-B-3` | 시간 역전 탐지 원칙 신설 |
| `CLAUDE.md §21` | 분석 아키텍처 진화 경로 v6.0→v8.0 업데이트 |
| `CLAUDE.md §22` | IA-Engine-D 설계 명세 신설 (H1 스키마·신뢰도 상한 캡·박사 기준) |
| `README.md` | 전면 업데이트 (v6.0.0, 품질 평가표, 10소스 파이프라인) |

**역할 분리 완성**
- Gemini: 글쓰기 (연쇄강도 HIGH/MEDIUM/LOW + 데이터기반/이론근거 정성 평가)
- IA-Engine-C: 신뢰도 숫자 점수 독점 산출 (§19-D 역산, 서버 측)

---

## ✅ [IA-Engine-D] H1 자동 생성 + Granger 검증 파이프라인 (2026-06-03) — v6.1.0

**구현 내용**

| 파일 | 역할 |
|------|------|
| `backend/services/hypothesis_extractor.py` (신규) | `[가설]` 섹션 정규식 파싱 → HypothesisSpec. region/ticker 결정론적 매핑 (Token-Zero) |
| `backend/services/hypothesis_verifier.py` (신규) | `correlation.py` `_run_granger()` 재활용 → p_value → PENDING/PARTIAL/VERIFIED 판정 |
| `backend/services/confidence_scorer.py` | `apply_verification_cap()` 추가 (PENDING≤75 / PARTIAL≤88 / VERIFIED=무제한) |
| `backend/api/intel_query.py` | 스트리밍 완료 후 H1 추출 → Granger 실행 → `hypothesis` SSE 이벤트 전송 + 캡 적용 |
| `frontend/src/views/InsightAnalystView.js` | `hypothesis` 이벤트 처리 + `_renderHypotheses()` — H1/H0/p값/lag/status 카드 |
| `frontend/styles/main.css` | `.ia__hyp-*` 스타일 추가 (VERIFIED=초록 / PARTIAL=주황 / PENDING=회색) |

**파이프라인 흐름**
```
Gemini 스트리밍 완료
  → hypothesis_extractor: [가설] H1 정규식 추출 + 변수→region/ticker 매핑
  → hypothesis_verifier:  _load_event_series + _get_market_series → _run_granger
  → verification_status: p<0.05=VERIFIED / p<0.15=PARTIAL / else=PENDING
  → apply_verification_cap: 신뢰도 점수에 상한 캡 적용
  → hypothesis SSE 이벤트 → 프론트 H1 카드 렌더링
```

**region/ticker 결정론적 매핑 (Token-Zero)**
- region 9종: eastern_europe / taiwan_strait / hormuz / korean_peninsula / bab_el_mandeb / suez / middle_east / malacca / sahel
- ticker 8종: CL=F / NG=F / TSM / KRW=X / ZW=F / GLD / ITA / SOXX

**실측 (단위 테스트)**
- "우크라이나 분쟁 강도 → WTI 유가": region=eastern_europe, ticker=CL=F ✅
- "대만해협 긴장 → TSMC 주가": region=taiwan_strait, ticker=TSM ✅
- "외교 성명 빈도 → 알 수 없는 지표": region=None, ticker=None → PENDING + error 기록 ✅
- PENDING cap 90→75, PARTIAL cap 90→88, VERIFIED cap 90→90 ✅

**verify 모드 신뢰도 버그 수정** (같은 세션): `_build_prompt()` verify 최종 판정 섹션에서 `신뢰도: N점/100` 줄 제거 → Gemini 자체 점수 출력 방지

**이론 연결**: Clive Granger(1969) F-test × 지정학 연쇄 인과 — Farrell & Newman Weaponized Interdependence의 "초크포인트 충격만 시장 전이" 명제를 통계 검정

### 현재 버전
`version.json`: **6.1.0** | phase: 6

---

## 다음 세션 시작점

## ✅ ACLED 대만해협 Cascade 0건 수정 (2026-06-03) — v6.1.1

**근본 원인**
- `_TRIGGER_COUNTRIES`에 `taiwan_strait` 누락 → `_fetch_region_events("taiwan_strait")`가 즉시 `[]` 반환, DB fallback에 도달 불가

**2차 원인**
- `events` + `event_archive` 모두 taipei_strait ACLED 이벤트의 severity 평균 ≈ 15 (시위·경찰 이벤트 위주)
- severity ≥ 50 이벤트: `events` 테이블 2건, `event_archive` 5건

**수정 내용** (`backend/services/cascade/engine.py`)
1. `_TRIGGER_COUNTRIES`에 `taiwan_strait: ["Taiwan", "China"]` 추가
2. `_load_region_events_from_db`: events 테이블 고강도 이벤트 < 5건이면 `event_archive` 추가 조회 (lat/lon은 payload JSON에서 추출)

**실측 결과**
- 수정 전: 발화 0건
- 수정 후: `taiwan_strait_conflict_to_soxx` → score=0.67, 발화 1건 ✅
- DB fallback: 698건 로드 (events 500 + archive 198 비중복)

**구조적 한계 (기록)**: 대만해협 ACLED는 민간 충돌 위주 → PLA 군사 도발은 OpenSky ADS-B(`military_flight` 룰)가 담당. Cascade 발화 빈도는 낮을 수밖에 없으나, 실제 발화 이벤트 발생 시 정상 동작함.

---

## ✅ [IA-Engine v6.2.0] 인사이트 엔진 3-Bug Fix (2026-06-03)

**배경**: v6.1.1 세 세트(한반도·중-일·이스라엘-이란) 평가에서 발견된 즉시 수정 항목.

| 버그 | 원인 | 수정 |
|------|------|------|
| [P0-A] 인사이트 미완성 저장 | 저장 전 완결성 검사 없음 | `validate_insight_completeness()` + `/save` 422 거부 |
| [P0-B] 신뢰도 100/100 재발 (데이터 공백) | Engine-C가 이벤트·Cascade 0 조건 미처리 | `apply_data_void_penalty()` — 0+0→상한60, 하나→상한72 |
| [P1] Engine-D ticker 오류 (Type B/C 변수) | ticker 없으면 무조건 매핑 실패로 PENDING | 변수 3분류 (Type_A/B/C) + 유형별 라우팅 |

**구현 파일**

| 파일 | 변경 |
|------|------|
| `services/confidence_scorer.py` | `apply_data_void_penalty()` + `validate_insight_completeness()` 신규 |
| `api/intel_query.py` | 패널티 적용 (source_counts 주입), `/save` 완결성 검사 |
| `services/hypothesis_extractor.py` | `VariableType`, `proxy_suggestions` 필드, `_classify_variable_type()` |
| `services/hypothesis_verifier.py` | Type_A/B/C 분기 라우팅 (B→ACLED 안내, C→proxy 제안) |
| `frontend/src/views/InsightAnalystView.js` | Type 뱃지 + proxy 제안 표시 |
| `frontend/styles/main.css` | `.ia__hyp-tag--type`, `.ia__hyp-proxy` 추가 |

**단위 테스트 결과**
- P0-B: 100→60(0+0), 80→72(하나 0), 85→85(정상) ✅
- P0-A: 미완성([가설] 없음) → 거부, 완결 → 허용 ✅
- P1: 유가→Type_A, 프록시활동→Type_B, 대응의지→Type_C(proxy 자동 제안) ✅ (6/6)

**v6.1.1 → v6.2.0 목표 상태 달성**
- 신뢰도: 데이터 공백 패널티 적용, 항상 60~88 범위 안정 ✅
- 저장: 미완성 인사이트 저장 불가 ✅
- Engine-D: Type B/C 변수에서 "ticker 미식별" 오류 → 유형별 안내 메시지로 전환 ✅

### 현재 버전
`version.json`: **6.2.0** | phase: 6

---

## ✅ 브리핑 추가 적재 (2026-06-04) — v6.2.0 유지

### 이번 세션 등록 브리핑 (7건)

| # | theory_id | 섹터 | 출처 | 요약 |
|---|-----------|------|------|------|
| 39 | `briefing_20260224_cfr_russia_gray_zone_europe` | gray_zone | CFR | 러시아 회색지대→저강도 전쟁 전환 창, NATO 억지력 정치적 신뢰 훼손 전략 |
| 40 | `briefing_20260512_wotr_russia_china_arctic_lawfare` | gray_zone | WotR | 러중 북극 법전쟁 — NSR 주권 통제·그림자 선단·대륙붕 규범 재작성 |
| 41 | `briefing_20190900_brookings_china_gray_zone_dod` | gray_zone | Brookings | 비대칭 방어 독트린(2019 원형) + 2026년 현실 예측 정확도 평가 |
| 42 | `briefing_20260318_cfr_iran_war_energy_chaos_asia` | energy | CFR | 이란전 개전 20일: 아시아 소비국 에너지 패닉, 보조금 한계, 사회 불안 |
| 43 | `briefing_20260317_chatham_iran_war_gulf_energy_toll` | energy | Chatham House | 이란전 개전 3주: 걸프 공급측 우회 역량 한계(25%), 선택적 봉쇄 구조 |
| 44 | `briefing_20260401_brookings_iran_energy_shocks_unrealized` | energy | Brookings | 이란전 1개월: 미실현 2차 충격, 1973+1979 합산 초과, CERAWeek 논의 |
| 45 | `briefing_20260429_chatham_defence_ai_investment_reconfigure` | techno | Chatham House | 방산 AI 붐·애국 기술·주권 AI 다극화, 이란전 AWS 데이터센터 타격 최초 실증 |

### 이란전 에너지 충격 3종 세트 완성
- **EN-1 (CFR, 개전 20일)** — 아시아 소비국 시각
- **EN-2 (Chatham House, 개전 3주)** — 걸프 공급측 시각
- **EN-3 (Brookings, 개전 1개월)** — 글로벌 중장기·미실현 2차 충격

세 보고서가 호르무즈 충격의 공급-수요-중장기 3각 실증 데이터를 완성함. `hormuz_tension_to_oil` Cascade 룰의 사회 불안·우회 한계·식량 연쇄 경로까지 근거 확보.

### Phase 6 게이트 현황 (2026-06-04 기준)

| 조건 | 이전 | 현재 | 목표 |
|------|------|------|------|
| 총량 | 38개 | **45개** | 50개 |
| gray_zone | ~6건 | **~9건** ✅ | 8건 |
| energy | ~5건 | **~8건** ✅ | 5건 |
| techno | ~5건 | **~6건** ✅ | 5건 |
| indo_pacific | ~9건 | ~9건 ✅ | 8건 |
| maritime | ~6건 | ~6건 ✅ | 5건 |
| cyber | ~7건 | ~7건 ✅ | 5건 |
| 출처 다양성 | INSS·CSIS·WotR | + **CFR·Brookings·Chatham** ✅ | 4기관+ |
| 2025년 이전 사례 | 1건 | **2건** (GZ-3 2019) | 3건 |
| 지역 균형 5대 | 3개 충족 | 3개 충족 | 5개 |

**현재 충족: 4개 / 5개 조건** (잔여: 총량 5개 + 2025년 이전 1건 + 지역 균형)

### TC-2 등록 완료 (2026-06-04)
- TC-2: `briefing_20251216_chatham_ai_bubble_china_rise` — LLM 수익화 딜레마 + 글로벌 사우스 침투 + 거버넌스 분기. TC-1의 선행 분석(2025.12). series_ref로 TC-1과 연결.

---

## 다음 세션 시작점

### Phase 6/7 방향 재정의 (2026-06-05)

**결정**: 시각화(브리핑 그래프 뷰 등) → Phase 8로 후순위 이동.
Phase 6·7은 **IA-Engine 분석 수준 향상**에만 집중.
로드맵: 계획 → 구현/테스트 → `eval_insight.py` 자동 평가 → 수정 → 재계획

### 현재 지표 (v6.3.2 자동화 테스트 기준)

| 지표 | 현재 | Phase 6 목표 | Phase 7 목표 |
|------|------|------------|------------|
| 신뢰도 평균 | 70/100 | 78+ | 85+ |
| Granger VERIFIED | 0건 | 1건+ (p<0.05) | 3건+ |
| UNVERIFIED 평균 | ~3.5건/케이스 | <1건 | <0.5건 |
| 분석 수준 | 박사 초입 81% | — | 박사 완성 90%+ |

### Phase 6 작업 목록

| Cycle | 항목 | 상태 | 우선순위 |
|-------|------|------|---------|
| **6-A 1단계** | SIPRI Arms Transfers + V-DEM + COW Wars CSV 적재 | ✅ v6.4.0 | — |
| **6-A 2단계** | 외교부 LOD IFANS 발간자료 — `connectors/mofa_lod.py` | ✅ v6.4.0 | — |
| **6-A eval** | `eval_insight.py` 재실행 → UNVERIFIED 37→20 (-46%) | ✅ v6.6.0 | — |
| **6-B** | Granger 통계력 강화 (lag 자동 최적화·r값·사이버 proxy) | ✅ v6.5.0 | — |
| **6-C** | H1 생성 품질 고도화 (추상 변수 제한·SIPRI Arms 섹터 필터) | ✅ v6.6.0 | — |

### Phase 7 작업 목록 (Phase 6 완료 후)

| Cycle | 항목 | 상태 |
|-------|------|------|
| **7-A** | 이론 라이브러리 구조화 — 12개 이론 예측변수·반례 추가 | ⬜ |
| **7-B** | 경쟁 이론 비교 엔진 — 3개 이론 예측값 편차 비교 | ⬜ |
| **7-C** | 종합 평가 — 자동화 테스트 20케이스, 신뢰도 85+ 선언 | ⬜ |

### Phase 8 (후순위)

브리핑 연쇄 그래프(P8-1) · 행위자 네트워크(P8-2) · 교차 인사이트(P8-4) · 타임라인 뷰(P8-5)

---

### 외교부 LOD 조사 결과 (2026-06-05)

SPARQL 엔드포인트: `https://opendata.mofa.go.kr/lod/sparql` (검증 완료)
REST JSON 패턴: `GET /mofapub/resource/Publication/{id}.json.data`
구현 파일: `backend/connectors/mofa_lod.py` (6-A 2단계에서 신규 생성)

| 데이터셋 | 건수 | IA-Engine 활용 | 판정 |
|---------|------|--------------|------|
| `mofapub` IFANS 발간자료 | 4,174건 | intel_analyzer 11번째 소스 (한반도·동아시아 컨텍스트) | ✅ 6-A 2단계 |
| `mofabrief` 대변인 브리핑 | 191건 (2022~2023) | 외교 신호 보조 | ✅ 동일 커넥터 |
| `mofadaily` 외교일지 | 6,288건 | 조약 데이터 — COW와 중복, 활용 낮음 | ❌ |
| `schema:Event` 역사 이벤트 | 2,128건 | 날짜 없음 — Granger 직접 사용 불가, DBpedia 브릿지로만 활용 | ⚠️ |

**온톨로지 핵심 발견**: 모든 Country + Event 엔티티에 `owl:sameAs` → DBpedia URI 연결 확인.
`mofa_lod.py`는 ISO2 국가코드 조회(경로 1)와 DBpedia 이벤트 URI 조회(경로 2) 두 경로 지원.

DBpedia 이벤트 URI 예시 (호르무즈 UNVERIFIED 직접 해소용):
- `dbpedia:Abqaiq–Khurais_attack` → 아브카이크 공격 관련 IFANS 발간자료
- `dbpedia:Houthi_insurgency` → 후티 반란 관련 발간자료
- `dbpedia:2022_Russian_invasion_of_Ukraine` → 러-우 전쟁 관련 발간자료

---

## Phase 6 게이트 최종 확인 (2026-06-04)

| 조건 | 현황 | 충족 |
|------|------|------|
| 총량 50개 | **50/50** | ✅ |
| 섹터 균형 6개 (각 ≥5건) | maritime 6·energy 8·techno 6·indo_pacific 9·gray_zone 9·cyber 7 | ✅ |
| 출처 다양성 4기관+ | INSS·CSIS·WotR·CFR·Brookings·Chatham·RAND·ECFR·FA | ✅ |
| 2025년 이전 사례 3건 | GZ-3(2019)·IP-1(2025.07)·TC-2(2025.12) | ✅ |
| 지역 균형 5대 | taiwan_strait·hormuz·bab_el_mandeb·korean_peninsula·eastern_europe | ✅ |

**모든 조건 충족 — Phase 6 착수 가능**

---

## ✅ [IA-Engine v6.3.0] 완결성·재시도·Type C Granger + Type A 강등 (2026-06-04)

**배경**: v6.2.0 네 세트(대만·한-미·미-중·러-우) 평가에서 발견된 4개 개선 항목.

### 구현 항목

| # | 문제 | 수정 |
|---|------|------|
| P0 | 완결성 검사 미흡 — H1 잘림·[문헌공백] 미체크 | `_REQUIRED_SECTIONS` + 8번째로 `[문헌공백]` 추가 + `_RE_H1_LINE` 전체 H1 완결 검사 |
| P1 | 저장 실패 시 이유 불명 + 수동 재시도 | 프론트 422 응답 파싱 → 실패 이유 배너 + `🔄 재분석` 버튼 |
| P2 | Type C 대리변수 제안만 하고 Granger 미실행 | `_REGION_DEFAULT_TICKER` 9개 지역 매핑 + `_run_granger_for_spec()` 내부 함수 → Type C에서 ACLED 시계열 + 지역 기본 ticker로 Granger 자동 실행 |
| P3 | Type A ticker 실패 시 PENDING 종료 | region 있으면 Type C로 자동 강등 → 대리변수 Granger 실행 |
| P4 | 두 번째 인사이트 카드 잘림 | `maxOutputTokens`: 8192 → 16384 |

### 검증 결과 (단위 테스트)

| 케이스 | 기대 | 결과 |
|--------|------|------|
| `[관찰]`만 있음 (한-미) | 거부 | `미완성: [주장] 섹션 없음` ✅ |
| H1 문장 잘림 (러-우) | 거부 | `H1 문장 미완성: '...유의하게...'` ✅ |
| 완결 카드 | 허용 | `완결` ✅ |
| `[문헌공백]` 누락 | 거부 | `미완성: [문헌공백] 섹션 없음` ✅ |

**Engine-D 변수 경로 완성:**
```
Type_C (추상 변수) + region_code 있음
  → ACLED 이벤트 시계열 + REGION_DEFAULT_TICKER → Granger 실행
  → 첫 p값 출력 가능 (러-우 세트 CL=F, 대만 세트 TSM)

Type_A ticker 미식별 + region 있음
  → var_type = Type_C 강등 → 동일 경로 진입
```

### 현재 버전
`version.json`: **6.3.0** | phase: 6

---

## ✅ 인사이트 분석 자동화 테스트 + 버그 픽스 (2026-06-04) — v6.3.1 → v6.3.2

### 자동화 테스트 인프라 구축

- `backend/tests/eval_insight.py` 신규 — 10케이스 자동 평가 스크립트
  - 백엔드 API SSE 직접 호출 → Gemini 실제 호출
  - 섹션 충족률, 신뢰도, H1 추출, Granger 상태 자동 채점
  - 503 에러 분류·재시도, 케이스 간 5초 딜레이
  - `eval_results/latest.json` 저장
- `backend/tests/eval_cases.yaml` 신규 — 10개 다양한 테스트 케이스
  - insight 6개, verify 2개, presentation 2개
  - 러-우·대만·한반도·사이버·일-한·사헬·호르무즈·북극·이란에너지·미중기술

### v6.3.1 — 테스트 과정 발견 버그 5종 수정

| # | 버그 | 수정 |
|---|------|------|
| B1 | `[문헌공백]` 3/5 케이스 누락 | 프롬프트 `### 문헌 공백 탐지` 별도 섹션 제거 + 카드 내 생략 금지 명시 |
| B2 | H1 다음줄 형식 미추출 | `_RE_H1` 정규식: `\[가설\]\n H1:` 패턴 추가 |
| B3 | verify 모드 `**H1 (주장 지지)**:` 미추출 | 정규식에 볼드+괄호 형식 추가 |
| B4 | eval `_check_h1()` 콜론 미탐지 | `H1[:：]` 문자 추가 + SSE 이벤트 존재 우선 사용 |
| B5 | `eastern_europe` region alias 미등록 | `correlation.py` `_REGION_ALIAS` 추가 |

### v6.3.2 — Granger 통계력 강화

- `hypothesis_verifier.py`: `_LOOKBACK_MONTHS` 18 → 24 (2년 데이터)
- `correlation.py`: sparse 지역(비제로<10일) 자동 주간집계 + market_series 동기화

**결과 (자동화 테스트 최종)**

| 지표 | v6.3.0 이전 | v6.3.2 이후 |
|------|------------|------------|
| 테스트 통과 | 수동 1~2개 | **10/10 PASS** |
| 섹션 100% | 불안정 | **10/10** |
| H1 추출률 | 불안정 | **6/6 케이스** |
| Granger | PENDING 전원 | **PARTIAL 5건** (Taiwan p=0.085, Ukraine p=0.145, Korean p=0.052) |
| 신뢰도 평균 | — | **70/100** |

### 자동화 테스트 실행 방법

```bash
# 전체 10케이스
backend/.venv/bin/python3 backend/tests/eval_insight.py --no-save-text

# 특정 케이스
backend/.venv/bin/python3 backend/tests/eval_insight.py --case taiwan

# 마지막 결과 재출력
backend/.venv/bin/python3 backend/tests/eval_insight.py --summary
```

### 현재 버전
`version.json`: **6.3.2** | phase: 6

---

## ✅ [Cycle 6-A] 외부 데이터 2차 적재 (2026-06-05) — v6.4.0

### 1단계 — 정형 수치 데이터 CSV 적재

**신규 파일**

| 파일 | 건수 | 내용 |
|------|------|------|
| `data/external/sipri_arms_seed.csv` | 37행 | SIPRI Arms Transfers 2020~2024 (공급국→수령국, TIV, 무기종류) |
| `data/external/vdem_seed.csv` | 42행 | V-DEM Democracy Index v14 (자유민주 지수·체제유형·부패지수) |
| `data/external/cow_wars_seed.csv` | 21행 | COW Wars DB — 한국전쟁·걸프전·러-우·이스라엘-하마스 등 주요 전쟁 선례 |
| `data/external/kiel_ukraine_support_seed.csv` | 22행 | Kiel Tracker Release 21 업데이트 (2024-06 → **2024-12**, BEL·ITA·ESP 추가) |

**신규 DB 테이블 3개** (`schema.sql` + `load_external_data.py`):
`sipri_arms_transfers` · `vdem_index` · `cow_wars`

### 2단계 — 외교부 LOD SPARQL 커넥터

**`backend/connectors/mofa_lod.py` 신규 생성**

| 항목 | 내용 |
|------|------|
| 엔드포인트 | `https://opendata.mofa.go.kr/lod/sparql` |
| 데이터셋 | IFANS 발간자료 4,174건 (2025-09까지 최신) |
| 경로 1 | ISO3→ISO2→국가 URI → relatedCountry 발간자료 |
| 경로 2 | DBpedia 이벤트 URI → owl:sameAs → relatedEvent 발간자료 |
| predicate 수정 | `bibo:abstract` · `mofadocu:relatedCountry` (온톨로지 검증 완료) |

### intel_analyzer.py 확장 (10소스 → 14소스)

| 소스 # | 이름 | 쿼리 조건 |
|--------|------|---------|
| 11 | `_get_sipri_arms` | 행위자 ISO3 supplier/recipient 매칭 |
| 12 | `_get_vdem` | 행위자 ISO3 |
| 13 | `_get_cow_wars` | 지역 relevance_tag + 행위자 ISO3 |
| 14 | `_get_ifans_publications` | 지역 DBpedia 이벤트 URI + 행위자 ISO2 |

### 검증 결과 (Gemini 미호출, 소스 레벨)

| 케이스 | Arms | VDEM | Wars | IFANS | 컨텍스트 |
|--------|------|------|------|-------|---------|
| 호르무즈 | 6건 | 2건 | 5건 | 5건 | 16,993자 |
| 북극 | 10건 | 2건 | 5건 | 4건 | 15,322자 |
| 한반도 | 4건 | 2건 | 2건 | 5건 | 16,598자 |

기존 대비 컨텍스트 +2,000~3,000자 증가. `eval_insight.py` 재실행은 Gemini rate limit 해제 후 다음 세션에서.

### 현재 버전
`version.json`: **6.4.0** | phase: 6

---

## ✅ [Cycle 6-B] Granger 통계력 강화 (2026-06-05) — v6.5.0

### 구현 내용

| 파일 | 변경 |
|------|------|
| `services/cascade/correlation.py` | `_run_granger` → AIC+min-p 하이브리드 lag 선택, F-통계량 4-tuple 반환 |
| `services/hypothesis_extractor.py` | `HypothesisSpec`에 `f_statistic` 필드 추가 |
| `services/hypothesis_verifier.py` | f_statistic 반영, `_SECTOR_DEFAULT_TICKER` 6종 추가, `_get_sector_proxy()` 신설 |
| `api/intel_query.py` | hypothesis SSE에 `f_statistic` 필드 추가 |
| `frontend/src/views/InsightAnalystView.js` | H1 카드에 `F = {f}` 표시 |

### AIC+min-p 하이브리드 lag 전략

```
1차) VAR.select_order(AIC) → 최적 lag 후보
2차) maxlag 내 min-p → 데이터에서 가장 강한 신호
→ 두 lag 중 p 값이 더 작은 쪽 선택 (통계적 정당성 + 민감도)
```

### Cycle 6-B 실측 결과 (2년 데이터, 2024-01~2026-06)

| 케이스 | 이전 | 이후 | |
|--------|------|------|--|
| 한반도 → KRW | PENDING (p=0.052) | **VERIFIED ✅ (p=0.048, F=3.05, lag=2)** | 목표 달성 |
| 대만 → TSMC | PARTIAL (p=0.085) | PARTIAL 🔶 (p=0.067, F=2.389, lag=3) | 개선 |
| 우크라이나 → WTI | PENDING | PARTIAL 🔶 (p=0.146, F=2.123, lag=1) | 개선 |
| 바브엘만데브 → WTI | PENDING | PENDING (p=0.157) | 유지 |

### 사이버 섹터 proxy (`_SECTOR_DEFAULT_TICKER`)

| 섹터 | ticker | 근거 |
|------|--------|------|
| `cyber` | ITA | 사이버 공격 → 방산투자 반응 |
| `techno` | SOXX | 기술 패권 → 반도체 ETF |
| `maritime` | CL=F | SLOC 차단 → 에너지 프리미엄 |
| `energy` | CL=F | 에너지 충격 직접 |
| `indo_pacific` | TSM | 대만해협 긴장 → TSMC |
| `gray_zone` | GLD | 불확실성 → 안전자산 |

### §22-C 체크리스트 업데이트

```
✅ IA-Engine-D: 최소 1개 H1에 Granger r값·p값 자동 산출
   → 한반도 VERIFIED p=0.048, F=3.05 달성
```

### 현재 버전
`version.json`: **6.5.0** | phase: 6

---

## ✅ [Cycle 6-C] H1 생성 품질 고도화 (2026-06-05) — v6.6.0

### 구현 내용

| 파일 | 변경 |
|------|------|
| `api/intel_query.py` | [UNVERIFIED] 규칙 명확화 — context 데이터는 태그 없이 인용 가능 |
| `api/intel_query.py` | H1 측정 가능성 강제 — X/Y는 정량 지표, 불가 시 선택 생략 |
| `api/intel_query.py` | 카드 2개 제한 (깊이 > 넓이) |
| `services/intel_analyzer.py` | SIPRI Arms 섹터 필터 — techno/cyber 전용 쿼리에 Arms 미주입 |

### 반복 디버깅 과정

| 시도 | UNVERIFIED | 문제 |
|------|-----------|------|
| v6.4.0 (6-A) | 39건 | Arms 데이터가 무관 쿼리에 주입 → 일본-한국 4→11 |
| v6.5.0C1 (카드2개 강제) | 42건 | 카드 수 제한이 역효과, 솔트타이푼 완전 실패 |
| v6.5.0C2 (섹터 필터) | 33건 | china_cyber_us 실패 지속 |
| **v6.6.0 (최종)** | **20건** | H1 선택적 + 섹터 필터 조합 |

### 최종 eval 결과 (v6.6.0)

| 케이스 | 기준(v6.3.2) | 최종 | 변화 |
|--------|------------|------|------|
| 러-우 에너지 | 5 | 0 | ✅ -5 |
| 사헬 | 3 | 0 | ✅ -3 |
| 호르무즈 | 4 | 0 | ✅ -4 |
| 북극 | 21 | 14 | ✅ -7 |
| 일본-한국 기술 | 4 | 5 | ❌ +1 |
| **합계** | **37** | **20** | **-17 (-46%)** |

평균 신뢰도: 70→**71** (+1) | H1 수: 23→**19**개 | 응답 시간: 46s→**35s**

### 현재 버전
`version.json`: **6.6.0** | phase: 6

---

## ✅ [Cycle 7-A] 이론 라이브러리 구조화 (2026-06-05) — v7.0.0

### 구현 내용

**목표**: 12개 이론에 예측변수·반례·경쟁이론 프론트매터 추가 → Gemini가 이론을 "레이블"이 아닌 "예측 도구"로 사용

**신규 DB 필드 6개** (`md_indexer.py` 스키마 + 마이그레이션 + INSERT):

| 필드 | 내용 |
|------|------|
| `independent_var` | 독립변수 (측정 가능 지표) |
| `dependent_var` | 종속변수 (측정 가능 지표) |
| `conditions` | 적용 조건 (JSON 배열) |
| `falsifiable_prediction` | 반증 가능 예측 명제 |
| `known_counterexample` | 알려진 반례 |
| `rival_theories` | 경쟁 이론 목록 (JSON 배열) |

**이론 파일 작업 (12개)**:

기존 8개 파일 프론트매터 업데이트:
- `mahan_sea_power.md` — IV: 해군력 투자 %GDP, 반례: A2/AD 비용 상승
- `weaponized_interdependence.md` — IV: 공급망 HHI, 반례: 유럽 가스 다변화
- `resource_weaponization.md` — IV: 에너지 의존도 %, 반례: 셰일 혁명
- `alliance_theory.md` — IV: 조약 강도 pact_intensity, 반례: 아프간 철수
- `hybrid_warfare.md` — IV: 비정규전 혼합 지수, 반례: 러-우 정규전 확전
- `a2ad_strategy.md` — IV: A2/AD 배치 밀도, 반례: 드론 비용 역전
- `digital_iron_curtain.md` — IV: 차단 지수, 반례: 중국 AI 글로벌 침투
- `gray_zone_strategy.md` — IV: 강압 행동 빈도/월, 반례: ASEAN 결속 강화

신규 4개 파일 생성:
- `library/04_indo_pacific/mearsheimer_offensive_realism.md` — 공격적 현실주의, 권력 극대화·지역 패권
- `library/04_indo_pacific/waltz_defensive_realism.md` — 방어적 현실주의·3수준 분석
- `library/06_cyber/libicki_cyber_deterrence.md` — 사이버 억지, 귀속 불확실성
- `library/00_methods/granger_causality.md` — Granger 인과분석 방법론

**intel_analyzer.py 확장**:
- SELECT 쿼리에 6개 신규 필드 추가
- `_build_context()`에 `## 이론 프로파일 (예측 도구)` 섹션 신규 추가
  - `asset_type=theory` + `independent_var` 있는 항목 최대 4개
  - IV·DV·반증 예측·반례·경쟁이론 구조화 출력 → Gemini 경쟁 이론 비교에 직접 활용

**검증 결과**:
- md_indexer 재실행: 94건 upserted, 0건 skipped/error
- `independent_var` 있는 이론 DB 조회: **12건** ✅
- 샘플 확인: Mahan·Weaponized Interdependence·Granger 등 정상 저장

**이론 연결**: §11 Phase 7-A 목표 — 이론을 텍스트 레이블에서 예측 도구로 전환.
Gemini가 이제 "Farrell&Newman 예측: HHI 증가 → 양보 증가 vs 실측: 유럽 가스 다변화 성공" 형태의 수치 편차 비교 가능.

### 현재 버전
`version.json`: **7.0.0** | phase: 7

---

## ✅ [Cycle 7-B] 경쟁 이론 비교 엔진 (2026-06-05) — v7.1.0

### 구현 내용

**신규 파일: `backend/services/theory_comparator.py`**

- `build_theory_comparison_context(sectors, regions, actors) -> str`
  - 섹터/지역 → 관련 이론 쌍 결정론적 선택 (6개 섹터·7개 지역 매핑 테이블)
  - 각 이론 프로파일 DB 조회 (IV·DV·반증 예측·반례·경쟁이론)
  - 이론별 실측값 조회 (SIPRI milex·Arms HHI·EIA 초크포인트·ACLED 건수·V-DEM)
  - "예측: [방향] / 실측: [수치] / 판정 요청" 형태 비교 텍스트 생성

**섹터-이론 쌍 매핑:**

| 섹터/지역 | 메인 이론 | 경쟁 이론 |
|-----------|---------|---------|
| energy | Weaponized Interdependence | Resource Weaponization |
| maritime | Mahan | A2AD |
| techno | Digital Iron Curtain | Weaponized Interdependence |
| indo_pacific | Mearsheimer | Waltz |
| gray_zone | Gray Zone | Hybrid Warfare |
| cyber | Libicki | Digital Iron Curtain |
| taiwan_strait | Mearsheimer | Mahan |
| hormuz | Resource Weaponization | Weaponized Interdependence |
| eastern_europe | Waltz | Hybrid Warfare |
| korean_peninsula | Alliance Theory | Mearsheimer |

**intel_analyzer.py 확장** (소스 #15):
- `build_theory_comparison_context()` gather 병렬 추가
- `context_text`에 이론 비교 섹션 후위 결합

**intel_query.py 프롬프트 강화:**
- 원칙 4번에 `★ 경쟁 이론 비교 프로파일 활용 지침` 추가
- [경쟁설명] 형식: `예측: [방향] / 실측: [수치] / 편차: [차이] / 우세: [이론명]`
- 수사적 기각 금지 — 수치 근거로 판정 의무화

**검증 결과:**
- 호르무즈: theory_cmp_chars=1370자, 컨텍스트 15278자 ✅
- 대만해협: Mearsheimer·Waltz·Mahan 3이론 동시 비교 ✅
- 사이버: Libicki + Digital Iron Curtain 비교 ✅
- 임포트 체인 전체 정상 ✅

### 현재 버전
`version.json`: **7.1.0** | phase: 7

---

## ✅ [Cycle 7-C] 자동화 테스트 20케이스 확장 + 종합 평가 (2026-06-05) — v7.2.0

### 구현 내용

**eval_cases.yaml — 케이스 10개 추가 (총 20개):**

| # | ID | 섹터 | 모드 |
|---|----|----|------|
| 11 | hormuz_iran_blockade | energy | insight |
| 12 | russia_china_arctic_control | gray_zone | insight |
| 13 | pla_taiwan_a2ad | indo_pacific+maritime | insight |
| 14 | houthi_red_sea_sloc | maritime | insight |
| 15 | salt_typhoon_cyber_deterrence | cyber | verify |
| 16 | china_ai_export_ban | techno | insight |
| 17 | ukraine_drone_innovation | gray_zone | verify |
| 18 | india_indo_pacific_balancing | indo_pacific | insight |
| 19 | iran_russia_tactic_transfer | gray_zone+cyber | presentation |
| 20 | mearsheimer_vs_liberal_taiwan | indo_pacific | verify |

**eval_insight.py 개선:**
- `_check_rival_comparison()` 신규 — 엄격(예측+실측 레이블) + 완화(이론2개+수치+판정) 2단계 채점
- `_diagnosis()`에 경쟁이론 수치 비교 충족률 통계 추가
- 503 재시도 1회 → 2회 (30초, 60초 간격)

### 최종 결과 (v7.2.0 기준, 오류 제외 17케이스)

| 지표 | 결과 | Phase 7 목표 |
|------|------|------------|
| PASS율 | **14/17 = 82%** (오류 3건 제외) | — |
| 평균 신뢰도 | **70/100** | 85+ ❌ |
| Granger VERIFIED | **2건** (한반도 p=0.048 + 북극 p=0.049) | 3건+ △ |
| 경쟁이론 수치 비교 | **0% 엄격 / 10% 완화** | 50%+ ❌ |
| H1 추출률 | **12/12 = 100%** | — |

### 목표 미달 원인 분석

**신뢰도 70 (목표 85+):**
- 현재 평균 75점대 케이스가 다수 (수치 인용 OK, H1 OK, 경쟁이론 일부)
- 전체 신뢰도 상한은 Gemini 응답 품질에 달려 있어 즉각 개선 어려움
- Phase 7 데이터/구조 개선만으로는 15점 상향 불가 — 지속적 데이터 누적 필요

**경쟁이론 수치 비교 0%:**
- 7-B에서 `예측:` `실측:` 레이블 형식을 프롬프트에 명시했으나
- Gemini가 정확한 레이블 없이 자유 서술로 경쟁이론 비교 → 자동 채점 miss
- 실제 응답에는 이론 비교가 포함되지만 형식 불일치로 미탐지 (구조적 gap)

### Phase 7 총합 달성 현황

| Cycle | 항목 | 상태 |
|-------|------|------|
| 7-A | 12개 이론 프론트매터 구조화 (IV·DV·반례·경쟁이론) | ✅ v7.0.0 |
| 7-B | 경쟁 이론 비교 엔진 — 섹터/지역 기반 이론쌍 선택 + 실측값 컨텍스트 | ✅ v7.1.0 |
| 7-C | 20케이스 확장 + rival_check 채점 + 503 재시도 강화 | ✅ v7.2.0 |

**§22-C 박사 수준 체크리스트 업데이트:**
```
✅ 시간 역전 오류 [TEMPORAL_REVERSAL] 탐지 (v6.0)
✅ ACLED 대만해협 이벤트 필터 수정 (v6.1.1)
✅ UNVERIFIED 평균 <1건/케이스 (v6.4.0 Phase 6-A)
✅ Granger VERIFIED 2건: 한반도 p=0.048 + 북극 p=0.049 (v6.5.0 + v7.2.0)
□  H1 Type_A/B 비율 50%+ → Phase 7 잔여 과제
□  경쟁이론 수치 편차 비교 50%+ → 프롬프트 형식 gap 해소 필요
□  신뢰도 평균 85+ → 데이터 누적·품질 향상 필요
```

### 현재 버전
`version.json`: **7.2.0** | phase: 7

---

## 다음 세션 시작점 (2026-06-05 세션 이후)

### 현재 지표 (v6.6.0, 2026-06-05 최종)

| 지표 | 세션 전(v6.3.2) | 현재(v6.6.0) | Phase 6 목표 | Phase 7 목표 |
|------|--------------|------------|------------|------------|
| 신뢰도 평균 | 70/100 | **71/100** | 78+ | 85+ |
| Granger VERIFIED | 0건 | **1건** (한반도 p=0.048, F=3.05) | 1건+ ✅ | 3건+ |
| UNVERIFIED 합계 | 37건 | **20건** (-46%) | — | — |
| 응답 시간 | 46s | **35s** | — | — |

### Phase 6 완료 현황

| Cycle | 항목 | 상태 |
|-------|------|------|
| 6-A | 외부 데이터 2차 적재 (SIPRI Arms·V-DEM·COW Wars·Kiel 2025·외교부 LOD) | ✅ v6.4.0 |
| 6-B | Granger 통계력 강화 (AIC lag·F-통계량·사이버 proxy) | ✅ v6.5.0 |
| 6-C | H1 품질 고도화 + SIPRI Arms 섹터 필터 + [UNVERIFIED] 규칙 개선 | ✅ v6.6.0 |

### Phase 7 완료 현황

| Cycle | 항목 | 핵심 파일 | 상태 |
|-------|------|---------|------|
| **7-A** | 이론 라이브러리 구조화 — 12개 이론 예측변수·반례 프론트매터 추가 | `library/` 마크다운 + `intel_analyzer.py` | ✅ v7.0.0 |
| **7-B** | 경쟁 이론 비교 엔진 — 섹터/지역 기반 이론 쌍 선택 + 예측값 vs 실측값 편차 컨텍스트 | `theory_comparator.py` + `intel_analyzer.py` + 프롬프트 | ✅ v7.1.0 |
| **7-C** | 20케이스 확장 + rival_check 채점 + 종합 평가 | `eval_insight.py` + `eval_cases.yaml` | ✅ v7.2.0 |

### 잔여 과제 (Phase 7 미달 항목 → 지속 개선)

| 항목 | 현재 | 목표 | 방향 |
|------|------|------|------|
| 신뢰도 평균 | 70 | 85+ | 데이터 누적·프롬프트 지속 개선 |
| 경쟁이론 수치 비교 | 0~10% | 50%+ | [경쟁설명] 형식 gap 해소 |
| Granger VERIFIED | 2건 | 3건+ | 더 많은 케이스 누적 |

### 다음 작업: Phase 7-D L2/L3 — 데이터 품질 대폭 강화 (계속)

**게이트**: 신뢰도 85+ + 경쟁이론 50%+ 동시 달성 → Phase 8 착수

---

## ✅ [Cycle 7-D L1] 데이터 대량 적재 + 버그 수정 (2026-06-06) — v7.3.1

### 7-D-X: [경쟁설명] 프롬프트 형식 gap 해소
- `intel_query.py` system_role에 구체적 예시 고정 삽입
- 예측:/실측:/판정: 레이블 + 자원무기화 실제 예시
- 결과: 경쟁이론 수치 비교 **0% → 100%** (엄격, 13/13 케이스)

### 7-D-7: SIA 반도체·기술 시장 데이터
- `semi_market_seed.csv` — 30행 (파운드리 점유율·HHI·희토류·EUV·CHIPS Act)
- TSMC 61.7%, HHI 3920, 갈륨 중국 80%, ASML 100% 독점

### 7-D-8: CSIS Cyber DB 20→68건 확장
- `csis_cyber_extended_seed.csv` — 2006~2024 주요 APT 전수 (estimated_damage_usd 포함)
- Stuxnet $10억, NotPetya $100억, SolarWinds $1,000억 피해 수치화

### 7-D-1: FRED 경제 시계열
- `fred_seed.csv` — 48행 (WTI·Brent·유럽가스·환율·금·미 국방비 2020~2024)

### 7-D-2: World Bank WGI 거버넌스 지수
- `world_bank_seed.csv` — 28행 (20개국 6지표, 사헬·북극 gray_zone 공백 해소)
- 말리 -2.37, 니제르 -2.56, 부르키나파소 -2.91 수치화

### 7-D-4: Polity5 정치체제 지수
- `polity5_seed.csv` — 39행 (39개국 -10~+10 체제 분류)

### 7-D-5: ITU ICT 개발 지수
- `itu_ict_seed.csv` — 40행 (사이버 역량 티어 1~4 분류)

### 7-D-6: HIIK 분쟁 강도 바로미터
- `hiik_conflict_seed.csv` — 30행 (1~5 강도 척도, 2023~2024)

### 인프라 확장
- `load_external_data.py`: 6개 신규 테이블 + 로더 (14소스 전체)
- `intel_analyzer.py`: 소스 15→21개 병렬 gather (FRED/WBK/Polity5/ITU/HIIK/SIA)
- `csis_cyber_incidents`: estimated_damage_usd 컬럼 마이그레이션

### 버그 수정 (v7.3.1)
- `entity_parser.py`: cyber 섹터 키워드 16개 추가 (억지·귀속·Libicki·APT 그룹명)
- `entity_parser.py`: APT 귀속 키워드 ACTOR_ALIASES 추가 + PRK 중복 정의 제거
- `intel_analyzer.py`: `_get_csis_incidents` techno 섹터 fallback 추가

### eval 결과 (v7.3.1 최종, 20케이스)

| 지표 | v7.2.0 | v7.3.0 | v7.3.1 | 목표 |
|------|--------|--------|--------|------|
| PASS율 | 82% | 95% | **100%** ✅ | — |
| 신뢰도 평균 | 70 | 67 | **71** | 85+ |
| 경쟁이론 [엄격] | 0% | 100% | **100%** ✅ | 50%+ |
| H1 추출률 | 100% | 92% | **100%** ✅ | — |
| PROVISIONAL | 3건 | 1건 | **0건** ✅ | — |
| Granger VERIFIED | 2건 | 2건 | **1건** (PARTIAL 7건) | 3건+ |

### 7-D L1 상태 (2026-06-06 기준)

| Sub | 항목 | 상태 |
|-----|------|------|
| 7-D-X | [경쟁설명] 형식 gap 해소 | ✅ v7.3.0 |
| 7-D-1 | FRED 경제 시계열 | ✅ v7.3.0 |
| 7-D-2 | World Bank WGI | ✅ v7.3.0 |
| 7-D-4 | Polity5 정치체제 | ✅ v7.3.0 |
| 7-D-5 | ITU ICT 개발 지수 | ✅ v7.3.0 |
| 7-D-6 | HIIK 분쟁 강도 | ✅ v7.3.0 |
| 7-D-7 | SIA 반도체 시장 | ✅ v7.3.0 |
| 7-D-8 | CSIS Cyber DB 확장 | ✅ v7.3.0 |
| 7-D-3 | Our World in Data | ⬜ L1 잔여 |

---

## 🎯 학술 정합성 재설계 (2026-06-06 결정) — 목표 전환

**방향 전환**: "신뢰도 숫자 81→85" → **"§19 원칙과 일치 + 인과추론 사다리 정직 표시"**

### 배경: Granger 과대주장 진단

검증층이 "Granger p<0.05 → VERIFIED"라 부르나, Granger는 *예측적 선행성*이지
구조적 인과가 아님. 이는 프로젝트 자신의 §19-C("수치 근거 없는 인과 주장 금지")와 충돌.
데이터 종합·이론 비교층은 견실하나 **인과 검증층이 방법의 한계를 초과 주장**.

### 학술 위반 → 해결 매핑

**Phase A — 정직성 재설계 (숫자보다 우선)**

| ID | 위반 | 해결 |
|----|------|------|
| A1 | 신뢰도가 *근거 충실도*와 *인과 검증*을 한 숫자로 혼동 (Goodhart) | **2축 분리**: 증거 등급(0-100) + 추론 등급(사다리 레이블) |
| A2 | Granger ≠ 인과인데 "VERIFIED" | **인과추론 사다리**: 기술적→상관→선행성(Granger)→준실험→실험. Granger=3번째 칸 "선행성(인과 아님·교란 미통제)" |
| A3 | 허위 쌍 보고 (사헬→GLD p=0.72) | 이론 근거 없는 쌍은 "상관" 칸 상한 + 허위상관 경고 |

**Phase B — 계량 가드 (Granger를 방어가능 증거로)**

| ID | 위반 | 해결 |
|----|------|------|
| B1 | 비정상 시계열 → 허위회귀 (Granger-Newbold 1974) | `adfuller` 단위근 검정 → 비정상 시 차분 |
| B2 | min-p lag 선택=명세탐색 / 다중검정 미보정 | lag AIC만 사전고정(min-p 폐기) + 가설 다수 시 Benjamini-Hochberg FDR |
| B3 | 양변량=교란 미통제 | 통제변수 ≥1(VIX·유가) → 조건부 Granger/VAR (차기) |
| B4 | EMH상 시장 lag Granger는 null 기대 | 사건→사건·저빈도 구조변수 (차기) |

**Phase C — 진짜 학술 척도 (형식→참)**

| ID | 위반 | 해결 |
|----|------|------|
| C1 | eval이 형식 준수만 측정 | 비자명성 + 출처 일관성 채점 (차기) |
| C2 | 20케이스 과적합 | 케이스 30+ / N회 median (차기) |

### 이번 세션 범위: A1·A2·A3 + B1·B2(FDR 포함)

차기: B3(조건부 Granger)·B4(사건→사건)·C(질적 평가).

**불편한 진실**: 정직 격하로 VERIFIED가 줄어 신뢰도 숫자가 **내려갈 수 있음** — 후퇴가
아니라 학술적 성숙. "도구가 자기 주장의 한계를 정확히 아는가"가 새 목표.

> ⚠️ 이전 P1~P5(숫자 중심) 계획은 본 학술 재설계로 **대체**됨.

---

## ✅ [학술 정합성 재설계 A1·A2·A3 + B1·B2] 완료 (2026-06-06) — v7.5.0

### 결과: 2축 분리 — 증거 등급 93 / 추론 등급 정직 표시

| 축 | 결과 | 의미 |
|----|------|------|
| **증거 등급** (grounding) | 평균 **93**/100 | 데이터·이론 충실도 — 인과 아님 |
| **추론 등급** (causal ladder) | 선행성 **0** / 상관 **4** / 기술적 **16** (/20) | 인과추론 사다리 정직 분포 |

**핵심 발견**: 엄밀 가드(정상성·AIC·FDR) 적용 후 **선행성(precedence) 0/20**.
이전 "VERIFIED 2건"(한반도 p=0.048 등)은 **명세탐색(min-p)·비정상성의 산물**이었음 —
적절한 차분 + AIC 사전고정 + FDR 보정 시 p=0.048 → 0.10 수준으로 상승, 유의성 소멸.
geopolitics→market 일별 Granger는 대부분 null (EMH·허위상관 비판이 옳았음을 실증).

### 구현 내역

**Phase A — 정직성 재설계**
| ID | 파일 | 변경 |
|----|------|------|
| A1 | `intel_query.py` · `confidence_scorer.py` | verification_cap 폐기. 증거 등급 ↔ 추론 등급 2축 분리 (Goodhart 결함 제거) |
| A2 | `hypothesis_verifier.py` | 인과추론 사다리 `기술적<상관<선행성`. "VERIFIED" 어휘 격하. 모든 결과에 "예측적 선행·인과 아님·교란 미통제" 단서 |
| A3 | `hypothesis_verifier.py` | 이론근거 화이트리스트 15쌍. 근거 없는 쌍(사헬→GLD)은 유의해도 '상관' 상한 + 허위상관 경고 |

**Phase B — 계량 가드**
| ID | 파일 | 변경 |
|----|------|------|
| B1 | `correlation.py` `_run_granger` | ADF 정상성 검정 → **컬럼별 독립 1차 차분** (Granger-Newbold 1974 허위회귀 방지) |
| B2 | `correlation.py` · `hypothesis_verifier.py` | lag=AIC 사전고정(min-p 폐기) + Benjamini-Hochberg FDR(q값) |

**부수 수정**: `_run_granger` 5-tuple 반환(meta 포함) → correlation.py 484·635 잠재
3-tuple 언팩 버그 동시 수정. `eval_insight.py` 2축 보고(추론 등급 분포) 추가.

### eval 지표 (v7.5.0, 20케이스)

| 지표 | v7.4.0 | v7.5.0 | 비고 |
|------|--------|--------|------|
| PASS율 | 20/20 | 20/20 | 유지 |
| 증거 등급 평균 | 81(혼합) | **93** | 캡 제거로 근거 충실도 직접 노출 |
| 추론: 선행성 | (VERIFIED 2) | **0** | 엄밀 가드로 허위 유의 제거 |
| 추론: 상관 | — | **4** | 경향성 수준 |
| 추론: 기술적 | — | **16** | 서술·이론 근거만 |
| 경쟁이론 [엄격] | 100% | 100% | 유지 |

### 학술적 의미

도구가 **자기 주장의 한계를 정확히 알게 됨**. "VERIFIED 인과"를 번쩍이는 대신
"증거는 충실하나 인과는 상관·서술 수준"이라고 정직하게 2축 표기. §19-C(수치 근거 없는
인과 주장 금지) 원칙과 일치. 학습 도구로서 *인과추론 방법론(Granger≠인과)을 시연*.

### 차기 (학술 정합 잔여)

| ID | 항목 | 상태 |
|----|------|------|
| C1 | eval 질적 평가 (LLM 심판 4축) | ✅ v7.7.0 |
| C2 | 케이스 20→30 + 사건→사건 전이 | ✅ v7.7.0 |
| A2+ | 프론트 UI 2축 표시 (사다리 뱃지) | ✅ v7.6.1 |
| C2+ | N회 median (확률성 완화) | ⬜ 차기 |

---

## ✅ [일본↔east_china_sea 지역 매핑] 완료 (2026-06-07) — v7.8.4

### 배경: 일본 쿼리가 항상 '📍 전체, 0지역' → Granger 검정 불가

`일본`이 entity_parser에서 행위자(JPN)로만 잡히고 **지역으로는 미인식**(east_china_sea
키워드에 센카쿠·동중국해만 있고 일본 없음). 그래서 일본 H1이 region=None → 검정 경로 못 탐.

### 진단 (east_china_sea는 인프라에 이미 존재)

- event_archive에 east_china_sea **767건** (Granger 충분)
- `(east_china_sea, ITA)`는 이미 이론근거 쌍, ITA는 로컬 FRED 캐시(defense_etf) 보유
- 단 `_REGION_DEFAULT_TICKER`·entity_parser·hypothesis_extractor에 일본 연결 누락

### 구현 (5개 매핑 일관 추가)

| 파일 | 변경 |
|------|------|
| `entity_parser.py` | east_china_sea 지역 키워드에 일본·japan·자위대·jsdf 추가 → 일본 쿼리가 region 감지 |
| `hypothesis_extractor.py` | `_REGION_MAP`에 east_china_sea 행 신설 (H1 텍스트 직접 매핑) |
| `hypothesis_verifier.py` | `_REGION_DEFAULT_TICKER["east_china_sea"]="ITA"` (검정용 기본 ticker) |
| `theory_comparator.py` | 이론쌍(Mahan+Mearsheimer)·FRED(EXJPUS 엔/달러)·ACLED(Japan,China) 추가 |
| (intel_analyzer) | OWID 군사비 비교는 이미 east_china_sea 보유 — 변경 불필요 |

### 검증 (함수 단위)

- `parse_query('일본 인사이트')` → regions=['east_china_sea'] actors=['JPN'] (이전 [])
- 일본 H1(광물→방위 생산비) → 이전 '검정 불가' → 지금 **east_china_sea→ITA Granger 실행**
  (p=0.2013, F=1.456, lag=5, n=488). p≥0.15라 '기술적' 등급이나 검정 경로는 열림.

---

## ✅ [AR-3 측정 가드레일 — 심판 절단버그 수정 + 루브릭 앵커링] 완료 (2026-06-07) — v7.8.7

### ⚠️ 측정자 불연속 — 비교 기준선 재설정

이 변경으로 LLM 심판 점수의 **측정 방식이 바뀜**. 따라서:
- **v7.8.6까지** (옛 루브릭, 6000자 절단): v7.8.0(종합 2.62)과 비교 가능 — AR-1a+AR-2 효과 측정용
- **v7.8.7부터** (앵커 루브릭, 12000자): 새 기준선. 이전 점수와 직접 비교 불가

### 발견: 심판 절단 버그 (측정 신뢰성 훼손)

- 인사이트 평균 5960자 / 최대 11051자 (2장 구조)인데 심판은 `full_text[:6000]`만 채점
- **29건 중 9건(31%)이 6000자 초과** → 늦게 나오는 [경쟁설명]·[문헌공백] 잘림
- → 해당 케이스 체계적 저평가 + 노이즈 (절단점이 케이스마다 달라짐)
- 이것이 추론정직성 2.70→2.42 같은 ±0.3 변산의 한 원인으로 추정

### 구현 (`tests/eval_insight.py`)

| 변경 | 내용 |
|------|------|
| 절단 한도 | 6000 → **12000자** (인사이트 전문 커버) |
| 루브릭 앵커링 | 1·5점만 정의 → **5단계 전부** 구체 기준 고정 (보간 변산 축소) |

### 측정 원칙 (메모리 정합)
심판은 프록시일 뿐(정직성 > 점수). 앵커링은 점수를 올리려는 게 아니라 **같은 출력에 같은 점수**가 나오게 해 개선의 신호/노이즈 분리를 돕는 가드레일.

---

## ✅ [AR-2 추론 사다리 — 직접검정 시계열 확장] 완료 (2026-06-07) — v7.8.6

### 원칙: 사다리를 부풀리지 않고 **정확하게** 만든다 (정직성 우선)

지정학→시장 관계는 본질적으로 약해 대부분 상관/기술적이 맞다. AR-2는 (1) 테스트 가능한
H1을 빠짐없이 **올바른 변수**로 검정하고 (2) 정당하게 유의하면 선행성에 도달하게 한다.

### 진단: 적재됐으나 미사용이던 일별 시계열 3종

`historical_macro_indices`에 일별 3년치 시계열 10종 적재돼 있으나 **brent·usd_twd·vix**가 매핑 누락 → 사용 불가였음.

### 구현 (Change 1·2·4 — Change 3은 위험 대비 이득 낮아 제외)

| 변경 | 내용 |
|------|------|
| correlation `_TICKER_TO_FRED` | BZ=F→brent, TWD=X→usd_twd, ^VIX→vix 추가 |
| extractor `_TICKER_MAP` | Brent·대만달러(TWD)·위안(CNY)·엔(JPY) 키워드 매핑 신설. 일반 'oil'보다 먼저 배치(first-match) |
| verifier `_THEORY_GROUNDED_PAIRS` | (taiwan_strait,TWD=X)·(eastern_europe/ukraine/hormuz/bab_el_mandeb, BZ=F) 추가 |
| 안전장치 | VIX는 통제변수 전용 — 종속 매핑 제외(조건부 Granger 퇴화 방지) |

### 검증 결과 (함수 단위)

**신규 선행성 케이스 발굴:**
- 대만해협 분쟁 → 대만 달러(TWD): **p=0.0005, n=483, 교란통제(VIX), 이론근거 → 선행성** ✅
  (이전엔 TWD 매핑 부재로 검정 불가/TSM 대체). 지정학 리스크 프리미엄 메커니즘.
- 호르무즈 → Brent: p=0.8883 → 기술적 (정직 — 이 윈도우에선 비유의)

**회귀 없음:** korea(KRW=X p=0.106 상관) · russia(CL=F p=0.537 기술적) · japan(ITA p=0.2013 기술적) 모두 동일 유지. AR-2는 신규 직접검정 경로만 추가.

### Change 3 제외 사유
Type_A→C 강등은 ticker=None일 때만 발생(우선할 추출 ticker 없음), 순수 Type_C에 구체 ticker 동시추출은 드묾 → 위험 대비 이득 낮음. 진짜 레버는 Change 1+2(매핑 확장→추출 성공률↑→Type_A 직접검정 유지)로 달성.

---

## ✅ [AR-1a 기존 데이터 완전 연결] 완료 (2026-06-07) — v7.8.5

### 핵심: DB에 이미 있던 4개 데이터를 theory_comparator 이론별 실측값으로 연결

신규 적재 0, 코드 연결만으로 경쟁이론 실측 라인 대폭 확충.

| 데이터 | 연결된 이론 | 실측 메시지 예시 |
|--------|-----------|----------------|
| **Polity5** (-10~+10) | mearsheimer·waltz | "CHN: Polity -7(autocracy) / JPN: +10(democracy) [Waltz 예측: +7이상=현상유지]" |
| **HIIK 분쟁강도** (1~5) | gray_zone·hybrid | "Sahel-Mali 강도4(제한전쟁) [Gray Zone 예측: 강도1~3 / Hybrid: 3~4]" |
| **ITU IDI** (ICT 발전지수) | libicki·digital_iron_curtain | "China IDI 71.5(50위) / USA IDI 87.0(15위) [Libicki: IDI↑→귀속능력↑]" |
| **OWID 군비·핵탄두** | mahan·a2ad·mearsheimer·waltz | "China 1.6%GDP 핵410기 / USA 3.3%GDP 핵3748기 / Japan 1.1%GDP" |

### 실측 라인 증가 (이전→이후)
- 동중국해(indo_pacific): ~6개 → **10개** (+OWID 군비·핵탄두 + Polity5)
- 사헬(gray_zone): ~4개 → **10개** (+HIIK 강도4 실측 추가)
- 대만(techno): ~10개 → **14개** (+ITU IDI + 강화된 OWID)

### 코드 변경
- `theory_comparator.py`: `_get_polity5`, `_get_hiik_conflict`, `_get_itu_ict_for_theories`, `_get_owid_military` 함수 4개 신설
- `build_theory_comparison_context`: 4개 함수 호출 + 이론별 실측 블록에 연결

### 검증 (함수 단위)
- 3개 지역 × 이론쌍 테스트 통과, 실측 라인 수치 정확 확인

---

## ✅ [검정불가 정보가치 + ITU 라벨 교정 + 고유명사 귀속] 완료 (2026-06-06) — v7.8.3

### 배경: 일본 인사이트 평가 피드백

평가가 3가지 지적. 1건은 평가가 틀렸고(환각 아님), 2건은 타당해 반영.

### 평가 검증 결과

| 평가 지적 | 사실 확인 | 조치 |
|----------|----------|------|
| "Operation Epic Fury 환각" | ❌ **환각 아님** — War on the Rocks 실제 기사 제목으로 briefing_queue.yaml에 존재 | 환각 게이트 대신 **오귀속 방지** 규칙 추가 (작전명을 다른 사건과 등치 금지) |
| ITU IDI 오용 (사이버 방어력 아님) | ✅ 타당 — IDI는 ICT 보급·접근성 지표 | 라벨 '사이버 역량 지수'→'ICT 발전 지수' + GCI/NCSI가 더 타당하다는 경고 |
| ticker 없는 검정 불가 정보가치 낮음 | ✅ 타당 | 미실행 분기마다 `inference_caveat`에 구체 사유+해결책 |

### 구현

| 파일 | 변경 |
|------|------|
| `intel_query.py` | 고유명사 귀속 규칙 — context 고유명사를 별개 사건 명칭으로 단정 금지 |
| `intel_analyzer.py` | ITU IDI 라벨 교정 + 사이버 방어력 직접근거 부적합 경고 |
| `hypothesis_verifier.py` | Type_B·Type_C·Type_A 미실행 분기에 `inference_caveat` 구체 사유 채움 (프론트는 이미 렌더) |

### 검증 (함수 단위)

일본 H1(사이버 공격 건수, region 없음) → 이전 일반문구 대신:
"검정 불가 — 종속변수가 '건수·빈도'(행동변수)이나 집계 지역 미식별. H1에 지역(예: '동중국해 분쟁 건수')과 집계 출처(ACLED/CSIS) 명시 필요."

### 남은 과제 (별도)

- `일본/Japan`이 `_REGION_MAP`에 없음 → 일본 쿼리는 항상 region 0지역. entity_parser/region 매핑에 일본↔east_china_sea 추가 검토 (이번 범위 밖)

---

## ✅ [Granger 변수 매핑 버그 수정 + 룰점수 라벨 교정] 완료 (2026-06-06) — v7.8.2

### 핵심: H1 선언 변수 ≠ 실제 검정 변수 버그 (한반도 인사이트 평가에서 발견)

한반도 인사이트 2의 H1은 'korean_peninsula + 원/달러(KRW/USD)'인데 실제 Granger는
**`middle_east → ITA`**로 검정됨 — 지역·티커 둘 다 틀림. 공유 즉시 신뢰 상실하는 버그.

### 근본 원인 (트레이스 확정)

1. H1이 '중국 광물 → 원/달러'라 지역명(한반도/북한)을 직접 안 씀 → `region_code=None`
2. 추출기는 `ticker=KRW=X`를 **정확히** 뽑았으나, region=None이라 정상 경로 못 탐
3. 섹터 proxy 폴백으로 빠짐 → H1의 '사이버' 키워드 → `ticker=ITA`로 **덮어쓰기** + `region="middle_east"` **하드코딩**

### 수정 (`hypothesis_extractor.py` · `hypothesis_verifier.py` · `intel_query.py`)

| Fix | 변경 |
|-----|------|
| **지역 상속** | `extract_hypotheses(text, default_regions)` — H1에 지역명 없으면 쿼리 지역(pq.regions) 상속. `_stream_gemini`에 pq.regions 전달 |
| **ticker 보존** | 섹터 proxy 폴백이 이미 유효한 ticker(KRW=X)를 ITA로 덮어쓰지 않도록 가드 |
| **폴백 명시** | region 추정 폴백 시 `inference_caveat`에 '[지역 미식별 — middle_east 추정 폴백]' 표기 |
| **룰점수 라벨** | cascade `correlation_score`를 '상관계수'→'룰 발화 점수'로 교정 + 경고 (통계 상관계수로 인용 금지). '0.78 상관계수' 둔갑 차단 |

### 검증 (함수 단위, eval/서버 없이)

같은 H1 재현:
- 수정 전: `region=None ticker=KRW=X` → 검증기서 `middle_east → ITA` (p=0.4483 무의미)
- 수정 후: `region=korean_peninsula ticker=KRW=X` → **`korean_peninsula → KRW=X` p=0.106 '상관'** (H1 선언과 일치)

→ 평가 지적 2건(변수 불일치 버그 + 0.78 출처 불투명) 모두 해소.

---

## ✅ [헤드라인 동사 규율 + 선택편향 경고] 완료 (2026-06-06) — v7.8.1

### 핵심: 헤드라인-데이터 불일치 차단 (자체 평가 피드백 반영)

러-우 인사이트 자체 평가에서 발견된 #1 위험: **헤드라인이 추론 등급보다 강한 인과를 단정**.
원인(구조적): Granger는 생성 후 실행되고, 동사 규율(원칙 #10)은 [주장]에만 적용 → [헤드라인]은 무규율.

### 구현 (`api/intel_query.py` `_build_prompt`)

| Fix | 변경 |
|-----|------|
| **헤드라인 동사 규율** | 원칙 #10 확장 — [헤드라인] 동사를 [주장] 등급에 종속. 상관/기술적이면 '강화/유발/제한/초래' 금지, '~와 동반된다/(가설)~할 가능성'만. 카드 형식에도 반영 |
| **선택·생존편향 탐지** | 원칙 #9-b 신설 — [관찰]이 소수/한쪽 사례('차단 성공'·'발견됨')에 의존 시 [한계]에 생존편향 명시 강제 + [주장] 등급 강등 |

### 검증 (단발 쿼리, eval 없이 육안)

같은 러-우 쿼리 재실행 — 헤드라인이 등급 표기 + 등급 동사로 전환:
- 이전: "사이버 공격은 복원력을 역설적으로 **강화하여** 효과를 **제한한다**" (인과 2개 단정, 등급 없음)
- 개선: "**(기술적)** ...사이버 공격이 **관찰되며**, ...기능하는 **것으로 보인다**"
- 개선: "**(상관)** 우크라이나 분쟁은 밀 선물 가격 상승과 **동반되며**, ...심화될 **가능성이 있다**"

→ 독자가 헤드라인만 봐도 검증 수준 인지. 생성 시점에 불일치 차단. 30케이스 eval은 차기 묶음 때.

---

## ✅ [7-D-7 반도체 확장 + 7-D-8 CSIS 확장 + theory_comparator 수치 연결] 완료 (2026-06-06) — v7.8.0

### 핵심: 경쟁이론엄밀 막힘의 구조적 원인 해소 — 이론 비교에 실측 수치 직결

**문제**: 경쟁이론엄밀(2.10)이 프롬프트로 개선 불가 — theory_comparator.py가 geomap.db(빈 DB)를 참조, semi_market 데이터 미연결
**해법 3종 세트**:

| 작업 | 결과 |
|------|------|
| 7-D-7 semi_market 확장 | 30건 → 50건 (+20). 신규 카테고리: china_self_sufficiency·memory_market·advanced_nodes·defense_tech |
| 7-D-8 CSIS 사이버 확장 | 68건 → **100건** (+32). Iran-Israel·인도-중국·북극·사헬 사이버전 추가 |
| theory_comparator DB 교정 | geomap.db → intel.db. `_get_semi_market_for_theories()` 신설 → Weaponized Interdependence·Digital Iron Curtain에 수치 직결 |

### 이론 비교 context 개선 예시 (techno/taiwan_strait)

```
실측 — 파운드리 HHI: 3920.0 (2024) | TSMC: 61.7% | SMIC: 5.9%
실측 — 중국 첨단 반도체 수입 의존도: 90.0% (2023) — 비대칭 의존 수치
실측 — 기술 분리 지표: 3nm TSMC 독점 100% | TSMC-SMIC 격차 4세대 | 갈륨 독점 80%
```

### theory_comparator FRED·WBK 추가 연결 (7-D-1·7-D-2)

- `_get_fred_for_theories()`: 유가(WTI/Brent)·가스·환율 최신값+추세% → **자원무기화 이론** 실측 ('긴장→상승' 예측과 대조)
- `_get_wbk_governance()`: WB WGI 정치안정·법치 지수 → **gray_zone 이론** 실측 ('거버넌스 공백 침투' IV)
- 검증: 사헬 gray_zone → WGI 정치안정 -2.37~-2.91 노출 / 호르무즈 → WTI 76.96 추세+85.6% 노출

### 7-D-X [경쟁설명] 형식 gap 해소 (프롬프트)

- `intel_query.py`: 경쟁이론 형식에 **'▶ 종합 판정:'** 라인 신설 — 두 이론 편차 직접 비교 후 우세 이론 수치 결론 강제 (insight·verify·card 3곳 모두)
- 비자명성 강화: **[통념 재확인 금지 자기검열]** + **[전이(contagion) 분석 특칙]** — 전이 주장은 차단조건·감쇠 비대칭을 수치로 요구

### 기타 개선

- `intel_analyzer._get_semi_market`: LIMIT 20→60, 카테고리 우선순위 재정렬 (china_self_sufficiency 최우선)
- `intel_analyzer._get_csis_incidents`: LIMIT 10→15, 포맷 6→8건

### eval 결과 (base eval은 theory_comparator 수정 전, 30케이스)

| 지표 | v7.7.2 | v7.8.0 base(수정전) |
|------|--------|-------------|
| PASS | 30/30 | 30/30 |
| 평균 신뢰도 | 92 | 92 |
| 경쟁이론 [엄격] | 100% | 100% |
| Granger PARTIAL | 1건 | **4건** (+3) |

LLM 심판 (26케이스, 수정 전): 비자명 2.81 / 정직 2.42 / 경쟁 2.08 / 반증 3.15 → 종합 2.62

**추론정직성 2.70→2.42 분석**: v7.7.2 이후 동사규율 프롬프트 diff 0줄 → 코드 회귀 아닌 **심판 노이즈**.
(메모리 feedback_honesty_over_judge: 심판은 프록시일 뿐). 다음 eval에서 재측정.

### 최종 --judge eval 결과 (v7.8.0, 29케이스 심판)

| 심판 축 | v7.7.2 | v7.8.0 최종 | 순효과 |
|---------|--------|-------------|--------|
| 비자명성 | 2.77 | 2.79 | ~0 (상승4/하락4 노이즈) |
| 추론정직성 | 2.70 | 2.45 | base 2.42→2.45 노이즈 회복 |
| **경쟁이론엄밀** | **2.10** | **2.21** | **+0.11** ✅ 막힌 축 돌파 |
| 반증가능성 | 3.20 | 3.14 | ~0 |
| 종합 | 2.69 | 2.65 | — |
| PASS / 신뢰도 | — | 30/30 / 92 | 형식 무회귀 |

**핵심 검증된 인과**: 경쟁이론엄밀 상승 케이스 = **정확히 데이터를 연결한 케이스**
- ↑ taiwan_semiconductor·ukraine_russia_energy·pla_taiwan_a2ad·salt_typhoon·hormuz_redsea (반도체 HHI·FRED 유가·CSIS 사이버 연결처)
- 비자명성도 동일 케이스(반도체·대만)에서 동반 상승 → **데이터 연결이 두 축을 함께 끌어올림 입증**
- 하락 2건은 데이터 무관 지역(south_china_sea·india) 노이즈

→ **결론: theory_comparator 빈 DB 버그가 7-D 데이터 적재 효과를 막던 진짜 병목이었음.**
   다음 7-D 데이터(FRED 전체·OWID·Comtrade)를 더 연결하면 더 많은 케이스가 동반 상승할 구조 확립.

### 다음 표적

- 7-D-9 (UN Comtrade 무역 의존도) → Weaponized Interdependence IV 추가 수치화
- 7-D 데이터를 theory_comparator 이론별로 더 연결 (indo_pacific milex·alliance 등)
- 비자명성: 데이터 무관 케이스의 노이즈 하락분 진단 (south_china_sea 4→2 원인)

---

## ✅ [B 추론정직성 + C 경쟁엄밀] 완료 (2026-06-06) — v7.7.2

### 핵심 발견: 심판 루브릭 ↔ §19 정직성 원칙의 구조적 충돌

B는 성공, C는 프록시 점수상 역효과 — 그러나 **C는 출력을 더 정직하게 만들었고,
사용자 결정으로 정직성을 점수보다 우선해 유지**. 이 충돌 자체가 중요한 발견.

### 구현 내역 (`api/intel_query.py` `_build_prompt`)

| 표적 | 변경 |
|------|------|
| **B 추론정직성** | 원칙 #10 신설 — 등급별 동사 규율(기술적='함께 관찰'/상관='상관한다, 유발 금지'/선행성='선행한다'/인과='유발한다'는 Granger+교란통제+이론 3조건시만). [주장]에 `(등급: …)` 표기 강제 |
| **C 경쟁엄밀** | 원칙 #4 강화 — '실측'에 구체적 숫자 의무(없으면 `[UNVERIFIED] 정량값 부재`), '판정'에 수치 편차 적시. insight·verify 카드 양쪽 |

### eval 결과 (v7.7.2, 30케이스+심판, BASE 92, PASS 30/30)

| 축 | v7.7.0 | v7.7.1(A) | v7.7.2(A+B+C) | 케이스 방향 |
|----|--------|-----------|---------------|-----------|
| 비자명성 | 2.40 | 2.86 | 2.77 | A 유지(노이즈) |
| **추론정직성** | 2.47 | 2.46 | **2.70** | ✅ 상승10/하락4 (순+6) |
| **경쟁이론엄밀** | 2.33 | 2.25 | **2.10** | ❌ 상승3/하락6 (순−3) |
| 반증가능성 | 3.13 | 3.18 | 3.20 | — |
| 종합 | 2.58 | 2.69 | 2.69 | 정체 |

### C 역효과의 진짜 원인 (단순 버그 아님 — 구조적)

C는 context에 숫자가 없는 이론쌍에서 모델이 정성적 판정으로 얼버무리던 것을
`[UNVERIFIED] 정량값 부재 → 판단 보류`로 **정직하게 인정**하게 만듦.
심판 루브릭("수치 편차=5점")은 이 정직한 '데이터 없음'을 '수사적'으로 보고 **감점**.

→ **심판(수치편차 보상) ↔ §19(없으면 [UNVERIFIED]) 구조적 충돌.**
데이터 부재 시 모델 선택지는 (a)환각 숫자[금지] (b)정직한 punt[심판 감점]뿐.
**진짜 해법은 프롬프트가 아니라 context에 숫자를 더 넣는 것(Phase 7-D 데이터 적재).**

### 결정 (2026-06-06): C 유지 — 정직성 > 프록시 점수

심판은 Gemini 의견(프록시)일 뿐 절대 진리 아님. 프로젝트 핵심 가치(§19 정직성,
v7.5 'Granger 정직 격하')와 정합. 경쟁 숫자 하락 감수, 7-D 데이터 적재로 추후 해소.

### 다음 표적

- **경쟁이론엄밀(2.10)**: 프롬프트로는 한계 도달 → **Phase 7-D 데이터 적재가 선결**
  (context에 수치가 있어야 정직하게 수치 편차 판정 가능). FRED·SIA·CSIS·OWID 등.
- **비자명성 2.77 → 3.5+**: 다수 케이스 3점 고정 — 추가 여지

---

## ✅ [A — 비자명성 프롬프트 강화] 완료 (2026-06-06) — v7.7.1

### 핵심: 심판 최저점(비자명성 2.40)을 표적해 +0.46 단독 상승

C1이 폭로한 내용 품질 4축 중 **최저점 비자명성**을 첫 표적으로 공략.
기존 프롬프트엔 *부정 지시*("'A가 증가했다' 수준 금지")만 있고 **생성 방법**이 없었음 →
심판 루브릭("1=재서술 / 5=독창적 통찰")에 대응하는 강제 장치 부재가 근본 원인.

### 구현 내역 (`api/intel_query.py` `_build_prompt`)

| 변경 | 내용 |
|------|------|
| 원칙 #6 재설계 | 부정 지시 → **생성 절차**: (a)통념 명시 → (b)반박·정교화·한정. 비자명성 원천 3종(반직관/교차도메인/범위조건) 중 택1 강제 |
| 카드 필드 신설 | `[통념]`·`[비자명기여]` — 심판이 full text로 읽는 강제 장치. 둘이 같으면 "비자명성 0점" 경고. 헤더 9→11개 |
| `[문헌공백]` 강화 | 막연한 '추가 연구 필요' 금지 → 구체적 구조적 공백·메커니즘 명시 |

### eval 결과 (v7.7.1, 30케이스 + 심판, BASE 92)

| 척도 | v7.7.0 | v7.7.1 | Δ |
|------|--------|--------|---|
| **비자명성** | 2.40 | **2.86** | **+0.46** |
| 추론정직성 | 2.47 | 2.46 | ~0 (표적 B, 미손댐) |
| 경쟁이론엄밀 | 2.33 | 2.25 | -0.08 (표적 C, 미손댐) |
| 반증가능성 | 3.13 | 3.18 | +0.05 |
| **종합** | 2.58 | **2.69** | +0.11 |
| PASS / 증거등급 | — | **30/30 / 92** | 형식 무회귀 확인 |

표적한 축만 단독 상승 → 변경의 인과가 깨끗이 분리됨. 형식 점수(증거등급 92, PASS 30/30) 무회귀.

### 다음 표적 (잔존 — 내용 품질 2.69→4.0+)

- **B 추론정직성(2.46)**: 추론 사다리 등급(선행성/상관/기술적)을 본문 주장 문구에 강제 반영 — '유발한다' 남용 차단
- **C 경쟁이론엄밀(2.25, 최저)**: 형식은 [엄격]100%이나 내용은 수사적 → 실제 수치 편차 의무화
- 비자명성도 2.86 → 3.5+ 추가 여지 (현재 다수 케이스 3점 고정)

---

## ✅ [C1 질적 평가 + C2 케이스 확장 + A2+ UI] 완료 (2026-06-06) — v7.7.0

### 핵심 발견: 형식 91점 vs 내용 2.58/5 (~52%)

C1(LLM 심판)이 그동안 형식 척도가 가리고 있던 **진짜 내용 품질**을 폭로.

| 척도 | 결과 | 의미 |
|------|------|------|
| 형식 (증거 등급) | **91**/100 | 잘 구조화·데이터 충실 |
| 추론 사다리 | 선행성 1 / 상관 4 / 기술적 25 | 인과는 대부분 서술 수준 |
| **내용 (LLM 심판)** | **2.58/5** | 진짜 박사 수준 척도 |
| — 비자명성 | 2.40 | "기존 사실 재확인 수준" |
| — 추론정직성 | 2.47 | 상관→인과 과대해석 잔존 |
| — 경쟁이론엄밀 | 2.33 | 수사적 비교 |
| — 반증가능성 | 3.13 | 상대적 양호 |

**§22-C "박사 90%"는 형식으로 달성됐으나 내용은 ~52%.** 신뢰도 숫자 최적화가
Goodhart의 법칙이었음을 C1이 정량 폭로. 이게 다음 개선의 진짜 표적.

### 구현 내역

| ID | 파일 | 내용 |
|----|------|------|
| C1 | `eval_insight.py` | `_judge_quality` — Gemini 4축 루브릭 채점(비자명성·추론정직성·경쟁엄밀·반증가능). `--judge` 플래그. eval은 테스트 하네스라 LLM 심판 허용 |
| C2 | `eval_cases.yaml` | 20→30 케이스. 사건→사건 전이 3개(중동→호르무즈·호르무즈→홍해·러우→중동) + 섹터 다양화(에너지·희토류·NATO·해양·사이버) |
| A2+ | `InsightAnalystView.js`·`main.css` | 2축 배지(증거+추론 사다리), 검정 가드 뱃지(교란통제/차분/이론근거), Granger 단서, 사건→사건 표시 |

### eval 결과 (v7.7.0, 30케이스 + 심판)

- 29/30 PASS (1 일시적 잘림), 증거 평균 91
- 추론: 선행성 1(중동→호르무즈) / 상관 4 / 기술적 25
- 경쟁이론 [엄격] 100% (18/18)
- **질적 종합 2.58/5** ← 새 표적

### 다음 개선 표적 (내용 품질 = 진짜 박사 수준)

형식·방법론 정합은 완성. 이제 **내용 품질 2.58→4.0+** 가 과제:
- 비자명성: 프롬프트가 "기존 사실 재확인" 넘어 문헌 공백 겨냥하도록 강화
- 추론정직성: 상관→인과 과대해석 잔존 — 사다리 등급을 본문 주장에 강제 반영
- 경쟁이론엄밀: 수사적 비교 → 실제 수치 편차 의무화 (이미 형식은 100%이나 내용 부실)
- ※ 단, LLM 심판도 Gemini 의견(프록시)임 — 절대 진리 아님. 형식보다 내용에 훨씬 근접한 척도일 뿐.

---

## ✅ [B3 조건부 Granger + B4 사건→사건] 완료 (2026-06-06) — v7.6.0

### 핵심 성과: 최초의 정당한 "선행성" 도달

엄밀 가드 적용 후 시장 경로는 모두 상관/기술적이었으나, **사건→사건 경로**가
교란·EMH에 강건한 진짜 선행성을 처음으로 포착.

### B3 — 조건부 Granger (교란 통제)

| 파일 | 변경 |
|------|------|
| `correlation.py` | `_get_control_series`(VIX), `_run_conditional_granger`(VAR.test_causality) |
| `hypothesis_verifier.py` | 통제변수 로드(쿼리당 1회 캐시) → 조건부 우선, 실패 시 양변량 fallback |
| `_classify_inference_grade` | '선행성' = 이론근거 + 유의 + **교란통제** 3조건. 미통제면 상관 상한 |

**발견**: 대만→TSMC가 VIX 통제 시 **p=0.135 → 0.918** (유의성 소멸).
겉보기 선행성이 사실 글로벌 위험(VIX) 공통 움직임이었음 — 교란 통제의 정확한 작동.

### B4 — 사건→사건 Granger (cascade 본질)

| 파일 | 변경 |
|------|------|
| `correlation.py` | `_load_global_conflict_series`(전세계 분쟁 baseline, 검정 두 지역 제외) |
| `hypothesis_extractor.py` | `dependent_region` 필드 + 종속 지역 탐지. `_match_region` **위치 기반**(방향 정확). when-then 연결어 확장("시/하면/할수록") |
| `hypothesis_verifier.py` | `_run_event_to_event` — 지역A→지역B 이벤트 조건부 Granger(글로벌 분쟁 통제). 전이 화이트리스트 `_THEORY_GROUNDED_CONTAGION` 6쌍 |

**발견 (라이브 입증)**: `middle_east → hormuz` **p=0.0008** (글로벌 분쟁 통제 후에도 강건)
→ **추론 등급 "선행성"**. EMH 대상이 아닌 분쟁 전이라 시장 테스트와 달리 진짜 선행 포착.
프로젝트 cascade 논제(§11-A)의 첫 방법론적 정당 입증.

### eval 결과 (v7.6.0)

| 지표 | 값 | 비고 |
|------|----|------|
| 20케이스 | 18/20 PASS (1 잘림·1 503, 일시적) | 증거 평균 93 |
| 추론(시장 케이스) | 선행성 0 / 상관 4 / 기술적 15 | EMH·VIX통제로 시장 경로 null 정직 |
| **추론(전이 케이스)** | **선행성 1** (middle_east→hormuz p=0.0008) | B4 사건→사건 정당 도달 |
| 경쟁이론 [엄격] | 100% | 유지 |

전이 eval 케이스(`middle_east_hormuz_contagion`) 추가 — C2 일부.

### 학술적 의미

시장 경로(EMH·교란으로 null)와 사건→사건 경로(전이 인과 포착)의 **방법론적 분리**.
"선행성"이 이제 **통제변수 조건부 + 이론근거 + 사건→사건**이라는 엄격한 3중 요건으로만
도달 가능 → 허위 유의 차단. 도구가 *언제 인과를 주장할 수 있고 없는지*를 정확히 구분.

---

## ✅ [Layer 1~4] 신뢰도 개선 — 점수 로직 + 사헬 재태깅 + OWID (2026-06-06) — v7.4.0

### 결과: 신뢰도 평균 71 → 81 (+10), 20/20 PASS

| 지표 | v7.3.1 | v7.4.0 | Phase 7 목표 |
|------|--------|--------|------------|
| 신뢰도 평균 | 71 | **81** | 85+ |
| 최저 점수 | 60 | **70** (60 바닥 해소) | — |
| PROVISIONAL | 0 | **0** | — |
| Granger VERIFIED | 1 | **2** | 3건+ |
| Granger PARTIAL | 7 | **9** | — |
| 경쟁이론 [엄격] | 100% | **100%** | 50%+ |
| PASS율 | 100% | **100%** | — |

### Layer 1 — 점수 로직 교정 (핵심 동인)

**근본 원인 (코드 진단)**: 신뢰도 71 = `8×60 + 9×75 + 2×88 + 1×100`.
두 가지 점수 로직 결함이 원인이었음:
- `data_void_penalty`가 7-D 신규 데이터(WBK·ITU·HIIK·semi 등)를 인식 못 해
  arctic·sahel·cyber·techno 8케이스를 60으로 캡
- `verification_cap`이 "최악 상태" 기준 → VERIFIED(p=0.012)를 PENDING이 60점으로 매장

| ID | 수정 | 파일 |
|----|------|------|
| L1-a | `data_void_penalty` 정형 소스 차등 (≥3→85 / 2→78 / 1→70 / 0→60) | `confidence_scorer.py` |
| L1-b | `verification_cap` 최악→최선 상태 (VERIFIED 1건이면 상한 해제) | `intel_query.py` |
| L1-c | `source_counts`에 fred/wbk/polity5/itu/hiik/semi/owid 추가 | `intel_analyzer.py` |

### Layer 2 — Granger 검증 깊이

| ID | 수정 | 비고 |
|----|------|------|
| L2-b | H1 독립변수 X에 지역/집계출처 명시 강제 (Type_B 과잉 억제) | 프롬프트 |

### Layer 3 — 데이터 커버리지

| ID | 수정 | 효과 |
|----|------|------|
| L3-a | 사헬 ACLED 19,560건 재태깅 (`retag_sahel_events.py`) | region_code='sahel', 359일 발생 → Granger 가능 |
| L3-b | OWID 군사비%GDP·핵탄두 261행 (`owid_seed.csv` + 소스 #22) | indo_pacific 군사력 수치화 |

### Layer 4 — 출력 형식·프롬프트

| ID | 수정 |
|----|------|
| L4-a | verify 모드 `[단계 4]`에도 예측:/실측:/판정: 레이블 적용 |
| L4-b | 쿼리 핵심 키워드를 [헤드라인]·[관찰]에 반영 지침 |

### eval 하네스 강건화

- `eval_insight.py`: 200이지만 잘린 응답(섹션<60%)·빈응답 자동 재시도
  (`_is_retryable` + `_section_fill`). 일시적 Gemini 잘림 복구.
  → 첫 실행 3건 잘림 발생했으나 재실행 시 75/75/85로 모두 정상 (일시적 현상 확인).

### 잔여 (다음 배치 — 85+ 달성용)

| ID | 항목 | 상태 |
|----|------|------|
| L2-a | cyber 사건 시계열 Granger | ⬜ CSIS 밀도 부족 (GTD/CSIS 200+ 확장 필요) |
| L2-c | actor-filter event study (PARTIAL→VERIFIED) | ⬜ |
| L3-c | UN Comtrade — 반도체 HHI 수치 | ⬜ (techno IV 실측화) |
| L3-d | Wikidata 조약·동맹 SPARQL | ⬜ |

### 외교부 LOD 추가 검토 (2026-06-06)

전체 클래스 인벤토리 조사 결과, 미사용 데이터셋은 `mofapress` 보도자료 2,300건뿐
(날짜+국가태그+초록 구조). **외교부 LOD 전체가 텍스트/엔티티 지식그래프 — 통계·수치 없음.**
현재 병목(수치 데이터)을 해소하지 못하므로 보류. Press는 한국 외교 신호 정성 데이터로
Phase 8 행위자 네트워크 단계에 더 적합. DiplomatJ는 기존 판정대로 활용 낮음.

---

## 다음 세션 개선 계획 (2026-06-06 분석 확정)

### 근본 원인 진단 (코드·DB 근거)

**신뢰도 71 고착의 산술적 분해 (20케이스):**

| 점수 | 케이스 수 | 캡 원인 |
|------|----------|--------|
| 60 | 8개 | `data_void_penalty` — event_archive에 arctic·sahel·cyber·techno = 0건 |
| 75 | 9개 | `verification_cap` PENDING — 최악 H1이 PENDING (캡 75) |
| 88 | 2개 | PARTIAL 캡 88 |
| 100 | 1개 | H1 없음 (캡 없음) |

`8×60 + 9×75 + 2×88 + 1×100 = 1431 ÷ 20 = 71.55` → 정확히 일치.

**결정적 결함 2가지:**

① `data_void_penalty`가 7-D 신규 데이터를 `source_counts`에서 인식하지 못함.
WBK·ITU·HIIK·CSIS·semi·FRED가 이미 DB에 있지만 패널티 판정에서 제외됨.
sahel 쿼리는 WBK 거버넌스(말리 -2.37), HIIK 강도, Polity5가 있는데도 "데이터 없음"으로 판정 중.

② `verification_cap`이 "최악 상태" 기준 → VERIFIED를 매장.
`worst = min(specs, ...)` 로직: VERIFIED 1건 + PENDING 1건 → 전체가 75 캡.
한 카드에서 Granger 검증을 통과해도 다른 H1의 PENDING이 전체를 끌어내림.

```
현재 71
 → Layer 1 (점수 로직 교정)              ≈ 80~82   [즉시, 코드 소량]
 → Layer 2 (Granger 깊이)               ≈ 83~85   [중간]
 → Layer 3 (ACLED 사헬/북극 + 데이터 L2/L3)  ≈ 85+ → Phase 8 게이트
```

---

### Layer 1 — 점수 로직 교정 (즉시, 코드 소량) ⬜

| ID | 항목 | 파일 | 예상 효과 |
|----|------|------|----------|
| **L1-a** | `data_void_penalty`에 7-D 구조화 소스 반영 — fred/wbk/polity5/itu/hiik/semi 중 N개 이상이면 void 아님 | `confidence_scorer.py` | 60점 8케이스 → 75~90 |
| **L1-b** | `verification_cap`을 "최악→최선" 기준으로 변경 — 1개라도 VERIFIED면 상한 해제 | `intel_query.py:351` | VERIFIED 보유 케이스 정상 평가 |
| **L1-c** | `source_counts`에 신규 6소스 카운트 추가 (L1-a 전제조건) | `intel_analyzer.py:1330` | L1-a 동작 가능화 |

---

### Layer 2 — Granger 검증 깊이 (중간) ⬜

| ID | 항목 | 파일 | 근거 |
|----|------|------|------|
| **L2-a** | CSIS 사이버 사건 → 월별 시계열 생성 → cyber H1 ITA/SOXX Granger 검증 | `hypothesis_verifier.py` + `correlation.py` | cyber는 region 없어 100% PENDING |
| **L2-b** | Type_B 과잉 생성 억제 — H1 카드당 측정가능 가설 최우선 (38건 중 30건 PENDING이 대부분 Type_B) | `intel_query.py` 프롬프트 | PENDING 대량 발생 구조 해소 |
| **L2-c** | actor-filter event study 구현 — PARTIAL 케이스(p=0.10~0.15) VERIFIED 돌파 (`hypothesis_verifier.py:156`에 "다음 버전 예정" 명시) | `hypothesis_verifier.py` | PARTIAL 7건 → VERIFIED 경로 |

---

### Layer 3 — 데이터 커버리지 공백 (7-D L2/L3 연계) ⬜

| ID | 항목 | 효과 |
|----|------|------|
| **L3-a** | ACLED sahel·arctic 재적재 — event_archive에 region_code 태깅 | sahel/arctic Granger·cascade 가능화 (현재 0건) |
| **L3-b** | 7-D-3 Our World in Data — 군사비·분쟁사망자·핵탄두·에너지 | indo_pacific 군사력 수치 |
| **L3-c** | 7-D-9 UN Comtrade — HS 8542 반도체 무역 HHI | Weaponized Interdependence IV 실측화 |
| **L3-d** | 7-D-10 Wikidata 조약·동맹 SPARQL | COW Alliances 보완 |

---

### Layer 4 — 출력 형식·프롬프트 (저비용) ⬜

| ID | 항목 | 근거 |
|----|------|------|
| **L4-a** | verify 모드 `[단계 4]`에도 `예측:/실측:/판정:` 레이블 적용 | salt_typhoon·mearsheimer verify이라 rival_check 미탐지 |
| **L4-b** | `china_ai` "수출규제" 키워드 누락 — 쿼리 핵심어 반영 지침 | 사소하나 키워드 체크 실패 |

---

**실행 순서**: L1-c → L1-a → L1-b → eval 재실행 → L2-b → L2-a → L3-a → eval 재실행

---

## Phase 7-D 계획 — 풀스케일 데이터 대량 적재 (2026-06-05 확정)

### 목표

신뢰도 평균 70 → 85+ / 경쟁이론 수치 비교 0% → 50%+ / Granger VERIFIED 2 → 3건+

### 핵심 원칙

- **대량 적재 + 스마트 라우팅**: DB에 많이 넣되, 쿼리 지역/섹터 → 관련 소스만 선택해서 Gemini에게 전달
- **컨텍스트 상한 유지**: 총 ~20,000자 상한 안에서 최적 소스 조합 자동 선택
- **Token-Zero 유지**: 모든 적재·라우팅 결정론적 처리. LLM 호출 금지

### 섹터별 공백 진단

| 섹터 | 현재 신뢰도 | 공백 원인 | 해결 소스 |
|------|-----------|---------|---------|
| cyber | 50~60 | APT 빈도·피해액 수치 없음 | CSIS 확장 + GTD |
| techno | 60~75 | 반도체 HHI·점유율 없음 | SIA + Our World in Data |
| gray_zone (사헬·북극) | 60~75 | 거버넌스·취약국 지수 없음 | WB WGI + Polity5 + HIIK |
| energy·maritime | 75 | 상대적 양호 | FRED 시계열 보완 |
| indo_pacific | 75 | 군사력 비교 얕음 | Our World in Data 군사 |

---

### 사이클 전체 구조 (12개 sub-cycle)

| Level | Sub | 항목 | 소스 | 건수 | 상태 |
|-------|-----|------|------|------|------|
| **L1** | 7-D-1 | FRED 경제 시계열 | FRED API (무료) | 48행 | ✅ v7.3.0 |
| **L1** | 7-D-2 | World Bank 거버넌스 | WB Open Data API | 28행 | ✅ v7.3.0 |
| **L1** | 7-D-3 | Our World in Data (군사비·핵탄두 subset) | GitHub CSV 공개 | 261행 | ✅ v7.4.0 |
| **L1** | 7-D-4 | Polity5 정치체제 지수 | CSV (무료 학술) | 39행 | ✅ v7.3.0 |
| **L1** | 7-D-5 | ITU ICT 사이버 역량 지수 | CSV (무료) | 40행 | ✅ v7.3.0 |
| **L1** | 7-D-6 | HIIK 분쟁 강도 바로미터 | CSV (무료) | 30행 | ✅ v7.3.0 |
| **L1** | 7-D-7 | SIA 반도체 시장 데이터 | 공개 보고서 CSV | 30행 | ✅ v7.3.0 |
| **L1** | 7-D-8 | CSIS Cyber DB 확장 | CSV (20→68건) | 68행 | ✅ v7.3.0 |
| **L2** | 7-D-9 | UN Comtrade 무역 의존도 | API (무료 제한) | 국가쌍 무역 | ⬜ |
| **L2** | 7-D-10 | Wikidata 조약·동맹 | SPARQL | 수천 건 | ⬜ |
| **L3** | 7-D-11 | GTD 테러 데이터베이스 | CSV (학술 무료) | 200,000+건 | ⬜ |
| **L3** | 7-D-12 | ACLED 전세계 확장 | API (이미 커넥터) | 전체 국가 | ⬜ |
| **공통** | 7-D-X | [경쟁설명] 형식 gap 해소 | 프롬프트 재설계 | — | ✅ v7.3.0 |
| **공통** | 7-D-Y | intel_analyzer 소스 확장 | 15→21소스 | 21소스 | ✅ v7.3.0 |

---

### Level 1 — 즉각 적재 (CSV seed + 가벼운 API)

#### 7-D-1: FRED 경제 시계열

**소스**: Federal Reserve Economic Data (무료 REST API, api.stlouisfed.org)

| 시리즈 ID | 내용 | 활용 지역/섹터 |
|---------|------|-------------|
| DCOILWTICO | WTI 유가 월별 | hormuz·energy |
| DCOILBRENTEU | Brent 유가 월별 | hormuz·energy |
| PNGASEUUSDM | 유럽 천연가스 가격 | eastern_europe·energy |
| KOREUS | 원/달러 환율 | korean_peninsula |
| EXCHUS | 위안/달러 환율 | taiwan_strait |
| EXJPUS | 엔/달러 환율 | taiwan_strait·indo_pacific |
| RUBUSD | 루블/달러 (비공식 proxy) | eastern_europe |
| MHHNGSP | 헨리허브 천연가스 | energy |
| GOLDAMGBD228NLBM | 금 가격 | gray_zone 불확실성 |
| USMC | 미국 군사비 (연간) | indo_pacific |

**구현**: `connectors/fred_adapter.py` + `data/external/fred_seed.csv`  
**DB 테이블**: `fred_indicators` (series_id · series_name · date · value · unit · region_hint)

#### 7-D-2: World Bank 거버넌스 지수 (WGI)

**소스**: World Bank Open Data API (data.worldbank.org/api)

| 지표 코드 | 내용 | 섹터 |
|---------|------|------|
| PV.EST | 정치 안정성·폭력 부재 | gray_zone |
| CC.EST | 부패 통제 | gray_zone |
| RL.EST | 법치 | gray_zone |
| GE.EST | 정부 효과성 | gray_zone |
| RQ.EST | 규제 품질 | techno |
| VA.EST | 발언·책임성 | cyber·인지전 |

**대상 20개국**: USA·CHN·RUS·IRN·PRK·UKR·SAU·ISR·IND·JPN·KOR·TUR·QAT·MLI·NER·BFA·ETH·YEM·NOR·CAN  
**구현**: `data/external/world_bank_seed.csv` + `intel_analyzer._get_wbk_governance()`  
**기대 효과**: "말리 정치안정 -1.82 (전세계 하위 3%)" 수치 직접 인용

#### 7-D-3: Our World in Data (대량 — 핵심 데이터셋)

**소스**: Our World in Data GitHub (owid/owid-datasets) — 모든 CSV 공개

| 데이터셋 | 내용 | 행 수 | 섹터 |
|---------|------|------|------|
| military-expenditure | 국가별 군비 지출 1960~ | ~5,000 | indo_pacific |
| share-of-gdp-military | 군비 GDP 비율 | ~5,000 | indo_pacific |
| armed-conflict | 국가간·내전 연간 사망자 | ~3,000 | gray_zone |
| battle-deaths | 분쟁 사망자 시계열 | ~3,000 | gray_zone |
| nuclear-warheads | 핵탄두 보유량 | ~500 | indo_pacific |
| energy-production-by-source | 에너지원별 생산량 | ~10,000 | energy |
| fossil-fuel-subsidies | 화석연료 보조금 | ~2,000 | energy |
| internet-users-by-country | 인터넷 보급률 | ~4,000 | cyber |
| trade-openness | 무역 개방도 | ~5,000 | energy·techno |

**구현**: `scripts/load_owid_data.py` (GitHub raw CSV 직접 다운로드)  
**DB 테이블**: `owid_data` (dataset · country · year · value · unit)

#### 7-D-4: Polity5 정치체제 지수

**소스**: Center for Systemic Peace (공개 CSV)

- 167개국 1800~현재 정치체제 점수 (-10 전제군주 ~ +10 완전민주)
- Polity5 점수 + 체제 전환 연도
- **활용**: V-DEM 보완, 행위자 체제 분류 강화  
**DB 테이블**: `polity5` (country_iso3 · year · polity_score · regime_type)

#### 7-D-5: ITU ICT Development Index

**소스**: ITU (itu.int, 공개 CSV)

- 170개국 ICT 인프라·이용·역량 종합 지수
- 사이버 보안 역량 proxy
- **활용**: cyber 섹터 국가별 사이버 역량 수치화  
**DB 테이블**: `itu_ict` (country_iso3 · year · idi_score · rank)

#### 7-D-6: HIIK 분쟁 강도 바로미터

**소스**: Heidelberg Institute for International Conflict Research (HIIK, 무료)

- 1992~현재 연간 분쟁 강도 (1=분쟁~5=전쟁)
- 200+개 분쟁 지역별 기록
- **활용**: ACLED 보완, 분쟁 강도 시계열 수치화  
**DB 테이블**: `hiik_conflict` (region · year · intensity · conflict_name)

#### 7-D-7: 반도체·기술 시장 데이터

| 데이터 | 수치 | 활용 |
|--------|------|------|
| SIA 파운드리 시장 점유율 | TSMC 52%, 삼성 17%, SMIC 7% (2023) | techno HHI |
| 핵심 광물 중국 의존도 | 갈륨 80%, 게르마늄 60%, 희토류 90% | techno |
| ASML EUV 장비 독점 | 네덜란드 100% 독점, 연간 ~50대 | techno |
| AI 칩 수출규제 품목 수 | A100/H100 등 BIS 통제 품목 | techno·cyber |
| 반도체 장비 5개국 HHI | ASML·AMAT·LAM·TEL 집중도 | techno |

**구현**: `data/external/semi_market_seed.csv`  
**DB 테이블**: `semi_market_data` (category · metric · value · year · source)

#### 7-D-8: CSIS Cyber Incidents DB 확장

- **현재**: 20건 (2015~2024 주요 사건)
- **목표**: 100+건 (2006~2024 전체)
- **추가 필드**: `perpetrator_country` · `target_country` · `target_sector` · `attack_type` · `estimated_damage_usd`
- **출처**: CSIS Significant Cyber Incidents 전체 목록 (csis.org/programs/strategic-technologies-program/significant-cyber-incidents)
- **구현**: `data/external/csis_cyber_extended_seed.csv`

---

### Level 2 — 단기 (API 커넥터 구축, 1~2세션)

#### 7-D-9: UN Comtrade 무역 의존도

**소스**: UN Comtrade API (comtradeapi.un.org, 무료 제한 100회/일)

- 국가쌍 무역 의존도 (HS 코드별)
- **핵심**: 반도체(HS 8542)·에너지(HS 27)·희토류(HS 2846) 무역 집중도
- HHI 자동 계산 → Weaponized Interdependence IV 직접 수치화
- **구현**: `connectors/comtrade_adapter.py`

#### 7-D-10: Wikidata 조약·동맹 SPARQL

**소스**: Wikidata SPARQL (query.wikidata.org, 무료)

외교부 LOD와 동일한 패턴 — 조약·국제기구 멤버십 대량 추출:
```sparql
SELECT ?treaty ?treatyLabel ?signDate ?country WHERE {
  ?treaty wdt:P31 wd:Q131569 .        # instance of: international treaty
  ?treaty wdt:P710 ?country .          # participant
  ?treaty wdt:P571 ?signDate .         # inception date
}
```
- **활용**: COW Alliance 보완, 미등록 양자 조약 커버
- **구현**: `connectors/wikidata_treaty.py`

---

### Level 3 — 중기 (대형 DB, 2~3세션)

#### 7-D-11: Global Terrorism Database (GTD)

**소스**: National Consortium for the Study of Terrorism (START), University of Maryland  
(학술 무료 등록, `data/external/` 로컬 보관)

- **규모**: 200,000+건 (1970~2020)
- **필드**: date · country · region · attack_type · target_type · group_name · killed · wounded
- **활용**: gray_zone·cyber 섹터 테러 강도 수치, ACLED 보완 (1970~2000 공백 해소)
- **DB 테이블**: `gtd_events` (연도별 파티셔닝, 지역 집계 인덱스)
- **주의**: 파일 크기 대용량 → 지역별 필터 후 적재

#### 7-D-12: ACLED 전세계 확장

**현재**: 41개국 252,409건 (아시아·중동·아프리카 일부)  
**목표**: 전세계 커버리지 (유럽·아메리카·오세아니아 포함)

- **방법**: 기존 `acled_bulk_ingest.py` 재실행 + 국가 목록 확장
- **추가 지역**: 동유럽(벨라루스·조지아·아르메니아) + 라틴아메리카(베네수엘라·콜롬비아) + 사헬 전체
- **기대 건수**: 400,000+건

---

### 공통 인프라 업그레이드

#### 7-D-X: [경쟁설명] 형식 gap 해소

**문제**: 경쟁이론 수치 비교 0% — Gemini가 내용은 서술하지만 `예측:` `실측:` 레이블 미사용

`intel_query.py` system_role에 구체적 예시 고정 삽입:
```
[경쟁설명] 섹션은 반드시 아래 형식을 사용하라:

이론명 (학자):
  예측: [수치·방향]
  실측: [context 소스의 실제 수치]
  판정: 우세/열세 — [근거 1줄]

예시 — 자원무기화 (Hirschman):
  예측: 에너지 의존도 증가 시 정치적 양보 증가
  실측: EU 러시아 가스 의존도 2021년 45% → 2024년 8% (EIA)
  판정: 열세 — 대체재 출현으로 무기화 효과 약화, 셰일 혁명이 반례
```

#### 7-D-Y: intel_analyzer.py 소스 확장

현재 15소스 → 20+소스 병렬:

```python
# 신규 추가 소스
loop.run_in_executor(None, _get_fred_data, pq.regions, pq.sectors),      # #16
loop.run_in_executor(None, _get_wbk_governance, pq.actors, pq.regions),  # #17
loop.run_in_executor(None, _get_owid_data, pq.actors, pq.regions),       # #18
loop.run_in_executor(None, _get_polity5, pq.actors),                     # #19
loop.run_in_executor(None, _get_itu_ict, pq.actors),                     # #20
loop.run_in_executor(None, _get_semi_market, pq.sectors, pq.regions),    # #21
loop.run_in_executor(None, _get_gtd_stats, pq.regions),                  # #22 (L3 후)
```

스마트 라우팅 원칙:
- cyber 쿼리 → CSIS + ITU + GTD 우선
- techno 쿼리 → SIA + UN Comtrade + OWID 우선
- gray_zone 쿼리 → WB WGI + Polity5 + HIIK + GTD 우선
- energy 쿼리 → FRED + EIA + OWID 에너지 우선

---

### 진행 순서 (우선순위)

```
즉시 (L1, 1세션):
  7-D-X (프롬프트 gap) → 즉각 효과
  7-D-7 (SIA 반도체) + 7-D-8 (CSIS 확장) → CSV만
  7-D-1 (FRED) + 7-D-2 (WB WGI) → API + seed
  7-D-3 (Our World in Data) + 7-D-4 (Polity5) + 7-D-5 (ITU) + 7-D-6 (HIIK)

단기 (L2, 1~2세션):
  7-D-9 (UN Comtrade) + 7-D-10 (Wikidata 조약)

중기 (L3, 2~3세션):
  7-D-11 (GTD 200,000건) + 7-D-12 (ACLED 전세계)

공통:
  7-D-Y (intel_analyzer 20+소스 확장) — 각 데이터 완료 후 점진적 통합
```

### 평가 기준

각 Level 완료 후 `eval_insight.py` 재실행:
- **L1 완료 후**: 신뢰도 평균 78+ + 경쟁이론 수치 비교 30%+
- **L2 완료 후**: 신뢰도 평균 82+
- **L3 완료 후**: 신뢰도 평균 85+ + 경쟁이론 수치 비교 50%+ → **Phase 8 착수**

### Phase 8 착수 조건

- 신뢰도 평균 85+ 달성
- 경쟁이론 수치 비교 50%+ 달성
- 두 조건 동시 충족 시 Phase 8 착수

### Phase 8 (후순위, Phase 7 완료 후)

브리핑 연쇄 그래프(P8-1) · 행위자 네트워크(P8-2) · 교차 인사이트(P8-4) · 타임라인 뷰(P8-5)


---

## 📦 Phase 8 상세 구현 일지 (v7.9.0 ~ v8.11.0, 2026-06-07~10)

> progress.md에서 2026-06-30 분리. Phase 8 박사수준 추론 사이클의 구현 상세.
> 요약·완료 게이트는 progress.md 본문 'Phase 8' 절에 유지됨.

### Cycle 8-C-5 — 회귀 수정 (DV 방향 조건부 완화 + API 오류 분리) (v8.11.0, 2026-06-10)

**Opus 분석 기반 수정 3건**:
1. **DV 방향 비교 조건부 완화** — "DV 실측 있을 때만" + 없을 때 `[UNVERIFIED] DV 부재` 정직 경로 (모델 freeze 해소)
2. **`**DV 예측 방향**` 독립 라벨 제거** — `반증 가능 예측` 줄에 부호(`▲/▼/↔`)만 인라인 병합 (출력 복붙 오염 차단)
3. **API 오류 감지 강화** — "과부하 상태" 메시지도 `error`로 분류 (FAIL→SKIP 처리)

**eval 결과 (15케이스 --judge, 2026-06-10) — Gemini API 과부하 환경**

| 항목 | v8.10.4 | v8.11.0 | Δ |
|------|---------|---------|---|
| PASS | 14/15 | **13/15 (오류 2, 실패 0)** | FAIL→오류 분리 ✅ |
| 평균 신뢰도 | 92 | **93** | +1 |
| judge 케이스 | 7 | **3** | API 과부하로 샘플 부족 |
| 경쟁이론엄밀 | 3.29 | **3.33** | ↑ (샘플 부족, 신뢰도 낮음) |
| 종합 | 3.46 | **3.00** | (샘플 3개 → 비교 불가) |

**공통 케이스 변화 (3개)**:
- `mearsheimer_vs_liberal_taiwan`: 경쟁 3→**4** ✅ (DV 방향 수정 효과)
- `salt_typhoon_cyber_deterrence`: 경쟁 4→3 (LLM 변동성)
- `taiwan_liberal_vs_realist`: 경쟁 4→3 (LLM 변동성)

**판정**: API 과부하로 judge 3케이스 → 유의미한 통계 비교 불가. API 안정 후 재측정 필요.
- 수정 1 (DV 조건부): `mearsheimer` +1 긍정 신호
- 수정 3 (오류 분리): exit code 0 ✅ (이전 FAIL 케이스 SKIP 처리됨)

### Cycle 8-C-4 — 추론 품질 3종 개선 시도 + 회귀 발생 (v8.10.4, 2026-06-10)

**목표**: 점수 정체 원인 3가지 동시 공략 (2순위→1순위→3순위 순으로 적용)

**구현 3건**:
1. **[2순위] 동사 강제 (v8.10.2)**: `intel_query.py` [주장] 섹션에 등급별 허용 동사 표 삽입 + 자기검열 단계 추가
2. **[1순위] 비자명 재료 주입 (v8.10.3)**: `claim_ledger.build_nob_hints()` 신규 함수 → 이론 반례 경계 3개 카드 템플릿에 직접 주입
3. **[3순위] DV 방향 비교 (v8.10.4)**: `theory_comparator._extract_dv_direction()` → 각 이론 프로파일에 `**DV 예측 방향**:` 추가, DV 방향 필수 비교 지침

**eval 결과 (15케이스 --judge, 2026-06-10)**

| 항목 | v8.9.0 (기준) | v8.10.4 | Δ |
|------|---------|---------|---|
| PASS | 29/30 | **14/15** | taiwan_semiconductor FAIL (빈응답) |
| 평균 신뢰도 | 92 | **92** (FAIL 제외) | 동일 |
| **비자명성** | 3.17/5 | **3.29/5** | ↑+0.12 |
| **추론정직성** | 3.17/5 | **3.57/5** | ↑+0.40 ✅ 최대 개선 |
| **경쟁이론엄밀** | 3.67/5 | **3.29/5** | ↓-0.38 ⚠️ 회귀 |
| **반증가능성** | 3.83/5 | **3.71/5** | ↓-0.12 |
| **종합** | 3.46/5 | **3.46/5** | 동일 (FAIL 제외 기준) |

> 주의: 이전 세션 요약에서 "3.16/5"로 오기됨 — taiwan_semiconductor FAIL(0점) 포함 평균. 정확한 비교 기준은 "FAIL 제외 7케이스 3.46/5".

**회귀 원인 분석**:
1. `taiwan_semiconductor` 완전 빈 응답 (confidence=0, 섹션 0%) — nob_hints 컨텍스트 길이 초과 추정
2. `경쟁이론엄밀 -0.38`: DV 방향 지침이 Gemini의 비교 구조를 혼란시킴 (IV 앵커 방식과 충돌 가능성)
3. `russia_china_arctic_control` 전 항목 2점 — 이 케이스가 점수 평균 끌어내림

**다음 과제**: Opus 분석 → 회귀 원인 확정 + 수정 방향 제시

### Cycle 8-C-3 — HIIK 쿼리 버그 수정 + Granger 오매핑 해소 (v8.9.0, 2026-06-10)

**외부 평가 기반 (Claude.ai + Gemini 교차 검토, v8.8.0 결과물 분석)**:

두 평가 공통 지적:
1. **[P0] Granger 변수 오매핑**: H1 "대테러 예방 예산 감소" → 실제 매핑 `hormuz × CL=F` (개념 무관) → p=0.9884 당연한 결과
2. **[P3] 앵커 미제공 잔존**: `_get_hiik_conflict`가 `WHERE region LIKE '%Iran%'`로 검색했으나 DB에는 `region='hormuz'` → **항상 빈 결과** (완전한 버그)

**수정 2건**:
1. `theory_comparator._get_hiik_conflict`: `WHERE region LIKE '%{country}%'` → `WHERE region=?` (region_code 직접 매핑)
   → hormuz(intensity=4), middle_east(intensity=5), eastern_europe(intensity=5) 정상 반환
2. `hypothesis_extractor._EVENT_DEP_KEYWORDS`: "지원"·"원조"·"지원액" 계열 추가
   → "우크라이나 지원 규모" 포함 H1 → `dep_region=eastern_europe` → `사건→사건` 경로 활성화

**eval 결과 (30케이스 --judge, 2026-06-10)**

| 항목 | v8.8.0 | v8.9.0 | Δ |
|------|--------|--------|---|
| PASS | 29/30 | **29/30** | 동일 |
| 평균 신뢰도 | 92 | **92** | 동일 |
| **선행성(Granger p<0.15)** | 0건 | **2건** | **▲ +2 ✅** |
| 상관 | — | 3건 | |
| 경쟁이론엄밀 | 3.53 | **3.35** | −0.18 ⚠️ |
| 종합 | 3.50 | 3.38 | −0.12 |
| Granger VERIFIED | 2 | **2** | 동일(새 케이스) |

**선행성 2건 상세**:
- `middle_east_hormuz_contagion`: ACLED 중동→호르무즈 사건→사건, p=0.0 (완전 유의)
- `ukraine_middleeast_contagion`: ACLED 우크라이나→중동, p=0.0111 ← 자원배분 메커니즘 Granger 입증

**LLM 점수 하락 분석 (정직성 원칙)**:
- 경쟁이론엄밀 -0.18: v8.8.0 vs v8.9.0 judge 샘플 23케이스 동일하나 LLM 변동성 범위. `taiwan_liberal_vs_realist` 경쟁=2 지속이 평균 끌어내림.
- 하락이 내 변경에서 기인하는지 검증: HIIK 데이터 직접 사용 케이스(gray_zone) 오히려 안정 (sahel=4, south_china_sea=3). 앵커 없던 케이스가 앵커 받았으므로 과잉 주장 가능성 없음.
- 노이즈 판단 유지.

**남은 문제**: `taiwan_liberal_vs_realist` 경쟁=2 (종합=2.25) 지속 → [앵커 미제공] 잔존 + Gemini 프롬프트 무시.

### Cycle 8-C-2 — theory_comparator 선택·앵커·실측 배선 확장 (v8.8.0, 2026-06-09)

**배경**: v8.7.0 진단에서 "이론 51개 적재해도 경쟁이론엄밀 안 오름" 근본 원인 규명 →
theory_comparator가 비교 등판 이론을 하드코딩 11개로 고정 + 군사 이론 milex 앵커 미작동.

**수정 4건**
1. **🐛 진짜 버그**: `_get_sipri_milex_for_theories`가 존재하지 않는 컬럼 `country_iso3`(실제 `iso3`) 참조
   → 예외 조용히 삼켜져 **모든 군사 이론이 milex 앵커 못 받던 근본 원인** (taiwan "[앵커 미제공]"의 정체). 수정.
2. **선택 풀 확장**: `_SECTOR/_REGION_THEORY_PAIRS` 11개 → 차별화 변수 쌍 중심 확대.
   핵심: 한 쌍에 서로 다른 metric 배치(현실주의=milex / 자유주의=trade_hhi / 민주평화=polity) → 실측값이 우열 판정.
3. **앵커 레지스트리 확장**: `_THEORY_ANCHORS` 10개 → 30개 (기존 적재 데이터에 정직 매핑, DV 직접측정 아님 명시 유지).
4. **`milex_min` 메트릭 추가**: NATO 무임승차(burden_sharing) 판정용 (2% GDP 가이드라인).

**eval 결과 (30케이스 --judge) — v8.7.0 대비 (둘 다 30케이스, 공정 비교)**

| 항목 | v8.7.0 | v8.8.0 | Δ |
|------|--------|--------|---|
| PASS | 25/30 | **29/30** | +4 ✅ |
| 평균 신뢰도 | 85 | **92** | +7 ✅ |
| PROVISIONAL(<60) | 2 | **0** | ✅ |
| 경쟁이론엄밀 | 3.40 | **3.53** | **+0.13 ✅ (타깃)** |
| 비자명성 | 3.47 | 3.53 | +0.06 |
| 추론정직성 | 3.67 | 3.27 | −0.40 ⚠️ |
| 반증가능성 | 3.73 | 3.67 | −0.06 |
| 종합 | 3.57 | 3.50 | −0.07 (노이즈 범위) |

**정직성 하락 분석 (메모리 §정직성>심판 원칙 준수)**:
- 하락 4건(india·middle_east_hormuz·ukraine_middleeast·eia_gas)은 **내 변경 영역 아닌 contagion/Granger 통계 케이스**.
  판정 코멘트가 늘 같던 "인과추론 엄밀성 부족" → LLM 심판 노이즈.
- **앵커 주입 케이스 육안 검증**: nato_burden_sharing "전제 충족, 직접 설명하지는 않음" 등 **과잉 주장 없이 정직**.
  → 내 변경이 dishonesty 유발 안 함 확인. 정직성 하락은 심판 변동.
- 개선 케이스: taiwan_liberal_vs_realist(최악 2.5) 경쟁 2→4·정직 2→3, sahel 경쟁 3→4.

**성과**: 타깃(경쟁이론엄밀)+구조(PASS·신뢰도) 명확 개선. milex 버그 수정이 핵심.
**남은 문제(다음 레버)**: Gemini가 제공된 비교 컨텍스트를 무시하고 자기 이론 선택 → "[앵커 미제공]" 잔존
(taiwan 케이스). **프롬프트 준수 강제**가 다음 사이클. § 군사·사이버 변수 단일화(milex 쏠림) = §20 Phase D 데이터 벽 잔존.

---

### eval 결과 (v8.7.0, 30케이스 --judge, 2026-06-09)

**30케이스 구조 평가**
- PASS: **25/30 (83%)** | FAIL: 5 | 오류: 0
- 평균 신뢰도: **85/100**
- 평균 응답시간: 51.3s

**LLM 심판 (15케이스 judge)**
| 항목 | v8.7.0 | 출발점(v7.8.9, 15케이스) | 목표 |
|------|------|------|------|
| 종합 | **3.57/5** | 3.68 | 4.2+ |
| 비자명성 | 3.47 | 3.57 | 3.9+ |
| 추론정직성 | 3.67 | 3.86 | — |
| 경쟁이론엄밀 | **3.40** | 3.43 | 4.0+ |
| 반증가능성 | 3.73 | 3.86 | — |

> ⚠️ 출발점은 15케이스(쉬운 케이스 편중), v8.7.0은 30케이스(하드케이스 포함) — 직접 비교 시 불리.

**구조 지표**
- 경쟁이론 수치비교[엄격]: **89%** (16/18, 이전 100% — 30케이스 확장으로 하드케이스 포함)
- H1 추출: **21/22 (95%)**
- Granger: VERIFIED 2건 ✅ · PARTIAL 2건 · PENDING 39건
- 추론등급: 선행성 2건, 상관 2건, 기술적 26건

**실패 케이스 분석** (사후 원문 검증으로 정정 — 2026-06-09)
| 케이스 | 실제 원인 |
|--------|------|
| korean_peninsula_alliance | **Gemini API 과부하** (full_text 44자 "API 과부하" 메시지) — 일시적 노이즈, 코드 무관 |
| china_cyber_us | 생성 449자에서 중단 (잘림) — 컨텍스트 길이 아닌 생성 조기 종료, 별개 이슈 |
| china_ai_export_ban | [검증포인트][문헌공백] 섹션 누락 (포맷 프롬프트) |
| india_indo_pacific_balancing | [검증포인트][문헌공백] 섹션 누락 (포맷 프롬프트) |
| taiwan_liberal_vs_realist | [단계5] 누락 · 질적 2.5/5 (경쟁이론 수치 비교 미충족) |

**진단 (사후 코드 분석으로 근본 원인 규명)**: 이론 51개 적재는 **경쟁이론엄밀(3.40)에 거의 무효**였다.
theory_comparator.py가 비교에 등판시키는 이론이 `_SECTOR_THEORY_PAIRS`/`_REGION_THEORY_PAIRS`에
**하드코딩된 11개**로 고정 → 라이브러리 51개 중 추가한 24개는 영원히 미선택.
구조 결함 3개: ① 선택 풀 11개 고정 ② 실측 주입 tid 문자열 하드코딩(`if "mahan" in tid`) ③ 앵커 레지스트리 10개.
판정 코멘트 15개가 일관되게 "실측 비교가 수치 편차로 이어지지 못함" — [앵커 미제공] 26회 등장.
→ 진짜 레버는 이론 추가가 아니라 **theory_comparator 선택·앵커·실측 배선 확장** (다음 사이클 8-C-2).
※ 단 군사·사이버 케이스는 변수가 milex_gap 하나로 몰려 차별화 불가 → §20 Phase D 데이터 벽 잔존.

---

### v8.7.0 구현 내역 (이론 대량 적재 12개 — 8-D 후속 4차, 51개 달성, 2026-06-09)

**목표**: 50개+ 이론 적재 — 방법론·사이버·기술·인도태평양 핵심 이론 완비

| 파일 | 이론 | 폴더 |
|------|------|------|
| `apt_attribution_theory.md` | APT 귀속 이론 (Rid & Buchanan 2015) | `06_cyber/` |
| `cyber_sovereignty.md` | 사이버 주권론 (Deibert 2013) | `06_cyber/` |
| `dual_use_technology.md` | 이중용도 기술 통제론 (Feigenbaum/Bauer) | `03_techno/` |
| `nuclear_taboo_theory.md` | 핵 금기 이론 (Tannenwald 1999) | `04_indo_pacific/` |
| `burden_sharing_theory.md` | 동맹 비용분담 이론 (Olson & Zeckhauser 1966) | `04_indo_pacific/` |
| `nuclear_nonproliferation_theory.md` | 핵 비확산 이론 (Waltz vs Sagan 1981) | `04_indo_pacific/` |
| `constructivism.md` | 구성주의 (Wendt 1992) | `00_methods/` |
| `prospect_theory_ir.md` | 전망 이론 (Levy 1992, Mercer) | `00_methods/` |
| `escalation_theory.md` | 에스컬레이션 이론 (Kahn 1962) | `05_gray_zone/` |
| `economic_sanctions_theory.md` | 경제 제재 이론 (Hufbauer/Drezner) | `05_gray_zone/` |
| `ai_strategic_competition.md` | AI 전략 경쟁론 (Allen/NSCAI 2021) | `03_techno/` |
| `critical_minerals_security.md` | 핵심 광물 안보론 (Overland 2019) | `03_techno/` |

**인덱싱 결과**: 124개 upsert, 오류 0

**섹터별 이론 수 (v8.7.0 기준)**

| 섹터 | 이전 | 현재 |
|------|------|------|
| indo_pacific | 15개 | 20개 |
| gray_zone | 6개 | 8개 |
| techno | 4개 | 7개 |
| maritime | 6개 | 6개 |
| energy | 5개 | 5개 |
| cyber | 3개 | 5개 |
| **합계** | **39개** | **51개** |

**claim_ledger 기대 효과**: 방법론(구성주의·전망이론)·핵 이론(금기·비확산) 추가로
비자명성 탐지 커버리지 확장 + APT 귀속·사이버 주권으로 사이버 섹터 원장 신호 강화

---

### v8.6.0 구현 내역 (이론 대량 적재 12개 — 8-D 후속 3차, 2026-06-09)

**목표**: 피인용 rival_theories 우선 + 취약 섹터(gray_zone·energy·maritime) 강화

**피인용 분석 기반 우선 추가 (3회/2회 피인용)**

| 파일 | 이론 | 폴더 | 피인용 |
|------|------|------|-------|
| `liberal_institutionalism.md` | 자유주의 제도론 (Keohane & Nye 1977) | `04_indo_pacific/` | 3회 |
| `hegemonic_stability_theory.md` | 패권 안정론 (Kindleberger 1973) | `04_indo_pacific/` | 2회 |
| `conventional_deterrence.md` | 재래식 억지론 (Mearsheimer 1983) | `04_indo_pacific/` | 2회 |
| `coercive_diplomacy.md` | 강압 외교 (Schelling 1966) | `04_indo_pacific/` | 2회 |

**섹터별 강화**

| 파일 | 이론 | 섹터 |
|------|------|------|
| `power_transition_theory.md` | 세력전이론 (Organski 1958) | indo_pacific |
| `democratic_peace_theory.md` | 민주 평화론 (Doyle 1983) | indo_pacific |
| `proxy_war_theory.md` | 대리전 이론 (Mumford 2013) | gray_zone |
| `salami_slicing.md` | 살라미 전술 (Mastro/Fravel 2014) | gray_zone |
| `lawfare.md` | 법전쟁 (Dunlap 2001) | gray_zone |
| `rentier_state_theory.md` | 렌티어 국가론 (Beblawi 1987) | energy |
| `energy_security_theory.md` | 에너지 안보론 (Yergin 1991) | energy |
| `corbett_sea_control.md` | 코르벳 제한적 제해권 (Corbett 1911) | maritime |
| `command_of_the_commons.md` | 공유지 지배권 (Posen 2003) | maritime |
| `techno_globalism.md` | 기술 세계주의 (Rosecrance 1996) | techno |
| `cognitive_warfare.md` | 인지전 이론 (du Cluzel 2020) | cyber |

**인덱싱 결과**: 112개 upsert, 오류 0

**섹터별 이론 수 (v8.6.0 기준)**

| 섹터 | 이전 | 현재 |
|------|------|------|
| indo_pacific | 6개 | 15개 |
| gray_zone | 3개 | 6개 |
| maritime | 4개 | 6개 |
| energy | 3개 | 5개 |
| techno | 3개 | 4개 |
| cyber | 2개 | 3개 |
| **합계** | **21개** | **39개** |

**claim_ledger 기대 효과**: rival_theories 피인용 이론들이 실제 문서로 존재하게 됨
→ 원장 신호 ②(경쟁이론 미해결 쌍)의 재료 대폭 확충 → 경쟁이론엄밀 상승 예상

---

### v8.5.0 구현 내역 (이론 신규 3개 추가 — 8-D 후속 2차, 2026-06-09)

**목표**: 원장 신호 ①②의 재료 확충 — 안보딜레마·역외균형·사이버 공세-방어 균형 신규 추가

| 파일 | 이론 | 폴더 |
|------|------|------|
| `security_dilemma.md` | 안보 딜레마 (Jervis 1978) | `04_indo_pacific/` |
| `offshore_balancing.md` | 역외균형 전략 (Mearsheimer & Walt 2016) | `04_indo_pacific/` |
| `cyber_offense_defense_balance.md` | 사이버 공세-방어 균형 (Lynn 2010, Buchanan 2017) | `06_cyber/` |

**7-A 필드 완비**: 모든 이론에 IV·DV·conditions·falsifiable_prediction·known_counterexample·rival_theories 포함.

**결과**: 총 이론 97개 (전 24개 → 이론 파일만 이전 21+3=24개 concept 이론). claim_ledger `_fetch_theory_claims` 확인 — 3개 모두 정상 노출.

**경쟁이론 커버리지 확장 (신규 이론의 rival_theories)**:
- 안보딜레마 ↔ Balance of Threat (Walt), Deterrence Theory, Offensive Realism
- 역외균형 ↔ Liberal Hegemony (Ikenberry), Primacy Theory, Alliance Entrapment
- 사이버 공세-방어 ↔ Cyber Deterrence (Libicki), Digital Iron Curtain, Security Dilemma in Cyberspace

---

### v8.4.0 구현 내역 (이론 라이브러리 보강 — 8-D 후속, 2026-06-09)

**진단**: 8-D 원장 메커니즘은 완성됐으나 신호 ①②(반례·경쟁이론)의 재료인 **이론 문서가
얇았다**. 이론 21개 중 9개가 7-A 프로파일 미완(반례·경쟁이론·예측 필드 빈 껍데기) →
검색엔 잡히나 원장 공백 탐지엔 미기여. 그 9개가 하필 골드셋 도메인과 정확히 겹침.

**작업**: 빈 껍데기 9개에 7-A 5종 필드(IV·DV·conditions·falsifiable_prediction·
known_counterexample·rival_theories) 추가. 품질 바 = 반례는 구체적·검증가능(막연한
'상황에 따라' 금지), 경쟁이론은 예측이 갈리는 진짜 긴장 쌍. 사용자(전공자) 검수.

| 보강 이론 | 핵심 반례 (검증가능) |
|----------|---------------------|
| 반도체 공급망 (TSMC) | CHIPS법·라피더스·SMIC 분산 시 전이 강도 하락 |
| 초크포인트/SLOC | 후티 공격에도 유가 제한적(2024~25, SPR·OPEC+ 흡수) |
| 자원의 저주 | 노르웨이·보츠와나 — 제도 질이 매개변수 |
| 정보전·인지전 | 핀란드·에스토니아 — 수용자 회복력이 매개 |
| 확장억제 | 핵우산 하 한국 독자핵 여론 70% — reassurance 미보장 |
| 코리아 디스카운트 | 밸류업 후에도 지속·반도체 호조 시 약화 — 단일 원인 아님 |
| FONOP | 2015~ 정례화에도 인공섬 군사화 지속 — 선언적 한계 |
| 진주목걸이 | 함반토타·과다르 군사기지화 정체 — 군민겸용 가정 한계 |
| 기술 민족주의 | 수출통제가 SMIC 7nm 자립 가속 — 역효과 |

**결과**: 이론 프로파일 완비 **12/21 → 21/21**. 모든 골드셋 케이스에서 원장 신호
①②가 표시 상한(반례5·경쟁4) 충족 (이전엔 다수 케이스 신호 얇음).

**eval (gold15 --judge) — 8-D 전체 진행 경로**

| 지표 | v8.2.0 (21심판) | 8-D 직결 (9) | v8.4.0 보강 (10) |
|------|----------------|-------------|------------------|
| **비자명성** | 3.43 | 3.56 | **3.70** |
| 추론정직성 | 3.33 | 3.44 | 3.50 |
| 경쟁이론엄밀 | 3.38 | 3.44 | 3.30 |
| 반증가능성 | 3.52 | 3.44 | 3.80 |
| **종합** | 3.42 | 3.47 | **3.58** |
| PASS | — | 13/15 | **15/15** |

**정직한 판정**:
1. ✅ 이론 보강이 비자명성을 직접 끌어올림 (3.43→3.70, +0.27). 2점대 케이스 소멸.
2. ✅ 종합 3.58 — Phase 8 전체 최고치. PASS 15/15(잘림 실패 0).
3. ⚠️ **경쟁이론엄밀 3.30 정체** — 원장이 경쟁이론을 풍부히 *노출*하나 그것들 간 *수치 판정*
   미수행. 이건 라이브러리 콘텐츠가 아니라 **8-C 앵커를 경쟁이론쌍 판정까지 확장**해야 풀림.
4. 비자명 3.9·종합 4.2 목표엔 미달이나 명확한 상승 궤도.

**다음 후보**:
- (a) 8-C 앵커 확장 — 원장이 노출한 경쟁이론쌍을 수치로 판정 → 경쟁이론엄밀 공략
- (b) cyber 이론 추가 (현재 libicki 1개) + 신규 정전 이론(안보딜레마·세력균형·역외균형)
- (c) Phase 10 후보: 하이브리드 임베딩 검색 (사용자 합의 — 추론 게이트 후)

### v8.3.0 구현 내역 (8-D — 문헌 공백 탐지, 2026-06-09)

**진단**: [문헌공백] 섹션이 순수 LLM 생성 → 엔진이 라이브러리 94개 문서가 실제로
무엇을 주장하는지 모른 채 추측 → 막연한 "추가 연구 필요"류 → 비자명성 3.43 고착.
**재료는 이미 있음**: 7-A가 이론 문서에 `known_counterexample`·`rival_theories` 구조화 완료.

**설계 결정 (사용자 승인)**: "기존 필드만 + 미래 확장 가능" — 오늘은 손 안 가게(기존
필드 자동 활용), 미래엔 막지 않게(`contested_by` 파이프라인 준비). 벡터 DB 등 신규 인프라 0.

| 파일 | 내용 |
|------|------|
| `services/claim_ledger.py` (신규) | 결정론적 문헌 공백 원장 — 3종 신호(①반례 클러스터 ②경쟁이론 미해결 ③교차도메인 밀도) + ④contested_by 확장 훅. 이론 프로파일 직접 조회(`_fetch_theory_claims`)로 검색 순위 의존 제거 |
| `services/library/md_indexer.py` | `contested_by` 컬럼 추가(스키마·마이그레이션·파싱·INSERT) — 미래 확장 훅, 오늘은 비어둠 |
| `services/intel_analyzer.py` | SELECT에 `contested_by` 추가 + 원장을 priority tier로 주입 (theory_cmp_ctx 패턴 재사용) |
| `api/intel_query.py` | [문헌공백] 원장 grounding 필수화 + **[비자명기여] 원장 직결** (3종 신호 → 반직관·교차도메인·범위조건 직접 매핑) |

**Token-Zero 준수**: 원장 추출·집계는 전부 Python 결정론. Gemini는 서술만. 추출 LLM 호출 0.

**확장성**: 새 라이브러리 문서 = md_indexer 인덱싱 즉시 원장 자동 합류(유지보수 0).
신호별 재료: ①② = 이론 문서(현재 12개, 보강 시 강화), ③ = 모든 문서(브리핑 포함).

**eval 결과 (골드셋 15, --judge) — 2단계 측정으로 진짜 레버 규명**

| 지표 | v8.2.0 (21심판) | 8-D run1 문헌공백만 (11) | 8-D run2 +비자명기여직결 (9) |
|------|----------------|------------------------|---------------------------|
| **비자명성** | 3.43 | 3.45 | **3.56** |
| 추론정직성 | 3.33 | 3.18 | 3.44 |
| 경쟁이론엄밀 | 3.38 | 3.09 | 3.44 |
| 반증가능성 | 3.52 | 3.64 | 3.44 |
| **종합** | 3.42 | 3.34 | **3.47** |

**정직한 판정**:
1. ✅ 메커니즘 완전 작동 — [문헌공백]이 원장 11/11 인용 ("원장 ②에서 지적된 바와 같이...")
2. ✅ **진짜 레버 규명** — run1(문헌공백만)은 비자명성 정체(3.45). [비자명기여]에도 원장을
   직결한 run2에서 3.56으로 상승. 심판은 [문헌공백] 칸이 아니라 [비자명기여] 라인을 채점함이 확인됨.
3. ◐ **목표 3.9 미달** — 3.56까지 왔으나 부족. 심판 표본 9케이스(잘림 재시도로 축소)라 노이즈 큼.
4. 8-D 핵심 교훈: 원장은 좋은 인프라지만 **이론 문서가 12개로 얇아** 신호 ①②가 제한적.
   → 비자명성 추가 상승은 **이론 라이브러리 보강**(반례·경쟁이론 늘리기)이 다음 레버.

**다음 후보 (사용자 논의)**:
- (a) 이론 라이브러리 보강 — 신호 ①② 재료 확충 → 비자명성 직접 상승
- (b) 하이브리드 임베딩 검색 — 키워드 LIKE의 한국어 재현율 한계 보완 (벡터 DB ❌, 메모리 내
  Gemini 임베딩 + LIKE 병행). 94개 규모라 DB 불필요. 별도 사이클, 선행 검증 필요

### v8.2.0 구현 내역 (8-C 보완 + 8-B — Granger 강화, 2026-06-09)

**8-C 보완: 앵커 인용 강제**

| 파일 | 변경 내용 |
|------|---------|
| `api/intel_query.py` | 앵커 인용 "있으면 인용" → **필수 규칙**으로 강화. context에 앵커 있으면 `판정:` 줄에 반드시 포함, 생략 시 "규칙 위반" 명시. 없을 때만 `[앵커 미제공]` |
| `api/intel_query.py` | `asyncio` 추가 + Gemini 503 지수 백오프 재시도 (5s→15s→30s, 최대 3회) |

**8-B: Granger 방법론 강화 (P90 극단 이벤트 + 구조적 설명 승격)**

이론적 근거: 지정학 충격의 시장 전이는 비선형 — 일상 이벤트는 노이즈, 극단 사건만 임계 전이 발생 (Farrell & Newman 2019).

| 파일 | 변경 내용 |
|------|---------|
| `services/cascade/correlation.py` | `_load_extreme_event_series()` 추가 — 비제로 P90 초과분(excess severity) 시리즈. 비제로 20일·극단 10일 최소 조건, weekly sparse 시리즈 제외 |
| `services/hypothesis_extractor.py` | `HypothesisSpec`에 `extreme_granger_p`, `extreme_granger_f` 필드 추가 |
| `services/hypothesis_verifier.py` | 정규 Granger p>0.15 시 P90 재시도 → 극단 유의(p<0.05) 시 PARTIAL 승격 + `[비선형 임계 전이]` 설명. 양쪽 모두 실패 시 `[구조적 설명]` inference_caveat 자동 추가. 캐시에 extreme_granger_p·f 저장 |

**eval 결과 (30케이스 --judge, 2026-06-09)**

| 지표 | v8.1.0 (7케이스) | **v8.2.0 (30케이스)** | 목표 | 판정 |
|------|-----------------|----------------------|------|------|
| PASS | — | **29/30 (97%)** | — | ✅ |
| 평균 신뢰도 | 93 | **90** | — | 동급 |
| **LLM 심판 종합** | 3.43 | **3.42** | 4.2+ | ⬜ 정체 |
| — 비자명성 | — | 3.43 | — | — |
| — 추론정직성 | — | 3.33 | — | — |
| — **경쟁이론엄밀** | 3.29 | **3.38** | 4.0+ | +0.09 ↑ |
| — 반증가능성 | — | 3.52 | — | — |
| 경쟁이론 수치비교[엄격] | 100% | **94%** | — | — |
| **Granger VERIFIED** | 0건 | **2건** ✅ | 2건 | ✅ 달성 |
| Granger 상관(PARTIAL) | 3건 | **5건** | — | ↑ |

**VERIFIED 2건 상세:**
- `middle_east_hormuz` (사건→사건 B4): 중동 분쟁 → 호르무즈 도발 전이 p=0.0000 (grounded=True)
- `ukraine_middleeast` (사건→사건 B4): 우크라이나 → 중동 분쟁 전이 p=0.0039 (grounded=True)

**정직한 판정:**
- ✅ Granger VERIFIED 2건 달성 (8-B 성공) — 단, B4 사건→사건 케이스로 LLM 심판 점수 낮음(2.8)
- ✅ 경쟁이론엄밀 +0.09 (8-C 보완 효과)
- ⬜ LLM 심판 종합 3.42 — 목표 4.2+까지 여전히 0.8p 차이
- ⚠️ `nato_burden_sharing` 케이스 1.0/5 충격 (NATO 데이터 부재) — 평균 하향 압력
- `nato_burden_sharing` 이상치 제외 시 종합 ~3.55 추정

**다음 (8-D):**
- 문헌 공백 탐지 — 라이브러리 주장 구조화 + 교차 모순 탐지

### v8.2.1 핫픽스 — nato_burden_sharing 데이터 공백 해결 (2026-06-09)

**문제**: `nato_burden_sharing` 케이스 1.0/5 (전체 평균 끌어내림)
- entity_parser가 "NATO·자유편승·방위비" 키워드에서 actors/sectors 미추출
- SIPRI milex 조회에 USA 하나만 전달 → 회원국 비교 불가

**수정:**
| 파일 | 내용 |
|------|------|
| `services/entity_parser.py` | NATO 키워드 감지 시 actors에 USA·DEU·FRA·GBR·POL 자동 추가 + `indo_pacific` 섹터 추가 |
| `services/intel_analyzer.py` | NATO core 4개국 감지 시 TUR 추가 확장 (DB 확인된 회원국만) |

**결과**: 1.0/5 → **3.75/5** (비자명 3·정직 4·경쟁 4·반증 4)

### v8.1.0 구현 내역 (8-C — 경쟁이론 정량 앵커, 2026-06-07)

**진단**: 융합2 편차 사전계산에도 경쟁이론엄밀이 안 오른 이유 — 계산한 게 "두 실측값 격차"지
"이론 예측 대비 실측 편차"가 아니었고, 이론 프로파일에 예측 방향·임계값이 부호화 안 됨.
+ 대부분 이론에서 DV(양보 빈도) 실측 시계열 부재 → IV만 있음.

**설계 결정 (사용자 승인)**: DV 데이터 공백으로 "IV→DV 회귀 편차"는 불가 →
**이론별 정량 앵커(임계값) 대비 실측 편차 = 전제조건 충족도**로 한정. "이론 입증" 아님(정직).
DV hand-coding 데이터셋 확보 시 "입증"으로 격상 → CLAUDE.md §20 Phase D에 장기계획 기록.

| 파일 | 내용 |
|------|------|
| `theory_comparator.py` | `_THEORY_ANCHORS`(9개 이론 임계·방향) + `_collect_anchor_metrics` + `_anchor_verdict` + 블록·종합 주입 |
| `api/intel_query.py` | [경쟁설명] 지침에 앵커 편차·전제충족 인용 안내 |
| `arithmetic_layer.py` | 재사용 (delta·fmt_signed·pct_point_gap) |
| `docs/cycle8c_design.md` | 설계 핸드오프 |

**정직성 가드**: 임계는 표준 기준만 (HHI 2500=美 DOJ, WGI 0, Polity ±6, HIIK 3).
실측 없으면 판정 생략. 종합은 metric 스케일 상이로 충족 여부만 비교(편차 크기 직접비교 금지).

**eval 결과 (골드셋 15, --judge --fast)**

| 지표 | v7.8.9 | v7.11.0 | v8.1.0 | 비고 |
|------|--------|---------|--------|------|
| 경쟁이론엄밀 | 3.43 | 3.10 | **3.29** | 8-C로 +0.19 회복 |
| 종합 | 3.68 | 3.42 | 3.43 | 정체 |
| 추론 사다리(상관) | — | 1/15 | **3/14** | 개선(8-A 누적) |
| 경쟁이론[엄격] | 100% | 91% | 100% | 회복 |
| 평균 신뢰도 | 93 | 92 | 93 | 동급 |
| 심판 케이스 수 | ? | 10 | **7** | 표본 작아 노이즈 큼 |

**정직한 판정**: 8-C는 **메커니즘 성공, 인용 강제 부족**의 절반 성공.
- 앵커 라인 정확히 생성·주입 확인 (taiwan_strait HHI 25449, TSMC↔SMIC 55.8%p 등 전부 Python 계산)
- `china_rareearth_techno`는 의도대로 작동 — "판정: 높은 HHI는 전제 조건 충족", competing_rigor **4점(최고)**
- **그러나 15케이스 중 앵커 '전제 충족' 표현 인용은 1건뿐** → Gemini 인용률 낮아 평균 효과 제한
- 원인: 프롬프트가 "있으면 인용"의 선택적 지침. 심판 7케이스라 수치 자체도 노이즈 큼

**다음 (보완 + 8-B)**:
1. [8-C 보완] 프롬프트 인용 강제 — "context에 앵커 있으면 [경쟁설명] 판정에 반드시 포함"
   (없으면 [산술 미제공] 유지 — 억지 생성 방지). eval 재측정은 8-B와 묶어 비용 절약.
2. [8-B] Granger 방법론 강화 — 극단사건 P90 + 고빈도 종속 + 조건부 통제

### v7.11.0 구현 내역 (8-A — H1 측정가능성 강제, 2026-06-07)

**진단**: Type_B 41%는 ① Gemini가 "분쟁 건수·도발 빈도"류를 종속변수로 자주 생성 +
② `_classify_variable_type`이 Type_C 키워드를 최우선 판별 → "유가 의존도"처럼 측정 가능한데
추상 키워드 섞인 변수를 Type_C로 오분류. Type_B는 verifier에서 검정 경로 없어 항상 PENDING 사망.

| 파일 | 내용 |
|------|------|
| `config/measurable_variables.yaml` (신규) | 검증 가능 변수 단일 카탈로그 — 시장지표 12개(ticker 정합) + ACLED 지역 10개 |
| `hypothesis_extractor.py` | yaml 로더 + `build_measurable_menu()` + `_classify`에 측정가능 우선 단계(`_match_ticker` 성공 시 Type_A) |
| `api/intel_query.py` | H1 규칙에 측정가능 메뉴 주입 + 종속변수 강제 선택 지침 |
| `docs/cycle8a_design.md` (신규) | 설계 핸드오프 |

**정직성 가드**: 측정 불가 변수는 Type_C/B 유지(억지 Type_A 전환 금지), "적합한 Y 없으면 정량 가설 없음" 명시.

### v7.11.0 eval 결과 (2026-06-07, 골드셋 15케이스 --judge --fast)

| 지표 | v7.8.9 | v7.11.0 | 판정 |
|------|--------|---------|------|
| **Type_B 비율** | 41% | **14%** (3/21) | ✅ 목표(<15%) 달성 |
| Type_A | — | 67% (14/21) | 검정 가능 변수로 이동 |
| PASS | 12/15 | 14/15 | ↑ |
| 평균 신뢰도 | 93 | 92 | 동급 |
| 경쟁이론 수치비교[엄격] | 100% | 91% (10/11) | 이상치 1건 누락 |

**LLM 심판 종합 — 표면 3.42 (하락), 이상치 제외 시 3.56**

`hormuz_iran_blockade` 케이스가 API 잘림으로 [경쟁설명]·[검증포인트]·[문헌공백] 3섹션
통째 누락(재시도 5회 미복구) → competing_rigor 1·honesty 2로 평균 잠식. 코드 아닌 API 문제.

| 축 | 전체(10) | 이상치 제외(9) | v7.8.9 |
|----|---------|--------------|--------|
| 비자명성 | 3.60 | **3.67** | 3.57 ↑ |
| 추론정직성 | 3.50 | 3.67 | 3.86 |
| 경쟁이론엄밀 | 3.10 | 3.33 | 3.43 |
| 반증가능성 | 3.50 | 3.56 | 3.86 |
| **종합** | 3.42 | **3.56** | 3.68 |

**정직한 판정 (합리화 없이)**
1. ✅ 8-A 성공 — Type_B 41%→14%, 비자명성 오히려 ↑(3.57→3.67). 측정가능 강제가 추론 품질 무해.
2. 종합 하락 주범은 이상치 1개(응답 잘림). 제외 시 3.56으로 v7.8.9와 노이즈 범위(±0.12) 내.
3. **단, 융합2 편차 사전계산이 경쟁이론엄밀 점수로 전환 안 됨** (3.43→3.33). 인정해야 할 사실 —
   융합2는 산술 인프라만 깔았고, theory_comparator의 편차→판정 연결은 **8-C 과제**임이 재확인.

**다음**: 8-C (경쟁이론 편차 본격 — 산술 레이어를 예측↔실측 편차 판정에 연결)

### v7.9.0 구현 내역 (융합1 — 관련성 게이트, 2026-06-07)

**intel_analyzer.py 단일 파일 작업**

| 추가 | 내용 |
|------|------|
| `_SOURCE_SPECS` | 17개 data 소스 섹터 친화도 테이블 |
| `_coverage_bonus()` / `_score_source()` | Token-Zero 관련성 점수 함수 (섹터 적중 +2.0, off-domain -1.0, 지역·행위자 coverage +0.5/+0.3) |
| `_emit_*()` × 17개 | 각 data 소스를 `list[str]` 블록으로 반환하는 순수 emitter 함수 |
| `_SOURCE_EMITTERS` | key → emitter 매핑 dict |

**`_build_context` 변경**
- `theory_cmp_ctx` 파라미터 추가
- backbone 직후 `theory_cmp_ctx` **priority tier** 우선 주입 (구 "잔량 append" 폐지)
- 17개 인라인 data 섹션 → 관련성 점수 정렬 후 budget 한도까지 emit
- 정직성 가드: 점수는 주제 적합성만, 가설 지지 여부 금지

**`build_intel_context` 변경**
- `theory_cmp_ctx=theory_cmp_ctx` 키워드 인자 전달
- 구 "잔량 append" 블록 제거

**효과**: cyber 쿼리 → CSIS·ITU 상위 배치 / energy 쿼리 → EIA·FRED 상위 배치 / theory_cmp 누락 0

### v7.10.0 구현 내역 (융합2 — Token-Zero 산술 레이어, 2026-06-07)

**신규: `services/arithmetic_layer.py`**
- `pct_change`, `delta`, `pct_point_gap`, `ratio`, `share_of`, `hhi`, `concentration_label`, `fmt_signed`
- 전부 None-safe · 0분모-safe · 예외 없이 None 반환 · 부작용 0

**`theory_comparator.py` 수정**

인라인 산술 3곳 → arithmetic_layer 통일 (수치 불변):
- `_get_sipri_arms_hhi`: `(dominant/total*100)` → `share_of()`
- `_get_fred_for_theories`: `(latest-oldest)/oldest*100` → `pct_change()`
- `_get_trade_hhi`: `sum(r²)*10000` → `hhi()`

격차 사전계산 주입 (`(사전계산)` 꼬리표):
- mahan·a2ad 블록: SIPRI 국방비 GDP% 격차
- mearsheimer·waltz 블록: 권력 격차(국방비)
- weaponized_interdependence 블록: FRED 추세 부호 강제(`fmt_signed`) + trade HHI `concentration_label`
- digital_iron_curtain 블록: TSMC↔SMIC 점유율 격차

**`intel_query.py` 수정**
- `system_role`에 **Token-Zero 산술 규율** 블록 추가 (암산 금지, context 값 인용 강제)
- [경쟁설명] 예시 교체 → `(사전계산)` 꼬리표 인용 패턴 (`-37.0%p, 사전계산`)

**설계 문서**
- `docs/fusion1_design.md` — Opus 설계 핸드오프
- `docs/fusion2_design.md` — Opus 설계 핸드오프

---

## ★ 차기 개선 로드맵 (2026-06-07 수립, Phase 7-D 완료분) — 인사이트 학술 완성도 + 성능

### 현재 좌표
- 형식·증거 등급: ✅ 천장 도달 (증거 92~100, PASS 30/30) → **더 손대지 말 것**
- 내용·추론 등급: ⬜ **프런티어** — LLM 심판 종합 2.6/5 (~52%)
  - 반증가능성 3.14(최고) · 비자명성 2.79 · 추론정직성 2.45 · **경쟁이론엄밀 2.21(최저, 데이터 병목)**
  - 추론 사다리: 대부분 **기술적** 고착 (VERIFIED 2 / PARTIAL 4)
- 검증된 인과(v7.8.0): **데이터→theory_comparator 연결 케이스만 경쟁이론엄밀↑** (나머지는 심판 노이즈)

### 착수 순서 (확정)

**[1순위] AR-1a — 기존 적재 데이터 완전 연결 (싼 값, 검증된 레버)**
- DB에 이미 있으나 theory_comparator 미연결인 데이터(Polity5·HIIK·ITU·OWID)를 지역×이론쌍에 연결
- east_china_sea처럼 전 지역의 이론쌍·실측 매핑 커버리지 완성
- 신규 적재 0 → 비용 최소, 경쟁이론엄밀 직접 상승
- 측정: [경쟁설명] 수치비교율 (현재 ~50% [엄격] → 케이스 다양성 확대)

**[2순위] AR-2 — 추론 사다리 천장 돌파 (구조적 약점)**
- 현재 Type_C는 H1 종속변수를 무시하고 '지역분쟁→지역proxy' 대체검정 → H1의 실제 주장 미검정
- 종속변수가 실측 시계열(SIPRI·EIA·FRED·OWID)에 매핑되면 proxy 대신 **그 변수 직접 검정**
- 측정: VERIFIED/PARTIAL 건수 (현재 2/4)
- PERF-2(Granger 캐싱)와 자연 중첩 → 함께 처리

**[3순위] AR-1b — 신규 데이터 (7-D L2/L3)**
- 기존 데이터 소진 후 Comtrade(무역 HHI) → 상호의존 무기화 IV 수치화, 이어서 GTD·ACLED 확장
- 측정: 신뢰도 평균 85+ + UNVERIFIED↓

**[가드레일] AR-3 — 측정 방법론 (전 과정에 병행)**
- 골드셋 10~15개 + 고정 루브릭 → 심판 점수 과적합(Goodhart) 방지
- 원칙: 심판 점수↑가 환각↑ 유발하면 기각 (정직성 > 프록시)

**[최후순위] PERF — 성능 (학술 프런티어 다음)**
- 레이턴시(~33s) context 가지치기 · 정적 데이터 캐싱 · eval 분기당 1회

### 운영 원칙
- 형식 점수 무회귀 확인만 하고 건드리지 말 것 (천장)
- 데이터는 **적재→intel_analyzer 노출→theory_comparator 연결 3단계 모두** 해야 점수 반영 (v7.8.0 버그 교훈)
- Phase 8(시각화) 게이트: 신뢰도 85+ & 경쟁이론 수치비교 50%+ 동시 충족

### 진행 현황 (2026-06-07)
```
[1] AR-1a 데이터 연결   ✅ v7.8.5 → 경쟁이론엄밀 +0.15
[2] AR-2 추론 사다리    ✅ v7.8.6 → 대만달러 선행성 역량 추가(p=0.0005)
[병행] AR-3 가드레일    ✅ v7.8.7 (심판 절단버그+앵커, 다음 eval부터 적용)
[3] AR-1b Comtrade      ✅ v7.8.8 → Weaponized Interdependence IV 수치화 (HHI proxy)
[최후] PERF             ✅ v7.8.9 → 3종 TTL 캐시 (yfinance 6h·Granger 1h·정적 5m)
[eval] 골드셋 측정      ✅ v7.8.9 기준 — 종합 3.68/5 (석사 중반), Phase 8 게이트 충족
```

### v7.8.9 eval 결과 (2026-06-07, 골드셋 15케이스 --judge)

| 지표 | v7.8.6 | v7.8.9 | Δ |
|------|--------|--------|---|
| PASS 비율 | 14/17 (82%) | 12/15 (80%) | 동급 |
| 평균 신뢰도 | 70/100 | **93/100** | **+23** |
| 경쟁이론 수치비교 [엄격] | ~50% | **100%** | **+50%p** |
| LLM 심판 종합 | 2.75/5 | **3.68/5** | **+0.93** |
| — 비자명성 | 2.77 | 3.57 | +0.80 |
| — 추론정직성 | 2.68 | 3.86 | +1.18 |
| — 경쟁이론엄밀 | 2.36 | 3.43 | +1.07 |
| — 반증가능성 | 3.18 | 3.86 | +0.68 |

**Phase 8 게이트 판정**: 신뢰도 93(≥85) ✅ + 경쟁이론 수치비교 100%(≥50%) ✅ → **Phase 8 착수 가능**

**학술 레벨**: 학부 우수(v7.8.0) → **석사 중반(v7.8.9)**

**남은 취약점**
- Granger 전원 PENDING (17개, p=0.54~0.98): Type_B 41% (측정불가 변수) + 평균 분쟁 강도→시장 비선형 구조
- 경쟁이론엄밀 3.43: 레이블 형식은 충족, 수치 편차 계산 깊이 부족
- 비자명성 3.57: 조합적 통찰 수준, 독창적 문헌 공백 식별 미흡
- 503 오류 5건 (Gemini 과부하 — 재시도로 대부분 복구)

**박사 수준(4.5/5) 도달 조건**
- Granger 유의 2건+ (현재 0건) → Type_B→Type_A 전환 + GTD 데이터 필요
- 경쟁이론 수치 편차 계산 심화 (예측값 vs 실측값 오차 명시)
- 비자명성: 기존 문헌이 다루지 않은 패턴 식별

**eval 비용 절감 (이번 세션 구현)**
- `--gold` 플래그: 30→15 케이스 (~50% 시간 절감)
- `--fast` 플래그: 대기 5s→2s, 재시도 15/40s→5/15s
- `eval_cases.yaml` 골드셋 15개 태깅 완료

### v7.8.8 구현 내역 (AR-1b Comtrade + 데이터 파이프라인 버그 5종 수정)

**AR-1b: UN Comtrade 무역 의존도 → Weaponized Interdependence IV 수치화**
- `_get_trade_dependency()` 신규 (intel_analyzer.py #23번 소스)
  - historical_trade_matrix 6,607건 활용 (HS 8542·27·26, 2020~2025)
  - dependency_ratio ≥ 0.1(10%) 쌍만 반환 — 비대칭 의존 구조 포착
  - 지역→핵심행위자 매핑 8개 지역 커버
- `_get_trade_hhi()` 신규 (theory_comparator.py)
  - HHI proxy = 상위 3쌍 dependency_ratio² 합산 × 10000 (>2500=독과점)
  - weaponized_interdependence·resource_weaponization 이론쌍에 자동 연결
- 검증 결과 (taiwan_strait, CHN·USA·KOR):
  - HS26 희토류 HHI=25449 (독과점, KOR←CHN 92.9%)
  - HS8542 반도체 HHI=17797 (독과점, KOR←CHN 79.9%)
  - [경쟁설명]에 "실측 — 반도체(HS 8542) 공급망 HHI: 17797 [UN Comtrade]" 자동 삽입

**할루시네이션·병목 5종 수정 (별도 세션)**
- Fix A: ITU IDI 경고 섹션 헤더로 이동 (사이버 방어력 동치 금지 선제 명시)
- Fix B: cascade `correlation_score` → `룰매칭강도` 라벨 변경
- Fix C: FRED 기본값(유가·금) 무조건 주입 제거 (`return []`)
- Fix D: `_over_budget()` 헬퍼 + Cycle 6-A/7-D 섹션 10개 가드 + 하드 절단 + theory_cmp_ctx 예산 가드
- Fix E: SIPRI arms 조건 단순화 (`bool(sectors) and all(s in {"techno","cyber"}...)`)

**이론 연결**: Farrell & Newman Weaponized Interdependence — 공급망 집중도(IV)가 정치적 레버리지로 전환되는 메커니즘을 Comtrade HHI로 직접 수치화.

### v7.8.9 구현 내역 (PERF — 레이턴시 개선)

**3종 TTL 캐시로 반복 쿼리 레이턴시 단축**

| 캐시 | 위치 | TTL | 효과 |
|------|------|-----|------|
| PERF-1: yfinance 시장 시계열 | `correlation.py` `_market_cache` | 6h | 동일 ticker 재다운로드 방지 (~10-20s 절약) |
| PERF-2: Granger 결과 | `hypothesis_verifier.py` `_granger_spec_cache` | 1h | 동일 지역·ticker 쌍 재계산 방지 (~5-10s 절약) |
| PERF-3: 정적 소스 5종 | `intel_analyzer.py` `_STATIC_CACHE` | 5m | Polity5·HIIK·ITU·semi_market SQLite 중복 I/O 방지 |

- `_cache_get/_cache_set`: `correlation.py` 모듈 레벨 TTL 딕셔너리 헬퍼
- `_gcache_get/_gcache_set`: `hypothesis_verifier.py` Granger 전용 캐시 헬퍼
- `_scache_key/_scache_get/_scache_set`: `intel_analyzer.py` 정적 소스 캐시 헬퍼 (list→tuple 변환)
- 5분 TTL → 개발 중 DB 재적재 즉시 반영 가능, 프로덕션에서 불필요한 재조회 차단

### v7.8.6 측정 결과 (AR-1a+AR-2 누적, 옛 루브릭 — v7.8.0과 비교가능)
| 심판 축 | v7.8.0 | v7.8.6 | Δ |
|---------|--------|--------|---|
| 비자명성 | 2.79 | 2.77 | ~0 |
| 추론정직성 | 2.45 | **2.68** | +0.23 |
| 경쟁이론엄밀 | 2.21 | **2.36** | +0.15 |
| 반증가능성 | 3.14 | 3.18 | +0.04 |
| **종합** | **2.65** | **2.75** | **+0.10** |

단서: v7.8.6은 22케이스 채점(v7.8.0=29, 절단·재시도로 일부 누락) — 완전 동일표본 아님.
AR-2의 대만달러 선행성은 eval H1이 'TWD'를 명시해야 발동 → 이 케이스셋엔 미발동(역량만 확보).

---
---

## 완료된 Phase 작업 기록

> 아카이브:  (Phase 0~7 완료 작업 로그, ~2,600줄)
