# 8-A — H1 측정가능성 강제 (구현 핸드오프)

> 설계+구현: Opus (2026-06-07). Phase 8 세 번째 사이클.
> **목표**: H1 종속변수를 "검증 가능한 변수 메뉴"에서만 고르게 강제 → Type_B(검정 불가) 41% → <15%.
> **측정**: `eval_insight.py --gold` Type_B 비율. 가드: PASS율 무회귀, 정직성(억지 Type_A 전환 금지).

---

## 0. 대상 파일

- **신규** `backend/config/measurable_variables.yaml` — 검증 가능 변수 단일 카탈로그
- `backend/services/hypothesis_extractor.py` — 메뉴 로더 + `_classify_variable_type` 측정가능 우선
- `backend/api/intel_query.py` — H1 규칙에 측정가능 메뉴 주입
- 버전: 7.10.0 → 7.11.0

## 1. 진단 (왜 Type_B가 41%인가)

`verify_hypotheses`에서 **Type_B는 유일하게 검정 경로가 없다**(verifier L376-395):
`actor_filter event study 미구현` → 항상 PENDING → 사다리 '기술적' 고착, Granger 0 기여.

Type_B가 41%로 솟는 두 원인:
1. **Gemini가 "분쟁 건수·도발 빈도"류를 종속변수로 자주 생성** (Type_B 키워드 `건수·빈도·공격` 매칭).
2. **`_classify_variable_type`이 Type_C 키워드를 최우선 판별**(L89): "유가 의존도"처럼 측정
   가능(유가→CL=F)인데 추상 키워드(의존도)가 섞이면 Type_C로 오분류돼 죽음.

→ Type_A(검정됨)·Type_C(ACLED 경로 검정됨)와 달리 Type_B만 죽은 분류.

## 2. 설계 — 공급·수요 양면

### 2-A. `measurable_variables.yaml` (단일 카탈로그)

기존 `_TICKER_MAP`(extractor)·`_REGION_DEFAULT_TICKER`(verifier)와 **내용 정합**.
프롬프트 메뉴 생성 + (보조) 분류에 공유. 매직값 하드코딩 회피(§7).

```yaml
market_indicators:        # Type_A — ticker 직결, 종속변수로 즉시 검정 가능
  - {name: "WTI 유가",  unit: "USD/배럴", ticker: "CL=F", aliases: [wti, 원유, 유가, crude, oil]}
  - {name: "Brent 유가", unit: "USD/배럴", ticker: "BZ=F", aliases: [brent, 브렌트]}
  - ... (NG=F, TSM, SOXX, ITA, GLD, KRW=X, TWD=X, CNY=X, JPY=X, ZW=F)
conflict_series:          # ACLED 지역 분쟁 건수 — 독립변수(X) 권장
  note: "종속변수로 쓸 땐 반드시 다른 지역 명시 → 사건→사건 경로로만 검정 가능"
  regions: [eastern_europe, taiwan_strait, hormuz, korean_peninsula, ...]
```

### 2-B. extractor — 측정가능 우선 분류 (수요 측 버그픽스)

`_classify_variable_type` 맨 앞에 **ticker 매칭 우선** 단계 추가:

```python
def _classify_variable_type(dependent_var):
    text = dependent_var.lower()
    # [8-A] 측정 가능 우선: 종속변수가 시장 지표로 매핑되면 Type_A.
    #   Type_C/B 키워드가 섞여 있어도(예: '유가 의존도'의 '유가') 검정 가능하므로 구제.
    if _match_ticker(text):
        return "Type_A", []
    # ... 이하 기존 Type_C → Type_B → Type_A 순
```

> 정직성 가드: 이건 "측정 가능한 변수를 측정 가능으로 본다"는 것이지, 측정 불가 변수를
> 억지로 Type_A로 만드는 게 아니다. `_match_ticker` 실패하면 그대로 Type_C/B 유지.

`build_measurable_menu() -> str` 신설: yaml → 프롬프트용 메뉴 텍스트 생성 (단일 소스).

### 2-C. intel_query — 프롬프트에 메뉴 주입 (공급 측 핵심)

`## H1 가설 작성 규칙` 섹션에 측정가능 메뉴 + 강제 선택 지침 추가:

```
★ [8-A 측정가능성 강제] H1의 종속변수 Y는 아래 [측정 가능 변수 메뉴]에서 선택하라.
   메뉴 밖 변수(도발 빈도·억지 의지·역량·신뢰성 등 추상/행동 변수)를 Y로 쓰면 검정 불가다.
   적합한 측정가능 Y가 없으면 솔직히 '[가설] 현 데이터로 검증 가능한 정량 가설 없음'으로 표기하라
   (억지로 무관한 시장지표를 갖다 붙이지 말 것 — 정직성 > 검정율).
   [측정 가능 변수 메뉴]
   {build_measurable_menu()}
```

## 3. 범위 경계

- 8-A = **Type_B 발생 억제**(프롬프트) + 오분류 구제(extractor). 새 검정 경로는 안 만든다.
- "건수→시장" 같은 신규 Granger 경로는 **8-B**(Granger 방법론 강화). 본 사이클 밖.

## 4. 정직성 가드 (필수)

- 측정가능 메뉴 강제가 **무관 변수 끼워맞추기**로 변질 금지 → "없으면 가설 없음" 명시.
- `_match_ticker` 실패 변수는 Type_C/B 유지 (억지 Type_A 금지).
- LLM 호출 0 (extractor·메뉴생성 전부 결정론적, §14-A).

## 5. 검증 단계

1. import·yaml 파싱 확인.
2. `_classify_variable_type("유가 의존도")` → Type_A (구 Type_C에서 구제 확인).
   `_classify_variable_type("억지 의지")` → Type_C 유지. `_classify_variable_type("도발 건수")` → Type_B 유지.
3. `build_measurable_menu()` 텍스트 육안 확인 (메뉴 누락·중복 없음).
4. **골드셋 eval**: `python backend/eval_insight.py --gold --judge --fast`
   - 목표: Type_B 비율 41% → <15%. 가드: PASS ≥ 12/15, 경쟁이론 수치비교 무회귀.
   - 정직성 점검: '정량 가설 없음' 증가가 환각 감소인지(↑정상) vs 회피인지 심판 코멘트 확인.
5. 통과 시 progress.md `[8-A] ✅` + version.json 7.11.0 + 같은 커밋.

## 6. 완료 후 다음

8-C (경쟁이론 편차 계산 — 산술 레이어 재사용) 또는 8-B (Granger 방법론 강화).
