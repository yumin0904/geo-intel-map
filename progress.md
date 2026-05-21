# 개발 진행 기록

## Phase 1 — MVP (완료)

### 완료된 레이어 (5/5)

| # | 레이어 | 파일 | 상태 |
|---|--------|------|------|
| 1 | 분쟁 이벤트 (ACLED) | `connectors/acled.py`, `ConflictEventsLayer.js` | ✅ |
| 2 | 군사기지 & 자산 | `MilitaryBasesLayer.js` | ✅ |
| 3 | 에너지 파이프라인 | `EnergyPipelinesLayer.js` | ✅ |
| 4 | 해상 초크포인트 | `ChokepointsLayer.js` | ✅ |
| 5 | 해저 광케이블 | `SubmarineCablesLayer.js` | ✅ |

### 주요 구현 내용
- ACLED API 연결 + Event 정규화 (`backend/connectors/acled.py`)
- 7일/30일 분쟁 이벤트 필터 토글 (789개 차이 확인)
- LayerManager + LayerPanel UI (토글 연동)
- 해저케이블 날짜변경선 수정 (태평양 경계 버그 해결)
- 마커 1,000+ 처리: MarkerCluster + Canvas 렌더링

---

## Phase 2 — 핵심 차별화 (진행 중)

### ✅ 첫 Cascade Rule 동작 (2026-05-21)

**바브엘만데브 긴장 → 유가** 인과 연쇄가 실제 데이터로 동작.
- 후티 공격(ACLED sev76, 2025-05-01) → WTI 원유(CL=F) +1.77% 실제 매칭
- 호르무즈 룰은 룰북에 유지(현재 강 안 고강도 분쟁 없어 0건, 해군 데이터 도입 시 자동 동작)

구현 파일:
- `backend/config/regions.yaml` + `services/region.py` — 좌표→region_code 판정
- `backend/models/cascade.py` — CascadeRule / CascadeLink
- `backend/config/cascade_rules.yaml` — 룰북 (bab_el_mandeb, hormuz)
- `backend/services/cascade/rule_loader.py` — YAML 로드+검증
- `backend/connectors/yfinance_adapter.py` — CL=F 유가 시계열 (yfinance)
- `backend/connectors/acled.py` — fetch()에 countries 옵션 추가 (걸프 조회)
- `backend/services/cascade/engine.py` — 룰 평가 엔진
- `backend/api/cascade.py` — `GET /api/cascade/links` (1시간 캐시)
- `frontend/src/layers/CascadeLayer.js` — 점선 화살표(원인→결과) + 이론 팝업

관련 이론: SLOC Interdiction(Mahan) / Resource Weaponization(Hirschman 1945)

✅ 시각 확인 완료 — 노랑 점선 화살표(weight 7.5px, 3배), 도착점 "유가 +1.77%" 레이블, 팝업 헤드라인 개선

### 🔜 다음 작업 (Phase 2)
- 실시간 레이어 (ADS-B / AIS / FIRMS)
- Cascade Rule Book 10개 이상으로 확장
- CascadeGraphView (Cytoscape) — 인과 그래프 뷰
- TimelineView — 시간순 이벤트 배열
- Theory Panel / Study Mode

---

## Phase 로드맵

- ✅ Phase 0: 기반 (FastAPI + Leaflet + 군사기지)
- ✅ Phase 1: MVP (5개 레이어 + LayerManager)
- 🔄 Phase 2: 핵심 차별화 — 첫 Cascade Rule 동작 ✅ / 실시간 레이어·룰 확장 진행 예정
- ⬜ Phase 3: 학습 도구 완성
