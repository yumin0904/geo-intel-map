# 헌법 부칙 분리 이관분 (2026-07-10)

> geo-intel-map/CLAUDE.md에서 이동한 이력·계획·해설 블록 (순수 move — 자구 수정 0).
> 매핑·근거: geo-os/docs/CONSTITUTION_SPLIT_20260710.md (2석 검토 v2). 구속 조항은 헌법에 잔류.


---

# ▣ §2 MVP 레이어 우선 구현 순서 (Phase 1~2 이력)

## 2. MVP 레이어 (11개) — 우선 구현 순서

| 우선순위 | 레이어 | 데이터 소스 | 구현 난이도 |
|---------|--------|------------|-----------|
| 1 | 분쟁 이벤트 (ACLED) | ACLED API (학술용 무료) | ★★☆ |
| 2 | 군사기지 & 자산 | 정적 GeoJSON 큐레이션 | ★☆☆ |
| 3 | 글로벌 에너지 파이프라인 | OSM Overpass / 정적 데이터 | ★★☆ |
| 4 | 해상 초점 (Chokepoints) | 정적 polygon 데이터 | ★☆☆ |
| 5 | 해저 광케이블 | TeleGeography 공개 데이터 | ★★☆ |
| 6 | 군용기 ADS-B | OpenSky Network API | ★★★ |
| 7 | 군함/상선 AIS | AISStream.io (무료 티어) | ★★★ |
| 8 | 위성 화재/열점 (VIIRS) | NASA FIRMS API | ★★☆ |
| 9 | 국가 불안정성 지수 (CII) | 자체 계산 (V-Dem + 가공) | ★★★★ |
| 10 | 사이버 위협 & 인터넷 차단 | NetBlocks, IODA | ★★☆ |
| 11 | 시장 지표 (오버레이) | yfinance, CoinGecko | ★★☆ |

**구현 원칙**: 1~5번까지 먼저 완성 후 6번 이상 진행. 한 번에 1개씩.


---

# ▣ §3 cascade_rules.yaml hormuz 완성 예시

- id: hormuz_tension_to_oil
  name: "호르무즈 긴장 → 유가"
  trigger:
    source_type: naval_activity
    region: hormuz
    severity_min: 60
  expected_response:
    source_type: market
    ticker: "CL=F"
    direction: up
    window_hours: 48
    threshold_pct: 1.5
  theory:
    framework: "Resource Weaponization"
    reference: "Hirschman (1945), 현대화 Drezner (2015)"

---

# ▣ §5 디렉토리 트리 (2026-06 시점 — 코드가 진실원)

```
geomap/
├── backend/
│   ├── api/                    # FastAPI 라우터
│   │   ├── layers.py           # 레이어별 GeoJSON 응답
│   │   ├── events.py           # 이벤트 CRUD
│   │   ├── cascade.py          # 인과 분석 API
│   │   └── study.py            # 학습 관련 (북마크, 노트)
│   ├── connectors/             # 외부 소스 어댑터 (1소스 = 1파일)
│   │   ├── base.py             # 공통 인터페이스
│   │   ├── acled.py
│   │   ├── opensky.py
│   │   ├── aisstream.py
│   │   ├── nasa_firms.py
│   │   └── yfinance_adapter.py
│   ├── services/
│   │   ├── normalize.py        # 원본 → Event 변환
│   │   ├── cascade/            # ★ 인과 엔진
│   │   ├── cii.py              # 국가 불안정성 지수 계산
│   │   └── region.py           # 지역 코드/지오펜싱
│   ├── models/                 # Pydantic 스키마
│   ├── db/                     # SQLite 모델, 마이그레이션
│   ├── jobs/                   # 스케줄러 작업
│   └── config/
│       ├── layers.yaml         # 레이어 메타데이터
│       ├── regions.yaml        # 지역 폴리곤 정의
│       └── cascade_rules.yaml  # ★ 인과 룰북
├── frontend/
│   ├── index.html
│   ├── src/
│   │   ├── core/
│   │   │   ├── MapController.js
│   │   │   ├── LayerManager.js
│   │   │   ├── EventBus.js
│   │   │   ├── StateStore.js
│   │   │   └── CascadeController.js  # ★
│   │   ├── layers/
│   │   ├── views/
│   │   │   ├── MapView.js
│   │   │   ├── TimelineView.js       # ★
│   │   │   └── CascadeGraphView.js   # ★
│   │   ├── panels/
│   │   │   ├── LayerPanel.js
│   │   │   ├── DetailPanel.js
│   │   │   ├── TheoryPanel.js        # ★ 이론 설명 패널
│   │   │   └── NotebookPanel.js      # ★ 공부 노트
│   │   ├── services/
│   │   │   └── api.js
│   │   └── config/
│   └── styles/
├── data/                       # 정적 GeoJSON (기지, 케이블, 파이프라인)
├── notebooks/                  # Jupyter (데이터 탐색, 룰 검증)
├── tests/
└── docs/
    └── theory_notes/           # ★ 학습 노트 마크다운
```

---

# ▣ 완료된 Phase 0~7 요약표

### 완료된 Phase 요약 (Phase 0~7)

| Phase | 버전 | 내용 |
|-------|------|------|
| 0 | v1.0.0 | FastAPI + Leaflet 기반, Event 모델 + SQLite, 군사기지 GeoJSON |
| 1 | v2.0.0 | 레이어 5개(ACLED·기지·파이프라인·초크포인트·케이블), LayerManager |
| 2 | v3.0.0 | 실시간 레이어 3개(FIRMS·AIS·ADS-B), Cascade Engine, 3-View(Map·Timeline·Graph), Study Mode |
| 3 | v4.0.0 | 이론 라이브러리, SandboxLab, GDELT 3-Stage Funnel, Sanctions, 추론 엔진 8단계 |
| 4 | v4.8.0 | 국가 지정학 프로파일, ReliefWeb, GDELT GKG, 데이터 품질 대시보드 |
| 5 | v5.4.0 | 멀티에이전트 섹터별 추론 병렬, IA-Engine 착수 |
| 6 | v6.6.0 | 외부 데이터 2차 적재(Cycle 6-A), Granger 통계력 강화(6-B), H1 품질 고도화(6-C) |
| 7 | v7.8.9 | 이론 라이브러리 구조화(7-A), 경쟁이론 비교 엔진(7-B), 20케이스 eval(7-C), 데이터 대량 적재(7-D) |

---

# ▣ Phase 8 측정 근거 + Cycle 이정표 (v7.8.9 서사)

**측정 근거 (v7.8.9 골드셋 15케이스)**: 점수 손실은 3곳 집중 —
① Granger 17/17 PENDING (Type_B 41% = DB에 없는 변수 발명 + Type_A p=0.92 노이즈)
② 경쟁이론엄밀 3.43 (레이블 100% but 편차 산술 없음 — Gemini가 수치를 '말'로만 비교)
③ 비자명성 3.57 (엔진이 기존 문헌 주장을 구조적으로 몰라 공백 못 짚음)

**실행 순서 (확정): 융합1·2 → 8-A → 8-C → 8-B → 8-D**

| # | Cycle | 공략 약점 | 핵심 레버 | 측정 목표 | 상태 |
|---|-------|---------|---------|---------|------|
| 융합1 | 관련성 게이트 조립 | 컨텍스트 비대·무관소스 환각 | 23소스 관련성 점수화 → 상위 N개만 주입 | 레이턴시↓ | ⬜ |
| 융합2 | Token-Zero 산술 레이어 | LLM 산술 환각 | 편차·비율·HHI·%변화 전부 Python 계산 → Gemini 서술만 | 산술 오류 0 | ⬜ |
| 8-A | H1 측정가능성 강제 | Type_B 41% | `measurable_variables.yaml` 메뉴 + extractor 프롬프트 강제 선택 | Type_B <15% | ⬜ |
| 8-C | 경쟁이론 편차 계산 | 경쟁이론엄밀 3.43 | theory_comparator 결정론적 편차 산출 + 정량 앵커 | 엄밀 3.6+ | ⬜ |
| 8-B | Granger 방법론 강화 | 유의 0건 | 극단사건(severity>P90) + 고빈도 종속변수 + 조건부 통제 | 유의 2건 또는 승격 | ⬜ |
| 8-D | 문헌 공백 탐지 | 비자명성 3.57 | 라이브러리 주장 구조화 + 교차 모순 탐지(구 P8-4 부활) | 비자명 3.9+ | ⬜ |
| 8-F | 음성 결과 분류·진단 엔진 (Negative-Result Triage) | 비유의·무의미 결과를 버리기만 하고 진단 안 함 | 비유의 4원인 결정론 진단 → 구조화된 개선 제안(탐색형 라벨) | 음성결과 진단율 100% · 탐색→확증 누출 0 | ⬜ |

---

# ▣ Phase 9 배경 (설계 논거)

**배경**: Granger는 사다리에서 '선행성'(비교적 약한 칸)에 불과하다. 그런데 현재 엔진은 모든 가설을
Granger 변종으로 강제 깔때기하고, 안 되면 폐기뿐이다. 이벤트스터디·합성통제 등 '준실험' 방법은
Granger보다 인과 신뢰도가 높은데 통째로 비어 있다. ("Granger 안 되면 다른 틀" 식 *순차 fallback*은
비효율 + method-level p-해킹이므로 금지 — 처음부터 최적 방법으로 직행한다.)

---

# ▣ Cycle 9-G 세부 + 실행 순서 (계획 서사)

**Cycle 9-G 세부 — 메타 평가(eval) 일반화 (9-0 후 착수)**

`eval_insight.py`가 지금은 `granger_p`·`granger_q`·verification_status로 "Granger 유의 몇 건"을
센다. 방법 다변화 후엔 *결과 유의성*이 아니라 **방법론적 정직성**을 채점하도록 전환:
- 라우팅이 옳았나(9-P-3 점검 결과 반영) · 각 방법 `assumptions_met` 자가검증이 작동했나
- 칸 배정이 `assumptions_met`를 존중했나(laundering 무발생) · 삼각측량 수렴/발산을 정직하게 보고했나
- 평가 기준: 골든셋 방법 라우팅 일치율 80%+ · laundering 0건 · 탐색→확증 누출 0(8-F 가드 회귀)

> ※ O1 본문↔검증 근본해법(2-pass)은 융합 아키텍처 5번에서 별도 추적(9-P 범위 밖, interim은 v8.12.1 완료).

**실행 순서**: **9-P(토대 수리)** → 9-0(라우터 골격) → 9-A(이벤트스터디 — cascade 직결·가벼움) → 9-B(회귀 — 적재된
SIPRI·V-Dem·WGI 패널 활용) → 9-C(비선형) → 9-D(네트워크) → 9-E(합성통제 — 가장 강하나 무거움) → 9-G(메타 평가 일반화).

---

# ▣ Phase 10·11·12 로드맵 + P12 설계 배경 (미래 계획)

### Phase 10 — 결과 검증·캘리브레이션 (Outcome Calibration) ⬅ Phase 9 다음 (2026-06-17 확정)

목표: 엔진의 **추론이 실제로 맞았는지** 닫는 진실 고리. 현 평가(eval_insight·confidence·grade)는
*형식적 엄밀성*만 보고 *결론의 적중*은 안 본다 → 엔진이 정교하게 일관되게 틀려도 못 잡는다.
과거 인사이트가 예측한 관계·시장변동·캐스케이드가 **실현됐는지 사후 채점**해 confidence를 반증가능하게 만든다.

**배경**: "박사 수준 4.2/5"는 LLM 심판이 *form*을 채점한 값일 뿐, *correctness*가 아니다. 박사는 *맞아서* 박사.

**게이트**: Phase 9(방법 다변화) 가동 후. ① 계측은 즉시, ② 채점은 결과 실현까지 시간 게이트.

| # | 항목 | 내용 | 상태 |
|---|------|------|------|
| 10-1 | 예측 계측(instrument) | 인사이트 산출 시 **반증가능 타깃 + 시점 + 방향/임계**를 로그에 적재 (지금 시작) | ⬜ |
| 10-2 | 결과 채점(score) | 타깃 시점 도래 시 실측값 대조 → 적중/실패 라벨 (시간 게이트) | ⬜ |
| 10-3 | 캘리브레이션 곡선 | "70% 신뢰 → 실제 적중률 70%인가" 신뢰도 보정 + Brier score | ⬜ |
| 10-4 | eval 재정초 | 9-G 메타평가에 **적중률 축** 추가 (form 점수와 분리) | ⬜ |

> Token-Zero: 채점은 실측 시계열 대조(산술)뿐, LLM 불필요. confidence_scorer는 form 점수와 **적중 점수 2축**으로 분리.

---

### Phase 11 — 자기개선·누적지능 (Self-Improvement) ⬅ 최상위 야심 (게이트 多)

목표: 엔진이 *더 나은 가설을 생성*하고 *과거로부터 학습*한다. 가장 강력하나 가장 무겁고 제약 충돌이 있어 후순위.

**게이트**: Phase 10(캘리브레이션) 가동 필수 — 적중 검증 없이 학습하면 오류가 복리로 증폭된다.

| # | 항목 | 내용 | 제약·게이트 | 상태 |
|---|------|------|-----------|------|
| 11-A | 가설 생성 품질(⑤) | 이론 기반 가설 공간 생성 + 경쟁 가설 판별 설계 | **Token-Zero와 충돌** → 양립성부터 검토하는 *실험적* 항목 | ⬜ |
| 11-B | 누적 메모리·사전확률(⑥) | 검증/반증된 관계를 사전확률로 누적(콜드스타트 해소) | **Phase 10 선행 필수** (복리 오류 방지) | ⬜ |

---

### Phase 12 — 시각화 (후순위, 엔진 박사 수준·검증·자기개선 후)

목표: 박사 수준으로 강화되고 다중 분석틀을 갖춘 엔진의 결과를 시각적으로 표현

**게이트**: 엔진 박사 수준(Phase 8) + 분석틀 다변화(Phase 9) + 검증·캘리브레이션(Phase 10) 후.
이 분기점이 **NEOUL 프로젝트 착수 지점**과 일치("글 하나를 지도로 변환하는 데모" → 별도 레포·브랜드 분리).
Phase 9~10 결과(방법별 등급·적중률)를 시각화 대상으로 반영.

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| P12-1 | 브리핑 연쇄 그래프 뷰 — `series_ref` Cytoscape 시각화 | `frontend/src/views/BriefingGraphView.js` | [ ] |
| P12-2 | 행위자 네트워크 자동 추출 — `event_refs` 공통 노드 생성 | `backend/api/library.py` 확장 | [ ] |
| P12-3 | Cascade 커버리지 갭 트리거 3종 — cyber/defense_policy/economic_coercion | `cascade_rules.yaml` / `engine.py` | [ ] |
| P12-4 | 브리핑 타임라인 뷰 | `frontend/src/views/BriefingTimelineView.js` | [ ] |

> ※ 구 P8-4(교차 인사이트 자동 생성)는 Phase 8 Cycle 8-D(문헌 공백 탐지)로 흡수됨.

### P12 설계 배경 보존 (2026-06-01 분석)

7개 브리핑 교차 검토에서 도출된 교차 인사이트 가설 — Phase 12 착수 시 활용:

- **한국 전략 공간 이중 압박**: 382호(북한) × 일본 국가행동분석 동시 작동 구조
- **외교 도미노 타임라인**: 중러(845) → 북중(848) → 다극(382) → 핵잠(849) 10일 연쇄
- **Cascade 엔진 맹점 3유형**: cyber·defense_policy·economic_coercion 미포착


---

# ▣ §20-C 박사 수준 체크리스트 (이정표 이력)

### 20-C. 박사 수준 도달 기준 체크리스트

현재 70% (신뢰도 평균 70/100). 완전한 박사 수준(90%+) 조건:

```
✅ 시간 역전 오류: [TEMPORAL_REVERSAL] 자동 탐지 및 재공식화 (v6.0 추가)
✅ ACLED 대만해협 이벤트 필터 수정 → Cascade 대만 0건 해소 (v6.1.1)

Phase 6 (데이터 기반 강화):
✅ UNVERIFIED 평균 <1건/케이스 (Cycle 6-A, v6.4.0)
✅ IA-Engine-D: Granger VERIFIED 2건 (한반도 p=0.048 + 북극 p=0.049, v7.2.0)
   ⚠️ 정정(2026-07-09): 한반도 p=0.048은 region 오염기(서울 이벤트 3,136건이 north_korea로
   월경해 korean_peninsula에서 누락) 버킷의 인공물 — v9.30.0 마이그레이션 후 재검정 p=0.2175
   (n=717)로 재유도 실패. north_korea 쌍도 p=0.6037(극단 84건, CNS 재라우팅으로 데이터 고갈
   해소 확인). 두 쌍 모두 정직 null. 판례 20260709-nk-region-bbox-contamination §20-C 재유도 완결.
□ H1 Type_A/B 비율 50%+ (현재 대부분 Type_C — 데이터 공백으로 인한 추상화)

Phase 7 (추론 고도화):
✅ 이론 라이브러리 12개 이론 IV·DV·반례·경쟁이론 구조화 (Cycle 7-A, v7.0.0)
✅ 이론 비교 엔진 구현 — theory_comparator.py, 섹터/지역 이론쌍 + 실측값 (Cycle 7-B, v7.1.0)
□ 경쟁이론 수치 비교 [경쟁설명] 50%+ 달성 (현재 0~10% — 형식 gap)
□ 신뢰도 평균 85+ (현재 70 — 섹터별 수치 데이터 공백이 원인)

Phase 7-D (데이터 품질 강화, 진행 예정):
□ FRED 경제 시계열 적재 → energy·환율 수치 강화
□ World Bank WGI 거버넌스 지수 → gray_zone·사헬·북극 공백 해소
□ SIA 반도체 시장 데이터 → techno 섹터 HHI 수치화
□ CSIS Cyber DB 20→100+건 확장 → cyber 섹터 수치 강화
□ [경쟁설명] 형식 gap 해소 → 경쟁이론 수치 비교 50%+ 달성
```
