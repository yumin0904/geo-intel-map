# 헌법 부속서 (2026-07-12) — CLAUDE.md 이력 분리 2차

> 볼트 점검위(20260710-vault-maintenance) 이월 안건 "엔진 헌법 분할"의 완결 — 헌법분할위 07-12 설계.
> 규약: **순수 move — 자구 수정 0.** 구속력 있는 현행 규칙(Granger 가드·8-gate·2-레인 분리·가드 3종·
> 융합 아키텍처·삼각측량 가드·Phase 9 마스터표·시그니처표)은 헌법 잔류, 여기는 완료 서사·미착수
> 청사진·폐기 코드의 사료다. 선례: constitution_annex_20260710.md (1차 수술).

---

## ▣ §11 Phase 8 — 완료 게이트 상세 (2026-07-12 완료 선언으로 이력화)

**게이트(착수)**: Phase 7-D 핵심 데이터 적재 ✅ + v7.8.9 측정 완료 (Phase 8 게이트 충족 확인)

**완료 게이트 (박사 수준 선언 — 3조건, 2026-07-12 재정의 비준. 구 4조건 중 Type_B 폐기)**

> 〔2026-06-17 게이트 조정〕 LLM 심판 변동성(±0.2~0.3)·측정 노이즈 현실화. 기존 4.2/4.0은 단기 달성 불가 수준 → 현 최고치(종합 3.58·경쟁이론 3.53) 기준 한 사이클 stretch로 조정.

| 조건 | 현재(v7.8.9) | 목표 |
|------|-------------|------|
| LLM 심판 종합 | 3.68/5 | **3.8/5+** |
| 경쟁이론엄밀 | 3.43/5 | **3.6/5+** |
| ~~Type_B 비율(측정불가 H1)~~ | 41%→37.8% | ~~15% 미만~~ **폐기(07-12 비준)** — 조달 커버리지 report-only 관찰로 대체 |
| Granger | 0 유의 | **2건 유의(p<0.05) 또는 구조적 설명 승격** |

> ※ 구 8-E(비선형 검정 B안)는 **Phase 9 — 분석틀 다변화의 9-C로 이동**. 비선형 검정도
> "분석틀"이므로 Method Router 체계와 함께 다루는 게 일관됨.

**범위 결정**: GTD(20만건)·ACLED 전세계 확장은 **8-D에서 필요 시에만**. 8-A~C는 기존 적재 데이터로 점수 선확보 (블라인드 적재 회피).

---

## ▣ §11 Cycle 8-F 세부 — 음성 결과 분류·진단 엔진 (미착수 청사진 — services/negative_result_triage.py 부재 실측 07-12)

**철학**: 과학은 입증(verification)이 아니라 반증(falsification)으로 전진한다(Popper).
정직성은 "결론을 내는 능력"이 아니라 "무의미한 결과를 폐기하고 *왜 안 됐는지* 정직하게
다루는 능력"에서 나온다. 8-gate가 폐기의 *앞쪽 절반*(애초에 무의미한 검정을 안 함)이라면,
8-F는 *뒤쪽 절반*(이미 나온 음성 결과를 진단하고 다음 검증을 제안)이다.

**⚠️ 절대 안티패턴 (이 사이클의 존재 이유)**

```
❌ "무의미한 관계 → 폐기 → 유의가 나올 때까지 변수·시차·지역·대리쌍 자동 탐색 → 발견으로 보고"
   = Garden of forking paths / data dredging = p-해킹. 정직성을 높이는 게 아니라 파괴한다.
✅ "무의미한 관계 → 폐기 → 왜 안 됐는지 진단 → 다음에 무엇을 검증해야 하는지 *제안*(탐색형 라벨)"
```

핵심 원칙: **개선 제안은 *실행해서 보고하는 결과*가 아니라 *구조화된 진단 + 다음 검증 제안*이다.
자동 재검정해서 유의를 보고하지 않는다.**

**파이프라인 3단계**

1. **폐기** (이미 구현): 8-gate + `verifier.py` "[검정 비유의]" 정직 문구
2. **진단** (8-F 핵심 — Token-Zero 결정론): 비유의 4원인을 기존 spec 필드로 판별

   | 진단코드 | 원인 | 결정론 신호 (기존 필드) |
   |---------|------|----------------------|
   | `D4_INSUFFICIENT` | ④ 데이터 부족 | `n_obs` 낮음(<40) 또는 이벤트/시장 시계열 짧음 |
   | `D2_NONLINEAR` | ② 비선형 미포착 | 정규 `granger_p`≥0.15 **AND** `extreme_granger_p`<0.05 |
   | `D3_BAD_PROXY` | ③ 대리변수 오류 | `theory_grounded=False` (화이트리스트 밖 쌍) |
   | `D1_NO_RELATION` | ① 무관계(정직한 결론) | `n_obs` 충분 + `theory_grounded=True` + 정규·극단 모두 깨끗이 비유의(둘 다 p>0.3) |

3. **개선 제안** (탐색형, 라벨 필수): 진단코드별 다음 행동 제시 (자동 실행 금지)

   | 진단코드 | 개선 제안 | 연계 |
   |---------|----------|------|
   | `D4_INSUFFICIENT` | 데이터 적재 확장(지역 이벤트 시계열·lookback↑) | Phase 6-A / 7-D |
   | `D2_NONLINEAR` | 적극적 비선형 검정(임계회귀·체제전환) | 8-E |
   | `D3_BAD_PROXY` | 더 나은 대리변수 또는 직접 DV(hand-coding) | `proxy_suggestions` / Phase 7-D(annex §20-C) |
   | `D1_NO_RELATION` | **관계 없음이 정직한 결론** — 경쟁 이론·구조적 설명으로 전환 (그 자체가 정보) | §19-B-2 ③ 문헌공백 |

**데이터 모델**: `HypothesisSpec`에 추가
```python
diagnosis_code: str | None = None        # D1_NO_RELATION / D2_NONLINEAR / D3_BAD_PROXY / D4_INSUFFICIENT
diagnosis_reason: str = ""               # 결정론 신호 근거
improvement_directive: str = ""          # 다음 검증 제안 (실행 아님)
exploratory: bool = False                # 탐색형이면 True — 확증 등급 승격 금지
```

**구현 파일**: `services/negative_result_triage.py`(신규) · `hypothesis_verifier.py`(검정 후 triage 호출) ·
`api/intel_query.py`(SSE 4필드) · `eval_insight.py`(진단율·누출 채점)

**평가 기준**
- 음성 결과(PENDING/비유의)에 `diagnosis_code` 부여율 **100%**
- 진단 정확도: 골드셋 수동 라벨과 일치율 (목표 80%+)
- **탐색형 결과가 확증(선행성/등급)으로 새는 케이스 0** (회귀 테스트 필수)

**게이트**: 8-gate(v8.12.0) 완료 ✅ → 착수 가능. 8-E와 독립(8-F는 진단·제안, 8-E는 실제 비선형 검정).

---

## ▣ §11 Cycle 9-P 세부 — 토대 수리 (마스터표 행이 현행 상태의 원천 — 여기는 결함 상세)

라우터·게이트의 판정 정확도가 이 4종에 달려 있으므로 9-0보다 **먼저** 처리한다.

| 항목 | 결함 | 수정 | 비고 |
|------|------|------|------|
| 9-P-1 | **H1 추출 버그** (DV 미식별, 두 가설 동일결과 붕괴) | `_RE_WHEN_THEN` 강화 + DV 미식별 폴백 + Granger 캐시 중복키 분리 | 게이트·라우터 토대 — **최우선** |
| 9-P-2 | **진단 독립성(L3)** | `theory_grounded` 단일실패점 분리(D3·등급 공유 해소) + `n_obs<40` 등 매직넘버 config화(§10) | 8-F 진단 정합 |
| 9-P-3 | **방법 오선택(L2)** | 라우터 판정 근거 로깅 + 라우팅 신뢰도/대안 플래그 → "성공해도 틀린 방법" 사후 점검 훅 | 9-0에 내장 |
| 9-P-4 | **출력 2계층화(O2)** | 표면(한 줄 결론 + 신뢰 한 단어) / 펼침(전체 진단·caveat) SSE·프론트 계약 | §0 비전공자 판독성 |

---

## ▣ §11 Cycle 9-0 세부 — MethodResult 공통 스키마 (구현 완료: services/methods/router.py·grader.py)

현재 1층 `_classify_inference_grade(p_value, theory_grounded, controlled)`는 시그니처부터 Granger
전용이고 '준실험' 칸은 미구현(기술적/상관/선행성만 존재). 방법이 늘면 각 방법의 통계량(CAAR·t값·
placebo-p)이 비교 불가가 된다. → **2계층 설계: 공통 사다리 계약(통합) + 방법별 얇은 어댑터(독자).**

원칙: **사다리 칸은 "식별전략 강도"라 방법 무관 공통 축이다.** 각 방법은 공통 결과 스키마를 구현한다:
```python
class MethodResult:
    method: str                 # "granger" | "event_study" | "synth_control" ...
    effect_estimate: float      # 방법 핵심 추정치 (CAAR/coef/gap)
    effect_size_label: str      # [②] 실질 유의성 — '무시(<임계)/작음/중간/큼' (significance와 분리)
    significance: float         # 방법 유의지표 (p/placebo-p/t)
    ci_low: float; ci_high: float  # [③] 불확실성 구간 (bootstrap/posterior) — 점추정 대신 구간
    reachable_rung: str         # 가정 충족 시 도달 가능 칸
    assumptions_met: bool       # 방법 고유 가정 자가검증 ← 정직성 핵심
    assumption_caveat: str
    robustness: dict            # [④] 내부 강건성 — 윈도우·이상치·대체프록시 민감도 결과
    confidence_within_rung: int
```
일반화된 grader: ① `assumptions_met=True`인 방법 중 **가장 강한 reachable_rung** 선택 →
② 삼각측량(수렴=신뢰도↑·발산=플래그)+FDR → ③ 신뢰도 캡(§20-B 일반화). 기존 Granger 로직은 첫 어댑터.

**[②③④ 흡수 — 결과 보고 3차원] grader/어댑터는 "유의/비유의"만이 아니라 셋을 함께 보고한다:**
- **② 효과 크기**: 통계적 유의 ≠ 실질 중요. magnitude를 실질 임계와 비교해 '무시할 수준'이면 명시
  (예: p<0.05여도 유가 0.1% 변동이면 '유의하나 실질 무시'). Token-Zero 산술.
- **③ 불확실성 구간**: 점추정+ad-hoc 0–100 → bootstrap/posterior **CI**로 보고 (`MethodResult.ci_*`).
- **④ 내부 강건성**: 윈도우 변경·이상치 제거·대체 프록시 민감도(within-method). 삼각측량(between-method)과 보완.
  결론이 perturbation에 뒤집히면 등급 강등. 각 9-A~E 어댑터가 자기 robustness 점검을 구현.

---

## ▣ §20-B 신뢰도 상한 캡 — 폐기 코드블록 (코드 DEPRECATED, confidence_scorer.py 2축 분리로 대체)

```python
if verification_status == "PENDING":   confidence_score = min(confidence_score, 75)
if verification_status == "PARTIAL":   confidence_score = min(confidence_score, 88)
if verification_status == "VERIFIED":  # 상한 없음 — Granger p<0.05 자동 충족 시
```
