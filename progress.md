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

### ✅ 상단 2단 바 (2026-05-25)

- `backend/api/stats.py` (신규) — `GET /api/stats/tension` (5분 캐시), `GET /api/stats/pizza-index` (1시간, KRW=X 실시간 BigMac 지수), `GET /api/stats/markets` (5분, WTI·금·반도체·원달러 4종 병렬)
- `backend/api/news.py` (신규) — `GET /api/news/ticker` (3분 캐시, importance≥0.7 & confidence≥0.8 최신 8건, Gemini 티커 포맷 번역)
- `backend/connectors/gemini_translator.py` — `translate_ticker_text()` 추가 (티커 전용 프롬프트, "ticker:" 접두사 캐시 분리)
- `backend/main.py` — `stats_router`, `news_router` 등록
- `frontend/src/views/TopBarView.js` (신규) — Row1(긴장도·피자·시장 3초 순환), Row2(뉴스 CSS 스크롤, hover pause, click 새탭)
- `frontend/styles/main.css` — `#top-bar` 2단 레이아웃, `ticker-scroll` 애니메이션, `#map` top:32px 이동, `.info-panel`·`#layer-panel` top:48px 조정
- `frontend/index.html` — `#top-bar` HTML 추가, `initTopBar()` 호출

실측 (서버 응답): 피자지수 74.6, WTI $96.6(-0.88%), 반도체 $537.33(+2.06%), ₩1513

### 현재 버전
`version.json`: **3.6.0**

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

## 다음 세션 시작점

### 우선순위 작업 (2026-05-25 예정)

1. ~~**상단 2단 바**~~ ✅ 완료
2. **분석실(SandboxLab) 버그 수정** — 현재 알려진 UI 버그 점검
3. **라이브러리 데이터 채우기** — 이론 카드 내용 보강 (참고문헌, 학습노트)
4. **인과 연쇄 레이어 검토** — CascadeLayer 동작 점검, 룰 보완
