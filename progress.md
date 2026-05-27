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
  - 상세 내용 클릭 펼침 (stages 3·4·6·7·8), `[🔬 분析실에서 열기]` 완료 버튼
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
- `backend/services/cascade/engine.py` — `_evaluate_trigger()`에 `target_timestamp=response_event.timestamp` 누락 버그 수정 (체이닝 synthetic event가 `now()`로 fallback하던 문제)
- `backend/config/cascade_rules.yaml` — 2단계 체인 2룰 추가 (총 13룰)
  - `bab_el_mandeb_to_oil_spike` (conflict → CL=F +1.5%, chain_output: "oil_spike")
  - `oil_spike_to_inflation` (chain_input: "oil_spike" → TIP +0.2%, chain_output: "inflation_pressure")
- `backend/config/cascade_rules.yaml` — `korean_tension_to_kospi`에 `chain_input: "krw_depreciation"` 추가 (기존 북한 미사일→KRW 체인 활성화)
- 실데이터 검증: 2023-11-19 홍해 위기 → CL=F +2.25% ✅ → TIP +0.30% ✅ → 2단계 체인 발화 확인
- 현재(2025-05) 기간은 미발화 (OPEC+ 증산·관세 우려로 TIP 하락) — 이론 불성립 기간 정상 처리
- 이론: Resource Weaponization (Hirschman 1945) → 거시경제 전이 (Drezner 2015)

### ✅ 3단계 반도체 체인 + CascadeGraphView 다단계 시각화 (2026-05-26)

**3단계 체인 룰 추가** (`cascade_rules.yaml`)
- `semiconductor_supply_risk_to_intc` — chain_input: "semiconductor_supply_risk" → INTC ↑1.5% (CHIPS Act 수혜 로테이션)
- `chips_act_investment_to_defense_tech` — chain_input: "chips_act_investment" → ITA ↑1.0% (방산·국방기술주, 종점)
- 전체 경로: `대만해협긴장(military_flight≥50)` → `TSM↓` → `INTC↑` → `ITA↑` (depth=1/2/3)
- 이론: Weaponized Interdependence → Techno-nationalism / Supply Chain Reshoring → Military-Industrial Complex
- 총 15개 룰, chain_input 룰 4개

**CascadeGraphView 다단계 노드 시각화** (`CascadeGraphView.js`)
- depth별 노드 색상: depth=1 황금(기존), depth=2 갈색+노랑 테두리, depth=3 진갈색+주황 테두리
- 체인 엣지(depth≥2) 점선(`line-style: dashed`) 구분
- `_buildElements()` 전면 재작성 — depth=1: region→ticker, depth≥2: parent_link_id로 srcTicker→dstTicker 체인 엣지 빌드
- `_highlightRegion()` — `successors()`로 전체 체인 경로 하이라이트 (이전: 직접 neighborhood만)
- TICKER_LABEL에 TIP·INTC 추가

**ReasoningPanel cascade depth 배지** (`ReasoningPanelView.js`)
- Stage 7 요약: depth≥3 → `🟠D3`, depth=2 → `🟡D2` 배지 표시
- Stage 7 상세: 링크별 `⬜D1/🟡D2/🟠D3` + 상관도 + 시간 표시
- `stages.py`: `cascade_chain` 항목에 `depth` 필드 추가

### ✅ 3단계 체인 실데이터 검증 + 룰 수정 (2026-05-27)

**검증 결과 (yfinance 실데이터)**
- 2022 펠로시 위기(08-01): D1(TSM↓2.45%)✅ → D2 미발화(SOXX +0.19% buy-the-dip)
- 2023 Joint Sword(04-05): D1(TSM↓2.14%)✅ → D2(SOXX↓0.52%)✅ → D3(ITA↑2.16%, 1주)✅ **3단계 전체 발화!**

**핵심 발견 (이론 vs 실증)**
- D2 INTC↑ 가설 폐기: INTC는 TSM 하락 후 오히려 -2.5~-6.6% 추가 하락. CHIPS Act 로테이션은 수주~수개월 시계열, 48h 부적합.
- D2 → SOXX↓(공급망 공포, 섹터 전체 하락)로 교체. 2023 발화: SOXX -2.24%(48h)
- D3 윈도우 72h→168h(1주): ITA는 방산 정책 기대 형성에 시차 필요. 2023 발화: ITA +2.16%(1주)
- 2022 이상치 해석: 기술주 과도 매도 선행 → 펠로시 방문이 '최악 회피' 신호 → buy-the-dip. 이론 불성립 아님, 교란 변수.

**수정 파일**
- `backend/config/cascade_rules.yaml` — D2·D3 룰 교체 (`semiconductor_supply_risk_to_sector_decline`, `semiconductor_sector_decline_to_defense`)
- `backend/scripts/verify_taiwan_chain.py` — 검증 스크립트 신규 + 실증 이론 노트 포함

### ✅ QQQ 분기 체인 구현 (2026-05-27)

**분기 구조**: `semiconductor_sector_decline` → ITA↑ (D3a) 와 QQQ↓ (D3b) 병렬 발화
- `semiconductor_sector_decline_to_qqq_drop` 룰 추가: QQQ↓0.8% in 168h
- 실증: 2023 Joint Sword -0.91% ✅, 2022 펠로시 후속 -1.45% ✅
- CascadeGraphView: TICKER_LABEL에 `QQQ: '나스닥\n(QQQ)'` 추가
- 학습 포인트: 같은 D2 신호 → "방산↑ + 나스닥↓" 동시 발화 — 위기는 승자와 패자를 동시에 만든다
- 총 16개 룰

### ✅ SandboxLab 체인 뷰어 구현 (2026-05-27, 미완료)

**구현 내용**
- `SandboxLabView.js` — 체인 뷰어 모드 추가
  - `cascade:loaded` 구독 → `_cascadeLinks`, `_cascadeEvents` 캐시
  - `sandbox:toggle({ event_id, report })` 페이로드 감지 → `_openWithChain()` 호출
  - `_buildChainElementsForRegion(region)` — D1 링크(evidence.region) → D2→D3 재귀 탐색
  - `_initChainCy(elements)` — dagre 상→하 트리, depth별 색상(빨강/황금/갈색/주황)
  - `_renderChainInfo(region, ...)` — 우측 패널에 D1/D2/D3 링크 요약 표시
- `main.css` — `.sandbox__chain-*` 스타일 추가
- fetch URL `/api/cascade/build` → `/api/cascade/links` 수정

### ✅ SandboxLab 체인 뷰어 버그 수정 (2026-05-27)

**버그 1 — `stages.py` region_code 누락**
- `backend/services/reasoning/stages.py` — `stage1_event_facts()` 반환값에 `region_code` 필드 추가
- 증상: `stage1.region_code`가 항상 `undefined` → 체인 뷰어가 `'unknown'` region으로 탐색, D1 링크 미발견

**버그 2 — `SandboxLabView.js` stages 타입 불일치**
- `frontend/src/views/SandboxLabView.js` — `_openWithChain()` 수정
  - `report.stages`는 `{"1_facts": {...}, ...}` object인데 `.find()`(array 메서드) 호출 → TypeError
  - `stages['1_facts']` 직접 접근으로 교체
  - `stage1.region` → `stage1.region_code`, `stage1.event_title` → `stage1.title` 필드명 수정

**검증**
- `/api/reasoning/{event_id}` Stage 1에서 `region_code: "south_china_sea"` 정상 반환 확인
- cascade/links D1 링크 region 분포: south_china_sea 14건 / bab_el_mandeb 4건 / middle_east 4건 / ukraine 3건 / suez 1건

### 현재 버전
`version.json`: **3.15.1**

### 다음 세션 우선순위

1. **SandboxLab 체인 뷰어 브라우저 최종 검증** — south_china_sea 이벤트 클릭 → AI분析 → 분析실 → D1 체인 트리 14건 표시 확인
2. 이후 추가 기능 논의

---

## Phase 3 후속 — 분석실 8단계 추론 루틴

학습자가 체계적인 지정학 추론을 수행하도록 하는 프레임워크.

| # | 단계 | 데이터 소스 | 상태 |
|---|------|------------|------|
| 1 | 사건 팩트 | ACLED, GDELT, FIRMS, AIS, ADS-B | ✅ 기존 자산 |
| 2 | 섹터 분류 | theory_library.yaml sector_tag | ✅ 기존 자산 |
| 3 | 역사적 비교 | case_studies.yaml (신규) | ⏳ |
| 4 | 거시 변수 | yfinance + FRED (환율/원자재) | 🔧 확장 필요 |
| 5 | 명분과 의도 | 외교 성명 RSS + Gemini 분석 | 🔮 Phase 4 |
| 6 | 제도적 저항 | UN 안보리, GSDB 제재 | ⏳ Step 8에 포함 |
| 7 | 시간적 추이 | cascade depth=4 체이닝 | ✅ 기존 자산 |
| 8 | 동맹 확산 | alliance_graph.yaml (신규) | ⏳ |

**신규 필요 파일**: `case_studies.yaml`, `alliance_graph.yaml`, `fred_adapter.py`, `backend/services/reasoning/`, `ReasoningPanelView.js`

---

---

## 서브 에이전트 도입 계획

### Phase 3 후반 (즉시 착수)

**8단계 추론 자동화**
- 사용자가 사건 선택 → 서브 에이전트가 8단계 자동 채움
- 서브 A: 사건 팩트 수집 (GDELT/ACLED)
- 서브 B: 역사 사례 매칭 (케이스 스터디 DB)
- 서브 C: 시장 반응 분석 (yfinance)
- 서브 D: 제재 레짐 조회
- 메인: 결과 종합 → 분석실 캔버스 자동 생성

**라이브러리 자동 확장**
- 새 이벤트 감지 → 관련 논문/보고서 자동 요약
- .md 파일 자동 생성 → library.db 업데이트
- 싱크탱크 보고서 자동 아카이브
  - CSIS (미국), RAND (미국)
  - IISS (영국), Chatham House (영국)
  - INSS — Institute for National Security Studies (이스라엘)
  - INSS — 국가안보전략연구원 (한국)
  - 한국 국방과학연구원 (ADD)

### Phase 4 (장기)
- 데이터 수집 병렬화 (GDELT/RSS/AIS/ADS-B)
- Cascade 자동 검증 (통계 + 실시간 + 역사 사례)

---

## 다음 세션 시작점

### 우선순위 작업 (다음 세션)

1. **Gemini 번역 재확인** — KST 2026-05-27 09:00 이후 뉴스 티커 + 맥락 요약 한국어 동작 확인 (오늘 할당량 소진 → 내일 리셋)
2. **ReasoningPanelView.js** — 8단계 추론 결과를 프론트엔드 패널로 표시 (이벤트 클릭 시 좌측 또는 하단 패널 오픈)
3. **데이터 계층형 보관 설계** — GDELT/ACLED 이벤트 TTL 정책, 오래된 데이터 아카이브
4. **라이브러리 데이터 채우기** — `library/` .md 신규 추가, theory_library.yaml 항목 보강
