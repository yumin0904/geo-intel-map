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

### 다음 세션 시작점
**Phase 1 — LayerManager + 레이어 토글 UI 구현**

추천 다음 작업 순서:
1. `frontend/src/core/LayerManager.js` — 레이어 등록·토글·상태관리
2. `frontend/src/panels/LayerPanel.js` — 사이드바 토글 UI
3. ACLED API 연결 (`backend/connectors/acled.py`) — 분쟁 이벤트 레이어 (Phase 1 우선순위 1위)

### 세션 재시작 명령어 (매번 이것만 기억하면 됨)

```bash
# 프로젝트 루트에서 — 터미널 2개 열고 각각 실행

# [터미널 1] 백엔드
cd ~/Projects/geo-intel-map/backend && source .venv/bin/activate && uvicorn main:app --reload --port 8000

# [터미널 2] 프론트엔드
cd ~/Projects/geo-intel-map/frontend && python3 -m http.server 5500

# [브라우저]
open http://localhost:5500 && open http://localhost:8000/docs
```
