# Cascade 룰 체이닝 — 미래 작업 설계 (구 CLAUDE.md §11-A, 2026-07-10 이관)

> **착수 게이트 [필수]**: 본문 말미 '구현 조건 (게이트)' 3종 충족 전 착수 금지.

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
