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

## 라이선스

개인 학습 프로젝트 (비공개)
