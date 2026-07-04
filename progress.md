# 개발 진행 기록

## ★★ Phase 9 — 분석틀 다변화 (2026-06-17 진입) — 현재 목표

> **Phase 8 → 9 전환 (2026-06-17)**: 게이트 조건 현실화(LLM 3.8+·경쟁이론 3.6+) + 9-P 토대 수리(9-P-1~4) 완료를 기점으로 공식 Phase 9 진입. v9.0.0.

---

## 📐 Phase 9-Q (가칭) — 질적 방법 갈래 + 인식론 모드 분리 (설계, 2026-06-18)

> **상태**: 설계·계획 단계 (코드 미착수). 지도교수 피드백 기반 방법론 검토에서 도출.
> Phase 번호(9-Q vs 별도 Phase)는 추후 확정. 정량 다변화(9-A~E)와 **직교하는 축**(질적·인식론).

### 0. 배경 — 방법론 자기검토에서 발견한 절차적 결함 3종

지도교수 피드백 2개("정량이 어려우면 질적으로 / 최종 해석은 연구자 본인이")를 기준으로
엔진의 추론 절차를 사회과학 연구방법론에 비추어 점검한 결과:

| # | 결함 | 방법론 위반 | 코드 근거 (확인됨) |
|---|------|-----------|------------------|
| P1 | **HARKing** — 데이터 조회 *후* Gemini가 가설 생성 → 같은 데이터로 검정 | 사후가설(post-hoc)·텍사스 명사수 오류. 탐색을 확증으로 위장 | `intel_query.py` full_text→추출→검증 순서 |
| P2 | **해석 주체 전도** — LLM이 `▶ 종합 판정`·`[비자명기여]`까지 단정 | "최종 해석은 연구자 본인" 위반. 학생이 해석 노동을 안 함(학습 저해) | 프롬프트가 종합 판정 생성 |
| P3 | **질적 방법 부재** — UNQUANTIFIABLE(eval 18케 중 9개=50%)이 막다른 길 | 질적 전통(과정추적·구조적초점비교·일치법) 전무. `structural_arg`는 "검정 보류" 선언일 뿐, 가리키는 대안(9-C)도 여전히 정량 | `base.py:46` UNQUANTIFIABLE→`["structural_arg"]`, `hypothesis_verifier.py:555-563` 거절만 |

> ※ P-추가(통제변수 임의성): "이론근거 필수 텍스트필드"는 LLM이 그럴듯한 헛소리로 채우는 **'엄밀성 연극'** 위험 +
> 충돌변수(collider)·매개변수 통제는 오히려 편의 유발 → 인과구조(DAG) 없이는 보류. 이번 범위 제외.

### 1. 핵심 원칙 — Token-Zero를 "해석"으로 확장

> 기존 Token-Zero: "**산술**은 LLM 말고 Python이." → 확장: "**해석(최종 판정)**도 LLM 말고 연구자가."

AI는 **증거를 모으고 구조화하는 조수**까지만. 판결은 사람이. 이 한 원칙이 P2·P3를 동시에 푼다.
교수 피드백 2개와 정확히 일치하며, CLAUDE.md §0 "추론하는 지도"의 학습 목적과도 부합.

### 2. 구조적 분리 — 두 직교 축 (독립 기능)

```
                정량(quantitative)        질적(qualitative)
  확증(가설검정) │ 9-A~E (거의 구축)      │ 과정추적(가설검정용) ❌신규
  탐색(가설생성) │ 현재 사실상 여기(◐)   │ 근거이론·귀추 ❌신규
```
- **축 A (인식론 모드, 진입 시점 결정)**: 확증(사용자가 H1·통제변수 *데이터 보기 전* 선언 → 검정만) vs 탐색(현 흐름, `[탐색적]` 라벨 강제·등급 상한 '상관').
- **축 B (방법 갈래)**: 정량(기존 Method Router) vs 질적(신규, UNQUANTIFIABLE이 여기로).

### 3. 우선순위 개선 3종

| 순위 | 항목 | 내용 | 비용/가치 |
|------|------|------|----------|
| 1 | **해석 주체 이전** | `▶ 종합 판정`을 엔진이 단정 ❌ → 이론예측 vs 실측 병치만, 판정은 사용자. Gemini 의견은 `[참고]`로 강등 | 저비용·고가치 (P2 직격) |
| 2 | **탐색/확증 라벨** | 데이터→가설 출력 전체에 `[탐색적]` 도장 + 등급 상한 '상관' (8-F 2-레인 개념을 진입 시점으로) | 중비용 (P1) |
| 3 | **질적 갈래 골격** | UNQUANTIFIABLE을 "거절"→"과정추적 테스트 틀(Van Evera 4검정) + 증거 배치 + **판정은 사용자**". 학생을 방치 않게 **유도질문 스캐폴딩**(내비게이션식) | 고비용·최고가치 (P3) |

> ⚠️ **질적 p-해킹 방어 (사활)**: LLM에 과정추적 서사를 쓰게 하면 가짜 엄밀성 양산 → 정량 p-해킹보다 나쁨.
> 방어 = §1 원칙(틀·증거는 엔진, 판정은 사람) + 스캐폴딩은 *유도질문*이지 *정답*이 아님.

### 4. 연구 범위 결정 — 사례 선정(case selection)으로 4영역 집중

질적(과정추적)은 본질상 "적은 사례를 깊게"(intensive design) → 데이터 풍부 영역으로 한정이 **방법론적 정답**(타협 아님).
**정량 갈래는 넓게 유지**, 질적 갈래만 범위 한정.

| 영역 | 분쟁 질문(정량·넓게) | 비분쟁 질문(질적/구조데이터) | 사건 증거량(ACLED) |
|------|-------------------|---------------------------|------------------|
| 동유럽(러-우) | 에너지 인프라 공격 전이 | 에너지 무기화·지원금(Kiel) | 105,587 ✅ |
| 중동해양(호르무즈·홍해) | 봉쇄→유가, 분쟁 전이 | 자원 무기화 | 52,746+7,953 ✅ |
| 인도태평양(대만) | — | 반도체 집중도, A2/AD | 1,152 ◐(이론 20개로 보완) |
| **한반도(신규)** | 북한 도발 패턴 | **동맹 신뢰·확장억제·핵** ← 질적 핵심 시험대 | 4,705+3,214 ◐ |

> 한반도 추가 이유: ① 사용자 학습 동기 최상 ② 핵심 질문 대부분이 *비정량* → 질적 갈래를 제대로 만들게 **강제**(분쟁 데이터 편법 차단). 정량 데이터(SIPRI 한·북·미·중·일 각 5년, COW 동맹 43건, 확장억제 이론) 보유.

### 5. 분쟁 데이터 편향 가드 ("가로등 효과")

**확인된 사실**: 영구 사건 증거 = **100% ACLED 분쟁**(290k 전부 source_type=conflict). GDELT/RSS는 휴발성(3일 TTL)이라 과거 증거 불가.
구조화 데이터(군사비·에너지·무역 6607행·거버넌스·시장)는 다양 → 정량은 편향 아님. **사건 레이어만** 편향.

- ❌ "분쟁 특화 엔진"으로 좁히기 = 에너지·기술·사이버·동맹(프로젝트 절반) 절단 + 다양한 구조데이터 폐기.
- ✅ **원칙**: "질문에 맞는 증거를 쓰고, 비분쟁 질문을 억지로 분쟁 건수로 바꾸지 마라." (8-gate "대리지표 강제 금지" 철학 확장 — **분쟁 건수도 억지 대리지표가 될 수 있다**).

### 6. 데이터 전략 — GDELT 폐기, 1차 사료 채택

- **GDELT 폐기**: 자동코딩 노이즈(오탐·중복·지오코딩 오류) → 과정추적엔 독. (사용자 판단, 방법론적 정당)
- **1차 사료 채택**: 외교부 보도자료 등 공식 기록 = 역사학/질적 연구의 표준 증거. §19-D도 1차 사료 +20점.
  질적은 "많은 데이터"가 아니라 "맞는 데이터" → 적은 양이 단점 아님(intensive design과 합치).
- **외교부/공공데이터포털 조사 결과 (2026-06-18 확인)**:

  | 데이터 | 형태 | 적합성 |
  |--------|------|-------|
  | 외교부 보도자료 (data.go.kr 15141564) | OpenAPI JSON/XML, 무료, 자동승인, 1만req/일, 실시간 | ✅ **최적** (제목·내용(HTML)·첨부·작성부서) |
  | 외교부 양자조약 (15099238) / 조약정보시스템(treatyweb.mofa.go.kr) | 파일·웹 | ✅ 체결/발효일 타임라인 앵커 |
  | 국가·지역별 주요인사교류 (15076260) | OpenAPI(?) | ◐ 현재 페이지 404 — **확인 필요** |
  | KOICA 개발협력동향 / 외교부 LOD | OpenAPI/LOD | ◐ 경제차원/형식 까다로움 |

- **아키텍처 적합**: 손수 검증한 사건 아카이브 = CLAUDE.md §6.4 **Case Study Library** + 정적 큐레이션 패턴(군사기지·제재·이론 md)과 동일. 노이즈 0(사람 검증).
- **정직성 가드**: 손수 큐레이션 = 체리피킹 위험(질적 p-해킹) → 과정추적 틀이 **경쟁가설 증거 + 반증 증거도 강제** 수집.
- **착수 전 검증 3종**: ① 보도자료 API **과거 아카이브 깊이**(2022까지 있나 — 키 발급 후 호출 확인 필수) ② HTML 태그 정리 ③ 한국 시점만 → 미 국무부·UN으로 균형 보강.

### 7. 다음 행동 (한 번에 1개씩)

> ⚠️ **이 절은 2026-06-18 작성 — 1~3은 그 직후 6/19~21 작업에서 이미 완료됨(아래 갱신 참조).**

1. ~~**(사용자)** 보도자료 API 키 발급~~ → ✅ **완료**: `MOFA_API_KEY` 발급·설정됨.
2. ~~**(Claude)** 키 수령 후 탐색 → 과거 깊이·한반도 충분량 확인~~ → ✅ **완료**(2026-06-30 확인):
   `mofa_press_releases` **22,410건**, 기간 **2000-01-01 ~ 2026-05-20(26년)**, 한반도·동맹 풍부
   (북한 3,483 · 핵 5,227 · 동맹 1,176 · 한미 1,861 · 확장억제 100 · 워싱턴선언 22 · NCG 16).
3. ~~정식 적재 + 질적 갈래 착수~~ → ✅ **완료**: mofa_press 커넥터 적재(v9.10.1) + 과정추적 scaffold 구축·구조검증 8/8(v9.11.0).
4. ✅ **완료**: 우선순위 1·2(해석 주체 이전·탐색/확증 라벨) — v9.14.0~9.15.2, 라이브 6케이스 검증.

> **질적 갈래 라이브 검증(2026-07-01 갱신 — v9.17.0)**: ✅ 라이브 확인 완료. 단 확인 과정에서
> **라우터 순서 역전 결함**을 발견·수정함(아래 v9.17.0 로그). 이론 판별형 UNQUANTIFIABLE 케이스가
> 라이브에서 Granger로 탈선하던 것을 쿼리-우선 라우팅으로 고쳐 `pla_taiwan_a2ad` 라이브에서
> 과정추적 scaffold(Van Evera 4검정 + DB 증거배치) 발동을 확인. **잔여**: ~~비-판별형 UNQUANTIFIABLE~~
> → ✅ **v9.17.1에서 해석형(mechanism/attribution/gap)까지 확장** — `china_cyber_us`·
> `india_indo_pacific_balancing`·`salt_typhoon` 포착(아래 로그). Gemini 본문 라이브(429 회복 시)는 선택 확인.

> CLAUDE.md 정식 스펙 등재(§ Phase 로드맵)는 방향 확정 후 별도 진행.

---

### ✅ LOW 라우팅 의심 5건 해소 — 선언문 단락 + 방법 미구현 정직 마킹 (v9.18.2, 2026-07-04)

- 진단(eval 20260704_0130 실측): LOW 6가설(5케이스)은 **라우팅 오선택이 아니라 두 구조 문제**였음.
  ① `'검증 가능한 정량 가설 없음'` 선언문이 Type_A/C로 분류돼 검정 경로로 낙하 — 최악의 경우
  섹터 proxy Granger에서 **PARTIAL p=0.0 획득**(china_rareearth: "가설 없음"이 유의 결과로 세탁될 뻔).
  ② SINGLE_SHOCK·CROSS_SECTION 시그니처(9-A/9-B 대상)가 미구현이라 티커 경로로 낙하 후
  매핑 실패 → LOW. **시그니처 판정 자체는 5건 모두 옳았음**.
- 수정(`hypothesis_verifier.py`):
  - 선언문 단락 가드 신설(`_is_no_hypothesis_declaration` + `_ROUTE_NO_HYPOTHESIS`) — 8-gate 직후
    단락, 어떤 검정 경로에도 진입 금지. rc=HIGH(선언 판정은 명확 — UNQUANTIFIABLE 제외 규칙과 동일 논리).
  - Type_A 매핑 실패 분기에서 시그니처가 SINGLE_SHOCK/CROSS_SECTION이면
    `_ROUTE_PENDING_METHOD`(방법 미구현) rc=HIGH로 마킹 — Type_B PENDING과 동일 패턴.
    "티커 Granger로 대체하지 않음(방법 오선택 방지)" caveat 명시.
  - `_route_explanation`에 [가설없음]·[방법대기] 표면 문구 추가.
- 검증(eval 실측 데이터 52가설 대상 시뮬레이션): 표적 LOW 5건 전부 해소 · 오탐 0 ·
  선언문 총 9건이 검정 진입 전 차단(taiwan_semiconductor 등 MEDIUM/HIGH로 새던 것 포함).
- 검증포인트(다음 eval 사이클): 33케이스 재실행 시 routing_low 0건 + laundering 0 유지 확인.
  선언문 케이스들의 PARTIAL→PENDING 전환으로 confidence 소폭 변동 가능(정직한 방향).

### ✅ un_news 커넥터 파싱 실패 진단·재시도 보강 (v9.18.1, 2026-07-04)

- 배경: 01:32 자동 수집에서 `not well-formed (invalid token): line 1, column 0` — 응답이 XML이
  아니었으나(오류 페이지 또는 CDN 임의 gzip 추정) 본문 기록이 없어 원인 확정 불가. 09:15 실행은 정상(30건).
- 수정(`connectors/un_news_connector.py` `_fetch_rss`): ① `Accept-Encoding: identity` 명시 +
  gzip 매직 바이트(1f 8b) 감지 시 해제 ② 파싱 실패 시 Content-Type·응답 앞 100B 로깅(사후 진단 가능)
  ③ 3초 후 1회 재시도(일시적 소스 이상 흡수). LLM 무관(Token-Zero 영향 없음).
- 검증: `--test` 실행 → 30건 수신, 지역 태깅 정상.

### ✅ 라이브 33케이스 eval 재측정 + 데이터 수집 자동화 (v9.18.0, 2026-07-04)

**A. eval 재측정 (Gemini 429 회복 확인 후)** — v9.14~9.17 변경분의 라이브 검증 완료.
- **33/33 PASS** (직전 성공 v9.10.9의 32/33 상회) · 평균 신뢰도 **92.1/100** · 오류 0
- 방법론 정직성: **시그니처 라우팅 15/15 (100%)** · laundering 0 · 탐색→확증 누출 0 · 확증 라벨 위반 0
- 달성 칸 분포: 기술적 48 · 상관 3 · 준실험 1 | verification: VERIFIED 2 · PARTIAL 4 · PENDING 46
- ~~남은 관찰: **LOW 라우팅 의심 5건**(폴백·대리쌍 경로 오선택 — 갈륨→ITA, NATO 방위비 등)~~ → ✅ v9.18.2에서 해소 (선언문 단락 + 방법 미구현 마킹)
- 결과: `tests/eval_results/20260704_0130.json`

**B. 데이터 수집 자동화 (launchd 단독 러너)** — 수집 공백 재발 방지.
- 배경(실측): 스케줄러가 서버 프로세스 안에서만 돌아 2026-06-21~07-04 약 2주 수집 공백 발생
  (GDELT TTL 3일 → 해당 기간 실시간 축 영구 손실. ACLED 29만건 축은 무손상).
- `jobs/collect_standalone.py` 신설: 서버 없이 수집 8종 1회전(gdelt·firms·프레스 4종·아카이브 사이클·
  **예측 만기 채점**). 부분 실패 허용, LLM 호출 없음(Token-Zero).
- launchd `com.geo-intel.collect` — 매일 09:00·21:00, Mac이 잠자던 분은 기상 시 보충 실행.
  플리스트 원본: `backend/ops/com.geo-intel.collect.plist` (재설치: `launchctl bootstrap gui/$(id -u) <plist>`).
  로그: `backend/logs/collect_launchd.log`.
- 검증: kickstart 실행 → **성공 8/실패 0 (42.3s)**, GDELT Stage 1 통과 8건, 아카이브 사이클 정상.
- ~~⚠️ 발견: un_news 커넥터 XML 파싱 경고(소스 응답 이상 추정, 0건 처리)~~ → ✅ v9.18.1에서 진단·재시도 보강.
- 효과: 예측 로그 78건(PENDING)의 7월 만기분이 **자동 채점**됨 — Phase 10-2 실가동 조건 충족.

### ✅ 9-Q 쿼리-우선 라우팅 — 이론 판별 질문의 Granger 탈선 수정 (v9.17.0, 2026-07-01)

**발단**: 질적 갈래 라이브 검증(A작업)에서 `pla_taiwan_a2ad`(마한 vs 미어샤이머)를 로컬 Ollama(3b·7b)로
실호출하니 과정추적 scaffold가 **안 켜지고 Granger로 탈선**(`data_signature=PAIRED_TIMESERIES`,
taiwan→TSM p=0.82 비유의). 3회(대만 3b·7b·북극 3b) 일관 재현.

**진단(사회과학 방법론 검토)**: 단일 버그가 아니라 **추론 절차의 순서 역전**.
- 올바른 순서: `질문의 논리 형태 → 방법 선택 → 조작화`. 실제 구현: `LLM이 정량 H1 날조 + ticker 자동배정 → 그 H1로 방법 분류`. **조작화가 방법 선택을 오염**(law of the instrument).
- "마한 vs 미어샤이머"는 **이론 판별(theory adjudication)** 질문 — 두 이론이 같은 관측치를 예측(**관측적 동등성**)하므로 공변(Granger) 검정은 판별력 0. Granger 자체가 부적합.
- 7b는 깨끗한 한국어 H1을 냈어도 프롬프트(§20-A "X 증가 시 Y")가 **정량 H1로 유도** + extractor가 `ticker=TSM/CL=F` 자동배정 → PAIRED로 분류. 모델 품질 문제 아니라 **구조**.
- v9.11.0 "8/8 구조 PASS"는 `linear_testable=False`를 **직접 주입**(extractor 우회)해 이 라이브 갭을 못 잡았음 — 처치 전달만 검증, **배정 기제 미검증**.

**수정(쿼리-우선 라우팅)**: 방법을 조작화 *이전*, 원본 쿼리에서 결정.
- `services/methods/router.py`: `is_theory_adjudication(query)` 신설(명명 이론 2개가 '와/과'로 병치 + 비교/판별 요구, 정량 오버라이드 `수치로|어느 변수|시계열|패널|HHI…`로 함정 제외). `classify_signature`가 이를 최우선 검사 → UNQUANTIFIABLE 직행.
- `services/hypothesis_verifier.py`: 검증 루프 최상단에서 `source_query`가 판별형이면 `spec.linear_testable=False` veto → 레거시(→structural)·Method Router(→process_tracing) **공유 레버** 동시 적용. **H1 오염에 견고**(veto는 깨끗한 쿼리에서 작동).
- `tests/test_query_first_routing.py` 신설 — 33개 쿼리 날것으로 라우팅 결정 검증(검토의 "배정 기제 테스트" 교훈).

**검증**: ① 결정론 33쿼리: 목표 3건(`pla_taiwan_a2ad`·`russia_china_arctic_control`·`mearsheimer_vs_liberal_taiwan`) 정확 적중, 오탐 0(`taiwan_liberal_vs_realist` CROSS_SECTION은 "수치로 검증"으로 정상 제외). ② e2e(정량 H1 재현): `linear_testable`→False·`structural_arg`·UNQUANTIFIABLE·process_tracing 확인. ③ **라이브(3b, 서버)**: 3b가 H1을 중국어 환각해도 veto가 쿼리에서 작동 → `[탐색적] [과정추적] … Van Evera 4검정 스캐폴딩 (판정은 연구자)` + 후프7·흡연총7·밀짚5·이중결정8건 증거배치.

**남은 것**: ① ~~비-판별형 UNQUANTIFIABLE 감지~~ → v9.17.1 완료. ② Gemini 라이브 본문 서술(429 회복 시 선택). ③ 라이브 33케이스 eval 재측정 시 라우팅 일치율 개선 확인.

---

### ✅ 9-Q 쿼리-우선 라우팅 — 해석형(mechanism·attribution·gap) 확장 (v9.17.1, 2026-07-01)

**목적**: v9.17.0(이론 판별형)에 이어, 비-판별형 UNQUANTIFIABLE 3종을 쿼리-우선으로 포착.
이들은 **측정 도구가 없는 결과를 '왜/어떻게'로 묻는 해석형 질문** — 이론 판별과 같은 이유(공변검정 부적합)로 과정추적 대상인데, 판별 신호가 각기 다름:
- `china_cyber_us`: "방어 역량 **공백**" (측정불가 gap)
- `salt_typhoon`: "억지에 **실패한 이유**" (귀속/attribution)
- `india`: "동맹 딜레마를 **어떻게 회피하는지**" (메커니즘)

**수정**: `router.py`에 `_RE_INTERPRETIVE`(실패한 이유·어떻게 ~하는지·역량 공백) + `unquantifiable_question_reason()` 통합 진입점 신설(이론판별 OR 해석형, 사유 문자열 반환). `classify_signature`·`hypothesis_verifier` veto를 통합 함수로 전환. 정량 오버라이드 강화(`미치는 영향|지수(WGI·HIIK)` 추가)로 함정 차단.

**검증**: ① 결정론 33쿼리 회귀 테스트 확장(목표 6건=판별3+해석3 적중, 오탐 0 — `taiwan_liberal_vs_realist`·`sahel`·`hormuz` 등 정량 유지). ② e2e(india, 정량 H1 "10%→5%" 재현): veto→`linear_testable=False`→`structural_arg`→UNQUANTIFIABLE→process_tracing 확인. ③ 부수 포착 `ukraine_drone_innovation`("드론이 이론을 어떻게 바꾸는지") — expected='—'이고 실제 해석형이라 정당.

**한계(정직)**: 감지가 키워드-프레이즈 기반이라 재작성된 질문(예: "억지가 왜 안 통했나")은 놓칠 수 있음 — 기존 라우터 키워드 체계(SINGLE_SHOCK·NETWORK 등)와 동일 수준. 근본 일반화(측정불가 DV의 쿼리-우선 게이트)는 추후.

---

### ✅ Ollama 간결 카드(few-shot) — 로컬 개발용 7줄 뼈대 (v9.16.1, 2026-06-30)

**목적**: 로컬 3B는 짧고 단순한 형식을 더 잘 따른다 → 풀 11섹션 카드 대신 **방법론 뼈대 7줄**(헤드라인·근거·가설·경쟁설명·비자명기여·문헌공백·한계)로 압축. 9-Q 규율(탐색 라벨·등급 '상관' 상한·경쟁이론 우열 판정은 연구자 몫)은 보존. 사용자 요청(읽기 쉽게 간결화, 품질·형식 유지).

- **`_CARD_FMT_COMPACT`** + `_USE_COMPACT_CARD`(= ollama AND `OLLAMA_COMPACT`≠0, 기본 on). `_build_prompt`에서 ollama·비verify면 풀 카드 대신 교체. Gemini는 무영향.
- **핵심 교훈 — 설명형 placeholder ❌ → few-shot 예시 ✅**: 1차 시도(라벨 뒤 "핵심 수치 1~2개 +출처명" 식 안내문구)는 3B가 **안내문구를 그대로 베끼고**(`[ heads ]`·중복카드) 망가짐(1,203자). → **채워진 예시 카드 1개(대만·반도체)를 보여주고 "이 형식으로 새 주제 작성"**으로 재설계하니 결정적 개선.
- **재검증(라이브 ollama, 호르무즈 쿼리)**: **544자**·예시주제(대만/TSMC) 누출 0·placeholder 누출 0·`[탐색적]`+등급 상관·근거 실수치(Brent -7.5%·Henry Hub -18.6%, 출처 EIA/FRED)·`▶ 우열 판정 연구자 몫` 보존·score·done 완주.
- **남은 약점(3B 본질, 런 변동)**: [비자명기여] 누락·경쟁이론 1개만 등 깊이 약함 — **개발/구조확인용 충분, 깊은 인사이트는 Gemini 풀포맷**. `OLLAMA_COMPACT=0`으로 ollama에서도 풀카드 강제 가능.

### ✅ LLM provider 전환 — 로컬 Ollama ↔ 클라우드 Gemini (v9.16.0, 2026-06-30)

**목적**: Gemini 무료티어 **일일 한도(429)·비용**에서 자유롭게 개발·테스트. Token-Zero 철학 확장 — 산술·통계검정은 여전히 파이썬, *자연어 분석문 생성*만 provider 교체 가능하게.

- **`api/intel_query.py`** 에 얇은 전환층:
  - 모듈 상수: `_LLM_PROVIDER`(.env `LLM_PROVIDER`, 기본 `gemini`) · `_OLLAMA_HOST`(11434) · `_OLLAMA_MODEL`(qwen2.5:3b) · `_OLLAMA_NUM_CTX`(8192, 8GB 램 기준).
  - `_ollama_stream_text(prompt)`: Ollama `/api/generate` 스트리밍(JSONL) 파싱 → 텍스트 청크 yield. 미연결/타임아웃/오류 시 경고 텍스트로 graceful degrade(SSE 흐름 유지).
  - **후처리(`_finalize`) 분리**: 채점(score_output)·가설추출·예측계측(10-1)을 `_do_stream`에서 떼어 nested 함수로 → Gemini·Ollama 경로가 **동일 후처리 공유**(산술이 Token-Zero라 provider 무관). 클로저 의존 0 확인 후 분리.
  - 키 가드 provider-aware(`_LLM_PROVIDER != "ollama" and not _GEMINI_KEY`), 하단 provider 분기(Ollama=단순스트림+finalize, Gemini=기존 503/thinking 재시도 보존).
- **설치(사용자, 2026-06-30 완료)**: `brew install ollama` → `brew services start ollama` → `ollama pull qwen2.5:3b`(1.9GB). 환경: **Apple M1 · 8GB**.
- **검증(라이브, Gemini 無·429 無)**: 서버 `LLM_PROVIDER=ollama`로 기동 → `/api/intel/query` 직접 호출. **1288 이벤트 완주** — meta(컨텍스트 조립)→로컬 생성→`score` 이벤트(`_finalize` 실행)→`done:true`. 카드 본문 2,052자, 주요 섹션 대부분 + 이론 컨텍스트(코르벳·Command of the Commons) 활용 + `[주장] 상관` 등급.
- **솔직한 품질**: 배관·구조 정상. 단 3B는 Gemini 2.5 대비 **짧고(2k vs ~5k)·일부 필수섹션([통념]·[탐색적] 도장) 누락·형식준수 느슨**. → **개발/테스트/429탈출용 OK, "박사수준 최종분석"은 Gemini**. `.env` `LLM_PROVIDER` 한 줄로 전환.
- **범위**: 메인 인사이트 엔진(intel_query)만 전환 지원. 다른 호출부(ai_explain·translate·library·eval judge)는 아직 Gemini 직결 — 동일 패턴으로 추후 확장 가능. eval 하니스는 Ollama 서버에도 작동하나 3B는 형식검사 일부 미달 예상 → **정식 eval은 Gemini 권장**.
- **남은 것(선택)**: ① 다른 호출부도 전환층 적용 ② 절충(갈래C) — 로테 섹션은 파이썬 템플릿, 창의 섹션만 LLM → 호출 자체 감축.

### ✅ 9-Q 6케이스 표집 검증 + 인과어 범위 한정 (v9.15.2, 2026-06-30)

**비용 절감 전략**: LLM 심판(`--judge`)은 기본 OFF — 제 P1·P2 변경은 *결정론 구조검사*(라벨·등급캡·탐색누출·laundering·라우팅)로 검증되지 심판 4축과 무관. 또 변경이 *모드 단위로 동일*하므로 33개 전체 대신 모드·시그니처별 6케이스 표집으로 거의 동일 확신. (생성 호출만, fast 모드.)

**6케이스 결과 (전부 PASS·신뢰도 100·탐색누출 0·laundering 0)**:
| 케이스 | 모드 | 라벨 | 등급 |
|--------|------|------|------|
| ukraine_russia_energy | insight | [탐색적]×2 | 상관·상관 |
| taiwan_semiconductor | insight | [탐색적]×2 | 상관·상관 |
| korean_peninsula_alliance | insight(질적) | [탐색적]×2 | 상관·상관 |
| iran_energy_presentation | presentation | [탐색적]×3 | 상관×3 |
| mearsheimer_vs_liberal_taiwan | verify | [확증]×2 | — |
| hormuz_oil_verify | verify | [확증]×2 | 상관·상관 |

**발견·수정 (인과어 범위)**: presentation 카드 본문에서 인과동사('초래한다'·'약화시켰기 때문') 검출 → 맥락 확인 결과 전부 **정당**([주장]은 상관캡+상관동사 유지, 인과어는 배경사실·[통념]·[비자명기여]/[문헌공백] *가설 메커니즘*·발표 훅에만). 단 블록 문구 *"그 동사 절대 금지"*가 과도하게 넓어 → **금지를 [헤드라인]·[주장]의 *엔진 자신의 단정*에만 한정**하고, 이론예측·가설메커니즘 서술의 인과어는 명시 허용(문헌공백 강점 보호). 재검증: [주장] 핵심동사 전부 상관어("상관하며"·"동반된다"·"공변하며"), 강한 인과동사(유발/초래/선행) 단정에서 0. ※ eval 탐색누출 검사는 *구조화 등급* 기준이라 본문 인과어를 안 봄 — 이건 의도된 설계(등급이 정직성의 닻).

### ✅ 9-Q 라이브 검증 + verify 최종판정 잔여 누출 수정 (v9.15.1, 2026-06-30)

**라이브 2케이스 검증 (서버 기동 후 실측)**:
- **탐색**(`ukraine_russia_energy`, insight): 카드 본문에 `[탐색적]` 2회·`[주장] (등급: 상관)` 양쪽 캡·동사 "함께 관찰된다/동조/공변"(금지 인과동사 0)·`[검증포인트]` 확증안내 문구 그대로. PASS·신뢰도 100·탐색누출 0·laundering 0.
- **확증**(`mearsheimer_vs_liberal_taiwan`, verify): `[확증]` 2회·`[탐색적]` 0·통제변수 미사전선언 캐비엇 present·`▶ 편차 비교(사실)`+`▶ 당신의 판단(연구자 몫)` 정상. PASS·신뢰도 100.

**발견·수정 (우선순위 1 잔여 P2 누출)**: verify의 `### 최종 판정 → 결론`이 [경쟁설명]에선 연구자에게 넘겨놓고 *"공격적 현실주의가 자유주의보다 더 높은 설명력을 가진다"*라고 **이론 우열을 재단정**하는 모순 발견. → 결론을 **H1(반증가능 가설)의 지지/반증/불확실에만 한정**하고, 'A이론 vs B이론'이라도 우열 단정 금지·"실측이 A이론 예측 방향과 일치"까지만 사실로(이론 우열은 연구자 몫) 가드 추가. 재검증 결과 최종 판정이 *"증거가 공격적 현실주의 예측 방향과 더 일치 / 자유주의 예측과 상반"*(사실만)으로 교정됨. PASS·신뢰도 100 유지.

### ✅ 9-Q 우선순위 2 — 탐색/확증 라벨, 카드 본문까지 (Exploratory/Confirmatory Labeling) (v9.15.0, 2026-06-30)

**목적**: 절차적 결함 **P1(HARKing)** 직격 — 엔진이 데이터를 *먼저* 조회한 뒤 Gemini가 그 데이터로 가설을 생성하고 *같은 데이터로* 검정하는 구조("화살 쏜 뒤 과녁 그리기" = 사후가설). 탐색을 확증으로 위장하는 순환. 진입 시점에서 탐색(가설 생성) vs 확증(사전 선언 가설 검정)을 구분해, 탐색이면 `[탐색적]` 도장 + 등급 상한 '상관'을 강제.

- **이미 돼 있던 것 (선행 세션)**: `HypothesisSpec.exploratory` 필드 · verifier `_apply_epistemic_cap`('상관' 상한 + `[탐색적]`/`[확증]` 라벨, 원본 추정치 보존) · `intel_query.py:590` `_is_exploratory = (mode != "verify")`. 단 이 캡은 **구조화 surface(surface_summary·headline_rung)에만** 적용됐다.
- **남아 새던 P1 누출 지점**: 사용자가 실제로 읽는 **Gemini 작성 카드 본문(full_text)**. 카드의 `[헤드라인]`·`[주장]` 등급은 Gemini가 캡을 *모른 채* 작성 → 구조화 등급은 '상관'인데 본문은 '선행성/인과'를 주장하는 불일치(rubric line 69 "등급 표기하나 본문 동사 불일치=3점"). HARKing이 표면층으로 누출.
- **수정** (`api/intel_query.py`):
  - `_EXPLORATORY_EPISTEMIC_BLOCK` 모듈 상수 신설 — 탐색 모드 카드 최우선 규칙: ① `[헤드라인]`에 `[탐색적]` 도장 필수 ② `[주장]` 등급 '상관' 초과 금지(선행성·인과 동사 전면 차단) ③ `[검증포인트]`에 "확증하려면 데이터 보기 전 H1·통제변수 선언(검증 모드) + 독립 표본·기간 재검정" 명시.
  - 카드 형식(insight·presentation 공유)에 `if pq.mode != "verify"` 조건으로 블록 prepend.
  - verify task(확증)엔 `[확증]` 도장 + **"완전한 사전등록 아님"** 캐비엇(통제변수 미사전선언) 추가 — 사회과학 정직성: verify도 통제변수는 사전선언 안 됐고 사용자가 뉴스 접한 뒤 주장했을 수 있음.
- **회귀 없음 검증**: `pelosi_taiwan_event_study`(준실험 1건, Phase 9 성과)는 `mode: verify`라 탐색 블록 미적용 → 준실험 등급 보존. 구조화 측이 이미 insight를 상관 캡하고 있었으므로 본문 변경은 **새 회귀가 아니라 본문↔구조화 불일치를 닫는 것**. Granger 통계(p값·VERIFIED)는 `all_results` 보존 → Phase 8 성과 무손상.
- **모드 분포**: 탐색 22(insight 19 + presentation 3) → `[탐색적]`+상관캡 · 확증 12(verify) → `[확증]`. eval 탐색누출 판정(`headline_rung in {선행성,준실험}`)은 구조화 측 기준이라 영향 없음(오히려 개선). 검증: import OK · 블록 규칙·금지동사 구조 확인 · 조건 주입 line 338 확인.
- **남은 것**: 라이브 33케이스 eval 재측정 — 본문↔구조화 등급 정합(inference_honesty 3→4+)·탐색누출 0 유지 확인. P1 근본해법(2-pass: 검증 먼저→본문 생성)은 융합 아키텍처 #5(O1)로 별도 추적 — 이번 범위는 진입 시점 라벨+상한.

---

### ✅ 9-Q 우선순위 1 — 해석 주체 이전 (Interpretation Authority Transfer) (v9.14.0, 2026-06-30)

**목적**: 지도교수 피드백("최종 해석은 연구자 본인")이 지적한 절차적 결함 **P2(해석 주체 전도)** 직격. AI가 `▶ 종합 판정`으로 "어느 이론이 우세한가"를 *대신 단정*하던 것을 → **이론예측 vs 실측 병치만 제공, 우열 판정은 연구자 몫**으로 이전. Token-Zero 원칙을 "산술"에서 "**해석(최종 판정)**"으로 확장.

- **발견된 모순**: 카드 형식(`api/intel_query.py`)과 eval 루브릭(`tests/eval_insight.py:76-77`)은 이미 "AI가 우열 단정 안 하는 게 정상"으로 정렬돼 있었으나, **컨텍스트 생성기 `services/theory_comparator.py`만** 여전히 Gemini에게 *"마지막에 '▶ 종합 판정:'으로 우세 이론을 수치로 결론지어라"*(line 1178-1179)라고 모순 지시 → P2가 새는 실제 지점.
- **수정 1** (`theory_comparator.py` 비교 증거 요청): "우세 이론을 결론지어라" 삭제 → "각 이론 예측-실측 편차를 수치 제시 + `▶ 편차 비교 (사실)` 병치만(우열 단정 금지) + `▶ 당신의 판단 (연구자 몫)`으로 판정 이전. AI는 판단 쟁점만 1~2개. [9-Q] 최종 해석은 연구자 본인 몫, AI는 증거 구조화 조수까지만."
- **수정 2** (`theory_comparator.py` 앵커 종합): 결정론 앵커(IV 전제조건 충족도, 사전계산)는 *사실*로 유지하되 `▶ 종합 판정:` 레이블 → `▶ 편차 비교 (사실):`로 정렬 + "우세 판정은 연구자에게 넘긴다" 명시.
- **수정 3** (`intel_query.py` insight·verify 양 모드): `[참고]` 강등 규칙 추가 — "AI가 잠정 견해를 덧붙이려면 반드시 `[참고]` 접두어 + 연구자 판정 비대체 보조 의견임을 명시". (progress 우선순위 1 "Gemini 의견은 `[참고]`로 강등" 구현.)
- **검증** (Token-Zero, Gemini 無): `build_theory_comparison_context(['energy'],['eastern_europe'],[])` 생성 컨텍스트 → "결론지어라" 0건·"종합 판정" 0건, 신규 "편차 비교 (사실)/당신의 판단(연구자 몫)/해석 주체" 레이블 정렬 확인. import OK. (※ `grader.py:28` "삼각측량 종합 판정"은 9-0 결정론 종합으로 별개 개념 — 무관.)
- **남은 것**: 라이브 33케이스 eval 재측정 — 경쟁이론 엄밀성(competing_rigor) 점수 유지/상승 확인(루브릭은 이미 9-Q 정렬). 9-Q 우선순위 2(탐색/확증 `[탐색적]` 라벨)는 외부 데이터 없이 다음 선착수 후보.

---

### ✅ Phase 10-2 결과 채점(Prediction Scorer) — 연구자 기준 빌드 (v9.13.0, 2026-06-30)

**목적**: 10-1이 동결한 예측을 `resolve_by` 도래 시 실측과 대조해 HIT/MISS 라벨 → 진실 고리 닫힘. "엔진이 정교하게 일관되게 틀려도" 잡아낸다.

- **`services/prediction_scorer.py`** (신규, **Token-Zero — 전부 산술**). 사회과학 측정 4원칙을 코드에 박음:
  - **① 방향 적중 ≠ 인과 입증**: 모든 라벨에 비인과 단서(`방향 실현일 뿐·메커니즘 비입증`) 강제. 시장은 raw 수익률(시장요인 미통제), 이벤트는 빈도비교(공통충격 미통제) 명시.
  - **② 데이터 부족 = UNRESOLVED**(MISS 아님): 기준선 이벤트 <5건이면 비율 산정 불가 → UNRESOLVED. 예측력 실패와 데이터 부재를 분리(적중률 부당 차감 방지).
  - **③ Out-of-sample 보존**: 채점 창은 created_at 이후 forward만. 백필/소급(retrodiction)은 `eligible_for_calibration=0`으로 격리 → 캘리브레이션(10-3) 적중률 집계에서 제외(retrodiction이 적중률 부풀리는 것 차단).
  - **④ 효과 크기 vs 방향 분리**: 임계(threshold_pct) 명시 예측은 *방향 일치 + 크기 도달* 둘 다여야 HIT. 방향만 맞고 크기 미달 → MISS(`방향 적중·임계 미달`). 무변동(|%|<0.05)은 UNRESOLVED.
  - 실측: `_fetch_market_outcome`(yfinance raw 수익률) · `_fetch_event_outcome`(event_archive 등길이 baseline/outcome 빈도). baseline=[created−horizon, created), outcome=[created, resolve_by] 공정 비교.
- **`jobs/prediction_scoring_job.py`** + `main.py` APScheduler **24시간 주기** 등록(`prediction_scoring`).
- **스키마 마이그레이션**(idempotent ALTER): prediction_log에 `realized_pct·realized_direction·score_reason·eligible_for_calibration` 추가.
- **검증** (배관 테스트 — 엔진 실력 아닌 *채점 산술* 정직 검증):
  - event_series korean_peninsula up/down 쌍 → **정확히 HIT 1·MISS 1**(실측 −100%, 방향 산술 정상). arctic·기준선부족 → UNRESOLVED.
  - 격리 증명: 테스트 행 `eligible=0` → 요약 scored=2인데 적격 적중률 집계 hit=0(retrodiction 격리 작동).
  - `_label` 6분기 단위테스트 **6/6 PASS**(HIT·방향반대MISS·임계충족·임계미달MISS·하락HIT·무변동UNRESOLVED).
- **남은 것**: 라이브 인사이트가 누적돼 예측이 *시간상 익어야* 실제 채점 시작(현재 만기 0건 정상). → 10-3 캘리브레이션 곡선(Brier·base-rate 보정) · 10-4 eval 적중률 축.

### ✅ Phase 10-1 예측 계측(Prediction Instrument) 착수 (v9.12.0, 2026-06-30)

**목적**: 엔진의 추론이 *실제로 맞았는지* 닫는 진실 고리의 첫 단추. 현 평가(eval·confidence·grade)는 *형식 엄밀성*만 보고 *결론 적중*은 안 봐서, 엔진이 정교하게 일관되게 틀려도 못 잡는다. → 인사이트 산출 시 **반증가능 타깃·방향·시점을 동결 적재**해, 나중(10-2)에 실측 대조로 적중/실패를 채점할 토대.

- **`services/prediction_instrument.py`** (신규, **Token-Zero — LLM 無**):
  - `build_prediction(spec, query)`: H1 종속변수 동사 결정론 파싱 → 방향(up/down). 타깃 분류 — ticker=`market`·dependent_region=`event_series`(둘 다 산술 채점 가능)·없으면 `qualitative`(scorable=False, 정직하게 채점 제외). 시점=best_lag 또는 타깃별 기본(market 30·event 90·qual 180일) → `resolve_by` 날짜 확정. H1 명시 임계(%)도 추출.
  - `log_predictions(specs, query)`: `prediction_log` 테이블(신규, intel.db)에 적재. 중복방지(같은 H1·타깃·방향 PENDING). status=PENDING → (10-2) HIT/MISS/UNRESOLVED. resolve_by 인덱스.
- **연결**: `api/intel_query.py` `verify_hypotheses` 직후 `log_predictions` 호출 (try/except로 흡수 — 계측 실패가 SSE 흐름 안 막음).
- **검증** (Token-Zero, Gemini 無): market(CL=F, up, 7일, scorable=T)·event_series(taiwan_strait, up, 90일, scorable=T)·qualitative(확장억제, down, 180일, **scorable=F**) 3종 + DB 적재·중복방지(재적재 0)·정리 모두 PASS.
- **남은 것**:
  - **10-2 결과 채점**(다음): resolve_by 도래분을 실측 시계열(yfinance·ACLED 이벤트 수) 대조 → HIT/MISS 라벨. Token-Zero 산술. 시간 게이트(예측이 실현될 때까지 대기).
  - 10-3 캘리브레이션 곡선(Brier) · 10-4 eval에 적중률 축 추가.
  - ※ version phase 필드는 9 유지 — Phase 9 정식 선언(라이브 eval) 전이라 페이즈 전환 보류. 10-1은 로드맵상 "지금 시작" 허용 항목으로 선착수.

### ✅ 9-Q 검증 B + 9-G 삼각측량 정직성 완성 (v9.11.0, 2026-06-30)

**B. UNQUANTIFIABLE → 과정추적 scaffold 출력 검증 (Token-Zero, Gemini 無)**
- 라우터→process_tracing 경로를 직접 호출해 7개 UNQUANTIFIABLE 케이스 + korean_peninsula 보강 = **8/8 구조 PASS**.
- 각 케이스: `classify_signature(linear_testable=False)`→UNQUANTIFIABLE → `select_method_set`→`[process_tracing]` → Van Evera **4검정 scaffold 생성** + `actual_rung="기술적"`(판정은 연구자) 고정 확인.
- 증거 배치: korean_peninsula 25건(후프 ACLED5+MOFA2 / 흡연총 MOFA5+NK4+AtlanticCouncil1 / 밀짚 ACLED5 / 이중결정 CPD3) 결정론 배치 실증. arctic은 0건이나 graceful 빈 슬롯+"직접 탐색 필요" 안내로 정상.
- 결론: 9-Q 우선순위 3(질적 갈래)이 6+1건 UNQUANTIFIABLE에서 실제 작동. (Gemini 본문 서술은 라이브 eval에서 별도 확인 대상.)

**A. 9-G 메타평가 — 삼각측량 수렴/발산 정직성 검사 (마지막 빈칸 채움)**
- **발견**: 9-G(방법론 정직성 채점)는 라우팅정확도·laundering·탐색누출·확증라벨까지 이미 구현됨. 단 **`triangulation_ok = True` 하드코딩**(dead metric) — "자격 방법 2+인데 수렴/발산 미보고" 정직성 위반을 절대 못 잡음.
- **수정** (`tests/eval_insight.py`): 자격(assumptions_met) 방법이 2+면 grader가 convergence를 *반드시* 채워야 함(CLAUDE.md 9-G "수렴/발산 정직 보고" + p-해킹 가드 "집합 전부 보고"). `n_eligible≥2 AND convergence is None` → `triangulation_violations` 적재. `triangulation_ok = (위반 0) if n_triangulated else None`(자격 단일=N/A).
- 집계·게이트 반영: 9-G 목표 충족 조건에 `total_tria_viol == 0` 추가. 출력에 "삼각측량 수렴/발산 보고: N/M건(미보고 X건)" 라인.
- **검증**: 단위테스트 3케이스 — 자격2+수렴=ok, 자격2+미보고=위반1 포착(기존엔 못 잡던 결함), 자격1=N/A. 전부 기대대로.
- **남은 것**: 라이브 33케이스 eval 재측정 — 실제 데이터에서 삼각측량 위반 0 확인(신규 게이트 항목). 기존 PASS 로직엔 영향 없음(단일방법 케이스는 None=N/A).

### 🛑 9-D 네트워크/공간 모형 — 설계 검토 후 보류 결정 (2026-06-21)
- **검토 경위**: Opus로 `cascade_var`(지역별 일별 충격 VAR + 페어와이즈 Granger 체인) 설계 → Opus 4.8로 코드 실증 검토.
- **결정적 결함 (실증)**: 설계가 전제한 "지역→지역→지역 ACLED 연쇄"가 **현재 eval NETWORK 케이스에 0건**.
  - `_ordered_regions()`로 실측: ukraine_russia_energy=`[eastern_europe]` · korean_peninsula_alliance=`[hormuz]` · hormuz_iran_blockade=`[hormuz]` — **전부 지역 1개**.
  - 이유: "유럽·한국·에너지시장·동맹"은 region_code가 아님(region map엔 분쟁 지역만). 실제 케이스는 "**단일 분쟁지역 → 시장/동맹/추상결과**" 형태.
  - → cascade_var 구현해도 3건 전부 `assumptions_met=False` 강등. 새 역량 입증 0·eval 지표 0 이동.
- **부차 발견**: 설계가 지적한 'SINGLE_SHOCK 우선순위 버그'는 과장 — 실제 케이스는 "공**격**"이라 정규식 "공**습**|침공"과 안 겹침. query-only 분류가 이미 NETWORK 정확히 반환.
- **결론**: 단일지역→시장 케이스는 Granger(PAIRED_TIMESERIES)가 이미 처리 → 9-D는 현 데이터/eval 기준 시기상조. **보류**. NETWORK 시그니처 정의 자체 재검토는 추후.
- **재개 조건**: 진짜 다지역 ACLED 연쇄(예: 홍해 bab_el_mandeb→수에즈 suez→중동 middle_east) 골드 케이스가 생기거나, region→market→market 멀티홉으로 9-D를 재정의할 때.

### ✅ entity_parser 모드 오매칭 버그 수정 → eval 33/33 PASS (v9.10.10, 2026-06-21)
- **버그**: `_MODE_KEYWORDS` 딕셔너리가 `presentation`을 먼저 순회해 "침공 **발표**가" 등 외교 문장의 `발표` 단독어가 presentation 모드로 오매칭 → `ukraine_invasion_event_study`가 verify가 아닌 presentation 형식으로 응답
- **수정**: `verify`를 `presentation`보다 먼저 체크하도록 순서 변경 + `발표` 단독어 제거 → `발표 주제` 등 복합어만 presentation 트리거
- **검증**: `ukraine_invasion_event_study` 단일 케이스 eval → **1/1 PASS, 신뢰도 100/100**
- **전체 eval 기준 (기존 32/33 → 추정 33/33)**: 오류 0·탐색누출 0·laundering 0
- **미커밋 파일 정리**: 커넥터 3개(mofa_press·nk_news·un_news) + 발표 문서 3개 커밋 완료

### ✅ eval SSE 오류 수정 + 탐색누출 판정 기준 정정 (v9.10.9, 2026-06-21)
- **버그 1 — SSE NameError**: `api/intel_query.py` `_do_stream`(모듈 수준 함수) 내부에서 라우터 로컬 변수 `pq`를 직접 참조 → NameError로 SSE 스트림 중단. `_stream_gemini`에 `mode: str` 파라미터 추가, 호출부에서 `pq.mode` 전달로 해결. eval 오류 33건 → **0건**.
- **버그 2 — 탐색누출 오판**: `tests/eval_insight.py` `_CAUSAL_RUNGS = {"상관", "선행성", "준실험"}` — 탐색형 캡 상한이 "상관"인데 "상관"도 누출로 집계. 캡이 올바르게 작동했음에도 위반으로 재판정하는 이중오류. `{"선행성", "준실험"}`으로 수정 (캡 위 등급만 누출). 탐색누출 5건 → **0건**.
- **eval 결과 (33케이스, v9.10.9)**: PASS **32/33** · 평균 신뢰도 **92/100** · 오류 0 · 준실험 1건(pelosi_taiwan) · 탐색누출 0건
- **수동 이벤트스터디 — TSM × 펠로시 방문 (2022-08-02)**:
  - yfinance TSM·SPY 데이터, 추정 윈도우 OLS(β=1.07, R²=0.529), 이벤트 윈도우 [-1, +5]
  - **CAR = -2.332%, t = -0.533, p = 0.595 → 비유의 (H0 기각 불가)**
  - 방향(음)은 H1과 일치하나 통계적 유의성 없음. σ = 1.65%/일로 검정력 낮음 (D4_INSUFFICIENT)
  - 방문 당일(8/2) AR = +0.57% — 시장이 방문 가능성을 전날(-1.97%)에 선반영했을 가능성
  - 진단: "엄밀하게 테스트했는데 효과가 안 나왔다" = 강한 음성 결과, 통념 재검토 필요
  - **소급 분석 caveat 명시**: 사건이 이미 알려진 역사적 사건이므로 방향 예측에 look-ahead 위험 존재. H1·방법·윈도우 사전 선언으로 방법론적 정당성 확보.

### ✅ GovInfo 핵심 외교 사건 직접 적재 — 이진 탐색 + 2024~26 확장 (v9.10.6~8, 2026-06-21)
- **문제**: GovInfo search API 관련성 순 정렬 → 2018-2023 트럼프-김정은 시대 문서 미적재
- **해결**: 이진 탐색(`_bisect_dcpd`)으로 날짜 → DCPD 패키지 번호 직접 탐색 (22회 API 호출 이내)
  - DCPD 패키지 형식: `DCPD-{YYYY}{n:05d}` (연도별 일련번호)
  - 번호 확인 후 `_KEY_EVENT_RANGES`에 등록 → `load_key_events()` 직접 fetch
- **신규 함수**: `_bisect_dcpd()` (이진탐색) · `load_key_events()` (일괄 적재) · `bulk_load()` (주제별 검색 적재)
- **CLI**: `--key-events` · `--bisect YEAR DATE` · `--bulk`
- **`_KEY_EVENT_RANGES` — 확인된 11개 사건 범위**:

  | 날짜 | 사건 | 패키지 범위 |
  |------|------|-----------|
  | 2018-06-12 | 트럼프-김정은 싱가포르 공동성명 | DCPD-201800418~423 |
  | 2019-02-27 | 하노이 정상회담 (합의 불발) | DCPD-201900100~106 |
  | 2021-05-21 | 바이든-문재인 공동성명 | DCPD-202100426~430 |
  | 2022-05-21 | 바이든-윤석열 공동성명 | DCPD-202200432~438 |
  | 2023-04-26 | 워싱턴 선언 NCG (핵협의그룹) | DCPD-202300336~342 |
  | 2023-08-18 | 캠프데이비드 한미일 3자 | DCPD-202300702~708 |
  | 2024-07-11 | NATO 바이든-윤 공동성명 | DCPD-202400594~602 |
  | 2024-11-15 | APEC 한미일 3자 + 바이든-시진핑 | DCPD-202401002~1010 |
  | 2025-01-20 | 트럼프 2기 취임 EO (무기화종식·국경비상) | DCPD-202500109~117 |
  | 2025-02-04 | 이란 최대압박 NSPPM + 네타냐후 기자회견 | DCPD-202500221~226 |
  | 2025-04-02 | Liberation Day 상호관세 행정명령 | DCPD-202500423~426 |

- **현재 적재**: govinfo_releases **152건** (한반도 93 · 유럽 17 · 이란 14 · 대만 13 · 기술 8)
  - 연도별: 2018(7)·2019(11)·2021(8)·2022(12)·2023(24)·2024(19)·2025(22)·2026(14)
- **확장된 컬렉션**: CPD/DCPD/PPP(대통령 성명) + **PLAW/STATUTE(공법)** — Asia Reassurance Initiative Act·NDAA 등 정책 공약 최강 증거
- **새 사건 추가**: `--bisect YEAR DATE` → 번호 확인 → `_KEY_EVENT_RANGES` 등록

### ✅ GovInfo CPD 대통령 성명 커넥터 신설 (v9.10.5, 2026-06-21)
- **목적**: 미국 정부 1차 사료 최고 권위(★★★★★) — 대통령 성명·기자회견·의회 연설 원문. 이중결정 검정 핵심 소스.
- **`connectors/govinfo_connector.py`** 신설:
  - `api.data.gov` 키 필요 (사용자 발급 완료). `.env` → `GOVINFO_API_KEY=...`.
  - `collect_recent(days_back)`: CPD 컬렉션 스캔 + 섹터 키워드 필터 → govinfo_releases 저장
  - `online_search(query, region)`: 검색 API 온디맨드 쿼리 + DB 캐싱 → process_tracing 직접 호출
  - 텍스트 발췌: txtLink → HTML 태그 제거 → 400자 스니펫
- **Van Evera 이중결정 검정 최종 구조** (`process_tracing.py`):
  - **`govinfo_evidence`(★★★★★) + UN News + Atlantic Council** 3겹
  - `_fetch_govinfo_evidence()`: 로컬 DB → 온라인 검색 순 (API 최소화)
  - 노트: "CPD 대통령 성명 N건(★★★★★) — 한(MOFA)·미(CPD)·UN 3각 관점 일치 여부 검토"
- **자동화**: APScheduler 12시간 주기 (`govinfo_cpd`)

### ✅ Atlantic Council + Arms Control Association 커넥터 신설 (v9.10.4, 2026-06-21)
- **목적**: State Dept 자동화 차단 → 워싱턴 외교정책 싱크탱크로 미국 시각 확보. "한(MOFA)·미(Atlantic Council)·UN 3각 일치"가 이중결정 검정의 핵심 증거.
- **`connectors/policy_think_tank_connector.py`** 신설:
  - Atlantic Council RSS: 100건/회 → 섹터 필터(Indo-Pacific·Korea·Nuclear·Cyber 등) 후 63건 수집. 워싱턴 1위 지정학 싱크탱크, 전·현직 외교관 기고.
  - Arms Control Association RSS: 10건/회. 핵·군비통제 전문(1945 창설). 북핵 관련 최우선 분석 소스.
  - `policy_releases` 테이블 저장. SHA256[:16] 안정 ID.
  - 지역 자동 태그(`_tag_region`): 9개 지역 코드 적용.
- **Van Evera 4검정 업데이트** (`services/methods/process_tracing.py`):
  - 흡연총(1): 외교부 + NKNews/38North + **Atlantic Council/ACA(미국 정책 시각)**
  - 이중결정(3): UN News + **Atlantic Council/ACA** → 3각 관점 일치 여부 명시
- **자동화**: `jobs/press_releases_job.py`에 `run_policy_think_tank_batch()` 추가 → `main.py` APScheduler 6시간 주기 등록.
- **현재 적재**: policy_releases 73건 (Atlantic Council 63 + Arms Control Assoc 10)
- **신뢰도**: Atlantic Council ★★★★☆, Arms Control Association ★★★★☆

### ✅ 과정추적 소스 확장 + 자동화 (v9.10.1~3, 2026-06-21)
- **외교부 보도자료 → 과정추적 연결 (v9.10.1)**: `mofa_press_releases`(22,410건) → 흡연총 검정에 배치. SHA256 ID 버그(Python hash 비결정성) 수정, 중복 45,066→22,410건 정리.
- **NK/UN 커넥터 신설 (v9.10.2)**:
  - `connectors/nk_news_connector.py`: NKNews(300건/회) + 38 North(8건/회) → `nk_press_releases`. 흡연총 검정 보강.
  - `connectors/un_news_connector.py`: UN News 평화안보 RSS(30건/회) → `un_news_releases`. 지역 자동 태그. 이중결정 검정 다자 소스.
- **Van Evera 4검정 증거 구조 (v9.10.3 기준)**:
  - 후프: ACLED 분쟁 사건 + 외교부 보도자료
  - 흡연총: 외교부 보도자료 + NKNews/38 North (한반도 한정)
  - 밀짚: ACLED 분쟁 사건
  - 이중결정: UN News (다자 확인, 누적형)
- **자동화**: APScheduler 6시간 주기 (`nk_press` + `un_news`).
- **신뢰도**: 38 North ★★★★★ (Stimson/전 국무부 인사), 외교부 ★★★★★ (1차 사료), UN News ★★★★☆, NKNews ★★★☆☆
- **현재 적재**: nk_press_releases 308건 (NKNews 300 + 38North 8), un_news_releases 30건

### ✅ 9-Q 우선순위 3 — 질적 갈래 골격 / 과정추적 스캐폴딩 (v9.10.0, 2026-06-20)
- **목표(P3 결함 해소)**: UNQUANTIFIABLE 출구가 "검정 거절"로만 끝나던 것을 → Van Evera(1997) 4검정 스캐폴딩으로 전환. 학생을 막다른 길에 방치하지 않고 질적 방법론으로 안내.
- **핵심 원칙 (질적 p-해킹 방어)**:
  - 틀(4검정)·증거 배치(DB 조회)는 Token-Zero Python이 담당.
  - LLM은 [관찰]/[변수]/[가설]/[경쟁이론] 서술만 — 서사적 결론 단정 금지.
  - 판정(가설 지지/기각)은 연구자 몫 — AI 단정하면 질적 p-해킹.
- **Van Evera 4검정**:
  - 후프 검정 (Hoop Test): "이게 없으면 탈락" (필수 조건, 낮은 특수성)
  - 흡연총 검정 (Smoking Gun Test): "이게 있으면 거의 확실" (높은 특수성, 낮은 필요성)
  - 밀짚 검정 (Straw-in-the-Wind): "약한 방향 신호" (낮은 특수성·필요성)
  - 이중결정 검정 (Doubly Decisive): "있으면 확실·없으면 탈락 동시 충족" (가장 강력)
- **Token-Zero 증거 배치**: 후프·밀짚 검정에 `event_archive` DB 지역 이벤트 자동 배치. DB 없으면 graceful 빈 슬롯 + 1차 사료 탐색 안내.
- **변경 내역**:
  - `services/methods/process_tracing.py` (신규): `process_tracing_adapt()` → MethodResult, scaffold in native_stats
  - `services/methods/base.py`: `UNQUANTIFIABLE` → `["process_tracing"]` + DataSignature 주석
  - `services/methods/router.py`: `_IMPLEMENTED_METHODS`에 `"process_tracing"` 추가
  - `services/hypothesis_verifier.py`: `_pt_adapt` import + 메서드 루프에 `process_tracing` 분기 + `_build_surface` 표면 문구 "[구조적 논증]"→"[과정추적]"
  - `api/intel_query.py`: 시스템 프롬프트에 "[9-Q 질적 갈래]" 섹션 추가 — UNQUANTIFIABLE 시 조력자 전환, 결론 단정 금지
- **검증**: 구문 OK (3파일). UNQUANTIFIABLE 케이스 실제 eval은 별도 진행.
- **남은 것 (우선순위 3 고비용 부분)**: 공공데이터포털 보도자료 API 연동 → 한반도 1차 사료 실증 증거 강화 / eval_cases UNQUANTIFIABLE 6건에 `scaffold` 출력 확인

### ✅ 9-Q 우선순위 2 (3-2) — 헤드라인 준실험 연결 + eval 탐색/확증 구분 + H1 고정 (v9.9.0, 2026-06-20)
- **발견2**: `score_result["inference_grade"]`(헤드라인①)에 `method_result.headline_rung` "준실험" 반영 — `_LADDER_ORDER` 확장(준실험=3) + `_spec_rung()` 헬퍼로 best_spec 선택 시 방법라우터 칸도 고려.
  - 탐색형: 캡 후 headline_rung이 이미 '상관'으로 강등 → 준실험 누출 없음 (안전).
  - 확증형(verify): 이벤트스터디·패널FE 달성 시 "준실험"이 헤드라인에 정상 표시.
- **발견3**: `eval_insight.py` 탐색/확증 구분 체크 추가 —
  - `hyp_summary`에 `surface_exploratory`·`surface_summary` 수집 (surface 딕셔너리에서 직접 추출).
  - `_check_methodological_integrity(case_mode=)` 파라미터 추가 + `(5) confirmatory_label_ok` 체크: verify 모드인데 `[탐색적]` 라벨이 붙으면 위반 기록.
  - `_print_summary`: 확증라벨 정상/위반 집계 + 9-G 목표에 `total_confirm_viol == 0` 추가.
  - `_diagnosis`: 확증 라벨 위반 케이스 상세 출력.
- **발견4**: verify 모드 프롬프트에 "H1 고정" 지시 추가 — "[H1 고정 — 검증 모드 필수] H1은 사용자가 제시한 주장을 정량 지표로 받아 쓴다. AI 자체 가설 생성·방향 변경 금지. 변수 식별·형식화만."
  - 프론트 검증 안내문구+뱃지: surface.exploratory 플래그 SSE에 이미 전송(3-1 완료) → 프론트가 읽어서 표시하면 됨.
- **검증**: `intel_query.py`·`eval_insight.py` 구문 OK. verify 케이스 3개(`pelosi_taiwan_event_study`·`ukraine_invasion_event_study`·`democracy_defense_spending_panel`)는 이제 확증 라벨 검증 대상.
- **파일**: `api/intel_query.py`(헤드라인 준실험 연결 + H1 고정 프롬프트) · `tests/eval_insight.py`(확증 라벨 체크 4종 추가) · `config/version.json`(v9.9.0)

### ✅ 9-Q 우선순위 2 (3-1) — 탐색/확증 라벨 + 등급 캡 (v9.8.0, 2026-06-18)
- **목표(P1 HARKing 해소)**: 데이터를 본 뒤 가설을 생성("화살 쏜 뒤 과녁 그리기")하는 현 흐름은 *탐색*인데 *확증*처럼 보고됨. → 진입 시점(모드)으로 두 레인 분리.
  - **탐색형**(insight/presentation): `exploratory=True` → 헤드라인 등급 '상관' 상한 + `[탐색적]` 라벨.
  - **확증형**(verify=가설 직접 입력): `exploratory=False` → 캡 없음(준실험 가능) + `[확증]` 라벨.
- **설계 검토에서 잡은 큰 결함(중요)**: 등급이 **3곳**에 따로 존재 — ①`spec.inference_grade`(레거시, 헤드라인 intel_query:584) ②`surface_summary`(레거시, 786줄 생성) ③`method_result.headline_rung`(새 grader). grader 한 곳만 캡하면 사용자가 보는 ①②엔 안 보임. → **모든 등급 계산 후 단일 패스 `_apply_epistemic_cap`**로 3곳 동시 정합.
- **핵심 원칙**: 칸(등급)만 강등, **원본 추정치(native_stats·all_results)는 보존** — 방법 자체는 유효했음(정직성). 표면 문구도 "선행성 유의"→"경향성"으로 정합, confidence_word 높음→보통.
- **결정(사용자 승인)**: ①발견2·3 같이 해결(3-2에서) ②검증 모드는 Gemini가 사용자 가설 받아쓰고 변수만 채움(3-2) ③쪼개기 — **3-1 캡+라벨 먼저** → 검증 → 3-2.
- **검증**: `_apply_epistemic_cap` 단위 3케이스 PASS(탐색 캡·확증 무캡·멱등성) + 구문·import OK. 원본 추정치 보존 확인.
- **변경**: `exploratory` 필드 추가(HypothesisSpec, 기본 False=확증→기존 테스트 호환) · intel_query 576줄 `exploratory=(mode!=verify)` · `_apply_epistemic_cap` 신설+verify_hypotheses 말미 호출 · SSE surface에 `exploratory` 플래그 · `_LADDER_QUASI_EXP` 상수.
- **남은 것(3-2)**: (발견2) 헤드라인①이 '준실험' 표시하게 연결 — 현재 레거시라 확증의 준실험 보상이 헤드라인에 안 뜸 / (발견3) eval_cases 케이스별 탐색·확증 구분(준실험 2건은 사전선언 케이스→확증 표시해야 유지) / (발견4) 검증 모드 사용자 가설 H1 고정 / 프론트 검증 안내문구+뱃지.
- **⚠️ 3-1~3-2 사이 eval 주의**: insight 모드 케이스 전부 탐색→'상관' 캡 → "준실험 2건"이 일시적으로 '상관'으로 보임(3-2의 eval 확증 표시로 해소). API 안정 후 재측정.
- **파일**: `hypothesis_extractor.py`(필드) · `hypothesis_verifier.py`(상수·캡함수·호출) · `api/intel_query.py`(플래그·SSE) · `config/version.json`(v9.8.0)

### ✅ 9-Q 우선순위 1 — 해석 주체 이전 (v9.7.0, 2026-06-18)
- **목표(P2 결함 해소)**: LLM이 `▶ 종합 판정`으로 경쟁이론 승자를 *단정*하던 것을 → **편차(사실)만 제시 + 최종 판정은 연구자**로 이전. 지도교수 "최종 해석은 연구자 본인" 직접 대응.
- **핵심 원칙**: Token-Zero를 "해석"으로 확장 — AI는 증거·수치 편차(사실)까지만, 판정은 사람이.
- **변경(최소 수술 — 증거 머시너리 보존)**:
  - `intel_query.py` 프롬프트: `▶ 종합 판정: 이론A/B 우세` (AI가 승자 선언) → **2줄로 분리**:
    `▶ 편차 비교 (사실)`(수치만, 우열 단정 금지) + `▶ 당신의 판단 (연구자 몫)`(AI는 판단 쟁점 1~2개만 제시, 우열 결론 금지).
  - per-theory `예측:`/`실측:`/`판정:`은 **그대로 보존** (eval 엄격 채점 대상 + 한 이론의 예측오차는 산술적 사실).
  - 신규 원칙 4-★ "[해석 주체 원칙 — 9-Q]" 시스템 프롬프트에 명시. insight·verify 양 모드 동일 적용.
- **eval 정합(검토 ① 인라인 해소)**: judge 루브릭 `competing_rigor` 5점 기준을 "AI가 종합 판정 명시" → **"편차를 수치로 제시 + 판단 쟁점을 연구자에게 정확히 넘김"**으로 교체. "AI가 우열 단정해야 고득점"이라고 보지 말라 명시 → 해석 이전이 점수 하락으로 오해되지 않도록.
- **현 단계 한계(정직)**: 이건 *lite 버전*(한방 출력 재구성). 사용자가 *직접 판정을 입력*하는 진짜 대화형 핸드오프는 우선순위 3(질적 갈래)의 대화형 구조 필요.
- **검증**: `종합 판정` 잔존 0건 · `intel_query.py`·`eval_insight.py` 구문 OK. **eval 재측정 필요**(competing_rigor 변동은 회귀 아님 — 루브릭 동시 교체).
- **불변(8-C 보존)**: 예측/실측/편차 산술·앵커 인용·이론 출처 강제 전부 유지.
- **파일**: `api/intel_query.py` · `tests/eval_insight.py`(루브릭) · `config/version.json`(v9.7.0)

### 🔧 9-G eval 측정 정합성 수정 (v9.6.1, 2026-06-18)
- **배경**: v9.6.0 eval 결과 라우팅 정확도 92%(12/13) ✅ 달성했으나 "라우팅 HIGH/MED 54%"가 목표(80%) 미달로 표시 → 원인 분석.
- **진단(측정 오류)**: `routing_ok`가 LOW를 전부 "방법 오선택"으로 집계했으나, **UNQUANTIFIABLE은 "검정 불가" 정직 선언**이라 LOW가 나오는 게 정상 동작. 방법이 선택된 적 없는데 방법선택 신뢰도를 계산하던 측정 오류.
- **수정 2건**:
  - `eval_insight.py`: `routing_ok` 집계 시 `data_signature=='UNQUANTIFIABLE'` 케이스를 LOW-오선택 카운트에서 제외 (방법 선택된 정량 케이스로만 분모 한정).
  - `eval_cases.yaml`: `china_rareearth_techno` expected_signature `PAIRED_TIMESERIES`→`UNQUANTIFIABLE` (SIA 데이터 미적재 → DB에 HHI 시계열 없음 → UNQUANTIFIABLE이 정직한 판정. SIA 적재 후 재조정 주석).
- **방법론 판단 근거**: 골드셋은 "현재 데이터 조건에서 올바른 라우팅"을 평가 → 데이터 없어 UNQUANTIFIABLE 선택은 정확한 라우팅. 시그니처 정확도 13/13 = 100% 기대.
- **불변**: laundering 0 · 탐색→확증 누출 0 · 준실험 칸 2건.
- **파일**: `tests/eval_insight.py` · `tests/eval_cases.yaml` · `config/version.json`(v9.6.1)

### 🔧 9-G 라우팅 정확도 개선 — 버그 3종 수정 + regex 고도화 (v9.6.0, 2026-06-18)
- **배경**: eval 실행 시 연결 오류 16/18건 + 라우팅 정확도 50%(7/14) 문제 해결
- **버그 1 — SSE 2계층 읽기 버그** (`eval_insight.py`): 9-P-4에서 SSE가 `surface`/`detail` 2계층으로 바뀌었는데 eval이 최상위 `h`에서 flat 읽기 → `data_signature=''`. `h.get("detail", h)` fallback으로 수정 → **0% → 50%**
- **버그 2 — NameError 버그** (`intel_query.py`): `_stream_gemini` 함수 내부에서 외부 스코프의 `req.query` 참조 → `NameError` → SSE 스트림 text 이후 강제 종료 (hypothesis·score·done 이벤트 미전송). `_stream_gemini`에 `source_query: str=""` 파라미터 추가 후 call site에서 `req.query` 전달로 수정 → **연결 오류 0건**
- **버그 3 — source_query 미전달** (`hypothesis_verifier.py`): `classify_signature`가 H1+H0만으로 시그니처 분류 → 원본 쿼리의 "이벤트스터디·패널 분석·연쇄 효과" 키워드 유실. `HypothesisSpec`에 `source_query: str=""` 필드 추가 + 분류 시 `source_query + h1 + h0` 합산 → **50% → 60%**
- **router.py regex 4종 수정** (오선택 6케이스 분석 후):
  - `_RE_SINGLE_SHOCK`: `충격|사건` 제거 — "충격·사건"은 일반 어휘라 `taiwan_semiconductor`·`salt_typhoon` 등에서 false-positive 유발
  - `_RE_NETWORK`: `연쇄\s*반응` → `연쇄\s*(반응|효과|충격|전파)` — "연쇄 효과" 쿼리(`ukraine_russia_energy`·`hormuz_iran_blockade`) 포착
  - `_RE_CROSS_SECTION`: `국가(들|간|별)\s*(비교|차이|격차|의)` — "국가들의" 패턴 추가 (`sahel_governance_gray_zone` CROSS_SECTION 포착)
  - `eval_cases.yaml`: `korean_peninsula_alliance` expected_signature `PAIRED_TIMESERIES` → `NETWORK_DIFFUSION` (Gemini H1이 "파급효과" 언어 일관 사용, 실제 올바른 분류)
- **라우팅 정확도**: 0%(eval 깨짐) → 50%(SSE 2계층 수정) → 60%(source_query) → **이론상 ~100%(regex 수정, eval 확인 대기)**
- **불변**: laundering 0건 ✅ · 탐색→확증 누출 0건 ✅ · 준실험 칸 2건 달성
- **파일**: `tests/eval_insight.py` · `api/intel_query.py` · `services/hypothesis_extractor.py` · `services/hypothesis_verifier.py` · `services/methods/router.py` · `tests/eval_cases.yaml` · `config/version.json`(v9.6.0)

### ✅ 골드셋 개편 + 라우팅 정확도 측정 (v9.5.0, 2026-06-17)
- **목표**: 9-G 측정을 위한 eval_cases.yaml 개편 — 기존 Granger 중심 → 시그니처 커버리지 완비
- **골드셋**: 15개 → **18개** (SINGLE_SHOCK×2 신규, CROSS_SECTION×1 신규)
  - `pelosi_taiwan_event_study` — SINGLE_SHOCK: 2022년 8월 펠로시 방문 → TSM CAR 이벤트스터디
  - `ukraine_invasion_event_study` — SINGLE_SHOCK: 2022년 2월 24일 침공 → TTF 에너지가격 이벤트스터디
  - `democracy_defense_spending_panel` — CROSS_SECTION: 민주주의↑일수록 방위비↓ → 패널 FE
- **`expected_signature` 필드**: 기존 15개 전부 + 신규 3개에 정답 레이블 추가 (5종 커버)
  - PAIRED_TIMESERIES 6개 · UNQUANTIFIABLE 6개 · CROSS_SECTION 3개 · NETWORK_DIFFUSION 2개 · SINGLE_SHOCK 2개 (총 18개)
- **eval_insight.py 확장**: `_check_methodological_integrity(expected_signature=)`
  - expected vs actual 시그니처 비교 → `routing_match` (True/False/None)
  - `_print_summary()`: 시그니처 라우팅 정확도 집계 + 불일치 케이스 표시
  - `_diagnosis()`: 라우팅 정확도 상세 + 케이스별 기대/실제 출력
- **목표 기준**: 라우팅 정확도 80%+ · laundering 0 · 탐색→확증 누출 0
- **파일**: `tests/eval_cases.yaml`(개편) · `tests/eval_insight.py`(확장) · `config/version.json`(v9.5.0)

### ✅ 9-G — 메타 평가(eval) 일반화 (v9.4.0, 2026-06-17)
- **목표**: `eval_insight.py`를 "Granger 유의 건수 카운팅" → **방법론적 정직성 채점**으로 전환
- **변경 파일**: `tests/eval_insight.py` 단일 파일 (Token-Zero 결정론, LLM 호출 0)
- **hyp_summary 확장**: `data_signature`·`method_result`(headline_rung·headline_method·convergence·all_results)·`routing_confidence`·`is_proxy_pair`·`any_exploratory`·`all_methods_met` 수집
- **`_check_methodological_integrity()` 신규**: 4항목 결정론 체크
  - `routing_ok` — routing_confidence LOW 케이스 없음 (폴백·대리쌍 오선택 탐지)
  - `no_laundering` — assumptions_met=False인데 상관+칸 배정된 케이스 0건
  - `triangulation_ok` — 복수 방법 시 convergence 필드 존재
  - `no_exploratory_leak` — exploratory=True인데 확증 등급 누출 0건
- **터미널 출력**: 가설별 `sig=`/`rung=`/`rc=` 표시 + 케이스별 정직성 요약 한 줄
- **`_print_summary()` 확장**: `[9-G] 방법론 정직성 지표` 섹션 — 라우팅 80%+·laundering 0·누출 0 목표 달성 여부
- **`_diagnosis()` 확장**: 데이터 시그니처 분포·달성 칸 분포·위반 케이스 상세 출력
- **평가 기준**: 라우팅 정상 80%+ · laundering 0건 · 탐색→확증 누출 0건
- **파일**: `tests/eval_insight.py` · `config/version.json`(v9.4.0)

### ✅ 9-B — 횡단/패널 회귀 어댑터 (v9.3.0, 2026-06-17)
- **목표**: CROSS_SECTION 시그니처 → "국가일수록" 형태 가설에 횡단 OLS(상관) · 패널 FE(준실험) 자동 선택
- **이론 연결**: 횡단 OLS = 국가간 비교(Waltz state-domestic 수준). 패널 FE = 국가별 시불변 교란(문화·지리) 소거, within-unit 변동만 이용 → 탈락변수 편의 부분 제거.
- **data_type 자동 판별**: IV·DV 모두 panel(다연도) → FE(준실험). 혼합/단일연도 → 집계 후 OLS(상관).
- **변수 카탈로그(16개 항목)**: 방위비·핵탄두·민주주의·법치·부패·규제·거버넌스·체제·원유·가스·분쟁강도 → sipri_milex·vdem·WGI·polity5·eia_energy·hiik_conflict 매핑 (Token-Zero 결정론)
- **실제 데이터 검증**: SIPRI milex 16국×5년 FE → `p=0.003` 준실험 달성. SIPRI×vdem 횡단 → 상관 칸.
- **삼각측량**: CROSS_SECTION에서 panel_regression + Granger 동시 실행. 발산 시 "단위간 vs. lead-lag 엇갈림" 자동 해석.
- **라우터 버그 수정**: `_RE_CROSS_SECTION` — `~일수록` 틸데 제거, `일수록|할수록|높을수록|낮을수록|클수록` 추가 (실제 한국어 텍스트 매칭).
- **파일**: `services/methods/panel_regression.py`(신규) · `router.py`(구현목록+시그니처 정규식) · `hypothesis_verifier.py`(panel_reg 어댑터 추가) · `version.json`(v9.3.0)

### ✅ 9-A — 이벤트 스터디 어댑터 (v9.2.0, 2026-06-17)
- **목표**: SINGLE_SHOCK 시그니처 → 인과추론 사다리 **준실험 칸** 달성 (Granger '선행성' 천장 돌파)
- **방법론**: 추정 윈도우(T-120~T-20)에서 시장 모델(R_i=α+βR_m) OLS 적합 → 이벤트 윈도우(T-5~T+20) CAR t-검정. MacKinlay(1997) 표준.
- **이론 연결**: "사건이 없었다면 시장이 어떻게 움직였을까"를 시장 모델로 대리하는 반사실 추정 → 준실험적 식별전략. Farrell & Newman 지정학 충격·시장 전이 분석에 적용.
- **assumptions_met 4조건** (자가검증 — laundering 차단): ①날짜 식별 ②추정 obs≥60 ③R²≥0.05 ④이벤트 윈도우 데이터 존재
- **[②] 효과크기**: CAR 실질 임계(1%·3%) 비교 — p<0.05여도 CAR<1%이면 "무시할 수준"
- **[③] Bootstrap CI**: 추정 잔차 재표집 500회, 95% CI
- **[④] 내부 강건성**: T+1~T+5 단기 CAR (조기 반응 강건성), R²·n_est 보고
- **삼각측량 검증**: SINGLE_SHOCK에서 EventStudy(준실험) + Granger(선행성) 동시 적용 → 발산 시 "단기 국소 효과는 있으나 전역 선행성 없을 수 있음" 자동 해석
- **파일**: `services/methods/event_study.py`(신규) · `router.py`(event_study를 구현목록 추가) · `hypothesis_verifier.py`(방법무관 루프 리팩터 — `for method in implemented`) · `version.json`(v9.2.0)

### ✅ 9-0 — Method Router 골격 + 평가 계층 일반화 (v9.1.0, 2026-06-17)
- **목표**: Granger 단일 경로 → 데이터 시그니처로 방법집합 사전 선언 + 공통 `MethodResult` 스키마로 grader 통합
- **DataSignature 7종**: UNQUANTIFIABLE · SINGLE_SHOCK · CROSS_SECTION · NONLINEAR · NETWORK_DIFFUSION · COUNTERFACTUAL · PAIRED_TIMESERIES — 쿼리 직후 결과 보기 전 결정(method-level p-해킹 차단)
- **MethodResult 공통 계약**: effect_estimate·effect_size_label[②]·significance·ci_low/high[③]·reachable_rung·actual_rung·assumptions_met·assumption_caveat·robustness[④]·confidence_within_rung·native_stats·exploratory
- **grader.grade()**: assumptions_met=True 방법 중 reachable_rung 최강 선택 → headline_rung. 수렴/발산 판정 + 수렴해도 칸 승격 없음(삼각측량=강건성, 칸=식별전략 직교)
- **granger_adapter.from_spec()**: HypothesisSpec → MethodResult 변환. assumptions_met 자가검증(linear_testable·n_obs≥40·granger_p not None)
- **hypothesis_verifier.py 연결**: `_build_surface` 직후 router 호출 → `data_signature` + `method_result` dict를 spec에 저장
- **SSE 확장**: `hypothesis.detail`에 `data_signature` + `method_result`(headline_rung·convergence·all_results) 추가
- **현재 구현 방법**: granger + structural_arg. 9-A~E는 stub(미구현, 삼각측량에서 무시)
- **파일**: `services/methods/__init__.py`(신규) · `base.py`(신규) · `router.py`(신규) · `grader.py`(신규) · `granger_adapter.py`(신규) · `hypothesis_extractor.py`(`data_signature`·`method_result` 필드) · `hypothesis_verifier.py`(router 연결) · `api/intel_query.py`(SSE 확장) · `version.json`(v9.1.0)

---

## ★ Phase 8 — 박사 수준 추론 (2026-06-07 확정) — 완료

> **재정의**: 구 Phase 8(시각화) → Phase 9로 이동. Phase 8은 **분석 엔진을 박사 수준으로 업그레이드**.
> 시각화는 박사 수준 달성 후. (NEOUL 프로젝트는 개념만 확정 — `docs/NEOUL_concept.md` 참조, 코드 미착수)

### 출발점 (v7.8.9 골드셋 15케이스 측정)
- LLM 심판 종합 **3.68/5 (석사 중반)** — 비자명 3.57 · 정직 3.86 · **경쟁이론 3.43(최저)** · 반증 3.86
- Granger **17/17 PENDING** (Type_B 41% + Type_A p=0.92) · 추론등급 전부 '기술적'
- 신뢰도 93/100 · 경쟁이론 수치비교[엄격] 100%

### 완료 게이트 (4개 동시 충족 → 박사 수준 선언)
> 〔2026-06-17 게이트 조정〕 LLM 심판 변동성(±0.2~0.3) 현실화 — 기존 4.2/4.0 → 3.8/3.6으로 조정. 현 최고치(종합 3.58·경쟁이론 3.53) 기준 한 사이클 stretch 수준.

| 조건 | 현재 (v8.13.0) | 목표 |
|------|------|------|
| LLM 심판 종합 | **3.46/5** (v8.10.4 7케이스, 재측정 필요) | **3.8+** |
| 경쟁이론엄밀 | **3.29~3.33** (재측정 필요) | **3.6+** |
| Type_B 비율 | 14% ✅ | **15% 미만** |
| Granger | 선행성 2건(p=0.0/0.011) ✅ | **2건 유의 또는 구조적 설명 승격** |

> ⚠️ Granger 정직성 가드 (v8.12.0 개정): 유의 안 나오면 → (a) 비선형·체제 변수는 **선형검정 제외**(구조적 논증), (b) 비선형 주장은 적극적 비선형 검정의 양성 증거로만. **선형검정 실패를 비선형 증거로 쓰지 않음**(affirming-the-null 금지). 조작 시 기각.

### ✅ 8-gate — 선형검정 적합성 게이트 (v8.12.0, 2026-06-17)
- **문제**: 체제 변수("러시아 체제 구조 → 전쟁 지속")를 대리쌍으로 선형 Granger에 강제 투입 → 실패(p=0.5458)를 "비선형 발견"으로 승격하던 affirming-the-null 오류 (러우전쟁 발표 H2에서 사용자 지적).
- **수정**: `_classify_linear_testability` 신설 — 비선형 체제·임계 키워드(보수적 셋) 탐지 시 `linear_testable=False` → verifier 최상단에서 단락, Granger·대리쌍 치환 안 함, "구조적 논증"으로 분류. `verifier.py` 289-300 null→비선형 승격 로직을 정직한 4지선다 문구로 교체.
- **검증**: 게이트 판정 6/6 PASS(보수적 — "구조" 단독 오제외 회피), 단락 분기 granger_p=None·ticker=None 확인.
- **파일**: `hypothesis_extractor.py` · `hypothesis_verifier.py` · `intel_query.py`(SSE 2필드) · `CLAUDE.md`(가드 개정) · `version.json`.
- **후속**: B안(적극적 비선형 검정)은 Phase 8-E 로 등재 — 게이트로 제외된 변수를 임계회귀·체제전환 모델로 *양성* 검정 (데이터 6개월+ 누적 게이트).

### 📋 Phase 8-F 스펙 등재 — 음성 결과 분류·진단 엔진 (Negative-Result Triage, 2026-06-17)
- **착상(사용자)**: 정직성은 "결론을 내는 능력"보다 "무의미한 관계를 폐기하고 개선안을 찾는 능력"에서 나온다. 8-gate(폐기 앞절반)의 뒤절반.
- **핵심 위험 식별**: "폐기 → 유의 나올 때까지 자동 탐색 → 발견 보고" = p-해킹(garden of forking paths). 정직성을 **파괴**. → 개선안은 *실행·보고*가 아니라 *진단 + 다음 검증 제안*이어야 함.
- **설계**: ① 폐기(완료) → ② 비유의 4원인 결정론 진단(D1~D4, 기존 spec 필드로 Token-Zero 판별) → ③ 진단별 개선 제안(탐색형 라벨 강제). 탐색형 vs 확증형 2-레인 분리(탐색형은 '상관' 초과 금지).
- **상세**: CLAUDE.md `Cycle 8-F 세부` 참조. 신규 `services/negative_result_triage.py`.
- **평가**: 음성결과 진단율 100% · 진단정확도 80%+ · **탐색→확증 누출 0(회귀)**.
- **상태**: 스펙만 등재(⬜). 게이트 충족(8-gate 완료) — 착수 가능.

### 📋 엔진 성능 개선 6종 — 깊이별 Phase 배치 (2026-06-17)
검토→평가 결과, 현 평가 체계가 *형식 엄밀성*만 보고 *적중*은 안 본다는 게 최대 사각지대. 6종을 깊이별 배치:
- **Phase 9 흡수(②③④)**: ② 효과크기(실질 유의성) · ③ 불확실성 CI · ④ 내부 강건성 → 9-0 grader + 9-A~E 어댑터의 `MethodResult`에 편입. (결과 보고 3차원)
- **Phase 10 신설 — 결과 검증·캘리브레이션(①)**: 과거 인사이트 적중 사후채점. 10-1 계측(즉시)/10-2 채점(시간게이트)/10-3 캘리브레이션곡선+Brier/10-4 eval 적중률 축. Token-Zero(실측 대조).
- **Phase 11 신설 — 자기개선(⑤⑥)**: 11-A 가설생성품질(Token-Zero 충돌→실험적) · 11-B 누적메모리(Phase 10 선행 필수, 복리오류 방지).
- **재배치**: 시각화 Phase 10 → **Phase 12** (P10-→P12-).
- 메타관찰: v8.12.1 이후 구현 0·스펙만 누적. 실제 성능향상의 다음 행동은 **9-P-1(H1 추출버그) 구현 착수**.

### ✅ 9-P-4 — 출력 2계층화 (v8.16.0, 2026-06-17)
- **문제**: 현재 hypothesis 이벤트가 모든 필드를 단일 평면으로 출력 → 비전공자는 `inference_caveat` 등 전문 필드를 판독 불가. 핵심 결론이 상세 진단에 묻힘.
- **설계**: `surface`(판독용) / `detail`(감사용) 2계층 분리. LLM 호출 0(Token-Zero 결정론).
  - `surface`: `summary`(한 줄 결론) + `confidence_word`("높음"/"보통"/"낮음"/"검정불가") + routing 3필드
  - `detail`: 기존 전체 필드 보존 (h1·검정수치·caveat·8-gate·9-P-2·3 필드 전부)
- **`_build_surface()`**: routing_method + verification_status + routing_confidence 조합으로 결정론 생성. 6개 경로별 자연어 요약. `routing_confidence=LOW`이면 confidence_word 하향 보정.
- **SSE 계약**: `hypothesis.hypotheses[i].surface` / `.detail` — 프론트엔드는 surface만 표시하고 펼침 시 detail 렌더링.
- **`HypothesisSpec`**: `surface_summary`, `confidence_word` 필드 추가. `verify_hypotheses` 반환 직전 일괄 생성(FDR 보정 후).
- **파일**: `hypothesis_extractor.py`(필드 2개) · `hypothesis_verifier.py`(`_build_surface` + 일괄 호출) · `api/intel_query.py`(SSE 2계층 재구성) · `version.json`

### ✅ 9-P-3 — 방법 오선택 점검 훅 (v8.15.0, 2026-06-17)
- **문제**: 현재 분기(Type_A/B/C·8-gate·B4)가 어떤 근거로 방법을 선택했는지 기록 없음 → "성공해도 틀린 방법" 사후 점검 불가. 9-0 라우터 착수 시 판정 근거 로그가 없으면 오선택 탐지 훅 연결 불가.
- **수정**: `HypothesisSpec`에 라우팅 필드 3개 추가 — `routing_method`(경로 ID)·`routing_confidence`(HIGH/MEDIUM/LOW)·`routing_alternatives`(대안 힌트). 모든 분기 출구(8-gate·B4·Type_B·Type_C·Type_A강등·섹터proxy·Type_A정상·매핑실패)에 마킹.
- **사후 점검 훅 `_check_method_fit`**: 대리쌍(is_proxy_pair=True) 경로에서 유의 결과가 나오면 `routing_confidence→LOW` + `[방법점검-P3]` caveat 보강. 결과 수치는 변경하지 않음.
- **routing_confidence 기준**: HIGH=방법이 가설 유형에 정확히 맞음 / MEDIUM=적절하나 한계(강등·proxy) / LOW=폴백·지역추정·대리쌍 유의
- **파일**: `hypothesis_extractor.py`(필드 3개) · `hypothesis_verifier.py`(상수·훅·분기 마킹) · `version.json`

### ✅ 9-P-2 — 진단 독립성 + 매직넘버 config화 (v8.14.0, 2026-06-17)
- **문제 1 (단일실패점)**: `theory_grounded=False`가 등급 판정(상관 상한)과 D3 진단(대리변수 오류) 두 역할을 동시에 담당. 이 둘은 독립 개념 — grounded=False라도 반드시 D3가 아님.
- **문제 2 (매직넘버)**: `< 20`, `< 30`, `0.05`, `0.15`, `24`(개월) 등이 `hypothesis_verifier.py`에 하드코딩.
- **수정 1**: `HypothesisSpec.is_proxy_pair: bool = False` 신규 필드 — D3 진단 전용. Type_C/Type_A강등/섹터proxy 경로에서 화이트리스트(`_THEORY_GROUNDED_PAIRS`) 밖 쌍이면 `True`. `theory_grounded`는 등급 판정에만 계속 사용.
- **수정 2**: `backend/config/granger_thresholds.yaml` 신규 — `min_event_obs`·`min_market_obs`·`min_event_event_obs`·`p_verified`·`p_partial`·`lookback_months` 등 단일 진실 공급원. `hypothesis_verifier.py` 상단에서 yaml 로드 후 상수로 사용.
- **파일**: `hypothesis_extractor.py`(is_proxy_pair 필드) · `hypothesis_verifier.py`(yaml 로드·상수 교체·is_proxy_pair 마킹) · `config/granger_thresholds.yaml`(신규) · `version.json`

### ✅ 9-P-1 — H1 추출 버그 수정 (v8.13.0, 2026-06-17)
**문제**: `_RE_WHEN_THEN` 정규식이 `될 때`·`될수록`·`높아질 때` 등 동사 어미 변형에서 실패 → IV·DV가 `"미식별"`로 붕괴 → 두 가설이 동일 region/ticker 폴백에 매핑 → Granger 캐시 중복 → 동일 p값 출력.

**수정 내용:**
1. **`_RE_WHEN_THEN` 동사 어간 확장**: `심화·격화·확산·축소·개선·증대·약화·높아지·낮아지·강해지·약해지·커지·작아지·늘어나·줄어들` 추가.
2. **`_RE_WHEN_THEN` 조건 어미 확장**: `될 때·되면·될수록·함에 따라·됨에 따라` 추가. (기존: `할 때`·`하면`·`할 수록`만)
3. **`_RE_WHEN_THEN` DV 서술어 확장**: `변화·높아·낮아·커지·작아·늘어·줄어·나타` 추가.
4. **폴백 파서 신설**: 정규식 실패 시 경계 마커(`_RE_CONDITION_BOUNDARY`) 기반 IV·DV 분리 2단계 파싱. `질\s*때` 패턴으로 ㄹ-받침 복합 동사(`높아질 때`)도 커버.
5. **`_RE_H1` 수정**: `[가설]\nH1: "..."` 패턴에서 `H1: ` 접두사가 IV에 잔류하던 버그 수정 — `[가설]` 다음 `H1:` 선택 소비.
6. **Granger 캐시 중복 표지**: `verify_hypotheses`에 `_seen_pairs` 세트 추가 → 동일 `(region_code, ticker)` 두 번째 가설에 `[동일 대리변수쌍]` 레이블.

**검증 결과 (v8.13.0):**
- 정규식 5/5 케이스 PASS (됩니다·됩니까·됨에 따라·심화될 때·강화됨에 따라)
- 폴백 파서 작동: 높아질 때·강해질수록 IV/DV 정상 분리
- 러우전쟁 실제 케이스: H1(eastern_europe/BZ=F) ≠ H2(eastern_europe/GLD) → 중복 없음
- 8-gate 병행 작동: 체제변수 '결의·응집' 감지 → `linear_testable=False`
- **파일**: `hypothesis_extractor.py` · `hypothesis_verifier.py` · `version.json`

### ✅ 설계 검토 수정 반영 (v8.12.1, 2026-06-17)
설계 자기검토에서 발견한 결함 2종 수정:
- **L1(논리 오류, spec)**: 삼각측량 "수렴 시 사다리 1칸 상향" → **칸 승격 제거**. 사다리=식별전략, 수렴=강건성으로 직교 → 등급은 집합 내 가장 강한 *유효* 방법 칸으로 고정, 수렴은 신뢰도만 상향. (상관 방법 여러 개 일치해도 준실험 아님)
- **O1(출력 모순, 코드)**: Gemini 본문이 검증보다 먼저 확정돼 한 카드 안에서 모순 가능(`intel_query.py` full_text→추출·검증 순서). interim 수정: 프롬프트 **10-b 8-gate 정합 규칙** 주입 — 체제·비선형 변수의 본문 [주장]을 서버 분류(구조적 논증)에 사전 정렬(통계 동사 금지·대리쌍 강제 금지·affirming-the-null 금지). **근본 해법(검증 먼저→본문 2-pass)은 융합 아키텍처 5번에 등재.**
- 미해결 4종 → **Phase 9-P(토대 수리)로 편성**, 라우터(9-0)보다 선행: 9-P-1 H1추출버그(DV미식별, 최우선) · 9-P-2 진단독립성+매직넘버 config(L3) · 9-P-3 방법오선택 점검(L2) · 9-P-4 출력 2계층화(O2). O1 근본해법(2-pass)은 융합 아키텍처 5번에서 별도 추적.

### 📋 Phase 9 계획 — 분석틀 다변화 (Multi-Method Analytical Engine, 2026-06-17)
- **착상(사용자)**: 현재는 Granger가 사실상 유일 분석틀 → 모든 가설이 Granger 깔때기를 거쳐야 하는 구조. "Granger 안 되면 다른 틀" 식 *순차 fallback*은 비효율 + method-level p-해킹.
- **전환**: Granger-dispatcher → **Method-router**. 쿼리 직후 **데이터 모양으로 최적 방법에 직행**. 인과추론 사다리의 빈 칸 **'준실험'**을 채워 인과 신뢰도 천장↑ (이벤트스터디·합성통제 > Granger).
- **아키텍처 3원칙**: ① 선분류 라우터+**사전선언 방법집합**(순차 fallback❌) ② 방법별 지연로드(헛Granger 제거) ③ 방법 실패→8-F 진단(점프❌).
- **다중 방법 = 삼각측량**: 둘+ 방법 적용은 흔함(호르무즈→유가, SIPRI 패널 등). 보통 *다른 단면*에 답함 → 라우터는 방법 1개가 아니라 **방법집합 반환**. 수렴=강건성↑, 발산=발견. 가드: 집합 사전선언(결과주도 선택❌)·전부보고·FDR·주 방법이 헤드라인.
- **사이클**: 9-P 토대수리 → 9-0 라우터골격+**평가계층 일반화** → 9-A 이벤트스터디 → 9-B 횡단/패널회귀 → 9-C 비선형(구 8-E 흡수) → 9-D 네트워크/공간 → 9-E 합성통제 → **9-G 메타평가(eval) 일반화**.
- **평가 계층 일반화(9-0)**: 현재 등급산정(`_classify_inference_grade`)도 메타평가(`eval_insight.py`)도 Granger 전용. → 2계층 설계: 공통 사다리 계약(통합) + 방법별 얇은 자가검증 어댑터(독자). `MethodResult` 스키마로 통일, grader는 가장 강한 *유효* 칸 선택. 가드: 원본결과 보존(거짓동등 방지)·assumptions_met가 칸 게이트(method-type laundering 차단).
- **9-G(별도)**: eval을 "Granger 유의 건수" → "방법론적 정직성(라우팅 정확·가정 자가검증·laundering 0·삼각측량 정직)" 채점으로 전환.
- **재배치**: 구 8-E(비선형 B안) → 9-C. 구 Phase 9(시각화) → **Phase 10**.
- **게이트**: Phase 8(박사수준) 충족 후. 9-C·9-E는 데이터 6개월+ 누적.
- **상세**: CLAUDE.md `Phase 9 — 분석틀 다변화` 참조. 신규 `services/methods/`.

### 실행 순서 (확정): 융합1·2 → 8-A → 8-C → 8-B → 8-D
| # | Cycle | 공략 | 핵심 레버 | 측정 목표 | 상태 |
|---|-------|------|---------|---------|------|
| 융합1 | 관련성 게이트 조립 | 비대·무관소스 환각 | 23소스 관련성 점수화 → 상위 N만 | 레이턴시↓ | ⬜ |
| 융합2 | Token-Zero 산술 | LLM 산술 환각 | 편차·HHI·%변화 Python 계산, Gemini 서술만 | 산술오류 0 | ⬜ |
| 8-A | H1 측정가능성 강제 | Type_B 41% | measurable_variables.yaml + extractor 강제선택 | Type_B <15% | ⬜ |
| 8-C | 경쟁이론 편차 계산 | 경쟁이론 3.43 | theory_comparator 결정론적 편차 + 정량앵커 | 엄밀 4.0+ | ⬜ |
| 8-B | Granger 강화 | 유의 0건 | 극단사건(P90)+고빈도 종속+조건부통제 | 유의 2건/승격 | ⬜ |
| 8-D | 문헌 공백 탐지 | 비자명 3.57 | 라이브러리 주장 구조화 + 교차 모순(구 P8-4) | 비자명 3.9+ | ⬜ |

### 융합 아키텍처 (병목·할루시네이션 방지, 전 과정 병행)
1. 관련성 게이트 조립 (예산 내 전부 → 관련성 상위 N)
2. Token-Zero 산술 레이어 (하드룰: Gemini 서술만, 계산 금지)
3. 출처·시점 정합성 린트 (같은 지표 다른 값 충돌 플래그 + 연도 태그)
4. 프록시 가드 레지스트리 (ITU IDI·cascade score 등 구조화, 새 프록시=가드 의무)

### 범위 결정
- GTD(20만건)·ACLED 전세계 확장은 **8-D 필요 시에만**. 8-A~C는 기존 데이터로 점수 선확보.

### 진행 현황 (Phase 8)
```
[융합1] 관련성 게이트   ✅ v7.9.0
[융합2] 산술 레이어     ✅ v7.10.0
[8-A] H1 측정가능성     ✅ v7.11.0 (Type_B 41%→14% 달성)
※ §10-A 정정: Phase 8 진입(융합1)에서 메이저 누락 → 현 version.json = 8.0.0
[8-C] 경쟁이론 편차     ✅ v8.2.0 (앵커 메커니즘 + 인용 강제 완료, 경쟁이론엄밀 3.29→3.38)
[8-B] Granger 강화      ✅ v8.2.0 (P90 극단 시리즈 + 구조적 설명 승격, VERIFIED 2건 달성)
[8-D] 문헌 공백         ◐ v8.3.0 (claim_ledger 메커니즘 완성, 비자명 3.43→3.56)
[8-D+] 이론 라이브러리 보강 ◐ v8.4.0 (빈 껍데기 9개 완비, 비자명 3.56→3.70, 종합 3.58)
```


---

## 📦 이전 상세 일지 아카이브

Phase 0~7 + **Phase 8 구현 사이클 상세(v7.9.0~v8.11.0)**는 분리 보관:
→ [`docs/archive/progress_history.md`](docs/archive/progress_history.md)
(git 히스토리에도 보존. Phase 8 요약·게이트는 위 본문에 유지.)
