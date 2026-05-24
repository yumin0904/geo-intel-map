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
| 8 | GDELT/RSS/Sanctions + 8단계 추론 루틴 | 🔄 GDELT 완료, Sanctions 진행 예정 |

### 이론 라이브러리 (.md 파일)
`library/` 14개 완비 — 5대 섹터 전체 커버 (maritime·energy·techno·indo_pacific·gray_zone).

### ✅ GDELT 3-Stage Funnel (2026-05-24)

- `backend/connectors/gdelt_connector.py` — Stage 1: 15분 export ZIP 다운로드, QuadClass≥3·GoldsteinScale≤-5·NumMentions≥3·5대섹터 FIPS 필터
- `backend/connectors/news_cross_validator.py` — Stage 2: Reuters·BBC·Al Jazeera·AP 4개 RSS 병렬 fetch, ≥2매체 언급 시 confidence 0.5→0.8
- `backend/services/gdelt_pipeline.py` — Stage 3 오케스트레이터 + GeoJSON 직렬화 (`unverified: true` 프로퍼티)
- `backend/models/event.py` — `confidence_score: float = 1.0` 필드 추가
- `backend/api/layers.py` — `GET /api/layers/gdelt` (15분 캐시)
- `frontend/src/layers/GdeltLayer.js` — 점선 테두리(미검증) / 실선(교차검증) 구분, ⚠️ 뱃지

실측: 24개 피처 | 교차검증 20개(✓) | 미검증 4개(⚠️) — confidence_score 0.8/0.5

### 현재 버전
`version.json`: **3.3.0** → 다음 완료 시 3.4.0 예정

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

1. **버그 수정**: 분석실 새 가설 생성 후 목록 미갱신 + 튜토리얼 캔버스 자동생성 미작동 확인
2. **버전 뱃지**: LayerPanel 하단 또는 지도 우하단에 `v3.3.0` 표시 (version.json에서 fetch)
3. **Step 8 착수**: 1·2·4·6단계부터 — 기존 yfinance 확장(FRED) + GSDB 제재 레이어 + case_studies.yaml 초안
