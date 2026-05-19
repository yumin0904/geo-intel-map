# 🌍 geo-intel-map

정치외교학 학습을 위한 지정학 인텔리전스 지도

## 핵심 기능

- 🗺️ 5대 섹터 통합 시각화 (해양/에너지/기술/군사/회색지대)
- 🔗 **Cascade Analysis**: 사건 → 지표 → 사건의 연쇄 추적
- 📚 정치외교학 이론과 연결된 학습 모드
- 📊 실시간 + 정적 데이터 통합 (ACLED, OpenSky, AIS, FIRMS 등)

## 기술 스택

- Backend: FastAPI (Python 3.12)
- Frontend: Vanilla JS + Leaflet
- DB: SQLite (Phase 1) → PostgreSQL+TimescaleDB (Phase 2)
- Visualization: Leaflet + vis-timeline + Cytoscape.js

## 개발 단계

- [ ] Phase 0: 기반 (헬로월드 + 첫 지도)
- [ ] Phase 1: MVP (5개 레이어 + 첫 Cascade Rule)
- [ ] Phase 2: 핵심 차별화 (실시간 + 룰북 + 인과 그래프)
- [ ] Phase 3: 학습 도구 완성

## 로컬 개발 시작하기

### 1. 가상환경 활성화 (매번 작업 시작 전)

```bash
# 프로젝트 루트에서 실행
source backend/.venv/bin/activate

# 비활성화할 때
deactivate
```

### 2. 백엔드 서버 실행

```bash
# backend 폴더 안으로 이동 후 실행해야 한다 (main.py가 있는 위치)
cd backend
uvicorn main:app --reload --port 8000
```

- `--reload` : 코드를 수정하면 서버가 자동으로 재시작됨. 개발 중에만 사용.
- `--port 8000` : 8000번 포트에서 실행. 브라우저에서 http://localhost:8000 으로 접근.
- 종료는 터미널에서 `Ctrl + C`

### 3. 동작 확인

서버 실행 후 아래 URL을 브라우저나 터미널에서 확인:

| 경로 | 설명 |
|------|------|
| http://localhost:8000/ | API 루트 |
| http://localhost:8000/api/health | 헬스체크 |
| http://localhost:8000/docs | 자동 생성 API 문서 (Swagger UI) |

```bash
# 터미널에서 확인 (curl)
curl http://localhost:8000/api/health
# → {"status":"ok","service":"geo-intel-map","version":"0.0.1"}
```

## 라이선스

개인 학습 프로젝트 (비공개)
