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

## 다음 시작점

### Phase 2 — 핵심 차별화

**첫 작업: 첫 Cascade Rule 동작 (호르무즈→유가)**

```
"progress.md 읽고 오늘 시작점 알려줘. 바로 시작하자."
```

작업 순서:
1. `backend/config/cascade_rules.yaml` — 호르무즈→유가 룰 작성
2. `backend/services/cascade/engine.py` — 룰 평가 엔진
3. `backend/services/cascade/rule_loader.py` — YAML 로드
4. 프론트엔드 Cascade 표시 (지도 점선 화살표)

관련 이론: Hirschman (1945) 자원무기화 + Drezner (2015)

---

## Phase 로드맵

- ✅ Phase 0: 기반 (FastAPI + Leaflet + 군사기지)
- ✅ Phase 1: MVP (5개 레이어 + LayerManager)
- 🔜 Phase 2: 핵심 차별화 (Cascade Rules + 실시간 레이어)
- ⬜ Phase 3: 학습 도구 완성
