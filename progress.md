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

## Phase 3 — 학습 도구 완성 (진행 중)

### 구현 체크리스트

| # | 항목 | 상태 |
|---|------|------|
| 1 | `md_indexer.py` — .md → SQLite FTS5 인덱싱 | ✅ |
| 2 | `deep_link.py` + `theory_library.yaml` — 이론↔지도 매핑 | ✅ |
| 3 | `api/library.py` — 6개 엔드포인트 | ✅ |
| 4 | `StateStore.js` — library 슬라이스 | ✅ |
| 5 | `TheoryLibraryView.js` — 풀스크린 2컬럼, marked.js 렌더, Gemini AI 설명 SSE | ✅ |
| 6 | `sandbox_solver.py` — BFS 가설 검증 엔진 | ✅ |
| 7 | `SandboxLabView.js` — Cytoscape 캔버스 + 검증 결과 UI + 튜토리얼 캔버스 자동생성 | ✅ |
| 8 | GDELT/RSS/Sanctions + 8단계 추론 루틴 | ✅ |

### 이론 라이브러리 (.md 파일)
`library/` 14개 완비 — 5대 섹터 전체 커버 (maritime·energy·techno·indo_pacific·gray_zone).

### ✅ Step 8 완료 — GDELT + Sanctions (2026-05-24)

- `backend/connectors/gdelt_connector.py` — Stage 1: 15분 export ZIP 다운로드, QuadClass≥3·GoldsteinScale≤-5·NumMentions≥3·5대섹터 FIPS 필터
- `backend/connectors/news_cross_validator.py` — Stage 2: Reuters·BBC·Al Jazeera·AP 4개 RSS 병렬 fetch, ≥2매체 언급 시 confidence 0.5→0.8
- `backend/services/gdelt_pipeline.py` — Stage 3 오케스트레이터 + GeoJSON 직렬화 (`unverified: true` 프로퍼티)
- `backend/models/event.py` — `confidence_score: float = 1.0` 필드 추가
- `backend/api/layers.py` — `GET /api/layers/gdelt` (15분 캐시)
- `frontend/src/layers/GdeltLayer.js` — 점선 테두리(미검증) / 실선(교차검증) 구분, ⚠️ 뱃지

실측: 24개 피처 | 교차검증 20개(✓) | 미검증 4개(⚠️) — confidence_score 0.8/0.5

### ✅ 제재 레짐 레이어 (2026-05-24)

- `backend/config/sanctions.yaml` — 15개 레짐 (UN SC·OFAC·EU·BIS, 5대 섹터 전체)
- `backend/connectors/sanctions_connector.py` — YAML → Event 정규화
- `backend/api/layers.py` — `GET /api/layers/sanctions` (24시간 캐시)
- `frontend/src/layers/SanctionsLayer.js` — 국가 버블 마커 (UN 보라/서방 주황/단자 파랑)

### ✅ 라이브러리 필터 UI 개편 (2026-05-24)

- `backend/services/library/md_indexer.py` — `use_case` 컬럼 추가 (concept/case_study/data/norm), `asset_type` → `use_case` 자동 파생
- `backend/api/library.py` — `_merge_db_only()` 추가 (YAML 미등록 DB-only 항목 지원), `get_theory()` DB-only fallback, `list_items()` DB-only 루프 + `use_case` 필터
- `library/04_sanctions_and_norms/` — 15개 제재 레짐 .md (asset_type: norm, use_case: norm)
- `frontend/src/views/TheoryLibraryView.js` — 섹터 탭·드롭다운 3개 → 칩 3행으로 전면 교체 (용도/지역/시대, 단일 선택, AND 조건)
- `frontend/styles/main.css` — `.lib-chip`, `.lib-chip-row`, `.lib-chip-label` 스타일 추가

라이브러리 DB: 29개 (이론 14 + 제재 15)

### ✅ ACLED 복합 중요도 점수 (2026-05-24)

- `backend/models/event.py` — `importance_score: float`, `cluster_count: int` 필드 추가
- `backend/services/importance_scorer.py` (신규) — 클러스터링(region+7일+inter1), 점수 계산(severity·recency·cascade·반복·gdelt, 5개 가중합)
- `backend/api/layers.py` — `get_conflict_events()`에 `cluster_events → score_events` 파이프라인 연결, GeoJSON 직렬화에 `importance_score·cluster_count·_score_breakdown` 포함
- `frontend/src/layers/ConflictEventsLayer.js` — importance 기반 zoom 가시성(≥0.7 항상/0.4~7 zoom≥5/나머지 zoom≥7), severity 4단계 반지름, 클러스터 배지, 팝업 breakdown
- `frontend/styles/main.css` — `.conflict-cluster-badge`, `.popup-importance` 스타일 추가

### ✅ ACLED Gemini on-demand 번역 (2026-05-24)

- `backend/connectors/gemini_translator.py` — SQLite 캐시(`translation_cache.db`), SHA-256 해시, Gemini 1.5 Flash 호출, 비용 추정(`estimate_cost`), 캐시 통계(`get_cache_stats`)
- `backend/api/translate.py` (신규) — `GET /api/translate` (importance≥0.7 게이트, 캐시 반영), `GET /api/translate/stats`
- `backend/main.py` — `translate_router` 등록
- `frontend/src/layers/ConflictEventsLayer.js` — ⭐ 이벤트 팝업에 "🌐 한국어로 보기" 버튼, `popupopen` 핸들러로 fetch → 스피너 → 번역 결과 div 교체
- `backend/.env.example` — `GEMINI_API_KEY` 항목 추가 (Google AI Studio 링크)
- `frontend/styles/main.css` — `.popup-translate-btn`, `.popup-translated` 스타일 추가

### ✅ GDELT 한국어 상세 템플릿 (2026-05-24)

- `backend/connectors/gdelt_connector.py` — CAMEO actor 코드 → 한국어 매핑(`_ACTOR_COUNTRY_KO`, `_ACTOR_TYPE_KO`), `_generate_description()` 3행 템플릿, `_actor_ko()`, `_instability_label()`
- `backend/services/gdelt_pipeline.py` — Stage 3: confidence 0.5→0.8 승격 시 description 재생성, `to_geojson()`에 `actor1_ko·actor2_ko` 노출
- `frontend/src/layers/ConflictEventsLayer.js` — GDELT 팝업 `actor1_ko·actor2_ko` 행, description `pre-line` 렌더

### ✅ 분쟁 레이어 통합 + 하단 UI 제거 (2026-05-24)

- `frontend/src/layers/ConflictEventsLayer.js` — ACLED + GDELT 병렬 fetch, 단일 레이어 통합 렌더링, 출처 뱃지 구분
- `frontend/index.html` — 하단 타임라인 패널(`#timeline-panel`) 제거, vis-timeline CDN 제거, `TimelineView` 연결 해제
- `frontend/index.html` — 분쟁 필터바(`#conflict-filter-bar`, 슬라이더/기간버튼) 제거, CASCADE GRAPH 패널 제거, `CascadeGraphView` 연결 해제
- `frontend/styles/main.css` — timeline·filter-bar·cgraph 관련 스타일 ~490줄 제거
- 파일 보존: `TimelineView.js`, `CascadeGraphView.js` (연결만 해제)

### ✅ 상단 3단 바 + 펜타곤 피자지수 + GDELT importance (2026-05-25)

**상단 3단 바 (48px)**
- `backend/api/stats.py` (신규) — `GET /api/stats/tension`, `/markets` (WTI·금·반도체·원달러), `/pizza-index`
- `backend/api/news.py` (신규) — `GET /api/news/ticker` (GDELT 전용, confidence≥0.8 우선·≥0.5 보충, 최신 8건)
- `frontend/src/views/TopBarView.js` (신규) — Row1(긴장도 `중동🔴78` compact + `🍕 26.6`), Row2(마켓 4종), Row3(뉴스 CSS 무한스크롤)
- `frontend/styles/main.css` — 3단 레이아웃, `#1a2332` 구분선, ticker-scroll 애니메이션
- `frontend/index.html` — 3단 HTML + `initTopBar()` 호출

**🍕 펜타곤 피자지수 툴팁**
- 호버 시 NORMAL/ELEVATED/GUARDED/CRITICAL 레벨 + 개념 설명 표시
- Share Tech Mono, `#00b4d8` cyan border, 0.2s fade-in
- 긴장도 평균 기반 자동 산출, "N분 전" 동적 계산

**GDELT importance_score + Gemini 번역**
- `backend/services/importance_scorer.py` — `score_gdelt_events()` (severity×0.3, recency×0.4, confidence×0.3)
- `backend/connectors/gdelt_connector.py` — `fetch_headline()` (source_url → og:title/<title> 추출, 병렬)
- `backend/connectors/gemini_translator.py` — 행동 중심 프롬프트 교체, `cache_key=source_url`, circuit breaker (RESOURCE_EXHAUSTED → 1시간 차단)
- 피자지수 위치 수정: `#tension-zone flex:none` → 아프리카 바로 옆

### ✅ 8단계 추론 엔진 + 뉴스 티커 dedup (2026-05-26)

**뉴스 티커 source_url 중복 제거**
- `backend/api/news.py` — source_url 기준 dedup (seen_urls set)

**8단계 지정학 추론 엔진**
- `backend/config/case_studies.yaml` (신규) — 역사 사례 12건 (5대 섹터 전체 커버)
- `backend/config/alliance_graph.yaml` (신규) — 동맹 14개 + 국가별 membership 인덱스
- `backend/services/reasoning/__init__.py` / `engine.py` / `stages.py` (신규)
  - Stage 1: 사건 팩트 (ACLED·GDELT actor 필드 통합 추출)
  - Stage 2: 섹터 분류 (theory_tags → sector 확장 매핑)
  - Stage 3: 역사적 비교 (case_studies.yaml 키워드·섹터 스코어링)
  - Stage 4: 거시 변수 (yfinance 섹터별 티커)
  - Stage 5: 명분과 의도 (Phase 4 placeholder)
  - Stage 6: 제도적 저항 (sanctions.yaml target_country 매칭)
  - Stage 7: 시간적 추이 (cascade_links DB 조회)
  - Stage 8: 동맹 확산 (alliance_graph.yaml)
- `backend/api/reasoning.py` (신규) — `GET /api/reasoning/{event_id}`, `POST /api/reasoning/batch`, 10분 캐시
- `backend/main.py` — reasoning_router 등록
- 실측: CHINA-JAPAN 이벤트 → 역사 3건·제재 1건·동맹 5개 정상 매칭, 0.4초

### ✅ 뉴스 티커 Gemini 번역 제거 + 8단계 추론 패널 프론트엔드 (2026-05-26)

**뉴스 티커 Gemini 완전 제거**
- `backend/api/news.py` — Gemini 번역 코드 전면 제거, 영문 원문 직접 표시
- 포맷: `[지역] 영문 헤드라인 · N시간 전` (HTML entity unescape 포함)
- `frontend/src/views/TopBarView.js` — `text_ko` → `text ?? text_ko` 호환 처리

**8단계 추론 패널 프론트엔드 (ReasoningPanelView.js)**
- `frontend/src/panels/ReasoningPanelView.js` (신규) — 우측 340px 슬라이드인, Share Tech Mono, z-index 1002
  - `reasoning:open` 이벤트 → `GET /api/reasoning/{event_id}` → 8단계 0.4s 순차 표시
  - 상세 내용 클릭 펼침 (stages 3·4·6·7·8), `[🔬 분석실에서 열기]` 완료 버튼
  - fix: `has-detail` 클래스 누락 수정 (cursor:pointer 미적용 버그)
- `frontend/src/layers/ConflictEventsLayer.js` — 팝업에 `[🤖 AI 분析]` 버튼 추가, `reasoning:open` 이벤트 발신
- `frontend/styles/main.css` — `.reasoning-panel`, `.rs-stage`, `.popup-reasoning-btn` 스타일
- `frontend/index.html` — `#reasoning-panel` div + `ReasoningPanelView` 마운트

### ✅ Phase 3 고도화 아키텍처 설계 확정 (2026-05-26)

- ACLED 1년 제약 대응 — 과거 베이스라인 vs. 실시간 GDELT 이원화 파이프라인 아키텍처 수립
- 3단계 지정학 팩트체커 (맥락·교차언론·물리센서) 및 Staging Buffer 구조 정립
- 7대 축 다차원 태그 매트릭스 스키마 확정 (Form/Region/Sector/Temporal/Level/DIME/Posture)
- Stage 8 동맹 확산 스코어링 수식 계량화 (Snyder 동맹 딜레마 적용)
- 계층형 데이터 보관 TTL 정책 설계 (핫 72h / event_archive 영구 / 소멸 자동화)
- Token-Zero GDELT CAMEO → 7대 축 파이썬 자동 매퍼 설계 (LLM 호출 없이 ActorType/EventRootCode/GoldsteinScale 결정론적 매핑)
- CLAUDE.md 섹션 §14~§18 추가 확정 (구현 예정 파일: `cameo_mapper.py` · `intelligence.py` · `verification_funnel.py` · `archive_manager.py`)

### ✅ 2026-05-26 세션 완료 작업 (v3.9.0 → v3.10.0)

#### 1. CAMEO → 7대 축 자동 매퍼 + IntelligenceMetadata
- `backend/models/intelligence.py` (신규) — `IntelligenceMetadata` Pydantic 모델 (7대 축 전체 필드)
- `backend/utils/cameo_mapper.py` (신규) — `map_gdelt_to_intelligence_tags()` 결정론적 매핑 (LLM 0토큰, §14 Token-Zero Rule)
  - Actor1Type1Code → level_of_analysis (Waltz), EventRootCode → instrument_of_power (DIME), GoldsteinScale ≤ -5 → revisionist
- `backend/models/event.py` — `intelligence_meta`, `is_staging` 필드 추가
- `backend/connectors/gdelt_connector.py` — `actor1_type1_code` 컬럼 추가, `_to_event()` mapper 연동

#### 2. 3단계 지정학 팩트체커 (Verification Funnel)
- `backend/services/verification_funnel.py` (신규) — 0.5 기저 + Stage1(+0.1 ACLED) + Stage2(+0.2 RSS) + Stage3(+0.1 센서) → 임계값 0.8
- `backend/connectors/news_cross_validator.py` — `fetch_rss_articles()`, `check_rss_match()` 공개 인터페이스 추가
- `backend/services/gdelt_pipeline.py` — `cross_validate()` → `enrich_with_funnel()` 교체, `to_geojson()` is_staging 필터

#### 3. 계층형 TTL 아카이브 관리자
- `backend/db/schema.sql` (신규) — `events`(핫) + `event_archive`(영구) + `sensor_snapshots` DDL
- `backend/db/archive_manager.py` (신규) — ACLED 즉시 귀속 / 고가치 GDELT 이관 / TTL 만료 삭제 / 센서 정리
- `backend/requirements.txt` — `apscheduler>=3.10,<4.0` 추가
- `backend/main.py` — lifespan에 스키마 초기화 + 1시간 크론 연결

#### 4. 7대 축 이론 라이브러리 전면 확장
- `library/**/*.md` × 29 — `geopol_region` / `temporal_era` / `level_of_analysis` / `instrument_of_power` / `strategic_posture` 이식 완료
- `backend/services/library/md_indexer.py` — DDL 5컬럼 + ALTER 마이그레이션 + parse/INSERT 확장 (29/29 upserted)
- `backend/api/library.py` — `list_items()` 8축 필터 (기존 5 + 신규 3)
- `frontend/src/views/TheoryLibraryView.js` — 칩 3행 → 5행 (분석수준·권력수단 추가), temporal_era 칩 업데이트

### ✅ ACLED 대량 인입 스크립트 (2026-05-26)

- `backend/connectors/acled.py` — `_normalize()` payload에 `data_source: 'ACLED'` 추가 (archive_manager 식별 필드 누락 버그 수정) + `confidence_score=1.0` 명시
- `backend/connectors/acled.py` — `fetch_range(since, until, countries, page_size=500)` 메서드 추가 (날짜 범위 + page=1,2,... 페이지네이션 완전 조회)
- `backend/scripts/acled_bulk_ingest.py` (신규) — CLI 단독 실행 스크립트
  - `--months 12` (기본), `--page-size 500`, `--dry-run` 옵션
  - 대상: 41개국 (인도-태평양 + 걸프 + 중동 + 동유럽/코카서스 + 아프리카 회색지대)
  - 월별 루프 + 국가 20개 배치 분할 → `archive_manager.write_events()` 자동 귀속
  - `INSERT OR IGNORE` 보장으로 재실행 안전
- 실측 (dry-run 1개월): **19,796건** (41개국, 중복 없음, 176초) → 12개월 약 **240,000건 / 35분** 예상

실행 방법: 
```bash
cd backend
source .venv/bin/activate
python3 scripts/acled_bulk_ingest.py --dry-run    # 건수 확인
python3 scripts/acled_bulk_ingest.py              # 실제 적재 (12개월, ~35분)
```

### ✅ ACLED 베이스라인 적재 + Stage 1 검증 (2026-05-26)

- `backend/scripts/acled_bulk_ingest.py` 실행 완료 — **232,533건** `event_archive` 적재 (41개국, 12개월, 29분)
- `backend/services/verification_funnel.py` — Stage 1 버그 2개 수정
  - `_stage1_baseline()` timestamp 필터 제거 (베이스라인은 전체 이력 참조)
  - `_REGION_ALIASES` 추가 (eastern_europe→ukraine, indo_pacific→taiwan_strait 등 광역 매핑)
- 실측: taiwan_strait 902건 / hormuz 221건 / eastern_europe(ukraine) 81,707건 → Stage1 +0.1 ✅

### ✅ Cascade 다단계 체이닝 구현 완료 (2026-05-26)

- `backend/models/cascade.py` — `region: str = ""` (chain-only 룰 `region` 필드 optional 허용)
- `backend/services/cascade/engine.py` — `_evaluate_trigger()`에 `target_timestamp` 누락 버그 수정
- `backend/config/cascade_rules.yaml` — 2단계 체인 2룰 추가 (총 13룰)
  - `bab_el_mandeb_to_oil_spike` (conflict → CL=F +1.5%, chain_output: "oil_spike")
  - `oil_spike_to_inflation` (chain_input: "oil_spike" → TIP +0.2%, chain_output: "inflation_pressure")
- 실데이터 검증: 2023-11-19 홍해 위기 → CL=F +2.25% ✅ → TIP +0.30% ✅ — 2단계 체인 발화 확인
- 이론: Resource Weaponization (Hirschman 1945) → 거시경제 전이 (Drezner 2015)

### ✅ 3단계 반도체 체인 + CascadeGraphView 다단계 시각화 (2026-05-26)

**3단계 체인 룰 추가** (`cascade_rules.yaml`)
- `semiconductor_supply_risk_to_sector_decline` — chain_input: "semiconductor_supply_risk" → SOXX↓2%
- `semiconductor_sector_decline_to_defense` — chain_input: "semiconductor_sector_decline" → ITA↑1.0% (방산·국방기술주, 종점)
- 전체 경로: `대만해협긴장(military_flight≥50)` → `TSM↓` → `SOXX↓` → `ITA↑` (depth=1/2/3)
- 총 15개 룰, chain_input 룰 4개

**CascadeGraphView 다단계 노드 시각화**
- depth별 노드 색상: depth=1 황금, depth=2 갈색+노랑 테두리, depth=3 진갈색+주황 테두리
- 체인 엣지(depth≥2) 점선(`line-style: dashed`) 구분, `_highlightRegion()` `successors()`로 전체 체인 경로 하이라이트

**ReasoningPanel cascade depth 배지**
- Stage 7 요약: depth≥3 → `🟠D3`, depth=2 → `🟡D2` 배지
- `stages.py` — cascade_chain 항목에 `depth` 필드 추가

### ✅ 3단계 체인 실데이터 검증 + SandboxLab 체인 뷰어 버그 수정 (2026-05-27)

**검증 결과 (yfinance 실데이터)**
- 2022 펠로시 위기(08-01): D1(TSM↓2.45%)✅ → D2 미발화(SOXX +0.19% buy-the-dip)
- 2023 Joint Sword(04-05): D1(TSM↓2.14%)✅ → D2(SOXX↓0.52%)✅ → D3(ITA↑2.16%, 1주)✅ **3단계 전체 발화!**
- 핵심: D2 INTC↑ 가설 폐기 → SOXX↓(공급망 공포)로 교체. D3 윈도우 72h→168h(1주).

**SandboxLab 체인 뷰어 버그 수정 (v3.15.1)**
- `stages.py` — `stage1_event_facts()` 반환값에 `region_code` 필드 추가
- `SandboxLabView.js` — `_openWithChain()` stages object/array 타입 불일치 수정, 필드명 수정

**브라우저 검증 + 추가 버그 수정 (v3.15.2)**
- [✅] GDELT IRAN vs IRAN 중복 필터 — `_filter_and_normalize()` 필터 ⑤ 삽입 (동일 국가 이벤트 skip)
- [⏳] 분석실 체인 트리 미표시 → region_code 불일치 (v3.15.3에서 해결)

### ✅ 분석실 체인 트리 렌더링 완료 (2026-05-27) — v3.15.3

- `stages.py` — `region_code` geofence 역조회 fallback (`region_for_point` import, 좌표 → 지역 자동 파생, 1,323개 None 이벤트 해결)
- `reasoning.py` — `_resolve_event()` 캐시 미스 시 `get_conflict_events()` / `get_gdelt()` warm-up 자동 호출
- `index.html` — `dagre@0.8.5` peer dependency 추가, cytoscape → dagre → cytoscape-dagre 순서 확정 (graphlib 오류 해결)
- `CascadeLink` 모델 — `rule_name: str | None` 필드 추가, engine.py D1·D2/D3 생성 시 `rule.name` 세팅
- `CascadeGraphView.js` / `SandboxLabView.js` — 엣지 레이블 `rule_name[:10]\n${pctStr}` 형식
- 실측: 우크라이나 → 밀선물 D1 3개 체인 트리 렌더링 성공

### ✅ FRED + Comtrade 베이스라인 + Stage 4/8 연동 (2026-05-27) — v3.16.0

**스키마 확장**
- `backend/db/schema.sql` — `historical_macro_indices` (FRED 일별 종가) + `historical_trade_matrix` (Comtrade 무역 의존도) 테이블 추가

**베이스라인 적재 스크립트**
- `backend/scripts/baseline_bulk_ingest.py` (신규)
  - FRED: WTI·금·원달러·대만달러·VIX 3년치 3,757건
  - WITS/Comtrade: HS 27(에너지)·8542(반도체)·26(희토류) CSV 파싱, dependency_ratio 자동 계산 6,116건

**Stage 4 로컬 쿼리 교체**
- `stages.py` — `stage4_macro_variables()` yfinance 실시간 → `historical_macro_indices` 로컬 쿼리, DB 미적재 시 yfinance fallback

**Stage 8 무역 의존도 추가**
- `stage8_alliance_spread()` — `trade_dependencies` 필드 추가 (Farrell & Newman Weaponized Interdependence 계량화)

### ✅ 국가 클릭 정보 패널 구현 완료 (2026-05-27) — v3.18.0

**백엔드**
- `backend/api/country.py` (신규) — `GET /api/country/{iso3}` + `GET /api/country/list`
  - 30분 캐시, 30개 주요 국가 정보 레지스트리
  - `_query_macro()` — FRED `historical_macro_indices` 최근 30일 (환율·원유·VIX)
  - `_query_trade()` — Comtrade `historical_trade_matrix` HS 8542/27/26 상위 5개 파트너
  - `_query_sanctions()` — `sanctions.yaml` ISO2 매칭 (target_country)
  - `_query_theories()` — `library.db` regions/geopol_region 매칭 (최대 12개)
  - 실측: KOR → macro 3개·trade 3 HS·theories 4개 / IRN → sanction 1건·theories 7개
- `backend/main.py` — `country_router` 등록

**프론트엔드**
- `frontend/src/layers/CountryLayer.js` (신규)
  - Natural Earth 110m GeoJSON CDN (jsDelivr → datasets/geo-countries)
  - sessionStorage 2차 캐시, Leaflet `countryPane` (z-index 201)
  - 호버 반투명 하이라이트 + 국가명 툴팁, 클릭 → `country:open { iso3, name_en }` 이벤트
- `frontend/src/panels/CountryPanelView.js` (신규)
  - 우측 슬라이드인 360px 패널 (ReasoningPanel 구조 재활용)
  - 5탭: 기본정보 / 거시지표 / 무역의존도 / 제재 / 관련이론
  - 거시지표: SVG sparkline (30일 추이) + 변동률 %
  - 무역의존도: 3 HS코드 × 5파트너 테이블 + 의존도 배지
- `data/trade/wits_trade_world.csv` — 16개국 491건, KOR 반도체 대중 의존도 76.7% 정상 출력
- 이론 연결: Farrell & Newman 'Weaponized Interdependence', Drezner 'Economic Coercion'

### ✅ 브라우저 검증 + 버그 수정 2건 (2026-05-29) — v3.18.1

- **CountryLayer 토글 누락 버그**: `index.html`에서 CountryLayer 등록이 `panel.mount()` 이후에 위치 → `panel.mount()` 앞으로 이동 (LayerPanel._render()는 mount 시점 스냅샷만 사용)
- **CORS 포트 8080 누락**: `backend/main.py` allowed_origins에 `localhost:8080` 추가
- **ZW=F 티커 레이블 통일**: `CascadeGraphView` `'밀\n선물'` → `'밀선물\n(ZW=F)'`, `SandboxLabView` → `'밀선물(ZW=F)'`
- Playwright 브라우저 fetch 실측 확인: CountryPanel 5탭(기본정보/거시지표/무역의존도/제재/관련이론) + 콘솔 에러 0건

### ✅ ReasoningPanel Stage 4/8 UI 렌더링 (2026-05-29) — v3.19.0

**Stage 4 (거시 변수) 필드명 수정**
- `summarizeStage`: `data.tickers` → `data.indicators ?? data.tickers` (v3.16.0 API 변경 대응)
  - 요약: `t.ticker` → `t.label ?? t.ticker ?? t.indicator`
- `buildDetailLines`: 필드명 교체 + `t.value` 사용 + `출처: FRED 베이스라인 DB` 표시
- 실측: `원달러 환율 (KRW/USD) ▲0.6% · 대만달러 환율 (TWD/USD) ▼0.5%` 정상 표시

**Stage 8 (동맹 확산) 상세 확장**
- `buildDetailLines` Stage 8: `trade_dependencies` 렌더링 추가
  - `reporter → partner` + HS 코드별 `hs_label (flow) X.X%` 형식
  - `── 무역 의존도 (Weaponized Interdependence) ──` 섹션 헤더
- `potentially_involved_countries` (잠재 연루국) 렌더링 추가
- 이론 연결: Farrell & Newman Weaponized Interdependence (2019)

### 현재 버전
`version.json`: **3.19.0**

### ✅ Stage 8 actor 매칭 강화 (2026-05-29) — v3.19.1

**문제**: `_NAME_TO_CODE` 18개 단순 매핑으로 ACLED 패턴 미처리 → 대부분 "관련 동맹 없음"

**수정** (`backend/services/reasoning/stages.py`):
- `import re` 추가
- `_extract_country()` 함수 신설 — 4단계 우선순위 추출:
  1. 직접 ISO3 (예: `CHN`) — membership 확인
  2. `Military/Police/Government Forces of [Country]` 정규식
  3. `Protesters ([Country])` 등 끝 괄호 패턴
  4. 전체 문자열 직접 매핑
- `_NAME_TO_CODE` 18개 → 50개+ 확장 (5대 섹터 핵심 국가 전체 + "the [Country]" 변종)
- `_REGION_ACTORS` fallback 추가 — actor 매핑 실패 시 region_code로 핵심 국가 추론
  (taiwan_strait→TWN/CHN/USA, hormuz→IRN/SAU/USA 등 11개 지역)
- `stage8_alliance_spread(actors, region_code="")` 시그니처 확장
- `engine.py` — `stage8_alliance_spread(actors, region)` 호출로 수정

**실측 결과**:
- `Protesters (Japan)` → `JPN` → 미일안보조약·쿼드 → USA·AUS·IND 잠재 연루 ✅
- `Military Forces of China + United States` → CHN+USA → NATO·AUKUS·QUAD ✅
- `Military Forces of Ukraine + Russia` → UKR+RUS → CSTO·SCO ✅
- `Protesters (Iran) + Military Forces of Israel` → IRN+ISR → 저항의 축·I2U2 ✅
- region=hormuz fallback → IRN+SAU+USA → 걸프협력회의·NATO 발화 ✅

### 현재 버전
`version.json`: **3.19.1**

### ✅ ACLED hot table 적재 + DB 우선 API (2026-05-29) — v3.20.0

**상황 파악**
- ACLED 학술 무료 계정 `ref_date = 2025-05-29` (1년 지연)
- 기존 bulk ingest: 2024-05~2025-05 (232,533건)
- 3개월 gap fill 실행: +19,875건 (2025-03~2025-05 보강)
- **최종 events 테이블: 252,409건, 2024-05~2025-05-29**

**DB 우선 API 경로 구축** (`backend/api/layers.py`)
- `_load_events_from_db()` 함수 신설
  - ① 5대 섹터 핵심 지역(taiwan_strait/ukraine/hormuz 등 13개) → LIMIT 8000
  - ② 최신 일반 이벤트 → LIMIT 3000
  - Python에서 dedup (key regions 우선)
- `get_conflict_events()` 수정: DB 우선 → live API fallback 구조
  - DB 충분(≥100건) 시 live ACLED API 호출 스킵
- **성능**: 캐시 콜드 기준 0.1초 (live API 대비 10~20배 빠름)
- **실측**: 1,147건 (clustering 후) — ukraine·middle_east·taiwan 등 모든 지역 포함

### 현재 버전
`version.json`: **3.20.0**

### ✅ Cascade 룰 추가 + 엔진 DB fallback (2026-05-29) — v3.21.0

**신규 룰 5개** (`backend/config/cascade_rules.yaml`, 15→21개)

| 룰 ID | 트리거 | 지표 | 발화 | 이론 |
|-------|--------|------|------|------|
| `korean_peninsula_to_krw` | korean_peninsula sev≥35 | KRW=X↑ | 0건(시위 sev=15 다수, 시장 미반응 실증) | Alliance Dilemma |
| `east_china_sea_to_defense` | east_china_sea sev≥50 | ITA↑ | 7건 ✅ | A2/AD, 일본 재무장 |
| `malacca_to_lng` | malacca sev≥40 | NG=F↑ | 10건 ✅ | Mahan SLOC, LNG 초크포인트 |
| `food_price_spike_to_tip` | food_price_spike 체인 | TIP↑ | 2건 ✅ | 식량→인플레이션 D2 |
| `risk_off_to_qqq_drop` | risk_off_sentiment 체인 | QQQ↓ | 1건 ✅ | 리스크오프 D2 |

**cascade engine DB fallback** (`backend/services/cascade/engine.py`)
- `_TRIGGER_COUNTRIES`에 korean_peninsula/north_korea/east_china_sea/malacca 추가
- `_load_region_events_from_db(region)` 함수 신설
- `_fetch_region_events()`: live API 결과 없을 시 DB 자동 fallback
- 총 cascade links: 23→44건

**학습 인사이트**: `korean_peninsula_to_krw` 0건 = 한반도 '시위' 이벤트(sev=15)는 KRW에 유의미한 영향 없음을 실증. 고강도 북한 도발(north_korea_missile_to_krw)과 명확히 구분됨.


### ✅ Cascade chain 브라우저 검증 (2026-05-29) — v3.21.0

- Playwright 실측: `[CascadeLayer] 44개 인과 링크 로드 완료` 로그 확인
- canvas 35,950 non-transparent pixels — `preferCanvas: true` 환경에서 polyline canvas 렌더링 확인
- cascade-target/arrowhead 마커 60개 viewport 표시
- 팝업: rule_name·ticker·가격변동·반응시간·상관도·이론 설명 완전 표시, 콘솔 에러 0건
- 신규 룰 API 반환 확인: malacca×10, east_china_sea×7, food_price_spike×2, risk_off×1

### 현재 버전
`version.json`: **3.21.0**

### 다음 세션 우선순위

1. **국가 레지스트리 확장** — 현재 30개 → 필요 시 추가 (CountryPanel 지원 국가 늘리기)
2. **GDELT 핫 데이터 보강** — 학술 ACLED 1년 지연 → GDELT 실시간으로 보완 (confidence 파이프라인 점검)
3. **Cascade 통계 검증** — Phase 3 목표: Granger 인과분석으로 룰 유효성 사후 검증 (`services/cascade/correlation.py`)

### ✅ 국가 레지스트리 33→41개 확장 (2026-05-30) — v3.22.0

- `_COUNTRY_INFO`에 8개 추가: AUS·TUR·QAT·NLD·EGY·PAK·POL·ETH
  - AUS/QAT/TUR/NLD: 무역 데이터 보유 (historical_trade_matrix)
  - EGY(수에즈)/PAK(SCO)/POL(NATO동방)/ETH(아프리카최대분쟁) 지정학 핵심
- `sector_tags` 폴백 추가: region_code=None 국가도 이론 표시
  - AUS → maritime/indo_pacific 8개, NLD → techno 4개, PAK → gray_zone 8개
- `_query_theories()` 시그니처 확장: `sector_tags` 폴백 쿼리 지원
- Playwright 실측: 8개 신규 국가 드롭다운·CountryPanel 오픈 확인

### ✅ GDELT 핫 데이터 보강 (2026-05-30) — v3.23.0

**RSS 소스 4→8개 교체** (`news_cross_validator.py`)
- Reuters/AP: DNS 실패로 제거
- 추가: Guardian·DW(독일공영)·France24·NHK World·NDTV·RFA(자유아시아)
- RSS 기사: 50건 → 230건 (4.6배↑), 8개 소스 전체 작동 확인

**부분 RSS 점수** (이분법 → 그라데이션)
- 이전: 2소스+ → +0.2 / 미달 → 0
- 이후: 1소스 → +0.1, 2소스+ → +0.2
- 새 승격 경로: ACLED(+0.1) + RSS1(+0.1) + Sensor(+0.1) = 0.8 ✅

**GDELT 24h DB 누적** (`layers.py`)
- `_save_gdelt_events()`: 승격 이벤트 events 테이블 저장 (INSERT OR IGNORE)
- `_load_gdelt_events_from_db(hours=24)`: DB 누적 이벤트 로드
- `get_gdelt()`: 최신 15분 + DB24h 병합, ID dedup
- 효과: 시간이 지날수록 GDELT 레이어 이벤트 밀도 증가

### 현재 버전
`version.json`: **3.23.0**

### ✅ GDELT 24h 파이프라인 검증 (2026-05-29)

- `run_gdelt_pipeline()` 직접 실행: 총 5건, 승격(confidence≥0.8) 2건, 스테이징 3건
- `_save_gdelt_events()` → `_load_gdelt_events_from_db(24h)` DB 저장/로드 정상
- 서버 실행 중 `/api/layers/gdelt` 호출 시 자동 누적 확인 (10건 저장 → 11건 로드)
- **코드 변경 없음** — 기존 v3.23.0 파이프라인 그대로 작동 확인

### ✅ CountryPanel 지도 클릭 flyTo 완료 (2026-05-29) — v3.23.1

**근본 원인**: `datasets/geo-countries` GeoJSON의 ISO3 키가 `ISO_A3`가 아닌 **`ISO3166-1-Alpha-3`**였음.
3곳(`_onFeatureClick`, `_onMapClick`, `flyToCountry`)에서 빈 문자열을 읽어 early return.

**수정 내용** (`frontend/src/layers/CountryLayer.js`)
- `getIso3(props)` / `getName(props)` 헬퍼 함수 추가 — 키 다양성 중앙화
- `onEachFeature`에 `click: _onFeatureClick` 핸들러 추가 (Canvas 최상단 발화 경로)
- `map.on('click')` 폴백 유지 (`_lastClickMs` 100ms dedup으로 중복 방지)
- `SESSION_KEY` → `v2` 갱신 (구 캐시 무효화)

**진단 과정**: Playwright로 확인
- `map.on('click')` 발화 O, bounds 매칭 O, but iso3 = '' → early return
- 수정 후: `fallback matched: Japan JPN` → 패널 `is-open`, `right: 0px`, title "일본" ✅

### 현재 버전
`version.json`: **3.23.1**

### ✅ Cascade Granger 인과성 검증 (2026-05-29) — v3.24.0

**구현 파일**
- `backend/services/cascade/correlation.py` (신규) — Granger 인과분석 엔진
  - `_load_event_series()`: region별 일별 severity 합산 (event_archive)
  - `_load_fred_series()`: WTI/KRW FRED DB 직접 쿼리
  - `_download_yfinance()`: TSM/GLD/ZW=F 등 yfinance 비동기 다운로드
  - `_run_granger()`: statsmodels F-test, maxlag=5, warnings 억제
  - `_run_extreme_correlation()`: 상위 25% 극단 이벤트 → 다음 날 수익률 비교
  - `run_correlation_analysis()`: 8개 룰 전체 검증, FRED 우선 → yfinance 폴백
  - `summarize_results()`: 학습용 해설 포함 요약
- `backend/api/cascade.py` — `GET /api/cascade/correlation` 추가 (24시간 캐시)
- `backend/requirements.txt` — `statsmodels>=0.14` 추가

**핵심 결과 (2024-06 ~ 2026-05, 8개 룰)**
| 검정 방법 | 지지 | 비지지 |
|----------|------|--------|
| Granger F-test (일별) | 0/8 | 8/8 |
| 극단 이벤트 방향 일치 | 2/8 | 6/8 |

**학습 인사이트**:
- Granger 비유의 ≠ 이론 무효. 지정학 충격 → 시장 전이는 **비선형 구조**
- ACLED 일반 이벤트(시위·폭력)는 시장 노이즈로 희석됨; cascade engine의 군사특화 트리거(ADS-B·AIS)가 올바른 접근
- ukraine→밀(ZW=F)·middle_east→금(GLD): 극단 이벤트 방향 일치 ✅ (자원무기화 이론 부분 지지)
- Farrell & Newman(2019) 무기화된 상호의존은 'chokepoint 봉쇄 같은 극단 충격'에서만 발현됨을 통계적으로 확인

### 현재 버전
`version.json`: **3.24.0**

### ✅ GDELT 24h 누적 밀도 검증 + 버그 수정 (2026-05-29) — v3.24.1

**검증 결과**
- 3h: 24건 → 4h: 3건 → 5h: 19건 → 5h말: 9건 추가 = **누적 64건** (INSERT OR IGNORE 중복방지 정상)
- `/api/layers/gdelt`: middle_east(24) · ukraine(24) · suez(6) · hormuz(6) · south_china_sea(4)
- 파이프라인 1회당 평균 9~11건 승격 (confidence≥0.8 교차검증 통과)

**버그 수정 3건**
1. **`_load_gdelt_events_from_db` timestamp → created_at**: GDELT timestamp는 자정(00:00)만 기록 → `created_at`(저장시각) 기준으로 교체
2. **archive_manager 24h 보관 조건**: `_promote_high_value`가 confidence≥0.8 GDELT를 즉시 event_archive로 이관해 24h 누적이 사라지는 문제 → `created_at < now-24h` 조건 추가
3. **event_archive UNION 쿼리**: event_archive에 lat/lon 컬럼 없음 → NULL fallback + payload 추출, ID 중복 제거 추가

**파일 수정**
- `backend/api/layers.py` — `_load_gdelt_events_from_db()` UNION 쿼리, created_at 필터, 중복 제거
- `backend/db/archive_manager.py` — `_promote_high_value()` 24h 최소 보관 조건

### 현재 버전
`version.json`: **3.24.1**

### ✅ Granger 결과 프론트엔드 표시 (2026-05-29) — v3.25.0

**분석실 탭 2분할: 가설 빌더 | Granger 검증**
- `frontend/src/views/SandboxLabView.js`
  - `import { api }` 추가 + `const BASE = api.BASE_URL` (기존 `/api/...` 상대경로 버그 전면 수정)
  - 헤더에 탭 바 추가: `🔬 가설 빌더` / `📊 Granger 검증`
  - `_switchTab(tab)` — 패널 전환, Granger 탭 첫 진입 시 API 호출
  - `_loadGrangerView()` — `GET /api/cascade/correlation` → 요약+룰 렌더
  - `_renderGrangerSummary()` — 통계 4개(총룰/데이터확보/Granger지지/방향일치) + 분석기간 + 핵심발견·이론함의
  - `_grangerCard()` — 룰별 카드: 지역→티커 방향, 판정뱃지(지지/비지지/데이터없음), p값·lag·n, 극단vs일반수익률, 이론·설명
  - `_openWithChain()` 진입 시 builder 탭으로 강제 전환 (체인 뷰어 보호)
- `frontend/styles/main.css` — `.sandbox__tabs`, `.sandbox__tab-btn`, `.sandbox__pane`, `.granger__*` 스타일 추가

**실측 확인**: 8개 룰 전체 표시 — 비지지 5개(p값·lag·n 포함) + 데이터없음 3개, 콘솔 에러 0건

### 현재 버전
`version.json`: **3.25.0**

### ✅ GDELT 파이프라인 스케줄러 등록 (2026-05-29) — v3.25.1

**문제**: `main.py` 스케줄러에 GDELT 잡이 없어 API 요청 시에만 파이프라인이 실행됨 (수동 트리거 구조)

**수정**
- `backend/api/layers.py` — `_save_gdelt_events` → `save_gdelt_events` (public export)
- `backend/jobs/gdelt_job.py` (신규) — `run_gdelt_batch()` 동기 래퍼 (asyncio.run → pipeline → save_gdelt_events)
- `backend/main.py` — `run_gdelt_batch` import + 스케줄러 15분 잡 등록 (`misfire_grace_time=120`)

**실측**: 18건 수집 → 승격 10건 DB 저장 확인 (`payload.data_source='GDELT'`), 스케줄러 두 잡 정상 등록
- `gdelt_pipeline` | interval[0:15:00]
- `archive_cycle`  | interval[1:00:00]

### ✅ yfinance 로컬 캐시 + Granger 8/8 완전 검증 (2026-05-29) — v3.26.0

**문제**: ZW=F·GLD·TSM·ITA·NG=F 5개 티커가 yfinance 네트워크 의존 → 일시 장애 시 "데이터 없음"

**해결**
- `backend/scripts/baseline_bulk_ingest.py` — `--yfinance` 플래그 + `ingest_yfinance()` 추가
  - `YFINANCE_TICKERS` dict (5개 티커 → indicator 이름 매핑)
  - 3년치 종가 → `historical_macro_indices` INSERT OR IGNORE 적재
- `backend/services/cascade/correlation.py`
  - `_TICKER_TO_FRED` 7개로 확장 (ZW=F/GLD/TSM/ITA/NG=F 로컬 DB 우선 조회)
  - `_END_DATE = date.today()` — 항상 오늘까지 분석 (고정 날짜 제거)
- 적재 실행: 3,764건 (ZW=F 753 + GLD 752 + TSM 752 + ITA 752 + NG=F 755)

**결과 (2024-06-01 ~ 2026-05-29, 8/8 데이터 확보)**

`korean_peninsula_to_krw` — 분석 기간 확장(+29일)으로 p=0.054 → **p=0.047 (Granger 유의 전환!)**
Snyder 동맹 딜레마: 한반도 지역 severity 누적이 원달러 환율에 선행하는 패턴 통계적 확인.

### 현재 버전
`version.json`: **3.26.0**

### ✅ 상단 바 긴장도·피자 지수 신뢰도 개선 (2026-05-29) — v3.27.0

**문제점 3가지**
1. 단순 severity 평균 → 저강도 시위가 고강도 전투를 희석
2. 호버 시 이유 없음 (건수·평균만 표시)
3. 피자 레벨 설명 추상적 ("야근 감지", "작전 임박")

**백엔드 개선** (`backend/api/stats.py` 전면 재작성)
- 이벤트 유형 가중치: 전투/폭발 ×1.5, 민간인 공격 ×1.3, 폭동 ×0.7, 시위 ×0.4
- 최근성 가중치: 0-3일 ×1.8, 4-7일 ×1.4, 8-14일 ×1.1, 15일+ ×1.0
- ACLED/GDELT 별도 쿼리 (UNION 중복 버그 수정)
- ACLED 400일 베이스라인 + GDELT 72h 실시간 신호 혼합 (0.65:0.35)
- Africa 국가 매핑 추가 (region_code=NULL → payload.country 폴백)
- 드라이버 top 3 추출: GDELT 실시간 우선 → ACLED 90일 → ACLED 전체 최신 폴백
- 응답에 `drivers`, `acled_count`, `gdelt_count` 필드 추가

**프론트엔드 개선** (`frontend/src/views/TopBarView.js`)
- 지역 호버 시 커스텀 드라이버 툴팁 표시
  - 데이터 소스(ACLED N건 + GDELT N건), 계산 방식 설명
  - 드라이버 최대 3개: 소스 출처·이벤트 유형·행위자·경과 시간
- 피자 레벨 설명 구체화 (4단계 × 역사 사례):
  - 🟢 NORMAL (0-35): "외교·제재 중심, 분쟁 국지전 수준" + 역사 사례
  - 🟡 ELEVATED (36-55): "전투 강도 상승, 우발 확전 위험" + 사례
  - 🟠 GUARDED (56-75): "복수 전선 동시 충돌, 공급망 압박" + 사례
  - 🔴 CRITICAL (76+): "강대국 직접 개입, 공급망 동시 붕괴 위험" + 사례
- 드라이버 툴팁 CSS (`frontend/styles/main.css`): `.driver-tooltip`, `.dt-*` 클래스
- `frontend/index.html`: `#driver-tooltip` div 추가

**현재 섹터 점수 (2026-05-29 기준)**
| 섹터 | 점수 | 레벨 | ACLED | GDELT |
|------|------|------|-------|-------|
| 중동 | 36.4 | medium | 8,626 | 66 |
| 인태 | 26.8 | low | 11,539 | 12 |
| 유럽 | 53.0 | medium | 18,853 | 81 |
| 아프리카 | 33.4 | low | 4,002 | 0 |

### 현재 버전
`version.json`: **3.27.0**

### ✅ Phase 3 공식 완료 선언 (2026-05-29)

Phase 3 체크리스트 8/8 완성. CLAUDE.md §11 Phase 3 → ✅ 상태 갱신.

### Phase 4 — 데이터 확충 & 적재 기반 강화 (착수)

우선순위 순:
1. 국가 지정학 프로파일 (`country_geopolitics.yaml` + CountryPanel 기본정보 탭 확장)
2. 실시간 소스 다변화 (ReliefWeb API/UN OCHA + RSS 분쟁전문 피드)
3. GDELT GKG 적재 (테마·톤 결정론적 매핑, Token-Zero 유지)
4. 데이터 품질 게이트 대시보드 (confidence·importance 모니터링)
5. Cascade 룰 자동 후보 생성 (Granger 유의쌍 → YAML draft, 인간 승인 필수)

Phase 5 (추론 지능화)는 Phase 4 완료 후 착수. CLAUDE.md §11에 로드맵 추가됨.

### ✅ Phase 3 브라우저 검증 완료 (2026-05-29)

- 드라이버 툴팁: 4개 지역 tension-item 렌더 → 중동 호버 시 소스·드라이버 3개 정상 표시 ✅
- 피자 레벨: 호버 시 현재 지수(37.0 ELEVATED)·4단계 가이드·역사 사례 전부 표시 ✅
- 콘솔 에러 0건

### ✅ Phase 3 공식 완료 선언 (2026-05-29) — v4.0.0

**Phase 3 체크리스트 8/8 완성. version.json → 4.0.0 / phase 4 bump.**

---

## Phase 4 — 데이터 확충 & 적재 기반 강화 (착수)

### 현재 버전
`version.json`: **4.0.0**

### Phase 4 완료 (2026-05-30) → Phase 5 착수 준비

**다음 세션 우선순위**: Phase 5 설계 — Stage 5 명분·의도 구현 로드맵 (Phase 4 완료 게이트 통과)

### ✅ 이론 라이브러리 전면 보강 (2026-05-30) — v4.7.0

**작업 내용 (29개 → 40개, +11개)**

| 단계 | 내용 | 결과 |
|------|------|------|
| 1단계 case_study | 7개 신규 작성 | 0개 → 8개 |
| 2단계 concept 보강 | 4개 신규 작성 | 14개 → 17개 |
| 3단계 중복 제거 | a2ad 중복 1개 삭제 | 41개 → 40개 |

**신규 case_study (8개)**:
- `case_pelosi_taiwan_2022` — 대만해협 D1 발화·D2 미발화 비교
- `case_joint_sword_2023` — 3단계 Cascade 전체 발화 실증 (핵심 사례)
- `case_houthi_red_sea_2023` — 비국가 SLOC 차단, 2단계 체인 발화
- `case_ukraine_invasion_2022` — 자원무기화 집대성, ZW=F 실증
- `case_ever_given_suez_2021` — 단일 SPOF 취약성, ZIM 급등
- `case_israel_hamas_2023` — 리스크오프 메커니즘, GLD +8%
- `case_chips_act_2022` — 기술 민족주의 제도화
- `case_nord_stream_sabotage_2022` — 에너지 인프라 공격·귀속 모호성

**신규 concept (4개)**:
- `indo_pacific_extended_deterrence` — 확장억제, 한미동맹 핵우산
- `maritime_string_of_pearls` — 진주목걸이 전략, 중국 인도양 거점
- `maritime_fonop` — 자유항행작전, 남중국해 국제법 충돌
- `indo_pacific_korea_discount` — 코리아 디스카운트, KRW/KOSPI 연결

**최종 현황**: concept 17 + norm 15 + case_study 8 = 총 40개
섹터별: maritime 8 / gray_zone 12 / energy 8 / indo_pacific 7 / techno 5
geopol_region 미설정: 0개 (100% 채움)

### 현재 버전
`version.json`: **4.7.0**

### ✅ [P4-0] 국가 지정학 프로파일 (2026-05-29) — v4.1.0

**구현 내용**
- `backend/config/country_geopolitics.yaml` (신규) — 핵심 15개국 지정학 프로파일
  - CHN·USA·RUS·IRN·TWN·KOR·JPN·SAU·ISR·UKR·PRK·IND·AUS·NLD·TUR
  - 7개 필드: `strategic_position` / `strategic_posture` / `alliances` / `key_risks` / `instrument_of_power` / `theory_refs` / `learning_note`
  - Waltz 3수준 + Snyder 동맹 딜레마 + DIME 프레임워크 기반 구조화
- `backend/api/country.py` — `_load_geo_profiles()` + `_query_geopolitics(iso3)` 추가, `get_country()` payload에 `geopolitics` 필드 연결
- `frontend/src/panels/CountryPanelView.js` — `renderInfo()` 확장, `_renderGeopolitics()` 신규 (지정학 섹션 렌더)
- `frontend/styles/main.css` — `.cp-geo-*` 스타일 9종 추가

**실측 (Playwright)**
- CHN 패널 기본정보 탭: 전략 포지션(🔴수정주의)·동맹 3개·리스크 3개·이론 3개·학습노트 정상 표시 ✅
- 프로파일 없는 국가(YEM): geopolitics 섹션 미표시 (graceful fallback) ✅
- 콘솔 에러 0건

**이론 연결**: Waltz '3수준 분석' (systemic→state→substate), Snyder '동맹 딜레마', DIME 프레임워크 (Diplomatic/Informational/Military/Economic)

### ✅ [P4-1] 실시간 소스 다변화 — ReliefWeb RSS (2026-05-30) — v4.2.0

**구현 내용**
- `backend/connectors/reliefweb.py` (신규) — UN OCHA ReliefWeb 커넥터
  - 일반 RSS 피드 수집 + 5대 섹터 21개 국가 키워드 필터링
  - 분쟁 키워드 30개 제목 필터, severity 3단계 추정 (65/45/30)
  - confidence_score=0.65 (UN 기관 출처), 이론 태그 자동 도출
  - 브라우저 헤더 우회 (ReliefWeb WAF 대응)
- `backend/jobs/reliefweb_job.py` (신규) — 30분 캐시 만료 잡
- `backend/main.py` — `reliefweb_pipeline` 30분 잡 등록
- `backend/api/layers.py` — `GET /api/layers/reliefweb` 엔드포인트 + 캐시

**실측**: 4건 (Gaza·Lebanon·Somalia·Lebanon Snapshot), conf=0.65, 엔드포인트 정상

**이론 연결**: Gray Zone Strategy (Hoffman 2007) — 분쟁·인도주의 경계 추적

### ✅ [P4-2] GDELT GKG 적재 (2026-05-30) — v4.3.0

**구현 내용**
- `backend/connectors/gdelt_gkg.py` (신규) — GKG V2 커넥터
  - lastupdate.txt에서 GKG ZIP URL 추출 + CDN 지연 최대 4슬롯 fallback
  - 분쟁 테마 접두사 12종 필터 (`CONFLICT·MILITARY·WA_·CRISISLEX_...`)
  - 5대 섹터 FIPS 코드 필터, `GkgRecord` 데이터클래스 (url·themes·tone·country_codes)
- `backend/utils/cameo_mapper.py` — `map_gkg_themes_to_tags()` 추가
  - GKG 테마 → instrument_of_power·sector_lead·strategic_posture 결정론적 매핑
  - `hostility_confirmed`: 테마 2개+ + tone≤-3.0 → 적대성 확인 플래그
- `backend/services/gdelt_pipeline.py` — GKG 병렬 수집 + 조인 통합
  - `asyncio.gather(fetch_latest_gdelt, fetch_gkg_records)` 동시 실행
  - source_url 조인 → gkg_themes·gkg_tone·gkg_hostility payload 추가
  - hostility_confirmed 이벤트 confidence 0.5→0.65 상향
  - GeoJSON에 gkg_themes·gkg_tone·gkg_hostility 필드 추가
- `backend/connectors/gdelt_connector.py` — export URL도 CDN 지연 fallback 추가

**실측**: 총 19건, 승격 8건, GKG 조인 15/19건 (78.9%), 적대성 확인 이벤트 포함

**이론 연결**: CLAUDE.md §14 Token-Zero Tagging — GKG 테마도 LLM 0토큰 결정론적 매핑

### ✅ [P4-3] 품질 게이트 대시보드 (2026-05-30) — v4.4.0

**구현 내용**
- `backend/api/stats.py` — `GET /api/stats/quality` 추가 (5분 캐시)
  - 72h 이벤트 소스별 집계: total·promoted·gkg_enriched·staging·high_importance
  - 전체 승격률·GKG 조인율·24h 버퍼 건수 집계
- `frontend/src/views/TopBarView.js` — `_refreshQuality()` + `_renderQualityBadge()` 추가
  - Row1 우측 `🔬 {승격률}%` compact 배지 (색상: green≥80% / amber≥50% / red<50%)
  - title 호버: 승격률·GKG조인율·버퍼건수·총건수
- `frontend/index.html` — `#quality-badge` div 추가
- `frontend/styles/main.css` — `.quality-badge` 스타일 추가

**실측 (Playwright)**: `🔬 100%` 배지 녹색 표시, title="승격률 100% | GKG 조인 0% | ..." ✅

### 현재 버전
`version.json`: **4.4.0**

---

## Phase 4 진행 현황 (2026-05-30 기준) ✅ 완료

| # | 항목 | 상태 | 버전 |
|---|------|------|------|
| P4-0 | 국가 지정학 프로파일 (15개국 YAML) | ✅ | v4.1.0 |
| P4-1 | ReliefWeb RSS 편입 (UN OCHA) | ✅ | v4.2.0 |
| P4-2 | GDELT GKG 적재 + 파이프라인 통합 | ✅ | v4.3.0 |
| P4-3 | 품질 게이트 대시보드 | ✅ | v4.4.0 |
| P4-4 | Cascade 룰 자동 후보 생성 | ✅ | v4.5.0 |

### ✅ [P4-4] Cascade 룰 자동 후보 생성 (2026-05-30) — v4.5.0

**구현 내용**
- `backend/services/cascade/correlation.py` — `run_candidate_scan()` + `generate_yaml_draft()` 추가
  - `_SCAN_TICKERS`: 기존 7개 + SOXX·QQQ·TIP·DX=F 4개 확장 (총 11개)
  - `_EXISTING_PAIRS`: 기존 검증 8쌍 제외 집합
  - `_get_all_regions()`: event_archive에서 이벤트 20건+ 지역 자동 추출
  - `CandidateResult`: GrangerResult 상속, 후보 전용 필드(방향·윈도우·임계치·점수) 추가
  - `run_candidate_scan()`: region × ticker 전체 조합 Granger + 극단 이벤트 병렬 검정 (p<0.10 또는 방향 일치)
  - `generate_yaml_draft()`: status: draft 마커 포함 YAML 초안 생성, severity_min 100 초과 시 기본값 50 사용
- `backend/api/cascade.py` — `GET /api/cascade/candidates` 엔드포인트 추가 (24h 캐시)
- `backend/scripts/cascade_rule_draft.py` (신규) — CLI 스크립트 (`--top N`, `--p 값`, `--save`)
- `backend/config/cascade_rules_draft.yaml` (신규) — 자동 생성 초안 파일

**실측 결과 (2026-05-30, 82개 후보, Granger p<0.05 11개)**

| 순위 | 후보 ID | p값 | 방향 | 이론 연결 |
|------|---------|-----|------|----------|
| 1 | south_china_sea → KRW=X | 0.0028 | UP | 남중국해 긴장 → 원화 약세 |
| 2 | south_china_sea → QQQ | 0.0103 | UP | (시장 동조화 노이즈 가능성) |
| 3 | taiwan_strait → KRW=X | 0.0110 | DOWN | (방향 재검토 필요) |
| 4 | east_china_sea → KRW=X | 0.0117 | DOWN | A2/AD → KRW 변동 |
| 9 | taiwan_strait → SOXX | 0.0299 | DOWN | Weaponized Interdependence 확장 |
| 10 | south_china_sea → ITA | 0.0369 | UP | SCS 긴장 → 방산주 수혜 ✓ |

**이론적으로 유의미한 상위 후보 (검토 권장)**:
1. **#9 taiwan_strait → SOXX (DOWN)**: TSMC 룰의 ETF 버전 — 공급망 공포가 개별 종목 넘어 섹터 전체에 전이
2. **#10 south_china_sea → ITA (UP)**: SCS 긴장 → 미 방산 ETF — east_china_sea → ITA와 비교 학습 가능
3. **#14 bab_el_mandeb → SOXX (UP)**: 에너지 충격 → 반도체 섹터 선행, 홍해 봉쇄의 기술 충격 경로

**사용 방법**
```bash
cd backend && source .venv/bin/activate
python3 scripts/cascade_rule_draft.py --top 15    # 콘솔 출력
python3 scripts/cascade_rule_draft.py --save      # YAML 파일 저장
# GET /api/cascade/candidates  ← API 엔드포인트 (24h 캐시)
```

### ✅ Cascade 룰 후보 검토 & 승인 (2026-05-30) — v4.6.0

**검토 결과 (82개 → 2건 처리)**

| 판정 | 룰 ID | 조치 내용 |
|------|--------|----------|
| ✅ 신규 추가 | `taiwan_strait_conflict_to_soxx` | conflict 직접 트리거, p=0.030, Δ=-0.17% |
| ⚠️ 파라미터 교정 | `south_china_sea_to_defense` | severity_min 50→60 (저강도 이벤트 제거) |
| ❌ 기각 (80개) | 강세장 spurious·방향 역설·이론 없음 | cascade_rules_draft.yaml에 보존 |

**기각 주요 패턴 3가지**
1. **강세장 spurious**: ukraine/malacca/SCS → QQQ/SOXX UP (2024 강세장과 시간적 동조화)
2. **방향 역설**: taiwan_strait/east_china_sea → KRW=X DOWN (이론에 역행, 보류)
3. **효과 크기 0**: south_china_sea → KRW=X (p=0.003이지만 Δ≈0)

**학습 포인트**: `taiwan_strait_conflict_to_soxx`는 기존 체인 경로
(military_flight→TSM→SOXX)와 달리 ACLED 분쟁→SOXX 직접 단락 경로.
Weaponized Interdependence — 허브 집중성이 클수록 충격 전파 속도 증가.

**총 활성 룰: 21 → 22개**

### 현재 버전
`version.json`: **4.6.0**

---

## Phase 4 진행 현황 (2026-05-31 기준) ✅ 완료

| # | 항목 | 상태 | 버전 |
|---|------|------|------|
| P4-0 | 국가 지정학 프로파일 (15개국 YAML) | ✅ | v4.1.0 |
| P4-1 | ReliefWeb RSS 편입 (UN OCHA) | ✅ | v4.2.0 |
| P4-2 | GDELT GKG 적재 + 파이프라인 통합 | ✅ | v4.3.0 |
| P4-3 | 품질 게이트 대시보드 | ✅ | v4.4.0 |
| P4-4 | Cascade 룰 자동 후보 생성 + 검토·승인 | ✅ | v4.6.0 |
| 부록 | 이론 라이브러리 전면 보강 | ✅ | v4.7.0 |

### ✅ 이론 라이브러리 전면 보강 (2026-05-31) — v4.7.0

29개 → 40개 (+11개): case_study 8개 + concept 4개 추가, a2ad 중복 1개 제거.

**신규 case_study**: Joint Sword 2023 (D1→D2→D3 실증 ★), 펠로시 2022, 후티 홍해,
우크라이나 침공, 에버기븐, 이스라엘-하마스, CHIPS Act, Nord Stream 파괴

**신규 concept**: 확장억제(한반도), 진주목걸이(인도양), FONOP(남중국해), 코리아 디스카운트

최종: concept 17 + norm 15 + case_study 8 = **총 40개**

### 현재 버전
`version.json`: **4.7.0**

---

### v4.8.0 브리핑 파이프라인 + INSS 4건 (2026-05-31)

**v4.8.0 브리핑 적재 파이프라인**
- md_indexer: briefing 타입 허용, source_org/published_date/event_refs 필드 추가
- stages.py Stage 3: library.db FTS briefing 자동 매칭 + briefing_refs 반환
- TheoryLibraryView: 브리핑 필터 칩 + 기관명 카드
- ReasoningPanelView: Stage 3 상세에 관련 브리핑 자동 표시
- 워크플로우: AI 요약 붙여넣기 -> .md + 인덱싱 -> push (세션당 5분)

**INSS 브리핑 7건 구조**

379호(2026.04) 이란전 군사·에너지·경제 <- 구조적 원인
844호(2026.05.21) 이란전 사이버·인지전 <- 379호 병렬 분석
845호(2026.05.22) 중러 정상회담 <- 1차 후폭풍
848호(2026.05.27) 시진핑 방북 예고 <- 2차 후폭풍
382호(2026.05) 북한 다극세계론 — 이념 프레임·북러 명분·전략 자율성
849호(2026.05.26) 한국 핵추진잠수함 특별법 설계 — 장보고 N사업 제도화 청사진
국가행동분석(~2022) 일본 — 요시다→아베 독트린, 수상관저·간담회 결정기제

핵심 발견: 사이버 공격은 ACLED 미등록 -> Cascade 엔진 맹점
source_type:cyber 트리거 추가 = Phase 5 설계 과제로 문서화

브리핑 추가: 새 세션에서 "progress.md 읽고 시작해줘. 아래 브리핑 등록해줘." + 요약본

### 현재 버전
version.json: 4.8.0

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

## 다음 세션 우선순위

**Phase 5 잔여 항목**

| # | 항목 | 파일 |
|---|------|------|
| 6 | 추론 체인 자기검증 (BFS 가설·반증 루프) | `services/reasoning/engine.py` |
| 7 | 멀티에이전트 섹터별 추론 병렬 | `services/reasoning/agents/` 신규 |
| 8 | LLM 종합 브리핑 계층 | `api/briefing.py` importance≥0.7 게이트 |

항목 8: §14 Token-Zero 위반 아님 — 사용자 명시 요청 기반 LLM 호출은 허용 범위.
병행 과제: 브리핑 지속 적재 (INSS, CSIS, RAND 등)

---

## Phase 6 — 브리핑 지식 그래프 & 교차 분석 (대기 중)

**착수 조건**: Phase 5 완료 + **브리핑 30개 이상 누적**
현재 브리핑: **7개** (2026-06-01 기준)

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
