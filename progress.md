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

### 우선순위 작업 (2026-05-27 예정)

1. **Gemini 리셋 확인** — KST 09:00 이후 `POST /api/translate/reset_circuit` 실행
2. **뉴스 티커 한국어 번역 확인** — `/api/news/ticker` 호출, 이모지·[지역] 포맷 정상 표시 여부
3. **분쟁 이벤트 맥락 요약 Gemini 동작 확인** — `generate_context_summary()` / `generate_gdelt_summary()` 실제 호출 테스트
4. **데이터 계층형 보관 설계** — GDELT/ACLED 이벤트 TTL 정책, 오래된 데이터 아카이브
5. **라이브러리 데이터 채우기** — `library/` .md 신규 추가, theory_library.yaml 항목 보강
6. **서브 에이전트 8단계 추론 자동화 설계 시작** — `backend/services/reasoning/` 구조 설계, case_studies.yaml 초안
