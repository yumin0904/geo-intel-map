# 8-C — 경쟁이론 편차 계산 (구현 핸드오프)

> 설계: Opus (2026-06-07). Phase 8 네 번째 사이클. 융합2 산술 레이어를 재사용.
> **목표**: 경쟁이론 "판정"을 Gemini 말 → Python 결정론 산출로. 정량 앵커 대비 실측 편차 계산.
> **측정**: 경쟁이론엄밀 3.33 → **4.0+**. 가드: 정직성(자의적 임계 금지), PASS 무회귀.

---

## 0. 대상 파일

- `backend/services/theory_comparator.py` — 정량 앵커 테이블 + 앵커 판정 함수 + 블록 주입
- `backend/api/intel_query.py` — [경쟁설명] 지침에 "앵커 판정은 context 제공값 인용" 추가
- (재사용) `backend/services/arithmetic_layer.py` — 융합2에서 만든 `delta`·`fmt_signed`·`concentration_label`
- 버전: 8.0.0 → 8.1.0

## 1. 진단 (왜 융합2로도 경쟁이론이 안 올랐나)

v7.11.0 eval: 경쟁이론엄밀 3.43 → 3.33 (미상승). 원인 둘:

1. **융합2가 계산한 건 "두 실측값 간 격차"**(TSMC↔SMIC 85%p)지, **"이론 예측 대비 실측 편차"가 아님.**
   심판이 보는 건 "예측 X vs 실측 Y, 편차 Z"인데 Z가 여전히 Gemini 말 판정.
2. **이론 프로파일에 예측 방향·임계값이 부호화 안 됨** — `falsifiable_prediction`이 자연어.
   "의존도 증가 시 양보 증가"의 방향(+)·임계(언제 '증가'로 보나)가 코드에 없어 판정 불가.

추가 제약: **DV(양보 빈도·정책 변화율 등) 실측 시계열이 대부분 없음.** IV만 있음(HHI·국방비·유가).
→ 이상적 IV→DV 회귀 편차는 불가. **현실적 8-C = IV 전제조건의 정량 충족도 + 임계 대비 편차.**

## 2. 설계 — 정량 앵커 + 결정론 판정

### 2-A. `_THEORY_ANCHORS` 테이블 (theory_comparator 모듈 레벨)

각 이론이 "적용 가능"하려면 실측 IV가 넘어야 할 **학술적으로 정당화된 임계값**을 부호화.
임계 근거를 주석으로 명시(자의적 임계 금지 — 정직성 가드).

```python
# theory_id → 정량 앵커. metric_key = 실측 dict에서 값을 꺼낼 키.
# direction "+": 실측이 threshold를 초과할수록 이론 전제 강하게 성립.
# 임계 근거는 표준 기준만 사용 (HHI 2500=美 DOJ 독과점, WGI 0=중립, Polity ±6 등).
_THEORY_ANCHORS: dict[str, dict] = {
    "energy_weaponized_interdependence": {
        "metric": "trade_hhi",  "threshold": 2500, "direction": "+",
        "unit": "", "anchor_label": "공급망 HHI 독과점 임계(美 DOJ 2500)",
        "interpret": "초과 → 비대칭 의존 구조 성립, Farrell&Newman 레버리지 예측 적용 가능",
    },
    "energy_resource_weaponization": {
        "metric": "eia_flow_mbpd", "threshold": 15.0, "direction": "+",
        "unit": "Mbpd", "anchor_label": "초크포인트 일일 통과량 임계(글로벌 원유 15%≈15Mbpd)",
        "interpret": "초과 → 차단 시 글로벌 충격 큼, 자원무기화 지렛대 성립",
    },
    "maritime_mahan_sea_power": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+",
        "unit": "%p", "anchor_label": "해군력(국방비%GDP) 우위 격차",
        "interpret": "양(+) → 해당국 SLOC 통제 우위, Mahan 예측 부합",
    },
    "indo_pacific_mearsheimer_offensive_realism": {
        "metric": "milex_gap_pp", "threshold": 0.0, "direction": "+",
        "unit": "%p", "anchor_label": "권력(국방비%GDP) 격차",
        "interpret": "격차 클수록 패권 추구 압력 — Mearsheimer 부합",
    },
    "indo_pacific_waltz_defensive_realism": {
        "metric": "polity_min", "threshold": 6, "direction": "+",
        "unit": "점", "anchor_label": "민주 임계(Polity +6, 민주평화론 경계)",
        "interpret": "행위자 모두 +6↑ → 현상유지 경향(Waltz), 미만이면 반례",
    },
    "gray_zone_gray_zone_strategy": {
        "metric": "wgi_pv_min", "threshold": 0.0, "direction": "-",
        "unit": "", "anchor_label": "정치안정 WGI 중립선(0)",
        "interpret": "음(-) → 거버넌스 공백, 회색지대 침투 전제 성립",
    },
    "gray_zone_hybrid_warfare": {
        "metric": "hiik_max", "threshold": 3, "direction": "+",
        "unit": "강도", "anchor_label": "HIIK 폭력위기 임계(3)",
        "interpret": "3↑ → 하이브리드전 활성, Hoffman 예측 부합",
    },
    "cyber_libicki_cyber_deterrence": {
        "metric": "itu_idi_min", "threshold": 70, "direction": "+",
        "unit": "IDI", "anchor_label": "ITU IDI 고역량 임계(70, proxy)",
        "interpret": "70↑ → 귀속·대응 역량 추정, Libicki 억지 성립 (※ IDI는 간접 proxy)",
    },
    "techno_digital_iron_curtain": {
        "metric": "semi_gap_pp", "threshold": 0.0, "direction": "+",
        "unit": "%p", "anchor_label": "TSMC↔SMIC 점유율 격차",
        "interpret": "격차 클수록 기술 분리·종속 심화 — 디지털 철의장막 부합",
    },
}
```

### 2-B. 실측값 → 앵커 metric 추출 (`_collect_anchor_metrics`)

build_theory_comparison_context가 이미 조회한 실측 dict(milex·trade_hhi·eia·wbk·polity5·
hiik·itu·semi)에서 앵커 metric_key에 해당하는 **단일 수치**를 뽑아 정규화:

```python
def _collect_anchor_metrics(milex, trade_hhi, eia, wbk, polity5, hiik, itu, semi) -> dict:
    m: dict[str, float] = {}
    # trade_hhi: HS 코드별 중 최대 HHI (가장 집중된 품목)
    if trade_hhi:
        m["trade_hhi"] = max((d.get("hhi_proxy", 0) for d in trade_hhi.values()), default=None)
    # eia: 최대 통과량
    if eia:
        m["eia_flow_mbpd"] = eia.get("flow_mbpd")
    # milex_gap_pp: 최상-최하 국방비 격차 (arithmetic_layer.pct_point_gap)
    vals = [v.get("gdp_pct") for v in milex.values() if v.get("gdp_pct") is not None]
    if len(vals) >= 2:
        m["milex_gap_pp"] = A.pct_point_gap(max(vals), min(vals))
    # polity_min: 행위자 중 최저 Polity (Waltz 민주 임계는 '모두' 넘어야 하므로 min)
    pv = [v.get("polity") for v in polity5.values() if v.get("polity") is not None]
    if pv: m["polity_min"] = min(pv)
    # wgi_pv_min: 최저 정치안정
    wv = [v.get("pv") for v in wbk.values() if v.get("pv") is not None]
    if wv: m["wgi_pv_min"] = min(wv)
    # hiik_max: 최고 분쟁 강도
    iv = [d.get("intensity") for d in hiik.values() if d.get("intensity") is not None]
    if iv: m["hiik_max"] = max(iv)
    # itu_idi_min, semi_gap_pp 동일 패턴 ...
    return m
```

### 2-C. 앵커 판정 함수 (`_anchor_verdict`) — Token-Zero 결정론

```python
def _anchor_verdict(theory_id: str, metrics: dict) -> str | None:
    """이론 앵커 임계 vs 실측 편차를 계산해 '판정' 라인을 결정론적으로 생성.
    DV 직접 측정이 아닌 IV 전제조건 충족도임을 라벨에 명시(정직성)."""
    anchor = _THEORY_ANCHORS.get(theory_id)
    if not anchor:
        return None
    val = metrics.get(anchor["metric"])
    if val is None:
        return None  # 실측 없으면 판정 생략 (억지 판정 금지)
    gap = A.delta(val, anchor["threshold"])          # 실측 - 임계
    direction = anchor["direction"]
    # 방향 부호화: + 이론은 gap>0이 충족, - 이론은 gap<0이 충족
    met = (gap > 0) if direction == "+" else (gap < 0)
    verdict = "전제 충족" if met else "전제 미충족"
    return (
        f"  앵커: {anchor['anchor_label']} | 실측 {val}{anchor['unit']} vs 임계 "
        f"{anchor['threshold']}{anchor['unit']} (편차 {A.fmt_signed(gap, anchor['unit'])}, 사전계산) "
        f"→ {verdict}: {anchor['interpret']}"
    )
```

### 2-D. 블록 주입 + 종합 판정

`build_theory_comparison_context`에서:
1. profiles 루프 직전 `metrics = _collect_anchor_metrics(...)` 1회 계산.
2. 각 이론 블록 끝에 `_anchor_verdict(tid, metrics)` 결과를 `empirical_lines`에 추가
   (None이면 생략).
3. **종합 판정(§비교 판정 요청)**: 두 이론의 앵커 편차를 Python이 직접 비교한 1줄 주입:
   ```
   ▶ 앵커 편차 비교 (사전계산): {이론A} 편차 {gapA} vs {이론B} 편차 {gapB}
     → 전제 충족도 우세: {gap 큰 쪽}
   ```
   Gemini는 이 줄을 [경쟁설명] ▶ 종합 판정에 인용.

### 2-E. intel_query 프롬프트 보강 (1줄)

[경쟁설명] 지침에 추가:
```
- '판정:'·'▶ 종합 판정:'에 context의 '앵커: ... (편차 X, 사전계산)' 값이 있으면 그 편차를 그대로 인용하라.
  앵커 편차는 IV 전제조건 충족도이지 DV 직접 측정이 아니므로, '전제 충족/미충족' 표현을 유지하라.
```

## 3. 정직성 가드 (필수 — 메모리 feedback_honesty_over_judge)

- **임계값은 표준 기준만**: HHI 2500(美 DOJ), WGI 0(중립선), Polity ±6(표준), HIIK 3(공식 정의).
  점수 올리려 자의적 임계 설정 금지. 근거를 anchor_label/주석에 명시.
- **DV 미측정 정직 표기**: 앵커는 IV 전제조건 충족도 → "전제 충족"이지 "이론 입증" 아님.
  라벨에 항상 명시. Gemini가 "이론 검증됨"으로 과장하지 않도록 프롬프트도 단속.
- **실측 없으면 판정 생략**(`_anchor_verdict` None) — 억지 판정으로 빈칸 채우기 금지.
- LLM 호출 0 (앵커 판정 전부 결정론, §14-A).

## 4. 범위 경계

- 8-C = IV 전제조건의 **임계 대비 편차 판정**. DV 실측 시계열 확보는 8-B/AR-1b 영역.
- 방향 부호화는 `_THEORY_ANCHORS`의 `direction` 필드로 최소 구현 (이론 프로파일 DB 스키마는 안 건드림 — 회귀 회피).

## 5. 검증 단계

1. import·문법 확인.
2. `_anchor_verdict` 단위 확인: taiwan_strait(weaponized_interdependence) → trade_hhi 17797 vs 2500
   → "편차 +15297, 전제 충족". sahel(gray_zone) → WGI 음수 → "전제 충족".
3. `build_theory_comparison_context("techno",["taiwan_strait"],["CHN","USA","KOR"])` 출력에
   "앵커: ... (편차 ..., 사전계산)" + "▶ 앵커 편차 비교" 라인 등장 확인.
4. **골드셋 eval**: `python tests/eval_insight.py --gold --judge --fast`
   - 목표: 경쟁이론엄밀 3.33 → 4.0+ (전체 평균 기준, 이상치 주의).
   - 가드: PASS ≥ 12/15, Type_B 무회귀(<15%), 비자명성 무회귀.
   - 정직성 점검: 심판이 "앵커 편차"를 엄밀성으로 인정하는지 vs 기계적 나열로 감점하는지 코멘트 확인.
5. 통과 시 progress.md `[8-C] ✅` + version.json 8.1.0 + 같은 커밋.

## 6. 완료 후 다음

8-B (Granger 방법론 강화 — 극단사건 P90 + 고빈도 종속 + 조건부 통제) 또는 8-D (문헌 공백 탐지).
