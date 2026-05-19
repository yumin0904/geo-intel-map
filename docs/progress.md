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

### 다음 세션 시작점
**Phase 0 — 4단계: 브라우저 동작 확인 + 5단계: 첫 GeoJSON (군사기지 점 표시)**

### 서버 실행 명령어

```bash
# 터미널 1 — 백엔드 (backend 폴더 안에서)
source backend/.venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000

# 터미널 2 — 프론트엔드 (frontend 폴더 안에서)
cd frontend
python3 -m http.server 5500

# 브라우저에서 열기
open http://localhost:5500        # 지도
open http://localhost:8000/docs   # FastAPI 자동 문서
```
