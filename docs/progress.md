# 개발 진행 기록

## 2026-05-19 (Phase 0 작업)

### 완료 항목
- [x] 프로젝트 폴더 뼈대 생성 (backend, frontend, data 등 전체 구조)
- [x] .gitkeep으로 빈 폴더 Git 추적 등록
- [x] Python 3.12 가상환경 설정 (backend/.venv)
- [x] requirements.txt 작성 및 패키지 설치 (fastapi, uvicorn, httpx, pydantic v2, python-dotenv, aiosqlite)
- [x] backend/main.py — FastAPI Hello World (GET /, GET /api/health)
- [x] frontend/index.html — Leaflet 다크 테마 지도 (CartoDB Dark Matter)
- [x] frontend/styles/main.css — CSS 변수 디자인 토큰
- [x] frontend/src/core/MapController.js — 지도 초기화 클래스

---

## 2026-05-20 (Phase 0 Step 4~5)

### 완료 항목
- [x] 백엔드 포트 8000 + 프론트 포트 5500 동시 실행 확인
- [x] `GET /api/health` 200 OK 검증
- [x] `data/military_bases.geojson` — 20개 기지 (USA 10, China 6, Allied 3, Russia 1)
  - 검증 좌표 (WGS84), theory_tags, significance, established_year 등 학습 필드 완비
- [x] `backend/api/layers.py` — `/api/layers/military-bases` GeoJSON 엔드포인트
- [x] `frontend/src/services/api.js` — 백엔드 HTTP 클라이언트 (중앙화)
- [x] `frontend/src/layers/MilitaryBasesLayer.js` — circleMarker 렌더링 + 팝업 + 툴팁
- [x] `frontend/styles/main.css` — 팝업/툴팁 다크 테마 CSS
- [x] 브라우저에서 지도 + 기지 마커 동작 확인 (서버 로그로 API 호출 검증)

### 현재 상태
- Phase 0 완료 ✅
- 마커 색상: 파랑(미국), 빨강(중국), 노랑(러시아), 초록(동맹)
- 클릭 시 팝업: 기지명/유형/설치연도/전략목적/학술의의/이론태그

---

### 좌표 검증 작업 (2026-05-20 오후)

- [x] 20개 기지 전체 Wikipedia(영문) 좌표 대조 검증
- [x] 소수점 5자리 정밀도 표준 적용 (DMS → decimal 변환 포함)
- [x] `coordinate_source` / `coordinate_verified_at` 메타데이터 필드 추가
- [x] 5개 큰 오차 발견 및 보정 완료:
  - 창이 NB: 경도 **4km** 오차 수정
  - 진주만-히캄: 경도 **2.5km** 오차 수정
  - 위린 NB(싼야): 경도 **6km** 오차 수정
  - PLA 지부티: **11km** 오차 수정 (Balbala 실제 위치 반영)
  - 잔장 NB: **11km** 오차 수정 (GlobalSecurity.org 기준)
- [x] Vladivostok → Fokino 기지로 대체 (Wikipedia 좌표 없음 → Fokino WP 사용)
- [x] git 커밋 완료: `63e00fa`

---

---

## 2026-05-20 (Phase 0 공식 완료)

### Phase 0 최종 결과 ✅

- **완료 일시**: 2026-05-20
- **최종 확인**: 다크 테마 Leaflet 지도 위 20개 군사기지 마커 브라우저 동작 확인
- **마커 색상**: 파랑(미국), 빨강(중국), 노랑(러시아), 초록(동맹국)
- **팝업 내용**: 기지명·유형·설치연도·전략목적·학술의의·이론태그
- **좌표 정밀도**: WGS84 소수점 5자리, Wikipedia 대조 검증 완료

---

---

## 2026-05-20 (Phase 1 작업)

### 완료 항목

**Step 1 — LayerManager + LayerPanel UI**
- [x] `frontend/src/core/EventBus.js` — pub/sub 싱글톤
- [x] `frontend/src/core/LayerManager.js` — 레이어 등록·토글·상태관리 (register() 한 줄로 패널 자동 반영)
- [x] `frontend/src/panels/LayerPanel.js` — 좌측 사이드바 (진영 필터 버튼 포함)
- [x] `frontend/styles/main.css` — 사이드바·필터 버튼 CSS
- [x] 브라우저 확인: 토글/필터/팝업 3가지 모두 동작 ✅
- [x] 커밋: `2c1c178`, `45bbf70`

**Step 2 — ACLED 분쟁 이벤트 레이어 (구현 완료, API 승인 대기)**
- [x] `backend/models/event.py` — Event Pydantic 모델 (CLAUDE.md 3.1 스펙)
- [x] `backend/connectors/base.py` — BaseConnector 추상 클래스
- [x] `backend/connectors/acled.py` — OAuth 토큰 캐싱/갱신, severity 정규화, theory_tags 매핑
- [x] `GET /api/layers/conflict-events` 엔드포인트
- [x] `frontend/src/layers/ConflictEventsLayer.js` — severity 기반 마커 크기/색상
- [x] 커밋: `c0edfde`
- ⏳ ACLED API 403 (계정 read 권한 승인 대기 중) — 승인 후 즉시 동작 예정

**Step 3 — 에너지 파이프라인 레이어**
- [x] `data/energy_pipelines.geojson` — 10개 파이프라인 (실제 경로 3~7개 좌표)
  - Nord Stream 1·2, 우크라이나 경유, Druzhba, Power of Siberia 1
  - CAGP, TANAP, TAP, Iran-Pakistan IP, ESPO
- [x] `GET /api/layers/energy-pipelines` 엔드포인트
- [x] `frontend/src/layers/EnergyPipelinesLayer.js`
  - 가스=주황(`#ff8c00`), 석유=노랑(`#ffd700`)
  - suspended=점선, sabotaged=파단선, planned=짧은 점선
  - 마우스오버 강조, 클릭 팝업: theory_tags·significance 포함
- [x] 브라우저 확인: 군사기지 + 에너지 파이프라인 동시 표시 ✅
- [x] 커밋: `53165a8`

---

### 현재 레이어 현황

| 레이어 | 상태 | 아이콘 | 기본 표시 |
|--------|------|--------|-----------|
| 군사기지 | ✅ 동작 | ⬡ | ON |
| 분쟁 이벤트 | ⏳ ACLED 승인 대기 | ◈ | OFF |
| 에너지 파이프라인 | ✅ 동작 | ━ | ON |

---

---

## 2026-05-21 (Phase 1 — ACLED 연결 + ConflictEventsLayer 완성)

### 완료 항목

**ACLED API 연결 및 디버깅**
- [x] 학교 계정(hanyang.ac.kr)으로 ACLED OAuth 토큰 발급 성공
- [x] `fields` 파라미터 버그 수정 — ACLED v2는 fields 지정 시 `[[],[]]` 배열 반환 → 제거
- [x] 날짜 범위 버그 수정 — 시스템 시계(2026)와 ACLED 데이터 범위(~2025) 불일치
  - `date_recency.date`를 upper bound로 사용하는 방식으로 해결
  - 24h 캐시(`_ref_date_cache`)로 probe 호출 최소화
- [x] `GET /api/layers/conflict-events` → 200개 이벤트 정상 수신 확인

**ConflictEventsLayer.js 완성**
- [x] severity 단계별 마커(0~29 초록, 30~59 노랑, 60~79 주황, 80~100 빨강)
- [x] MarkerCluster CDN 추가 (1000개 이상 시 자동 클러스터링)
- [x] 팝업 한글화: event_type 영문 → 한국어 매핑 (시위/집회, 무력충돌 등)
- [x] 줌 레벨 필터: 줌 ≤6은 severity 60+ 만 표시, 줌 7+은 전체 표시

**성능 최적화 (CLAUDE.md 섹션 8)**
- [x] 백엔드 1시간 TTL 캐시 — 두 번째 요청: 11.8s → 21ms (560배)
- [x] `limit: 500 → 200` — 전송량 60% 감소
- [x] 팝업 지연 바인딩 — 클릭 시 최초 1회만 생성

**DivIcon 펄스 애니메이션**
- [x] `circleMarker` → `L.divIcon` 전환 (군사기지 원형 유지, 분쟁 이벤트 펄스 구분)
- [x] CSS `@keyframes conflict-pulse` — 바깥으로 퍼지는 링 효과
- [x] severity별 펄스 속도: 0.5s(최고) / 1s / 2s / 3s(낮음)
- [x] CSS 변수(`--cdot-color`, `--cdot-duration`)로 컴포넌트 내 하드코딩 제거

**지도 UX 개선**
- [x] 초기 뷰: `[25, 125]` zoom 4 → `[36.0, 128.0]` zoom 5 (한반도 중심)
- [x] `worldCopyJump: true` — 날짜변경선 패닝 시 지도 연속 표시

### 현재 레이어 현황

| 레이어 | 상태 | 아이콘 | 기본 표시 |
|--------|------|--------|-----------|
| 군사기지 | ✅ 동작 | ⬡ | ON |
| 분쟁 이벤트 | ✅ 동작 (ACLED, 200개) | ◈ | ON |
| 에너지 파이프라인 | ✅ 동작 | ━ | ON |

---

### 다음 세션 시작점
**"심각도 슬라이더 + GitHub 연결"**

추천 작업 순서:
1. LayerPanel에 severity 범위 슬라이더 UI 추가 (0~100 필터)
2. `ConflictEventsLayer.setMinSeverity(n)` 메서드로 실시간 필터링
3. GitHub remote 연결 및 push

### 세션 재시작 명령어

```bash
# [터미널 1] 백엔드
cd ~/Projects/geo-intel-map/backend && source .venv/bin/activate && uvicorn main:app --reload --port 8000

# [터미널 2] 프론트엔드
cd ~/Projects/geo-intel-map/frontend && python3 -m http.server 5500

# [브라우저]
open http://localhost:5500
```

---

---

## 2026-06-03 (브리핑 적재 세션 — 18~26번째)

### 완료 항목

**Cyber 카테고리**
- [x] `briefing_20260318_rand_gamification_narrative_cognitive_warfare` — [Cyber 4/5] 게임 언어의 무기화: 풀뿌리 인지전과 서사 수확 작전 (RAND, 18번째)

**Energy 카테고리** (4/5 완료, 1개 보류)
- [ ] Energy 1/5 — Does OPEC Still Matter? (WotR) → `status: deferred`
- [x] `briefing_20260515_ecfr_postwar_uae_gulf_politics` — [Energy 2/5] 전후 UAE와 걸프 정치의 재편 (ECFR, 19번째)
- [x] `briefing_20260522_ecfr_imec_wartime_redesign` — [Energy 3/5] IMEC 전시 재설계 (ECFR, 20번째)
- [x] `briefing_20260508_wotr_russia_hormuz_playbook_baltic` — [Energy 4/5] 러시아의 호르무즈 플레이북 (WotR, 21번째)
- [x] `briefing_20260519_rand_hormuz_mine_clearing` — [Energy 5/5] 호르무즈 소해 작전 (RAND, 22번째)

**Gray Zone 카테고리** (2/4 완료, 2개 보류)
- [x] `briefing_20260519_wotr_somaliland_recognition_red_sea` — [Gray Zone 1/4] 소말릴란드 승인의 문제 (WotR, 23번째)
- [ ] Gray Zone 2/4 — Western Withdrawal, Jihadist Expansion: Sahel (WotR) → `status: deferred`
- [x] `briefing_20260514_wotr_kremlin_battlefield_home` — [Gray Zone 3/4] 크렘린의 진짜 전장은 국내다 (WotR, 24번째)
- [x] `briefing_20260529_wotr_glass_jaw_economic_fragility` — [Gray Zone 4/4] 유리 턱: 미국 경제 취약성 (WotR, 25번째)

**Maritime 카테고리** (진행 중)
- [x] `briefing_20260528_wotr_sea_control_revolution` — [Maritime 1/5] 제해권 혁명 (WotR, 26번째)

### 현재 브리핑 라이브러리 현황

| 항목 | 수치 |
|------|------|
| 총 적재 브리핑 수 | **26개** |
| 오늘 세션 추가 | **+9개** (18~26번째) |
| 큐 잔여 보류 포함 | **deferred 3개** (Energy 1/5, Gray Zone 2/4, 구 세션 1개) |

### 다음 세션 시작점

**Maritime 2/5~5/5 계속 적재 후 Indo-Pacific 카테고리로 이동**

Maritime 잔여 (4개):
- Missing Navies: Hormuz Crisis (WotR)
- Japan Should Help Sink China's Invasion Fleet (RAND)
- South Korea's 500,000 Drone Warriors (WotR)
- Leading in the Dark: Submarine Commanders (WotR)
