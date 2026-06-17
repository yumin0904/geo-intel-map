# SYSTEM PROMPT — Geopolitical Cascade Intelligence Map (v2)

## 0. 프로젝트 정체성

이 프로젝트는 **정치외교학 학습을 위한 개인용 지정학 분석 도구**다.
일반적인 OSINT 대시보드(예: World Monitor)와 다음 두 가지가 다르다:

1. **학습 우선**: 모든 데이터는 국제정치 이론(해양력, 자원무기화, 회색지대전략 등)과 연결되어 해석 가능해야 한다.
2. **연쇄 분석(Cascade Analysis) 중심**: 단순 시각화가 아니라 "사건 → 지표 변화 → 또 다른 사건"의 인과 추적이 핵심 기능이다.

사용자는 **비전공자 개발자**(정치외교학과 학부생)이며, 시스템은 항상 다음을 만족해야 한다:
- 저비용 (무료/저가 API 우선)
- 고효율 (불필요한 데이터 로드 금지)
- 높은 코드 품질 (확장 가능한 아키텍처)
- 최신 정보 접근성 (실시간 또는 일 단위 갱신)

---

## 1. 핵심 6대 섹터 (도메인 우선순위)

이 프로젝트가 다루는 영역은 다음으로 한정한다. 그 외 레이어는 **명시적으로 거절**한다.

| # | 섹터 | `sector_tag` | 정치외교학 연결 이론 |
|---|------|-------------|---------------------|
| 1 | 해양 초점주의 & SLOC | `maritime` | Mahan 해양력, 진주목걸이 vs 인도-태평양 전략 |
| 2 | 에너지 지정학 & 인프라 | `energy` | 자원무기화, 상호의존의 무기화 (Farrell & Newman) |
| 3 | 기술 패권 & 보이지 않는 인프라 | `techno` | Techno-nationalism, Digital Iron Curtain |
| 4 | 인도-태평양 군사 대치 | `indo_pacific` | 동맹이론, A2/AD, 제1열도선 |
| 5 | 회색지대 & 비전통 안보 | `gray_zone` | Hybrid Warfare, Gray Zone Strategy |
| 6 | 사이버 안보 & 인지전 | `cyber` | Information Operations, APT 귀속, Cognitive Warfare |

**섹터 구분 원칙**:
- `techno`: 반도체·5G·공급망 등 기술 패권의 **구조적·경제적** 차원
- `gray_zone`: 비국가 행위자, 프록시전, 하이브리드전의 **물리적** 차원
- `cyber`: 사이버 공격·방어·인지전의 **작전적** 차원 (2026년 이란전 사이버전, APT, 선거 개입 등)

---

## 2. MVP 레이어 (11개) — 우선 구현 순서

| 우선순위 | 레이어 | 데이터 소스 | 구현 난이도 |
|---------|--------|------------|-----------|
| 1 | 분쟁 이벤트 (ACLED) | ACLED API (학술용 무료) | ★★☆ |
| 2 | 군사기지 & 자산 | 정적 GeoJSON 큐레이션 | ★☆☆ |
| 3 | 글로벌 에너지 파이프라인 | OSM Overpass / 정적 데이터 | ★★☆ |
| 4 | 해상 초점 (Chokepoints) | 정적 polygon 데이터 | ★☆☆ |
| 5 | 해저 광케이블 | TeleGeography 공개 데이터 | ★★☆ |
| 6 | 군용기 ADS-B | OpenSky Network API | ★★★ |
| 7 | 군함/상선 AIS | AISStream.io (무료 티어) | ★★★ |
| 8 | 위성 화재/열점 (VIIRS) | NASA FIRMS API | ★★☆ |
| 9 | 국가 불안정성 지수 (CII) | 자체 계산 (V-Dem + 가공) | ★★★★ |
| 10 | 사이버 위협 & 인터넷 차단 | NetBlocks, IODA | ★★☆ |
| 11 | 시장 지표 (오버레이) | yfinance, CoinGecko | ★★☆ |

**구현 원칙**: 1~5번까지 먼저 완성 후 6번 이상 진행. 한 번에 1개씩.

---

## 3. CASCADE ANALYSIS (★ 핵심 차별 기능 ★)

### 3.1 데이터 모델

모든 데이터는 **Event**로 정규화된다. 레이어가 무엇이든 결국 Event 테이블에 쌓인다.

```python
class Event(BaseModel):
    id: str                          # uuid
    timestamp: datetime              # UTC
    source_type: str                 # "conflict" | "market" | "infra" | "naval" | ...
    source_id: str                   # 원본 소스의 식별자
    location: tuple[float, float]    # (lat, lon), 없으면 region 사용
    region_code: str | None          # ISO 또는 자체 region 코드 (예: "taiwan_strait")
    severity: int                    # 0-100, 정규화된 심각도
    title: str
    description: str
    payload: dict                    # 소스별 원본 데이터
    theory_tags: list[str]           # ["A2AD", "gray_zone", ...]
```

```python
class CascadeLink(BaseModel):
    id: str
    source_event_id: str
    target_event_id: str
    time_delta_seconds: int
    correlation_score: float         # 0-1
    link_type: Literal["rule", "statistical", "manual"]
    rule_id: str | None              # 룰 기반인 경우
    evidence: dict                   # 근거 (지역 매칭, 시간 윈도우 등)
    theory_ref: str | None           # 관련 이론 (학습 노트)
```

### 3.2 Cascade Rule Book (구현 핵심)

룰은 **YAML 파일**로 관리한다. 코드 수정 없이 룰만 추가하면 새 인과관계가 등록된다.

```yaml
# /config/cascade_rules.yaml
- id: taiwan_strait_to_tsm
  name: "대만해협 군사긴장 → TSMC 주가"
  trigger:
    source_type: military_flight
    region: taiwan_strait
    severity_min: 50
  expected_response:
    source_type: market
    ticker: "TSM"
    direction: down
    window_hours: 24
    threshold_pct: 1.0
  theory:
    framework: "Weaponized Interdependence"
    reference: "Farrell & Newman (2019)"
    learning_note: "반도체 공급망 집중도가 정치적 충격에 어떻게 전이되는지 관찰"

- id: hormuz_tension_to_oil
  name: "호르무즈 긴장 → 유가"
  trigger:
    source_type: naval_activity
    region: hormuz
    severity_min: 60
  expected_response:
    source_type: market
    ticker: "CL=F"
    direction: up
    window_hours: 48
    threshold_pct: 1.5
  theory:
    framework: "Resource Weaponization"
    reference: "Hirschman (1945), 현대화 Drezner (2015)"
```

### 3.3 Cascade Engine 책임

```
/services/cascade/
  ├── engine.py          # 메인 엔진: 새 Event 발생 시 룰 평가
  ├── rule_loader.py     # YAML 룰 로드 & 검증
  ├── correlation.py     # 통계적 상관분석 (Phase 2)
  └── graph_builder.py   # 그래프 구조 빌드 (시각화용)
```

새 Event가 들어오면:
1. `engine`이 모든 룰을 평가
2. trigger 조건에 맞으면 expected_response 윈도우 동안 대기
3. 윈도우 안에 매칭 이벤트 발생 → `CascadeLink` 생성
4. 시각화 레이어로 푸시

### 3.4 시각화 (3-View System)

| 뷰 | 라이브러리 | 용도 |
|---|-----------|------|
| 지도 뷰 | Leaflet | 공간적 인과관계 (점선 화살표) |
| 타임라인 뷰 | vis-timeline | 시간순 이벤트 배열 |
| 인과 그래프 뷰 | Cytoscape.js | 한 이벤트의 상하위 노드 트리 |

**전환 원칙**: 같은 이벤트를 세 뷰에서 모두 클릭 가능. ID 기반 연동.

---

## 4. TECH STACK (확정)

### Backend
- **FastAPI** (Python 3.11+)
- 비동기: `httpx`, `asyncio`
- 데이터 검증: `pydantic v2`
- 스케줄러: `APScheduler` (cron 패턴)
- DB: **Phase 1** SQLite + JSON 컬럼 → **Phase 2** PostgreSQL + TimescaleDB
- 캐시: `cachetools` (메모리) → Redis (필요 시)
- 룰 엔진: YAML + Python 직접 평가 (외부 룰엔진 라이브러리 불필요)

### Frontend
- **Vanilla JS** ES6 모듈 (빌드도구 없음)
- 지도: **Leaflet** + `leaflet.markercluster` + `leaflet.heat`
- 타임라인: **vis-timeline**
- 그래프: **Cytoscape.js**
- 차트: **uPlot** (시장 지표용, 가벼움)
- 스타일: CSS 변수 기반 토큰

### 인프라
- 로컬 개발 우선, 배포는 마지막 단계
- Git + GitHub (private repo 권장)
- `.env` + python-dotenv (절대 키 커밋 금지)
- 배포 시 Fly.io / Railway / Render 무료 티어

---

## 5. 아키텍처

```
geomap/
├── backend/
│   ├── api/                    # FastAPI 라우터
│   │   ├── layers.py           # 레이어별 GeoJSON 응답
│   │   ├── events.py           # 이벤트 CRUD
│   │   ├── cascade.py          # 인과 분석 API
│   │   └── study.py            # 학습 관련 (북마크, 노트)
│   ├── connectors/             # 외부 소스 어댑터 (1소스 = 1파일)
│   │   ├── base.py             # 공통 인터페이스
│   │   ├── acled.py
│   │   ├── opensky.py
│   │   ├── aisstream.py
│   │   ├── nasa_firms.py
│   │   └── yfinance_adapter.py
│   ├── services/
│   │   ├── normalize.py        # 원본 → Event 변환
│   │   ├── cascade/            # ★ 인과 엔진
│   │   ├── cii.py              # 국가 불안정성 지수 계산
│   │   └── region.py           # 지역 코드/지오펜싱
│   ├── models/                 # Pydantic 스키마
│   ├── db/                     # SQLite 모델, 마이그레이션
│   ├── jobs/                   # 스케줄러 작업
│   └── config/
│       ├── layers.yaml         # 레이어 메타데이터
│       ├── regions.yaml        # 지역 폴리곤 정의
│       └── cascade_rules.yaml  # ★ 인과 룰북
├── frontend/
│   ├── index.html
│   ├── src/
│   │   ├── core/
│   │   │   ├── MapController.js
│   │   │   ├── LayerManager.js
│   │   │   ├── EventBus.js
│   │   │   ├── StateStore.js
│   │   │   └── CascadeController.js  # ★
│   │   ├── layers/
│   │   ├── views/
│   │   │   ├── MapView.js
│   │   │   ├── TimelineView.js       # ★
│   │   │   └── CascadeGraphView.js   # ★
│   │   ├── panels/
│   │   │   ├── LayerPanel.js
│   │   │   ├── DetailPanel.js
│   │   │   ├── TheoryPanel.js        # ★ 이론 설명 패널
│   │   │   └── NotebookPanel.js      # ★ 공부 노트
│   │   ├── services/
│   │   │   └── api.js
│   │   └── config/
│   └── styles/
├── data/                       # 정적 GeoJSON (기지, 케이블, 파이프라인)
├── notebooks/                  # Jupyter (데이터 탐색, 룰 검증)
├── tests/
└── docs/
    └── theory_notes/           # ★ 학습 노트 마크다운
```

---

## 6. 학습 보조 기능 (정치외교학 전공자 특화)

### 6.1 Theory Panel
이벤트 클릭 시 우측에 **관련 이론 카드**가 자동 표시:
- 이론 이름 + 주요 학자
- 한 줄 요약
- 현재 이벤트와의 연결 설명
- 추천 읽기 자료 링크 (논문, 보고서)

### 6.2 Study Mode (학습 모드)
사이드바 토글로 전환:
- **Brief Mode**: 일반 사용 (대시보드)
- **Study Mode**: 이론 태그 강조, 인과관계 자동 하이라이트, 노트 입력창 상시 표시

### 6.3 Notebook (개인 노트)
이벤트별로 메모 저장 (로컬 SQLite). 추후 마크다운으로 내보내기.

### 6.4 Case Study Library
대표 사례를 미리 저장 (예: "2022 펠로시 대만 방문", "2023 홍해 후티 공격"):
- 클릭 시 해당 시점으로 지도 시간 이동
- 당시 발생한 모든 이벤트와 cascade 자동 표시
- 관련 이론과 함께 학습 가능

---

## 7. CODING STANDARDS (비전공자 친화)

### Python
- 타입 힌트 필수, 모든 함수에 docstring (한국어 OK)
- async는 외부 I/O가 있을 때만, 단순 함수는 sync 유지
- 외부 API 응답은 반드시 **connector에서 Event로 정규화** 후 반환
- 에러는 절대 무시 금지 — 최소 `logger.warning`

### JavaScript
- ES6 모듈, default export 지양
- 함수형 우선, 클래스는 매니저급에만
- 모든 비동기는 async/await
- DOM 셀렉터는 파일 상단 const로 추출

### 공통
- 매직 넘버 금지 → `config/`로 추출
- 한 함수 = 한 책임, 50줄 초과 시 분리 검토
- 주석: **"왜"**를 설명. 정치외교학적 이유도 코멘트로 남기면 좋음
  ```python
  # 호르무즈는 글로벌 원유 운송의 약 20%가 통과하므로 severity 가중치 1.5배
  severity *= 1.5 if region == "hormuz" else 1.0
  ```

---

## 8. 성능 원칙

### 지도 렌더링
- 1,000+ 마커 → 무조건 `markercluster` 또는 `L.canvas()`
- `preferCanvas: true` 기본
- 줌/팬 이벤트는 `debounce(150ms)` + `requestAnimationFrame`
- bbox 기반 lazy load (`map.getBounds()` 활용)
- 레이어 토글은 데이터 재요청 없이 visibility만 변경

### 데이터 전송
- 응답은 gzip 압축
- 좌표 정밀도 5자리 (1m)
- 실시간 데이터는 **SSE** 우선 (WebSocket은 양방향 필요할 때만)
- 폴링은 최소 60초 간격

### Cascade 계산
- 이벤트 들어올 때마다 전체 룰 평가 = O(rule 수). 룰 100개 이하면 즉시 계산 OK
- 통계적 상관은 nightly batch로
- 결과는 `CascadeLink` 테이블에 영속화 → 매번 재계산 금지

---

## 9. RESPONSE PROTOCOL (Claude의 답변 규칙)

사용자가 요청하면:

1. **요청 분류**: ①신규 레이어 ②cascade 룰 ③버그 ④아키텍처 결정 ⑤이론 매핑 ⑥일반 학습 질문
2. **컨텍스트 명시**: 어느 파일·모듈에 영향 (예: `connectors/acled.py`, `cascade_rules.yaml`)
3. **변경 영향 선언**: 어떤 다른 부분에 파급되는지
4. **코드 제시**: 변경 부분만, 전체 파일 덤프 금지
5. **검증 단계 제안**: 어떻게 테스트할지

### 이론과 코드 연결
새 cascade 룰이나 새 레이어를 도입할 때, **관련 정치외교학 이론을 1~2문장으로 명시**한다. 사용자가 학습 도구로 쓰기 때문에 이게 중요하다.

예시:
> 이 룰은 Farrell & Newman의 "Weaponized Interdependence" 이론을 적용한 것입니다. 글로벌 공급망의 비대칭성이 정치적 무기로 전환되는 메커니즘을 관찰하는 데 사용됩니다.

### 비전공자 배려
- AI가 자동 생성한 코드도 사용자가 한 줄씩 이해할 수 있도록 **핵심 부분에 한국어 주석** 첨부
- 새 라이브러리 도입 시 "왜 이걸 쓰는가" 1~2줄 설명
- "Phase 1 / Phase 2" 식으로 단계 분리해서 부담 줄일 것

---

## 10. 안티패턴 (절대 금지)

- ❌ 모든 데이터를 클라이언트로 한 번에 전송
- ❌ 외부 API 응답 스키마를 프론트에 직접 노출 (Event 정규화 필수)
- ❌ Cascade 룰을 코드에 하드코딩 (반드시 YAML)
- ❌ 마커 1만 개 직접 추가 (클러스터링/캔버스 사용)
- ❌ 색상·임계값을 컴포넌트에 하드코딩
- ❌ 데이터 없이 시각화 먼저 (Event 모델 먼저 설계)
- ❌ "정치적으로 민감"하다고 데이터를 임의로 검열·왜곡
- ❌ 비전공자가 이해 못 한 채로 코드 진행

---

## 10-A. 버전 관리 규칙

`backend/config/version.json` 은 **단일 진실 공급원(Single Source of Truth)** 이다.

```json
{ "version": "3.0.0", "phase": 3 }
```

### 업데이트 시점
- **Phase 전환 시**: `phase` 번호 올림 + `version` 메이저 버전 올림 (예: 2.x.x → 3.0.0)
- **주요 기능 완료 시**: `version` 마이너 올림 (예: 3.0.0 → 3.1.0)
- **버그 수정 / 소규모 변경**: `version` 패치 올림 (예: 3.0.0 → 3.0.1)

### 절대 하지 말 것
- ❌ `index.html` 또는 JS 파일에 버전 문자열 하드코딩
- ❌ `main.py` FastAPI 앱 `version=` 파라미터를 version.json과 따로 관리

### progress.md 완료 기록 시 함께 할 것
작업 완료를 progress.md에 기록할 때, 해당 작업이 마이너 이상 변경이라면
`version.json`도 함께 bump한 뒤 두 파일을 같은 커밋에 포함한다.

---

## 11. PHASE ROADMAP

### Phase 0 — 기반 (1주)
- [ ] FastAPI + Leaflet 헬로월드
- [ ] Event 모델 + SQLite 스키마 확정
- [ ] 정적 GeoJSON 1개 (군사기지) 표시

### Phase 1 — MVP (2~3주)
- [ ] 레이어 5개 (1~5번 우선순위)
- [ ] LayerManager + 토글 UI
- [ ] DetailPanel 기본 동작
- [ ] **첫 Cascade 룰 1개 동작** (예: 호르무즈→유가)
- [ ] TimelineView 기본 표시

### Phase 2 — 핵심 차별화 (1~2개월)
- [ ] 실시간 레이어 3개 (ADS-B, AIS, FIRMS)
- [ ] Cascade Rule Book 10개 이상
- [ ] CascadeGraphView (Cytoscape)
- [ ] Theory Panel
- [ ] Study Mode

### Phase 3 — 학습 도구 완성 ✅ (완료)

**Veto 확정 (구현 금지)**
- MapLibre 3D Globe → Phase 4 격리
- 외교부 안전여행 API → Phase 4 후순위
- Gemini 영상 자막 추출 → 완전 폐기
- X(트위터) 임베드 → Mastodon/Bluesky 대체

**신규 구현 항목 (우선순위 순)**
1. md_indexer.py → TheoryLibrary 데이터 소스
2. deep_link.py + theory_library.yaml → 이론↔지도 매핑
3. api/library.py → 프론트 데이터 연결
4. SandboxLab (Cytoscape.js 노드 캔버스)
5. Sanctions 레이어 (GSDB/UN 안보리)
6. GDELT 3-Stage Funnel + confidence_score

**신규 데이터 필드**
- CascadeLink: depth(int), parent_link_id, chain_output
- Event: confidence_score (ACLED=1.0, GDELT미검증=0.5, 교차검증=0.8)
- 무한루프 방지: _MAX_CHAIN_DEPTH=4

### Phase 4 — 데이터 확충 & 적재 기반 강화

목표: 추론의 연료 확충 + 데이터 신뢰도 강화

**게이트**: Phase 3 완성 공식 선언 후 착수. 항목 4는 Granger 데이터 6개월+ 누적 후(§11-A 게이트).

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 0 | 국가 지정학 프로파일 — CountryPanel 기본정보 탭 확장 | `country_geopolitics.yaml` / `country.py` / `CountryPanelView.js` | [ ] |
| 1 | 실시간 소스 다변화 — ReliefWeb API(UN OCHA) 편입, RSS 분쟁전문 피드 추가 | `connectors/reliefweb.py` | [ ] |
| 2 | GDELT GKG 적재 — 테마·톤 필드 결정론적 매핑 (Token-Zero 유지) | `connectors/gdelt_gkg.py` / `cameo_mapper.py` 확장 | [ ] |
| 3 | 데이터 품질 게이트 대시보드 — confidence·importance 모니터링 상단바 확장 | `api/stats.py` / `TopBarView.js` | [ ] |
| 4 | Cascade 룰 자동 후보 생성 — Granger 유의쌍 스캔 → YAML draft 제안 (인간 승인 필수) | `services/cascade/correlation.py` 확장 | [ ] |

---

### Phase 5 — 추론 지능화 ✅ (완료, v5.4.0)

목표: 규칙·매칭 기반 → 가설 생성·반증 추론

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 5 | Stage 5 (명분·의도) 구현 — GKG 톤/테마 + actor posture 결합 | `services/reasoning/stages.py` | ✅ v5.0.0 |
| 6 | 추론 체인 자기검증 — 8단계 ↔ Sandbox BFS 가설·반증 루프 | `services/reasoning/engine.py` / `sandbox_solver.py` | ✅ v5.1.0 |
| 7 | 멀티에이전트 — 섹터별 추론 에이전트 병렬 + 종합 에이전트 | `services/reasoning/agents/` (신규) | ✅ v5.4.0 |
| 8 | LLM 종합 브리핑 계층 | — | ❌ 취소 (IA-Engine으로 대체) |

---

### Phase 6 — IA-Engine 데이터 기반 강화 (현재 진행 중, v6.3.2)

목표: 분석의 원료(데이터) 확충 + Granger 통계력 강화 → UNVERIFIED 감소, VERIFIED 달성

**게이트**: Phase 5 완료 ✅ + 브리핑 50개 ✅ (2026-06-04 달성)

**사이클 구조**: 계획 → 구현/테스트 → 자동화 평가(`eval_insight.py`) → 수정 → 재계획

| # | Cycle | 목표 | 핵심 파일 | 상태 |
|---|-------|------|---------|------|
| 6-A | 외부 데이터 2차 적재 | UNVERIFIED 평균 <1건/케이스 | `data/external/` + `intel_analyzer.py` | ⬜ |
| 6-B | Granger 통계력 강화 | VERIFIED 1건+ (p<0.05) | `hypothesis_verifier.py` + `correlation.py` | ⬜ |
| 6-C | H1 생성 품질 고도화 | Type_A/B 비율 50%+ | `hypothesis_extractor.py` + 프롬프트 | ⬜ |

**Cycle 6-A 세부 (외부 데이터 2차 적재)**

현재 UNVERIFIED 높은 케이스: 북극(21건) · 호르무즈(4건) · 사헬(3건) → 해당 지역 커버 소스 부재

**1단계 — 정형 수치 데이터 (CSV seed, 즉시 ROI 최대)**

| 소스 | 해결 공백 | 우선순위 |
|------|---------|---------|
| SIPRI Arms Transfers DB | 무기 의존도·동맹 자율성 수치화 | ★★★ |
| V-DEM Democracy Index | 행위자 체제 유형 정량화 (사헬·북극) | ★★★ |
| COW Wars DB | 전쟁 선례 시계열 (역사 비교) | ★★ |
| Kiel Tracker 2025 업데이트 | 현재 2024-06 기준 → 최신화 | ★★ |
| IISS Military Balance 주요 수치 | 군사력 비교 직접 인용 | ★★ |

**2단계 — 외교부 LOD SPARQL (1단계 완료 후)**

- SPARQL 엔드포인트: `https://opendata.mofa.go.kr/lod/sparql`
- REST JSON 패턴: `GET /mofapub/resource/Publication/{id}.json.data`
- 구현 파일: `backend/connectors/mofa_lod.py`

**온톨로지 구조 (검증 완료, 2026-06-05)**

Core 클래스 7종: `Area · Country · City · Person · Organization · Event · Year`
Domain 클래스 4종: `Publication · Briefing · Press · DiplomatJ`

| 데이터셋 | 건수 | 활용 방식 |
|---------|------|---------|
| `mofapub` IFANS 발간자료 | 4,174건 | intel_analyzer 11번째 소스 — 한반도·동아시아 한국 시각 |
| `mofabrief` 대변인 브리핑 | 191건 (2022~2023) | 한국 정부 외교 신호 보조 |
| `schema:Event` 역사 이벤트 | 2,128건 | DBpedia sameAs 브릿지 (날짜 없음, 직접 사용 불가) |

**핵심: `owl:sameAs` → DBpedia 전체 연결 (검증 완료)**

모든 Country와 Event 엔티티가 DBpedia URI에 연결되어 있음:
```
Country/RU  → dbpedia:Russia
Country/KP  → dbpedia:North_Korea
Event: 러시아-우크라이나 전쟁(2022) → dbpedia:2022_Russian_invasion_of_Ukraine
Event: 후티 반란(2004)             → dbpedia:Houthi_insurgency
Event: 2019년 아브카이크 공격        → dbpedia:Abqaiq–Khurais_attack
```

**`mofa_lod.py` 쿼리 경로 2종 (모두 검증 완료)**

경로 1 — ISO2 국가 코드로 발간자료 조회:
```sparql
SELECT ?label ?date ?abstract WHERE {
  ?s a <http://opendata.mofa.go.kr/mofapub/Publication> .
  ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
  ?s <http://opendata.mofa.go.kr/mofapub/pubDate> ?date .
  ?s <http://opendata.mofa.go.kr/mofapub/abstract> ?abstract .
  ?s <http://opendata.mofa.go.kr/core/relatedCountry>
     <http://opendata.mofa.go.kr/core/resource/Country/{ISO2}> .
} ORDER BY DESC(?date) LIMIT 5
```

경로 2 — DBpedia 이벤트 URI → 관련 발간자료 조회 (UNVERIFIED 직접 감소):
```sparql
SELECT ?label ?date ?abstract WHERE {
  ?event <http://www.w3.org/2002/07/owl#sameAs> <{dbpedia_uri}> .
  ?s <http://opendata.mofa.go.kr/core/relatedEvent> ?event .
  ?s a <http://opendata.mofa.go.kr/mofapub/Publication> .
  ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
  ?s <http://opendata.mofa.go.kr/mofapub/pubDate> ?date .
  ?s <http://opendata.mofa.go.kr/mofapub/abstract> ?abstract .
} ORDER BY DESC(?date) LIMIT 5
```

intel_analyzer 진입 로직:
```python
# entity_parser가 지역 코드 추출 → ISO2 매핑 (경로 1)
# 또는 쿼리 키워드 → DBpedia URI 매핑 테이블 (경로 2)
# 예: "hormuz" → dbpedia:Abqaiq–Khurais_attack 등 관련 이벤트 URI 목록
```

평가 기준: `eval_insight.py` 재실행 → UNVERIFIED 평균 3.5건 → <1건

**Cycle 6-B 세부 (Granger 통계력)**

현재: PARTIAL 5건(p≤0.145), VERIFIED 0건

| 문제 | 수정 방법 |
|------|---------|
| 사이버 섹터 proxy 변수 없음 | `_REGION_DEFAULT_TICKER`에 cyber 섹터 매핑 추가 |
| lag 고정(4) | AIC 기준 자동 lag 선택 (`statsmodels select_order`) |
| Granger F-통계량 미출력 | `r값` 추가 → §22-A H1 스키마 완전 충족 |

평가 기준: VERIFIED 1건 달성 (대만·한반도 집중 공략, 현재 p=0.085/0.052)

**Cycle 6-C 세부 (H1 품질)**

현재: 추상 변수(의도·의지) H1 → Granger 불가 구조

| 문제 | 수정 방법 |
|------|---------|
| 추상 변수 H1 | 프롬프트: "X/Y는 측정 가능한 지표(건수·가격·비율·금액)여야 함" |
| H1 과잉 생성(최대 4개) | 최대 2개 제한 + 검증 가능성 우선 |
| Type_C proxy 품질 | proxy 제안 시 실제 소스명 함께 제시 |

평가 기준: `eval_insight.py` Type_A/B 비율 50%+

---

### Phase 7 — IA-Engine 추론 고도화 ✅ (Cycle 7-A~C 완료, v7.2.0)

목표: 경쟁 이론 실제 비교 + 이론 라이브러리 구조화 → 박사 수준 90%+

**게이트**: Phase 6 전체 Cycle 완료 + UNVERIFIED 평균 <1건 + VERIFIED 1건+

**사이클 구조**: 계획 → 구현/테스트 → 자동화 평가 → 수정 → 재계획

| # | Cycle | 목표 | 핵심 파일 | 상태 |
|---|-------|------|---------|------|
| 7-A | 이론 라이브러리 구조화 | 12개 이론 예측 변수·반례 구조화 | `library/` 프론트매터 확장 | ✅ v7.0.0 |
| 7-B | 경쟁 이론 비교 엔진 | 섹터/지역 이론쌍 + 실측값 편차 컨텍스트 | `theory_comparator.py` + 프롬프트 | ✅ v7.1.0 |
| 7-C | 종합 평가 & 캡 해제 | 20케이스 확장, rival_check 채점 추가 | `eval_insight.py` 확장 | ✅ v7.2.0 |
| **7-D** | **데이터 품질 대폭 강화** | **신뢰도 70→85+, 경쟁이론 비교 50%+** | `connectors/` + `data/external/` | ⬜ **진행 예정** |

**Cycle 7-A 세부 (이론 라이브러리 구조화)**

현재: 이론이 마크다운 텍스트로만 존재 → Gemini가 태그로만 참조, 예측 도구로 활용 불가

목표 구조 (각 이론 프로파일 프론트매터 확장):
```yaml
independent_var: "공급망 집중도 (HHI 지수)"
dependent_var: "피의존국 외교 양보 빈도"
conditions: ["비대칭 의존 구조", "대체재 부재"]
falsifiable_prediction: "집중도 증가 시 양보 증가 (통제: 군사력 균형)"
known_counterexample: "중국 SMIC 자립화 시 설명력 하락"
rival_theories: ["Balance of Power", "Liberal Interdependence"]
```

대상 12개 이론: Mahan · Farrell&Newman · Snyder · Mearsheimer · Waltz · Libicki · Hirschman · Hoffman · A2AD · Digital Iron Curtain · Gray Zone · Granger

평가 기준: [경쟁설명] 섹션에서 수치 편차 비교 등장 비율 50%+

**Cycle 7-B 세부 (경쟁 이론 비교 엔진)**

현재: 경쟁 이론 기각이 수사적 수준 ("~라는 반례가 있다")
목표: 이론 A 예측값 vs 이론 B 예측값 vs 실측값 비교 → 우세 이론 자동 선택

```
쿼리 입력
  → 관련 이론 2~3개 자동 선택 (이론 프로파일 기반)
  → 각 이론의 예측 방향 도출
  → ACLED/SIPRI/EIA 실측값과 비교
  → 예측 성공률 높은 이론 우세 판정
  → [경쟁설명] 섹션에 수치 편차 포함
```

**Cycle 7-C 세부 (종합 평가)** ✅ v7.2.0

- 자동화 테스트 10개 → 20개 확장 ✅
- rival_check 채점 (엄격/완화 2단계) 추가 ✅
- 결과: 14/17 PASS(82%), 신뢰도 평균 70, VERIFIED 2건 (한반도·북극)

**Cycle 7-D 세부 (데이터 품질 대폭 강화)**

현재 미달 원인: 섹터별 수치 데이터 공백 → cyber·techno·gray_zone 60점대 고착
목표: 신뢰도 평균 70 → 85+, 경쟁이론 수치 비교 0% → 50%+

**풀스케일 12-sub-cycle (2026-06-05 확정)**

| Level | Sub | 항목 | 소스 | 규모 | 우선순위 |
|-------|-----|------|------|------|---------|
| L1 | 7-D-1 | FRED 경제 시계열 | FRED API (무료) | ~20 시리즈 | ★★★ |
| L1 | 7-D-2 | World Bank WGI | WB Open Data API | 200국×6지표 | ★★★ |
| L1 | 7-D-3 | Our World in Data | GitHub CSV 공개 | 수만 행 | ★★★ |
| L1 | 7-D-4 | Polity5 정치체제 지수 | CSV (학술 무료) | 167국 시계열 | ★★ |
| L1 | 7-D-5 | ITU ICT 사이버 역량 | CSV (무료) | 170국 | ★★ |
| L1 | 7-D-6 | HIIK 분쟁 강도 바로미터 | CSV (무료) | 1992~현재 | ★★ |
| L1 | 7-D-7 | SIA 반도체 시장 데이터 | 공개 보고서 CSV | ~50행 | ★★★ |
| L1 | 7-D-8 | CSIS Cyber DB 확장 | CSV (20→100+건) | 100+건 | ★★★ |
| L2 | 7-D-9 | UN Comtrade 무역 의존도 | API (무료 제한) | 국가쌍 무역 | ★★ |
| L2 | 7-D-10 | Wikidata 조약·동맹 | SPARQL | 수천 건 | ★★ |
| L3 | 7-D-11 | GTD 테러 데이터베이스 | CSV (학술 무료) | 200,000+건 | ★★★ |
| L3 | 7-D-12 | ACLED 전세계 확장 | API (커넥터 있음) | 400,000+건 목표 | ★★★ |
| 공통 | 7-D-X | [경쟁설명] 형식 gap 해소 | 프롬프트 재설계 | — | ★★★ |
| 공통 | 7-D-Y | intel_analyzer 20+소스 확장 | 점진적 통합 | — | ★★★ |

**섹터별 공백 진단:**

| 섹터 | 현재 신뢰도 | 공백 | 해결 소스 |
|------|-----------|------|---------|
| cyber | 50~60 | APT 빈도·피해액 수치 없음 | CSIS 확장 + GTD + ITU |
| techno | 60~75 | 반도체 HHI·점유율 없음 | SIA + Our World in Data + Comtrade |
| gray_zone (사헬·북극) | 60~75 | 거버넌스·취약국 지수 없음 | WB WGI + Polity5 + HIIK + GTD |
| energy·maritime | 75 | 상대적 양호 | FRED 시계열 보완 |
| indo_pacific | 75 | 군사력 비교 얕음 | Our World in Data 군사 데이터 |

**평가 기준:**
- L1 완료 후: 신뢰도 평균 78+ + 경쟁이론 수치 비교 30%+
- L2 완료 후: 신뢰도 평균 82+
- L3 완료 후: 신뢰도 평균 85+ + 경쟁이론 수치 비교 50%+ → **Phase 8 착수**

상세 계획: `progress.md` Phase 7-D 섹션 참조

---

### Phase 8 — 박사 수준 추론 (PhD-level reasoning) ⬅ 현재 목표 (2026-06-07 재정의)

목표: 인사이트 분석 엔진을 석사 중반(3.68/5) → 박사 수준(4.2/5+)으로 업그레이드.
**시각화 아님** — 엔진 자체의 추론 깊이를 높인다. (구 Phase 8 시각화는 Phase 10으로 이동)

**게이트(착수)**: Phase 7-D 핵심 데이터 적재 ✅ + v7.8.9 측정 완료 (Phase 8 게이트 충족 확인)

**완료 게이트 (박사 수준 선언 — 4개 동시 충족)**

| 조건 | 현재(v7.8.9) | 목표 |
|------|-------------|------|
| LLM 심판 종합 | 3.68/5 | **4.2/5+** |
| 경쟁이론엄밀 | 3.43/5 | **4.0/5+** |
| Type_B 비율(측정불가 H1) | 41% | **15% 미만** |
| Granger | 0 유의 | **2건 유의(p<0.05) 또는 구조적 설명 승격** |

> ⚠️ Granger 정직성 가드 (v8.12.0 개정): 유의가 안 나오면 →
> (a) 변수가 비선형·체제류면 **선형검정 대상에서 제외**하고 구조적 논증으로 명시한다
>     (선형검정 부적합 게이트 — `hypothesis_extractor._classify_linear_testability`).
> (b) 비선형을 주장하려면 **임계회귀(TAR)·체제전환 등 적극적 비선형 검정으로 양성 증거**를 제시한다.
> 선형검정의 실패(p≥0.05) 자체를 비선형의 증거로 쓰지 않는다 (affirming-the-null 금지).
> 점수 위해 유의를 조작하면 기각 (정직성 > 프록시).
>
> 〔개정 배경〕 체제 변수("러시아 체제 구조 → 전쟁 지속")는 임계·체제전환으로 작동하는데
> 선형 Granger에 대리쌍으로 강제 투입한 뒤 그 실패를 "비선형 발견"으로 승격하던 것은
> 논리적으로 affirming the consequent였다. 게이트가 이를 선택 단계에서 차단한다.

**측정 근거 (v7.8.9 골드셋 15케이스)**: 점수 손실은 3곳 집중 —
① Granger 17/17 PENDING (Type_B 41% = DB에 없는 변수 발명 + Type_A p=0.92 노이즈)
② 경쟁이론엄밀 3.43 (레이블 100% but 편차 산술 없음 — Gemini가 수치를 '말'로만 비교)
③ 비자명성 3.57 (엔진이 기존 문헌 주장을 구조적으로 몰라 공백 못 짚음)

**실행 순서 (확정): 융합1·2 → 8-A → 8-C → 8-B → 8-D**

| # | Cycle | 공략 약점 | 핵심 레버 | 측정 목표 | 상태 |
|---|-------|---------|---------|---------|------|
| 융합1 | 관련성 게이트 조립 | 컨텍스트 비대·무관소스 환각 | 23소스 관련성 점수화 → 상위 N개만 주입 | 레이턴시↓ | ⬜ |
| 융합2 | Token-Zero 산술 레이어 | LLM 산술 환각 | 편차·비율·HHI·%변화 전부 Python 계산 → Gemini 서술만 | 산술 오류 0 | ⬜ |
| 8-A | H1 측정가능성 강제 | Type_B 41% | `measurable_variables.yaml` 메뉴 + extractor 프롬프트 강제 선택 | Type_B <15% | ⬜ |
| 8-C | 경쟁이론 편차 계산 | 경쟁이론엄밀 3.43 | theory_comparator 결정론적 편차 산출 + 정량 앵커 | 엄밀 4.0+ | ⬜ |
| 8-B | Granger 방법론 강화 | 유의 0건 | 극단사건(severity>P90) + 고빈도 종속변수 + 조건부 통제 | 유의 2건 또는 승격 | ⬜ |
| 8-D | 문헌 공백 탐지 | 비자명성 3.57 | 라이브러리 주장 구조화 + 교차 모순 탐지(구 P8-4 부활) | 비자명 3.9+ | ⬜ |
| 8-F | 음성 결과 분류·진단 엔진 (Negative-Result Triage) | 비유의·무의미 결과를 버리기만 하고 진단 안 함 | 비유의 4원인 결정론 진단 → 구조화된 개선 제안(탐색형 라벨) | 음성결과 진단율 100% · 탐색→확증 누출 0 | ⬜ |

> ※ 구 8-E(비선형 검정 B안)는 **Phase 9 — 분석틀 다변화의 9-C로 이동**. 비선형 검정도
> "분석틀"이므로 Method Router 체계와 함께 다루는 게 일관됨.

> **8-gate (v8.12.0 완료)**: 선형검정 적합성 게이트 — 체제·임계 변수를 선형 Granger 트랙에서
> 제외하고 "구조적 논증"으로 분류. null→비선형 승격(affirming-the-null) 제거. 그 제외된
> 변수들을 *적극적으로* 비선형 검정하는 것은 **Phase 9-C**(분석틀 다변화)에서 다룬다.

**융합 아키텍처 (병목·할루시네이션 방지, 전 과정 병행)**
1. 관련성 게이트 조립 — "예산 내 전부" → "관련성 상위 N개"
2. Token-Zero 산술 레이어 — 하드룰: Gemini는 서술만, 계산 금지
3. 출처·시점 정합성 린트 — 같은 지표 다른 값 충돌 플래그 + 연도 태그(시대착오 방지)
4. 프록시 가드 레지스트리 — "프록시 X는 A 뜻함, B 아님" 구조화 (ITU IDI·cascade score 등). 새 프록시 = 가드 등록 의무

**범위 결정**: GTD(20만건)·ACLED 전세계 확장은 **8-D에서 필요 시에만**. 8-A~C는 기존 적재 데이터로 점수 선확보 (블라인드 적재 회피).

---

#### Cycle 8-F 세부 — 음성 결과 분류·진단 엔진 (Negative-Result Triage)

**철학**: 과학은 입증(verification)이 아니라 반증(falsification)으로 전진한다(Popper).
정직성은 "결론을 내는 능력"이 아니라 "무의미한 결과를 폐기하고 *왜 안 됐는지* 정직하게
다루는 능력"에서 나온다. 8-gate가 폐기의 *앞쪽 절반*(애초에 무의미한 검정을 안 함)이라면,
8-F는 *뒤쪽 절반*(이미 나온 음성 결과를 진단하고 다음 검증을 제안)이다.

**⚠️ 절대 안티패턴 (이 사이클의 존재 이유)**

```
❌ "무의미한 관계 → 폐기 → 유의가 나올 때까지 변수·시차·지역·대리쌍 자동 탐색 → 발견으로 보고"
   = Garden of forking paths / data dredging = p-해킹. 정직성을 높이는 게 아니라 파괴한다.
✅ "무의미한 관계 → 폐기 → 왜 안 됐는지 진단 → 다음에 무엇을 검증해야 하는지 *제안*(탐색형 라벨)"
```

핵심 원칙: **개선 제안은 *실행해서 보고하는 결과*가 아니라 *구조화된 진단 + 다음 검증 제안*이다.
자동 재검정해서 유의를 보고하지 않는다.**

**파이프라인 3단계**

1. **폐기** (이미 구현): 8-gate + `verifier.py` "[검정 비유의]" 정직 문구
2. **진단** (8-F 핵심 — Token-Zero 결정론): 비유의 4원인을 기존 spec 필드로 판별

   | 진단코드 | 원인 | 결정론 신호 (기존 필드) |
   |---------|------|----------------------|
   | `D4_INSUFFICIENT` | ④ 데이터 부족 | `n_obs` 낮음(<40) 또는 이벤트/시장 시계열 짧음 |
   | `D2_NONLINEAR` | ② 비선형 미포착 | 정규 `granger_p`≥0.15 **AND** `extreme_granger_p`<0.05 |
   | `D3_BAD_PROXY` | ③ 대리변수 오류 | `theory_grounded=False` (화이트리스트 밖 쌍) |
   | `D1_NO_RELATION` | ① 무관계(정직한 결론) | `n_obs` 충분 + `theory_grounded=True` + 정규·극단 모두 깨끗이 비유의(둘 다 p>0.3) |

3. **개선 제안** (탐색형, 라벨 필수): 진단코드별 다음 행동 제시 (자동 실행 금지)

   | 진단코드 | 개선 제안 | 연계 |
   |---------|----------|------|
   | `D4_INSUFFICIENT` | 데이터 적재 확장(지역 이벤트 시계열·lookback↑) | Phase 6-A / 7-D |
   | `D2_NONLINEAR` | 적극적 비선형 검정(임계회귀·체제전환) | 8-E |
   | `D3_BAD_PROXY` | 더 나은 대리변수 또는 직접 DV(hand-coding) | `proxy_suggestions` / §20 Phase D |
   | `D1_NO_RELATION` | **관계 없음이 정직한 결론** — 경쟁 이론·구조적 설명으로 전환 (그 자체가 정보) | §19-B-2 ③ 문헌공백 |

**탐색형 vs 확증형 2-레인 분리 (p-해킹 방어 핵심)**

| | 탐색형(exploratory) | 확증형(confirmatory) |
|---|---|---|
| 목적 | "다음에 *무엇을* 검증하나" 제안 | 사전 등록 가설 검정 |
| 출력 | 가설·연구공백 제안 (발견 아님) | 등급 부여 가능 |
| 라벨 | 항상 `[탐색적]` 강제 | `[검증포인트] 충족` |
| 등급 상한 | `상관` 초과 금지 | 사다리 전체 |

**자동 재검정을 허용할 경우(선택)의 가드 3종 (없으면 탐색만)**
- 사전 등록: 어떤 후보를 볼지 미리 고정 (탐색트리 동결)
- 다중검정 보정: 전체 탐색트리에 FDR 적용 (`verifier.py:561` 기존 BH 보정 확장)
- 홀드아웃: 발견은 out-of-sample 재현돼야 하며, 무조건 `exploratory=True`

**데이터 모델**: `HypothesisSpec`에 추가
```python
diagnosis_code: str | None = None        # D1_NO_RELATION / D2_NONLINEAR / D3_BAD_PROXY / D4_INSUFFICIENT
diagnosis_reason: str = ""               # 결정론 신호 근거
improvement_directive: str = ""          # 다음 검증 제안 (실행 아님)
exploratory: bool = False                # 탐색형이면 True — 확증 등급 승격 금지
```

**구현 파일**: `services/negative_result_triage.py`(신규) · `hypothesis_verifier.py`(검정 후 triage 호출) ·
`api/intel_query.py`(SSE 4필드) · `eval_insight.py`(진단율·누출 채점)

**평가 기준**
- 음성 결과(PENDING/비유의)에 `diagnosis_code` 부여율 **100%**
- 진단 정확도: 골드셋 수동 라벨과 일치율 (목표 80%+)
- **탐색형 결과가 확증(선행성/등급)으로 새는 케이스 0** (회귀 테스트 필수)

**게이트**: 8-gate(v8.12.0) 완료 ✅ → 착수 가능. 8-E와 독립(8-F는 진단·제안, 8-E는 실제 비선형 검정).

---

### Phase 9 — 분석틀 다변화 (Multi-Method Analytical Engine) ⬅ Phase 8 다음 목표 (2026-06-17 확정)

목표: **Granger-dispatcher → Method-router.** 분류 출구가 "Granger 변종 아니면 폐기"뿐이던
단일 분석 구조를, 쿼리 직후 **데이터 모양으로 최적 방법에 직행**하는 다중 분석 엔진으로 전환한다.
인과추론 사다리의 빈 칸인 **'준실험(quasi-experimental)'**을 채워 인과 신뢰도 천장을 올린다.

**배경**: Granger는 사다리에서 '선행성'(비교적 약한 칸)에 불과하다. 그런데 현재 엔진은 모든 가설을
Granger 변종으로 강제 깔때기하고, 안 되면 폐기뿐이다. 이벤트스터디·합성통제 등 '준실험' 방법은
Granger보다 인과 신뢰도가 높은데 통째로 비어 있다. ("Granger 안 되면 다른 틀" 식 *순차 fallback*은
비효율 + method-level p-해킹이므로 금지 — 처음부터 최적 방법으로 직행한다.)

**게이트**: Phase 8(박사 수준 4게이트) 충족 후 착수. 9-C(비선형)·9-E(합성통제)는 데이터 6개월+ 누적 게이트.

**아키텍처 3원칙 (효율·정직)**
1. **선분류 라우터 + 일발 디스패치** — fallback 체인 ❌. 데이터 모양으로 *사전* 방법 1개 선택.
2. **방법별 지연 로드** — 선택된 방법이 필요한 데이터만 로드 (비시계열 가설의 헛Granger 로드 제거).
3. **방법 실패 → 8-F 진단** — 다른 방법으로 점프 ❌, 진단·개선 제안 ✅ (method-level p-해킹 차단).

**p-해킹 가드**: 방법은 데이터 모양으로 선택(유의 여부로 선택 ❌). 복수 방법이 정당히 적용되면
사전 선언 후 *전부* 실행·보고(FDR 보정). 유의한 것만 골라 보고 금지.

| # | Cycle | 방법 | 데이터 시그니처 | 사다리 칸 | 우선순위 | 상태 |
|---|-------|------|---------------|----------|---------|------|
| 9-0 | Method Router 골격 | 데이터모양 판정→디스패치 (8-gate를 한 출구로 일반화) | — | — | ★★★ 선행 | ⬜ |
| 9-A | 이벤트 스터디 / ITS | 사건 전후 비정상변동 | `SINGLE_SHOCK` (특정 날짜 단일사건) | 준실험 | ★★★ | ⬜ |
| 9-B | 횡단/패널 회귀 | 고정효과 회귀 | `CROSS_SECTION` (국가간 비교·시간축 없음) | 상관~준실험 | ★★★ | ⬜ |
| 9-C | 비선형 검정 (구 8-E) | 임계회귀(TAR)·체제전환·전이엔트로피 | `NONLINEAR` (체제·임계, 정량화 가능) | 준실험 | ★★ | ⬜ 데이터누적 |
| 9-D | 네트워크/공간 모형 | 공간자기상관·네트워크 전이 | `NETWORK_DIFFUSION` (전이·확산) | 준실험 | ★★ | ⬜ |
| 9-E | 합성통제법 | 반사실 합성 단위 | `COUNTERFACTUAL` (단일단위 정책효과) | 준실험(최강) | ★ | ⬜ 데이터누적 |

**실행 순서**: 9-0(라우터 골격) → 9-A(이벤트스터디 — cascade 직결·가벼움) → 9-B(회귀 — 적재된
SIPRI·V-Dem·WGI 패널 활용) → 9-C(비선형) → 9-D(네트워크) → 9-E(합성통제 — 가장 강하나 무거움).

**데이터 시그니처 → 방법 판정 (Token-Zero 결정론)**

| 시그니처 | 판정 신호 (기존 spec/쿼리 필드) | 방법 |
|---------|------------------------------|------|
| `UNQUANTIFIABLE` | linear_testable=False (8-gate) | 과정추적/구조적논증 |
| `SINGLE_SHOCK` | 쿼리/H1에 특정 날짜·명명 사건 (펠로시 방문 등) | 9-A |
| `CROSS_SECTION` | "국가들 사이 / ~일수록", 시간 진화 없음 | 9-B |
| `NONLINEAR` | 임계·체제 키워드이나 정량화 가능 | 9-C |
| `NETWORK_DIFFUSION` | dependent_region 존재 + 전이/확산 프레임 | 9-D |
| `COUNTERFACTUAL` | 단일 단위 "X 없었다면" 반사실 (제재·전쟁) | 9-E |
| `PAIRED_TIMESERIES` | 짝지은 정상 시계열 (기본) | Granger (기존) |

**구현 파일**: `services/methods/` 신설 — `router.py` · `event_study.py` · `panel_regression.py` ·
`nonlinear.py` · `network.py` · `synthetic_control.py`. `hypothesis_verifier.py`는 라우터 호출로 전환.
인과추론 사다리(`_classify_inference_grade`)에 '준실험' 칸 활성화.

**평가 기준**
- 방법 라우팅 정확도: 골드셋 수동 라벨과 일치율 80%+
- '준실험' 등급 도달 인사이트 1건+ (Granger 천장 돌파)
- 효율: 비시계열 가설의 헛Granger 로드 0
- 탐색→확증 누출 0 (8-F 가드 회귀 유지)

---

### Phase 10 — 시각화 (후순위, 박사 수준 + 분석틀 다변화 후)

목표: 박사 수준으로 강화되고 다중 분석틀을 갖춘 엔진의 결과를 시각적으로 표현

**게이트**: Phase 8 완료(박사 수준 4개 게이트 충족) 후. 이 분기점이 **NEOUL 프로젝트 착수 지점**과 일치
("글 하나를 지도로 변환하는 데모"가 작동하는 시점 → 별도 레포·브랜드 분리). Phase 9(분석틀) 결과를
시각화 대상으로 반영.

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| P10-1 | 브리핑 연쇄 그래프 뷰 — `series_ref` Cytoscape 시각화 | `frontend/src/views/BriefingGraphView.js` | [ ] |
| P10-2 | 행위자 네트워크 자동 추출 — `event_refs` 공통 노드 생성 | `backend/api/library.py` 확장 | [ ] |
| P10-3 | Cascade 커버리지 갭 트리거 3종 — cyber/defense_policy/economic_coercion | `cascade_rules.yaml` / `engine.py` | [ ] |
| P10-4 | 브리핑 타임라인 뷰 | `frontend/src/views/BriefingTimelineView.js` | [ ] |

> ※ 구 P8-4(교차 인사이트 자동 생성)는 Phase 8 Cycle 8-D(문헌 공백 탐지)로 흡수됨.

### P10 설계 배경 보존 (2026-06-01 분석)

7개 브리핑 교차 검토에서 도출된 교차 인사이트 가설 — Phase 10 착수 시 활용:

- **한국 전략 공간 이중 압박**: 382호(북한) × 일본 국가행동분석 동시 작동 구조
- **외교 도미노 타임라인**: 중러(845) → 북중(848) → 다극(382) → 핵잠(849) 10일 연쇄
- **Cascade 엔진 맹점 3유형**: cyber·defense_policy·economic_coercion 미포착

---

## 11-A. 미래 작업: Cascade 룰 체이닝

현재 Cascade는 **1단계 (사건 → 지표)** 구조.
추후 **다단계 연쇄 (사건 → 사건 → 사건)** 구현 예정.

### 설계 방향

각 `cascade_rules.yaml` 룰에 chain 필드가 이미 추가되어 있음 (2026-05-22 완료):

```yaml
chainable: true
chain_output: "semiconductor_supply_risk"   # 이 룰이 생성하는 시장 신호 타입
next_rule_hint: "semiconductor_to_chips_act"  # 다음 룰 ID
```

### 구현 시 변경 파일

- `backend/services/cascade/engine.py` — 체이닝 로직 (chain_output → 다음 트리거 매핑)
- `backend/models/cascade.py` — `CascadeLink`에 `depth: int` 필드 추가 (1단계=1, 2단계=2, ...)
- `frontend/src/views/CascadeGraphView.js` — 다단계 노드 트리 시각화

### 예시 체인

```
대만해협 긴장 (conflict, severity≥50)
  → TSMC 주가 하락         [chain_output: semiconductor_supply_risk]
  → 반도체 공급망 위기
  → 미국 CHIPS Act 강화    [chain_output: chips_act_investment]
  → 중국 보복 제재
```

### 구현 조건 (게이트)

- 최소 **6개월치 이벤트 데이터** 누적 후
- **Granger 인과분석**으로 통계 검증 후 (Phase 3 `services/cascade/correlation.py`)
- Phase 3 학습 도구 완성 이후 착수

---

## 12. 매 응답 자가 점검

- [ ] 5대 섹터 범위 안에 있는가?
- [ ] Event 모델로 정규화되는가?
- [ ] Cascade 분석에 기여하는가? (장기적으로)
- [ ] 정치외교학 이론과 연결 가능한가?
- [ ] 비전공자가 이해할 수 있게 설명되었는가?
- [ ] Phase에 맞는 작업인가? (단계 건너뛰지 않았는가)
- [ ] 무료/저가 자원만 사용하는가?

---

*이 시스템은 "보는 지도"가 아니라 "추론하는 지도"를 지향한다. 모든 결정은 사용자의 정치외교학 학습에 기여해야 한다.*

---

## 13. 토큰 효율 원칙

### 세션 시작
- progress.md만 읽고 시작 (CLAUDE.md 재정독 불필요)
- 시작 명령: "progress.md 읽고 오늘 시작점 알려줘. 바로 시작하자."

### 작업 중
- 파일 전체 읽기 금지 → 필요한 부분만
- 한 작업 완료 시 /clear로 컨텍스트 초기화
- 코드는 변경 부분만 제시 (전체 파일 덤프 금지)

### 사용자에게
- 매 세션 시작 시 이 원칙을 한 줄로 상기시켜줄 것
  예: "💡 토큰 절약: 작업 완료 시 /clear, 파일은 필요한 부분만 요청하세요"

---

## 14. LLM 사용 원칙 & Token-Zero Tagging Rule

### 14-A. [필수 원칙] Token-Zero Tagging
실시간 첩보(GDELT/RSS) 수집 시 7대 축 태그 부여에 Gemini/Claude API를 절대 호출하지 않는다.
반드시 `backend/utils/cameo_mapper.py`의 Deterministic 파이썬 로직으로 백엔드 1차 태깅을 완료해야 한다.

#### GDELT CAMEO 매핑 기준
| 태그 축 | 입력 필드 | 매핑 규칙 |
|---------|----------|----------|
| `level_of_analysis` | `Actor1Type1Code` | IGO/MNI → systemic, GOV/MIL/COP/LEG → state_domestic, REB/INS/NGO/CVL → non_state |
| `instrument_of_power` | `EventRootCode` | 01~05 → diplomatic, 16 → economic, 17~20 → military, 그 외 → informational |
| `strategic_posture` | `GoldsteinScale` | ≤ -5.0 → revisionist, 그 외 → status_quo |

LLM 호출은 **사용자가 명시적으로 요청한 "AI 설명 SSE"** 또는 **번역** 기능에만 허용된다.

---

## 15. 데이터 모델 고도화 — 7대 축 다차원 태그 매트릭스

모든 `Event` 및 `library/*.md` 프론트매터에 아래 7개 필드를 강제 적용한다.

| 축 | 필드명 | 값 선택지 | 이론적 근거 |
|---|--------|----------|-----------|
| 1 | `form_type` | concept / case_study / norm / data_point | — |
| 2 | `geopol_region` | taiwan_strait / hormuz / bab_el_mandeb / eastern_europe 등 | 지오펜싱 코드 |
| 3 | `sector_lead` | maritime / energy / techno / alliance / gray_zone | 5대 섹터 |
| 4 | `temporal_era` | cold_war / post_cold / us_china_rivalry / **hot** (최근 7일) | 시대 배경 |
| 5 | `level_of_analysis` | systemic / state_domestic / non_state | Waltz 3수준 |
| 6 | `instrument_of_power` | diplomatic / informational / military / economic | DIME 프레임워크 |
| 7 | `strategic_posture` | status_quo / revisionist | Snyder 동맹 딜레마 |

Pydantic 모델: `backend/models/intelligence.py` → `IntelligenceMetadata`

---

## 16. 3단계 지정학 팩트체커 (Verification Funnel)

실시간 첩보는 `is_staging: bool = True` 상태로 버퍼에 먼저 적재된다.
아래 3단계를 통과하여 `confidence_score >= 0.8`에 도달해야 대시보드에 승격된다.

| Stage | 검증 방법 | 점수 보정 |
|-------|----------|---------|
| 1 | ACLED 베이스라인 대조 (지역별 과거 분쟁 패턴) | +0.1 |
| 2 | RSS 4대 매체 교차 검증 (Reuters·BBC·Al Jazeera·AP 중 ≥2개) | +0.2 |
| 3 | 물리 센서 결합 (반경 50km, 12시간 이내 FIRMS/AIS/ADS-B 이상 징후) | +0.1 |

초기값 0.5 → 최대 0.9. 미달 자산은 `is_staging: True` 유지, 3일 후 자동 삭제.
구현 파일: `backend/services/verification_funnel.py`

---

## 17. Stage 8 동맹 확산 (Alliance Diffusion) 알고리즘

글렌 스나이더 '동맹의 딜레마(Alliance Dilemma)' 계량화.

- `Diffusion_Score ≥ 80`: **동맹 연루(Entrapment) 위험** → Actor C의 군사 자산 레이어 점선 하이라이트
- `Diffusion_Score < 50` + 외교 성명 생략: **동맹 방기(Abandonment) 징후** → sanctions.yaml 교차 분석

`pact_intensity` 기준값: NATO=1.0, 조·러조약=0.90, 미·필리핀=0.85
구현 파일: `backend/config/alliance_graph.yaml`, Stage 8 로직은 `backend/services/reasoning/stages.py`

---

## 18. 계층형 데이터 보관 정책 (TTL)

| 소스 | 핫 테이블 보관 | 아카이브 이관 조건 | 완전 삭제 |
|------|-------------|-----------------|---------|
| GDELT/RSS | 3일 (72h) | confidence≥0.8 또는 importance≥0.7 → `event_archive` 영구 보존 | 미검증(≤0.5) 3일 후 자동 삭제 |
| ACLED | 상시 (1년 전 고정) | 인입 즉시 `event_archive` 영구 귀속 (베이스라인 상수) | 없음 |
| FIRMS | 24h | Cascade Link 매칭된 열점만 보존 | 미매칭 48h 후 삭제 |
| AIS/ADS-B | 12h 스냅샷 | 초크포인트·기지 주변 이상 로그만 보존 | 일반 로그 24h 후 소멸 |

구현 파일: `backend/db/archive_manager.py`

---

## 19. 인사이트 엔진 생성 원칙 (2026-06 로드맵 반영)

### 19-A. 인사이트 생성 6단계 구조 [필수]

인사이트 분석실(`/api/intel/query`)의 Gemini 프롬프트는 반드시 아래 순서를 따른다.
현상 기술(description)에서 멈추지 말고 **인과 검증(causal verification)** 단계까지 진입할 것.

```
[단계 1] 관찰 — 측정 가능한 현상 서술 (수치·사례 포함)
[단계 2] 변수 — 독립변수·종속변수·통제변수 식별
[단계 3] 가설 — H1 반증 가능 형태로 공식화
          예: "X가 증가할 때, Y가 통계적으로 유의하게 변화한다 (통제변수 Z)"
[단계 4] 경쟁 이론 — 대안 설명 1~2개 나열 후 우선 기각 대상 선정
[단계 5] 데이터 — 사용된 소스 + 수치, 없으면 [UNVERIFIED] 태그 필수
[단계 6] 연쇄 고리 강도 자기평가
          HIGH(>70%) / MEDIUM(40~70%) / LOW(<40%)
          MEDIUM 이하 고리 포함 연쇄 → [SPECULATIVE] 레이블 명시
```

### 19-B. 인사이트 카드 출력 형식 표준 [권장]

※ 신뢰도 숫자 점수는 서버(IA-Engine-C)가 독점 산출 — Gemini 출력에 포함 금지.

```
[헤드라인] 한 줄 요약 (비자명적 발견 — "A가 증가했다" 수준 금지)
데이터기반: 고/중/저  |  이론근거: 고/중/저  |  연쇄강도: HIGH/MEDIUM/LOW

[관찰]      측정 가능한 현상 (수치·날짜·사례 포함, 없으면 [UNVERIFIED])
[주장]      인과 주장 — 방향·강도·조건 명시
[가설]      H1: "X가 증가할 때 Y가 통계적으로 유의하게 변화한다 (통제변수 Z)" 형태
[근거]      데이터 소스명 + 수치 (없으면 [UNVERIFIED])
[한계]      이 분석이 답하지 못하는 것
[경쟁설명]  대안 이론 A: 설명 / 반례: 〜할 경우 설명력 하락
            대안 이론 B: 설명 / 기각 근거: 〜
[검증포인트] 다음 세션에서 확인할 지표·소스
[문헌공백]  기존 연구가 이 패턴을 충분히 다루지 않는 이유
```

### 19-B-3. 시간 역전 탐지 [필수 — v6.0.0 추가]

각 인과 연결 고리에서 원인·결과 이벤트의 날짜를 반드시 확인한다.
결과 이벤트가 원인 이벤트보다 이전에 발생한 경우:
- `[TEMPORAL_REVERSAL]` 태그 필수
- 주장을 "A가 B를 유발" → "공통 구조적 선행 조건" 또는 "B가 A의 선행 지표"로 재공식화
- 인사이트 주장을 수정하지 않은 채 [한계]에만 언급하는 것은 금지

### 19-B-2. 유지·확장할 강점 [필수 보존]

아래 세 가지는 학부 수준 대부분의 분석 도구가 하지 못하는 기능이다.
개선 과정에서 **절대 약화시키지 말 것.**

#### ① 다중 이론 프레임 자동 연결
행위자 프로파일(revisionist·gray_zone 등)에서 방어적 현실주의·동맹 이론·비대칭 위협 이론을 자동 매핑하는 기능.
→ **유지하되, 이론 레이블에 "이 이론으로 설명되지 않는 반례" 필드를 항상 추가할 것.**

```
예시:
이론: Weaponized Interdependence (Farrell & Newman)
설명: 반도체 공급망 집중이 미국의 대중 레버리지로 작동
반례: 중국이 SMIC를 통해 자립화할 경우 이 프레임의 설명력 하락
```

#### ② 다중 도메인 교차 분석
군사·에너지·사이버 도메인을 동시에 포착하는 기능은 단일 도메인 도구 대비 명확한 우위.
→ **인사이트 생성 시 "어떤 도메인이 어떤 경로로 어떤 도메인에 영향을 미치는가"를 명시적으로 서술할 것.**

```
예시:
[사이버 → 에너지] 이란전 사이버전(844호)에서 진화한 PLC 공격 기술이
우크라이나 에너지 인프라 공격에 전이될 경로와 조건
```

#### ③ 독창적 패턴 포착 — 문헌 공백 탐지 [최고 경쟁력]
"유리 턱(Glass Jaw)", "역외균형자 vs 전방배치 헤게몬 긴장", "이란-러시아 전술 전이 가설"처럼
**기존 문헌에서 충분히 검증되지 않은 공백을 겨냥하는 것**이 핵심 경쟁력.
→ **인사이트 생성 프롬프트에 항상 명시적으로 요구할 것:**

```
"기존 주류 문헌이 충분히 다루지 않은 공백(gap)을 탐지하라.
 이미 알려진 사실을 재서술하는 것은 인사이트가 아니다."
```

### 19-C. 절대 금지 패턴

- ❌ "A → B를 시사한다" / "가능성이 높다" 로만 끝내는 것 → 반드시 고리 강도 명시
- ❌ 대안 설명 기각 과정 없이 단일 이론으로 수렴
- ❌ 결과를 곧바로 의도로 귀속 ("강경 정권 온존 = 미국 실패" 형태)
- ❌ 수치 근거 없는 인과 주장 → [UNVERIFIED] 태그 없이 서술

### 19-D. 인사이트 신뢰도 산출 기준

| 항목 | 배점 |
|------|------|
| 수치 데이터 직접 인용 | +30 |
| 1차 사료(원문 보고서·통계 DB) 참조 | +20 |
| 반증 가능 가설 포함 | +20 |
| 경쟁 이론 비교 포함 | +15 |
| 연쇄 고리 강도 명시 | +15 |
| 기본값 | 0 |

합계 0~100. 60 미만 인사이트는 [PROVISIONAL] 레이블.

---

## 20. 인사이트 엔진 데이터 로드맵 (우선순위)

### Phase A — 즉시 적재 가능 (공개 API / CSV)

| 소스 | 커버리지 | 해결 공백 | 우선순위 |
|------|---------|---------|---------|
| SIPRI Military Expenditure | 173개국 국방비 %GDP | 자유편승 검증, 역할분담 | ★★★ |
| SIPRI Arms Transfers DB | 전 세계 무기 이전 1950~ | 동맹 자율성, 의존도 | ★★★ |
| COW Alliance Data | 동맹 형성·해체 1816~ | 동맹 이탈 위험 시계열 | ★★★ |
| Kiel Institute Ukraine Support Tracker | 서방 대우크라이나 지원 | 연쇄 고리 검증 핵심 | ★★★ |
| EIA International Energy Stats | 전 세계 에너지 생산·소비 | 유가충격 정량화 | ★★★ |
| CSIS Significant Cyber Incidents | 2006~ 사이버 공격 DB | 사이버전 기준점 | ★★ |
| V-DEM Democracy Index | 202개국 민주주의 지수 | 행위자 체제 유형 | ★★ |
| Kyiv School of Economics 피해 DB | 우크라이나 인프라 피해 | 에너지 공격 강도 | ★★ |

**즉시 ROI 최대 조합: SIPRI + COW + Kiel Tracker 3종 적재 + 프롬프트 6단계 재설계**
→ 인사이트 수준 석사 중반 → 석사 후반으로 상향 기대.

### Phase B — 중기 (파싱·정제 필요)
- IISS Military Balance 연간 보고서 (PDF → 구조화)
- 미 국방부 예산 문서 (PDF, comptroller.defense.gov)
- Microsoft MSTIC / Mandiant APT 보고서 (이란-러시아 TTPs 유사도)
- 크렘린·외무부 공식 성명 (텍스트 스크래핑)

### Phase C — 장기 (라이선스 필요)
- IISS Military Balance API (유료)
- Oxford Economics Global Model
- Harvard Shorenstein 허위정보 DB

### Phase D — 종속변수(DV) 직접 코딩 데이터셋 (싱크탱크 수준, 외부 협력 가능)

**배경**: 8-C는 DV(외교 양보·정책 변화) 실측 시계열 부재로 "IV 전제조건 충족도"에 한정됨.
연구자 표준 방법 중 가장 강한 ②직접 코딩(hand-coding) DV 데이터셋을 확보하면,
8-C의 "전제조건 충족" → **"이론 입증"으로 격상** (IV→DV 회귀·Granger 직접 검정 가능).

| 후보 DV | 코딩 방법 | 확보 경로 |
|---------|----------|----------|
| 외교 양보 빈도 | 공동성명·UN 투표 동조율·제재 동참/이탈 이벤트화 | 자체 hand-coding / 학교 교수 협력 |
| 정책 변화율 | 정책 선언·법안·예산 변동 코딩 | 연구소 데이터셋 수령 |
| 동맹 이탈/연루 | 외교 문서·성명 코딩 | 기존 학술 DB(COW 확장) + 자체 보완 |

**실행 메모 (사용자)**: 본인 직접 코딩 가능 / 교수님 지도 / 연구소 데이터 수령 중 택1.
확보 시 `Type_C proxy` → `Type_A 직접 검정`으로 승격, 경쟁이론 "입증" 주장 가능.

---

## 21. 분석 아키텍처 진화 경로

```
v5.x (완료): 행위자 프로파일 → 이론 매핑 → 서술적 인사이트
v6.x (완료): 행위자 프로파일 → 변수 식별 → 10소스 병렬 데이터 조회 → 수치 근거 포함 인사이트
             + §19-D 역산 신뢰도 점수 (IA-Engine-C) + 시간 역전 탐지 + H1 자동 생성 + Granger
             → 평균 70/100, PARTIAL 5건, 박사 초입 81% (2026-06-04 자동화 테스트 기준)

Phase 6 목표 (데이터 기반 강화):
  Cycle 6-A: 외부 데이터 2차 적재 → UNVERIFIED <1건/케이스
  Cycle 6-B: Granger 통계력 강화 → VERIFIED 1건+ (p<0.05)
  Cycle 6-C: H1 생성 품질 고도화 → Type_A/B 비율 50%+
  → 목표: 신뢰도 평균 78+

Phase 7 목표 (추론 엔진 고도화):
  Cycle 7-A: 이론 라이브러리 구조화 ✅ (12개 이론 IV·DV·반례·경쟁이론 프론트매터)
  Cycle 7-B: 경쟁 이론 비교 엔진 ✅ (theory_comparator.py — 섹터/지역 이론쌍 + 실측값)
  Cycle 7-C: 20케이스 eval 확장 ✅ (14/17 PASS, 신뢰도 평균 70, VERIFIED 2건)
  Cycle 7-D: 데이터 품질 강화 ⬜ (FRED + World Bank + SIA + CSIS 확장 → 신뢰도 85+)
  → 현재: 신뢰도 평균 70/100, PARTIAL 9건, VERIFIED 2건 (v7.2.0 기준)
```

**핵심 전환 원칙:**
> "무슨 일이 일어나고 있는가"(현황 기술) →
> "왜 이 설명이 경쟁 이론보다 더 타당한가"(인과 검증)를 데이터로 보여주는 도구

---

## 22. IA-Engine-D 설계 명세 (v7.0 목표)

### 22-A. H1 자동 생성 출력 스키마

```python
{
  "H1": "X가 증가할 때 Y가 통계적으로 유의하게 감소한다 (통제변수: Z1, Z2)",
  "H0": "X와 Y 사이에 통계적으로 유의한 관계가 없다",
  "independent_var": "미국 CPI",
  "dependent_var": "Kiel Tracker 월별 지원액",
  "control_vars": ["선거 주기", "지정학 위기 강도"],
  "data_sources": ["FRED CPI", "Kiel Institute"],
  "lag_estimate": 3,            # 개월
  "verification_status": "PENDING",  # PENDING → PARTIAL → VERIFIED
  "granger_p": null             # 검증 후 채워짐
}
```

### 22-B. 신뢰도 상한 캡 규칙 [필수]

```python
if verification_status == "PENDING":   confidence_score = min(confidence_score, 75)
if verification_status == "PARTIAL":   confidence_score = min(confidence_score, 88)
if verification_status == "VERIFIED":  # 상한 없음 — Granger p<0.05 자동 충족 시
```

### 22-C. 박사 수준 도달 기준 체크리스트

현재 70% (신뢰도 평균 70/100). 완전한 박사 수준(90%+) 조건:

```
✅ 시간 역전 오류: [TEMPORAL_REVERSAL] 자동 탐지 및 재공식화 (v6.0 추가)
✅ ACLED 대만해협 이벤트 필터 수정 → Cascade 대만 0건 해소 (v6.1.1)

Phase 6 (데이터 기반 강화):
✅ UNVERIFIED 평균 <1건/케이스 (Cycle 6-A, v6.4.0)
✅ IA-Engine-D: Granger VERIFIED 2건 (한반도 p=0.048 + 북극 p=0.049, v7.2.0)
□ H1 Type_A/B 비율 50%+ (현재 대부분 Type_C — 데이터 공백으로 인한 추상화)

Phase 7 (추론 고도화):
✅ 이론 라이브러리 12개 이론 IV·DV·반례·경쟁이론 구조화 (Cycle 7-A, v7.0.0)
✅ 이론 비교 엔진 구현 — theory_comparator.py, 섹터/지역 이론쌍 + 실측값 (Cycle 7-B, v7.1.0)
□ 경쟁이론 수치 비교 [경쟁설명] 50%+ 달성 (현재 0~10% — 형식 gap)
□ 신뢰도 평균 85+ (현재 70 — 섹터별 수치 데이터 공백이 원인)

Phase 7-D (데이터 품질 강화, 진행 예정):
□ FRED 경제 시계열 적재 → energy·환율 수치 강화
□ World Bank WGI 거버넌스 지수 → gray_zone·사헬·북극 공백 해소
□ SIA 반도체 시장 데이터 → techno 섹터 HHI 수치화
□ CSIS Cyber DB 20→100+건 확장 → cyber 섹터 수치 강화
□ [경쟁설명] 형식 gap 해소 → 경쟁이론 수치 비교 50%+ 달성
```
