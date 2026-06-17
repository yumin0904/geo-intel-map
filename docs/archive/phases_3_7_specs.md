# 완료된 Phase 3~7 상세 스펙 (아카이브)

> 이 파일은 CLAUDE.md에서 분리된 완료된 Phase 상세 내용입니다.
> 현재 진행 중인 Phase 8+ 스펙은 CLAUDE.md를 참조하세요.

### Phase 3 — 학습 도구 완성 ✅ (완료)

**Veto 확정 (구현 금지)**
- MapLibre 3D Globe → Phase 4 격리
- 외교부 안전여행 API → Phase 4 후순위
- Gemini 영상 자막 추출 → 완전 폐기
- X(트위터) 임베드 → Mastodon/Bluesky 대체

**신규 구현 항목 (우선순위 순)**
1. md_indexer.py → TheoryLibrary 데이터 소스
2. deep_link.py + theory_library.yaml → 이론↔지도 매핑
3. api/library.py → 프론트 데이터 연결
4. SandboxLab (Cytoscape.js 노드 캔버스)
5. Sanctions 레이어 (GSDB/UN 안보리)
6. GDELT 3-Stage Funnel + confidence_score

**신규 데이터 필드**
- CascadeLink: depth(int), parent_link_id, chain_output
- Event: confidence_score (ACLED=1.0, GDELT미검증=0.5, 교차검증=0.8)
- 무한루프 방지: _MAX_CHAIN_DEPTH=4

### Phase 4 — 데이터 확충 & 적재 기반 강화

목표: 추론의 연료 확충 + 데이터 신뢰도 강화

**게이트**: Phase 3 완성 공식 선언 후 착수. 항목 4는 Granger 데이터 6개월+ 누적 후(§11-A 게이트).

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 0 | 국가 지정학 프로파일 — CountryPanel 기본정보 탭 확장 | `country_geopolitics.yaml` / `country.py` / `CountryPanelView.js` | [ ] |
| 1 | 실시간 소스 다변화 — ReliefWeb API(UN OCHA) 편입, RSS 분쟁전문 피드 추가 | `connectors/reliefweb.py` | [ ] |
| 2 | GDELT GKG 적재 — 테마·톤 필드 결정론적 매핑 (Token-Zero 유지) | `connectors/gdelt_gkg.py` / `cameo_mapper.py` 확장 | [ ] |
| 3 | 데이터 품질 게이트 대시보드 — confidence·importance 모니터링 상단바 확장 | `api/stats.py` / `TopBarView.js` | [ ] |
| 4 | Cascade 룰 자동 후보 생성 — Granger 유의쌍 스캔 → YAML draft 제안 (인간 승인 필수) | `services/cascade/correlation.py` 확장 | [ ] |

---

### Phase 5 — 추론 지능화 ✅ (완료, v5.4.0)

목표: 규칙·매칭 기반 → 가설 생성·반증 추론

| # | 항목 | 파일 | 상태 |
|---|------|------|------|
| 5 | Stage 5 (명분·의도) 구현 — GKG 톤/테마 + actor posture 결합 | `services/reasoning/stages.py` | ✅ v5.0.0 |
| 6 | 추론 체인 자기검증 — 8단계 ↔ Sandbox BFS 가설·반증 루프 | `services/reasoning/engine.py` / `sandbox_solver.py` | ✅ v5.1.0 |
| 7 | 멀티에이전트 — 섹터별 추론 에이전트 병렬 + 종합 에이전트 | `services/reasoning/agents/` (신규) | ✅ v5.4.0 |
| 8 | LLM 종합 브리핑 계층 | — | ❌ 취소 (IA-Engine으로 대체) |

---

### Phase 6 — IA-Engine 데이터 기반 강화 (현재 진행 중, v6.3.2)

목표: 분석의 원료(데이터) 확충 + Granger 통계력 강화 → UNVERIFIED 감소, VERIFIED 달성

**게이트**: Phase 5 완료 ✅ + 브리핑 50개 ✅ (2026-06-04 달성)

**사이클 구조**: 계획 → 구현/테스트 → 자동화 평가(`eval_insight.py`) → 수정 → 재계획

| # | Cycle | 목표 | 핵심 파일 | 상태 |
|---|-------|------|---------|------|
| 6-A | 외부 데이터 2차 적재 | UNVERIFIED 평균 <1건/케이스 | `data/external/` + `intel_analyzer.py` | ⬜ |
| 6-B | Granger 통계력 강화 | VERIFIED 1건+ (p<0.05) | `hypothesis_verifier.py` + `correlation.py` | ⬜ |
| 6-C | H1 생성 품질 고도화 | Type_A/B 비율 50%+ | `hypothesis_extractor.py` + 프롬프트 | ⬜ |

**Cycle 6-A 세부 (외부 데이터 2차 적재)**

현재 UNVERIFIED 높은 케이스: 북극(21건) · 호르무즈(4건) · 사헬(3건) → 해당 지역 커버 소스 부재

**1단계 — 정형 수치 데이터 (CSV seed, 즉시 ROI 최대)**

| 소스 | 해결 공백 | 우선순위 |
|------|---------|---------|
| SIPRI Arms Transfers DB | 무기 의존도·동맹 자율성 수치화 | ★★★ |
| V-DEM Democracy Index | 행위자 체제 유형 정량화 (사헬·북극) | ★★★ |
| COW Wars DB | 전쟁 선례 시계열 (역사 비교) | ★★ |
| Kiel Tracker 2025 업데이트 | 현재 2024-06 기준 → 최신화 | ★★ |
| IISS Military Balance 주요 수치 | 군사력 비교 직접 인용 | ★★ |

**2단계 — 외교부 LOD SPARQL (1단계 완료 후)**

- SPARQL 엔드포인트: `https://opendata.mofa.go.kr/lod/sparql`
- REST JSON 패턴: `GET /mofapub/resource/Publication/{id}.json.data`
- 구현 파일: `backend/connectors/mofa_lod.py`

**온톨로지 구조 (검증 완료, 2026-06-05)**

Core 클래스 7종: `Area · Country · City · Person · Organization · Event · Year`
Domain 클래스 4종: `Publication · Briefing · Press · DiplomatJ`

| 데이터셋 | 건수 | 활용 방식 |
|---------|------|---------|
| `mofapub` IFANS 발간자료 | 4,174건 | intel_analyzer 11번째 소스 — 한반도·동아시아 한국 시각 |
| `mofabrief` 대변인 브리핑 | 191건 (2022~2023) | 한국 정부 외교 신호 보조 |
| `schema:Event` 역사 이벤트 | 2,128건 | DBpedia sameAs 브릿지 (날짜 없음, 직접 사용 불가) |

**핵심: `owl:sameAs` → DBpedia 전체 연결 (검증 완료)**

모든 Country와 Event 엔티티가 DBpedia URI에 연결되어 있음:
```
Country/RU  → dbpedia:Russia
Country/KP  → dbpedia:North_Korea
Event: 러시아-우크라이나 전쟁(2022) → dbpedia:2022_Russian_invasion_of_Ukraine
Event: 후티 반란(2004)             → dbpedia:Houthi_insurgency
Event: 2019년 아브카이크 공격        → dbpedia:Abqaiq–Khurais_attack
```

**`mofa_lod.py` 쿼리 경로 2종 (모두 검증 완료)**

경로 1 — ISO2 국가 코드로 발간자료 조회:
```sparql
SELECT ?label ?date ?abstract WHERE {
  ?s a <http://opendata.mofa.go.kr/mofapub/Publication> .
  ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
  ?s <http://opendata.mofa.go.kr/mofapub/pubDate> ?date .
  ?s <http://opendata.mofa.go.kr/mofapub/abstract> ?abstract .
  ?s <http://opendata.mofa.go.kr/core/relatedCountry>
     <http://opendata.mofa.go.kr/core/resource/Country/{ISO2}> .
} ORDER BY DESC(?date) LIMIT 5
```

경로 2 — DBpedia 이벤트 URI → 관련 발간자료 조회 (UNVERIFIED 직접 감소):
```sparql
SELECT ?label ?date ?abstract WHERE {
  ?event <http://www.w3.org/2002/07/owl#sameAs> <{dbpedia_uri}> .
  ?s <http://opendata.mofa.go.kr/core/relatedEvent> ?event .
  ?s a <http://opendata.mofa.go.kr/mofapub/Publication> .
  ?s <http://www.w3.org/2004/02/skos/core#prefLabel> ?label .
  ?s <http://opendata.mofa.go.kr/mofapub/pubDate> ?date .
  ?s <http://opendata.mofa.go.kr/mofapub/abstract> ?abstract .
} ORDER BY DESC(?date) LIMIT 5
```

intel_analyzer 진입 로직:
```python
# entity_parser가 지역 코드 추출 → ISO2 매핑 (경로 1)
# 또는 쿼리 키워드 → DBpedia URI 매핑 테이블 (경로 2)
# 예: "hormuz" → dbpedia:Abqaiq–Khurais_attack 등 관련 이벤트 URI 목록
```

평가 기준: `eval_insight.py` 재실행 → UNVERIFIED 평균 3.5건 → <1건

**Cycle 6-B 세부 (Granger 통계력)**

현재: PARTIAL 5건(p≤0.145), VERIFIED 0건

| 문제 | 수정 방법 |
|------|---------|
| 사이버 섹터 proxy 변수 없음 | `_REGION_DEFAULT_TICKER`에 cyber 섹터 매핑 추가 |
| lag 고정(4) | AIC 기준 자동 lag 선택 (`statsmodels select_order`) |
| Granger F-통계량 미출력 | `r값` 추가 → §22-A H1 스키마 완전 충족 |

평가 기준: VERIFIED 1건 달성 (대만·한반도 집중 공략, 현재 p=0.085/0.052)

**Cycle 6-C 세부 (H1 품질)**

현재: 추상 변수(의도·의지) H1 → Granger 불가 구조

| 문제 | 수정 방법 |
|------|---------|
| 추상 변수 H1 | 프롬프트: "X/Y는 측정 가능한 지표(건수·가격·비율·금액)여야 함" |
| H1 과잉 생성(최대 4개) | 최대 2개 제한 + 검증 가능성 우선 |
| Type_C proxy 품질 | proxy 제안 시 실제 소스명 함께 제시 |

평가 기준: `eval_insight.py` Type_A/B 비율 50%+

---

### Phase 7 — IA-Engine 추론 고도화 ✅ (Cycle 7-A~C 완료, v7.2.0)

목표: 경쟁 이론 실제 비교 + 이론 라이브러리 구조화 → 박사 수준 90%+

**게이트**: Phase 6 전체 Cycle 완료 + UNVERIFIED 평균 <1건 + VERIFIED 1건+

**사이클 구조**: 계획 → 구현/테스트 → 자동화 평가 → 수정 → 재계획

| # | Cycle | 목표 | 핵심 파일 | 상태 |
|---|-------|------|---------|------|
| 7-A | 이론 라이브러리 구조화 | 12개 이론 예측 변수·반례 구조화 | `library/` 프론트매터 확장 | ✅ v7.0.0 |
| 7-B | 경쟁 이론 비교 엔진 | 섹터/지역 이론쌍 + 실측값 편차 컨텍스트 | `theory_comparator.py` + 프롬프트 | ✅ v7.1.0 |
| 7-C | 종합 평가 & 캡 해제 | 20케이스 확장, rival_check 채점 추가 | `eval_insight.py` 확장 | ✅ v7.2.0 |
| **7-D** | **데이터 품질 대폭 강화** | **신뢰도 70→85+, 경쟁이론 비교 50%+** | `connectors/` + `data/external/` | ⬜ **진행 예정** |

**Cycle 7-A 세부 (이론 라이브러리 구조화)**

현재: 이론이 마크다운 텍스트로만 존재 → Gemini가 태그로만 참조, 예측 도구로 활용 불가

목표 구조 (각 이론 프로파일 프론트매터 확장):
```yaml
independent_var: "공급망 집중도 (HHI 지수)"
dependent_var: "피의존국 외교 양보 빈도"
conditions: ["비대칭 의존 구조", "대체재 부재"]
falsifiable_prediction: "집중도 증가 시 양보 증가 (통제: 군사력 균형)"
known_counterexample: "중국 SMIC 자립화 시 설명력 하락"
rival_theories: ["Balance of Power", "Liberal Interdependence"]
```

대상 12개 이론: Mahan · Farrell&Newman · Snyder · Mearsheimer · Waltz · Libicki · Hirschman · Hoffman · A2AD · Digital Iron Curtain · Gray Zone · Granger

평가 기준: [경쟁설명] 섹션에서 수치 편차 비교 등장 비율 50%+

**Cycle 7-B 세부 (경쟁 이론 비교 엔진)**

현재: 경쟁 이론 기각이 수사적 수준 ("~라는 반례가 있다")
목표: 이론 A 예측값 vs 이론 B 예측값 vs 실측값 비교 → 우세 이론 자동 선택

```
쿼리 입력
  → 관련 이론 2~3개 자동 선택 (이론 프로파일 기반)
  → 각 이론의 예측 방향 도출
  → ACLED/SIPRI/EIA 실측값과 비교
  → 예측 성공률 높은 이론 우세 판정
  → [경쟁설명] 섹션에 수치 편차 포함
```

**Cycle 7-C 세부 (종합 평가)** ✅ v7.2.0

- 자동화 테스트 10개 → 20개 확장 ✅
- rival_check 채점 (엄격/완화 2단계) 추가 ✅
- 결과: 14/17 PASS(82%), 신뢰도 평균 70, VERIFIED 2건 (한반도·북극)

**Cycle 7-D 세부 (데이터 품질 대폭 강화)**

현재 미달 원인: 섹터별 수치 데이터 공백 → cyber·techno·gray_zone 60점대 고착
목표: 신뢰도 평균 70 → 85+, 경쟁이론 수치 비교 0% → 50%+

**풀스케일 12-sub-cycle (2026-06-05 확정)**

| Level | Sub | 항목 | 소스 | 규모 | 우선순위 |
|-------|-----|------|------|------|---------|
| L1 | 7-D-1 | FRED 경제 시계열 | FRED API (무료) | ~20 시리즈 | ★★★ |
| L1 | 7-D-2 | World Bank WGI | WB Open Data API | 200국×6지표 | ★★★ |
| L1 | 7-D-3 | Our World in Data | GitHub CSV 공개 | 수만 행 | ★★★ |
| L1 | 7-D-4 | Polity5 정치체제 지수 | CSV (학술 무료) | 167국 시계열 | ★★ |
| L1 | 7-D-5 | ITU ICT 사이버 역량 | CSV (무료) | 170국 | ★★ |
| L1 | 7-D-6 | HIIK 분쟁 강도 바로미터 | CSV (무료) | 1992~현재 | ★★ |
| L1 | 7-D-7 | SIA 반도체 시장 데이터 | 공개 보고서 CSV | ~50행 | ★★★ |
| L1 | 7-D-8 | CSIS Cyber DB 확장 | CSV (20→100+건) | 100+건 | ★★★ |
| L2 | 7-D-9 | UN Comtrade 무역 의존도 | API (무료 제한) | 국가쌍 무역 | ★★ |
| L2 | 7-D-10 | Wikidata 조약·동맹 | SPARQL | 수천 건 | ★★ |
| L3 | 7-D-11 | GTD 테러 데이터베이스 | CSV (학술 무료) | 200,000+건 | ★★★ |
| L3 | 7-D-12 | ACLED 전세계 확장 | API (커넥터 있음) | 400,000+건 목표 | ★★★ |
| 공통 | 7-D-X | [경쟁설명] 형식 gap 해소 | 프롬프트 재설계 | — | ★★★ |
| 공통 | 7-D-Y | intel_analyzer 20+소스 확장 | 점진적 통합 | — | ★★★ |

**섹터별 공백 진단:**

| 섹터 | 현재 신뢰도 | 공백 | 해결 소스 |
|------|-----------|------|---------|
| cyber | 50~60 | APT 빈도·피해액 수치 없음 | CSIS 확장 + GTD + ITU |
| techno | 60~75 | 반도체 HHI·점유율 없음 | SIA + Our World in Data + Comtrade |
| gray_zone (사헬·북극) | 60~75 | 거버넌스·취약국 지수 없음 | WB WGI + Polity5 + HIIK + GTD |
| energy·maritime | 75 | 상대적 양호 | FRED 시계열 보완 |
| indo_pacific | 75 | 군사력 비교 얕음 | Our World in Data 군사 데이터 |

**평가 기준:**
- L1 완료 후: 신뢰도 평균 78+ + 경쟁이론 수치 비교 30%+
- L2 완료 후: 신뢰도 평균 82+
- L3 완료 후: 신뢰도 평균 85+ + 경쟁이론 수치 비교 50%+ → **Phase 8 착수**

상세 계획: `progress.md` Phase 7-D 섹션 참조

---



---

# 데이터 로드맵 & 아키텍처 진화 경로 (아카이브)

## 20. 인사이트 엔진 데이터 로드맵 (우선순위)

### Phase A — 즉시 적재 가능 (공개 API / CSV)

| 소스 | 커버리지 | 해결 공백 | 우선순위 |
|------|---------|---------|---------|
| SIPRI Military Expenditure | 173개국 국방비 %GDP | 자유편승 검증, 역할분담 | ★★★ |
| SIPRI Arms Transfers DB | 전 세계 무기 이전 1950~ | 동맹 자율성, 의존도 | ★★★ |
| COW Alliance Data | 동맹 형성·해체 1816~ | 동맹 이탈 위험 시계열 | ★★★ |
| Kiel Institute Ukraine Support Tracker | 서방 대우크라이나 지원 | 연쇄 고리 검증 핵심 | ★★★ |
| EIA International Energy Stats | 전 세계 에너지 생산·소비 | 유가충격 정량화 | ★★★ |
| CSIS Significant Cyber Incidents | 2006~ 사이버 공격 DB | 사이버전 기준점 | ★★ |
| V-DEM Democracy Index | 202개국 민주주의 지수 | 행위자 체제 유형 | ★★ |
| Kyiv School of Economics 피해 DB | 우크라이나 인프라 피해 | 에너지 공격 강도 | ★★ |

**즉시 ROI 최대 조합: SIPRI + COW + Kiel Tracker 3종 적재 + 프롬프트 6단계 재설계**
→ 인사이트 수준 석사 중반 → 석사 후반으로 상향 기대.

### Phase B — 중기 (파싱·정제 필요)
- IISS Military Balance 연간 보고서 (PDF → 구조화)
- 미 국방부 예산 문서 (PDF, comptroller.defense.gov)
- Microsoft MSTIC / Mandiant APT 보고서 (이란-러시아 TTPs 유사도)
- 크렘린·외무부 공식 성명 (텍스트 스크래핑)

### Phase C — 장기 (라이선스 필요)
- IISS Military Balance API (유료)
- Oxford Economics Global Model
- Harvard Shorenstein 허위정보 DB

### Phase D — 종속변수(DV) 직접 코딩 데이터셋 (싱크탱크 수준, 외부 협력 가능)

**배경**: 8-C는 DV(외교 양보·정책 변화) 실측 시계열 부재로 "IV 전제조건 충족도"에 한정됨.
연구자 표준 방법 중 가장 강한 ②직접 코딩(hand-coding) DV 데이터셋을 확보하면,
8-C의 "전제조건 충족" → **"이론 입증"으로 격상** (IV→DV 회귀·Granger 직접 검정 가능).

| 후보 DV | 코딩 방법 | 확보 경로 |
|---------|----------|----------|
| 외교 양보 빈도 | 공동성명·UN 투표 동조율·제재 동참/이탈 이벤트화 | 자체 hand-coding / 학교 교수 협력 |
| 정책 변화율 | 정책 선언·법안·예산 변동 코딩 | 연구소 데이터셋 수령 |
| 동맹 이탈/연루 | 외교 문서·성명 코딩 | 기존 학술 DB(COW 확장) + 자체 보완 |

**실행 메모 (사용자)**: 본인 직접 코딩 가능 / 교수님 지도 / 연구소 데이터 수령 중 택1.
확보 시 `Type_C proxy` → `Type_A 직접 검정`으로 승격, 경쟁이론 "입증" 주장 가능.

---

## 21. 분석 아키텍처 진화 경로

```
v5.x (완료): 행위자 프로파일 → 이론 매핑 → 서술적 인사이트
v6.x (완료): 행위자 프로파일 → 변수 식별 → 10소스 병렬 데이터 조회 → 수치 근거 포함 인사이트
             + §19-D 역산 신뢰도 점수 (IA-Engine-C) + 시간 역전 탐지 + H1 자동 생성 + Granger
             → 평균 70/100, PARTIAL 5건, 박사 초입 81% (2026-06-04 자동화 테스트 기준)

Phase 6 목표 (데이터 기반 강화):
  Cycle 6-A: 외부 데이터 2차 적재 → UNVERIFIED <1건/케이스
  Cycle 6-B: Granger 통계력 강화 → VERIFIED 1건+ (p<0.05)
  Cycle 6-C: H1 생성 품질 고도화 → Type_A/B 비율 50%+
  → 목표: 신뢰도 평균 78+

Phase 7 목표 (추론 엔진 고도화):
  Cycle 7-A: 이론 라이브러리 구조화 ✅ (12개 이론 IV·DV·반례·경쟁이론 프론트매터)
  Cycle 7-B: 경쟁 이론 비교 엔진 ✅ (theory_comparator.py — 섹터/지역 이론쌍 + 실측값)
  Cycle 7-C: 20케이스 eval 확장 ✅ (14/17 PASS, 신뢰도 평균 70, VERIFIED 2건)
  Cycle 7-D: 데이터 품질 강화 ⬜ (FRED + World Bank + SIA + CSIS 확장 → 신뢰도 85+)
  → 현재: 신뢰도 평균 70/100, PARTIAL 9건, VERIFIED 2건 (v7.2.0 기준)
```

**핵심 전환 원칙:**
> "무슨 일이 일어나고 있는가"(현황 기술) →
> "왜 이 설명이 경쟁 이론보다 더 타당한가"(인과 검증)를 데이터로 보여주는 도구

---

