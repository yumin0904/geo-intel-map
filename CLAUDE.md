# SYSTEM PROMPT — Geopolitical Cascade Intelligence Map (v2)

## 0. 프로젝트 정체성

이 프로젝트는 **정치외교학 학습을 위한 개인용 지정학 분석 도구**다.
일반적인 OSINT 대시보드(예: World Monitor)와 다음 두 가지가 다르다:

1. **학습 우선**: 모든 데이터는 국제정치 이론(해양력, 자원무기화, 회색지대전략 등)과 연결되어 해석 가능해야 한다.
2. **연쇄 분석(Cascade Analysis) 중심**: 단순 시각화가 아니라 "사건 → 지표 변화 → 또 다른 사건"의 인과 추적이 핵심 기능이다.

사용자는 **비전공자 개발자**(정치외교학과 학부생)이며, 시스템은 항상 다음을 만족해야 한다:
- 저비용 (무료/저가 API 우선)
- 고효율 (불필요한 데이터 로드 금지)
- 높은 코드 품질 (확장 가능한 아키텍처)
- 최신 정보 접근성 (실시간 또는 일 단위 갱신)

---

## 1. 핵심 6대 섹터 (도메인 우선순위)

이 프로젝트가 다루는 영역은 다음으로 한정한다. 그 외 레이어는 **명시적으로 거절**한다.

| # | 섹터 | `sector_tag` | 정치외교학 연결 이론 |
|---|------|-------------|---------------------|
| 1 | 해양 초점주의 & SLOC | `maritime` | Mahan 해양력, 진주목걸이 vs 인도-태평양 전략 |
| 2 | 에너지 지정학 & 인프라 | `energy` | 자원무기화, 상호의존의 무기화 (Farrell & Newman) |
| 3 | 기술 패권 & 보이지 않는 인프라 | `techno` | Techno-nationalism, Digital Iron Curtain |
| 4 | 인도-태평양 군사 대치 | `indo_pacific` | 동맹이론, A2/AD, 제1열도선 |
| 5 | 회색지대 & 비전통 안보 | `gray_zone` | Hybrid Warfare, Gray Zone Strategy |
| 6 | 사이버 안보 & 인지전 | `cyber` | Information Operations, APT 귀속, Cognitive Warfare |

**섹터 구분 원칙**:
- `techno`: 반도체·5G·공급망 등 기술 패권의 **구조적·경제적** 차원
- `gray_zone`: 비국가 행위자, 프록시전, 하이브리드전의 **물리적** 차원
- `cyber`: 사이버 공격·방어·인지전의 **작전적** 차원 (2026년 이란전 사이버전, APT, 선거 개입 등)

---

## 2. MVP 레이어 (Phase 1~2 구현 순서표) → 이관: `docs/archive/constitution_annex_20260710.md` — 구현 현황은 frontend/src/layers/ 실측이 진실원 (실측 2026-07-10: 12레이어 구현, 표의 10번 NetBlocks/IODA는 미구현)

---

## 3. CASCADE ANALYSIS (★ 핵심 차별 기능 ★)

### 3.1 데이터 모델

모든 데이터는 **Event**로 정규화된다. 레이어가 무엇이든 결국 Event 테이블에 쌓인다.

```python
class Event(BaseModel):
    id: str                          # uuid
    timestamp: datetime              # UTC
    source_type: str                 # "conflict" | "market" | "infra" | "naval" | ...
    source_id: str                   # 원본 소스의 식별자
    location: tuple[float, float]    # (lat, lon), 없으면 region 사용
    region_code: str | None          # ISO 또는 자체 region 코드 (예: "taiwan_strait")
    severity: int                    # 0-100, 정규화된 심각도
    title: str
    description: str
    payload: dict                    # 소스별 원본 데이터
    theory_tags: list[str]           # ["A2AD", "gray_zone", ...]
```

```python
class CascadeLink(BaseModel):
    id: str
    source_event_id: str
    target_event_id: str
    time_delta_seconds: int
    correlation_score: float         # 0-1
    link_type: Literal["rule", "statistical", "manual"]
    rule_id: str | None              # 룰 기반인 경우
    evidence: dict                   # 근거 (지역 매칭, 시간 윈도우 등)
    theory_ref: str | None           # 관련 이론 (학습 노트)
```

### 3.2 Cascade Rule Book (구현 핵심)

룰은 **YAML 파일**로 관리한다. 코드 수정 없이 룰만 추가하면 새 인과관계가 등록된다.

```yaml
# /config/cascade_rules.yaml
- id: taiwan_strait_to_tsm
  name: "대만해협 군사긴장 → TSMC 주가"
  trigger:
    source_type: military_flight
    region: taiwan_strait
    severity_min: 50
  expected_response:
    source_type: market
    ticker: "TSM"
    direction: down
    window_hours: 24
    threshold_pct: 1.0
  theory:
    framework: "Weaponized Interdependence"
    reference: "Farrell & Newman (2019)"
    learning_note: "반도체 공급망 집중도가 정치적 충격에 어떻게 전이되는지 관찰"

# (두 번째 완성 예시 hormuz_tension_to_oil → docs/archive/constitution_annex_20260710.md · 실룰 전수는 config/cascade_rules.yaml)
```

### 3.3 Cascade Engine 책임

```
/services/cascade/
  ├── engine.py          # 메인 엔진: 새 Event 발생 시 룰 평가
  ├── rule_loader.py     # YAML 룰 로드 & 검증
  ├── correlation.py     # 통계적 상관분석 (Phase 2)
  └── graph_builder.py   # 그래프 구조 빌드 (시각화용)
```

새 Event가 들어오면:
1. `engine`이 모든 룰을 평가
2. trigger 조건에 맞으면 expected_response 윈도우 동안 대기
3. 윈도우 안에 매칭 이벤트 발생 → `CascadeLink` 생성
4. 시각화 레이어로 푸시

### 3.4 시각화 (3-View System)

| 뷰 | 라이브러리 | 용도 |
|---|-----------|------|
| 지도 뷰 | Leaflet | 공간적 인과관계 (점선 화살표) |
| 타임라인 뷰 | vis-timeline | 시간순 이벤트 배열 |
| 인과 그래프 뷰 | Cytoscape.js | 한 이벤트의 상하위 노드 트리 |

**전환 원칙**: 같은 이벤트를 세 뷰에서 모두 클릭 가능. ID 기반 연동.

---

## 4. TECH STACK (확정)

### Backend
- **FastAPI** (Python 3.11+)
- 비동기: `httpx`, `asyncio`
- 데이터 검증: `pydantic v2`
- 스케줄러: `APScheduler` (cron 패턴)
- DB: **Phase 1** SQLite + JSON 컬럼 → **Phase 2** PostgreSQL + TimescaleDB
- 캐시: `cachetools` (메모리) → Redis (필요 시)
- 룰 엔진: YAML + Python 직접 평가 (외부 룰엔진 라이브러리 불필요)

### Frontend
- **Vanilla JS** ES6 모듈 (빌드도구 없음)
- 지도: **Leaflet** + `leaflet.markercluster` + `leaflet.heat`
- 타임라인: **vis-timeline**
- 그래프: **Cytoscape.js**
- 차트: **uPlot** (시장 지표용, 가벼움)
- 스타일: CSS 변수 기반 토큰

### 인프라
- 로컬 개발 우선, 배포는 마지막 단계
- Git + GitHub (private repo 권장)
- `.env` + python-dotenv (절대 키 커밋 금지)
- 배포 시 Fly.io / Railway / Render 무료 티어

---

## 5. 아키텍처

구조는 **코드가 진실원** — 실측하라 (트리 스냅샷은 `docs/archive/constitution_annex_20260710.md`).
핵심 경계 2칙: **connectors/ = 1소스 1파일 (base.py 공통 인터페이스)** · **services/normalize.py = 원본→Event 변환 단일 관문**.

---

## 6. 학습 보조 기능 (정치외교학 전공자 특화)

### 6.1 Theory Panel
이벤트 클릭 시 우측에 **관련 이론 카드**가 자동 표시:
- 이론 이름 + 주요 학자
- 한 줄 요약
- 현재 이벤트와의 연결 설명
- 추천 읽기 자료 링크 (논문, 보고서)

### 6.2 Study Mode (학습 모드)
사이드바 토글로 전환:
- **Brief Mode**: 일반 사용 (대시보드)
- **Study Mode**: 이론 태그 강조, 인과관계 자동 하이라이트, 노트 입력창 상시 표시

### 6.3 Notebook (개인 노트)
이벤트별로 메모 저장 (로컬 SQLite). 추후 마크다운으로 내보내기.

### 6.4 Case Study Library
대표 사례를 미리 저장 (예: "2022 펠로시 대만 방문", "2023 홍해 후티 공격"):
- 클릭 시 해당 시점으로 지도 시간 이동
- 당시 발생한 모든 이벤트와 cascade 자동 표시
- 관련 이론과 함께 학습 가능

---

## 7. CODING STANDARDS (비전공자 친화)

### Python
- 타입 힌트 필수, 모든 함수에 docstring (한국어 OK)
- async는 외부 I/O가 있을 때만, 단순 함수는 sync 유지
- 외부 API 응답은 반드시 **connector에서 Event로 정규화** 후 반환
- 에러는 절대 무시 금지 — 최소 `logger.warning`

### JavaScript
- ES6 모듈, default export 지양
- 함수형 우선, 클래스는 매니저급에만
- 모든 비동기는 async/await
- DOM 셀렉터는 파일 상단 const로 추출

### 공통
- 매직 넘버 금지 → `config/`로 추출
- 한 함수 = 한 책임, 50줄 초과 시 분리 검토
- 주석: **"왜"**를 설명. 정치외교학적 이유도 코멘트로 남기면 좋음
  ```python
  # 호르무즈는 글로벌 원유 운송의 약 20%가 통과하므로 severity 가중치 1.5배
  severity *= 1.5 if region == "hormuz" else 1.0
  ```

---

## 8. 성능 원칙

### 지도 렌더링
- 1,000+ 마커 → 무조건 `markercluster` 또는 `L.canvas()`
- `preferCanvas: true` 기본
- 줌/팬 이벤트는 `debounce(150ms)` + `requestAnimationFrame`
- bbox 기반 lazy load (`map.getBounds()` 활용)
- 레이어 토글은 데이터 재요청 없이 visibility만 변경

### 데이터 전송
- 응답은 gzip 압축
- 좌표 정밀도 5자리 (1m)
- 실시간 데이터는 **SSE** 우선 (WebSocket은 양방향 필요할 때만)
- 폴링은 최소 60초 간격

### Cascade 계산
- 이벤트 들어올 때마다 전체 룰 평가 = O(rule 수). 룰 100개 이하면 즉시 계산 OK
- 통계적 상관은 nightly batch로
- 결과는 `CascadeLink` 테이블에 영속화 → 매번 재계산 금지

---

## 9. RESPONSE PROTOCOL (Claude의 답변 규칙)

사용자가 요청하면:

1. **요청 분류**: ①신규 레이어 ②cascade 룰 ③버그 ④아키텍처 결정 ⑤이론 매핑 ⑥일반 학습 질문
2. **컨텍스트 명시**: 어느 파일·모듈에 영향 (예: `connectors/acled.py`, `cascade_rules.yaml`)
3. **변경 영향 선언**: 어떤 다른 부분에 파급되는지
4. **코드 제시**: 변경 부분만, 전체 파일 덤프 금지
5. **검증 단계 제안**: 어떻게 테스트할지

### 이론과 코드 연결
새 cascade 룰이나 새 레이어를 도입할 때, **관련 정치외교학 이론을 1~2문장으로 명시**한다. 사용자가 학습 도구로 쓰기 때문에 이게 중요하다.

예시:
> 이 룰은 Farrell & Newman의 "Weaponized Interdependence" 이론을 적용한 것입니다. 글로벌 공급망의 비대칭성이 정치적 무기로 전환되는 메커니즘을 관찰하는 데 사용됩니다.

### 비전공자 배려
- AI가 자동 생성한 코드도 사용자가 한 줄씩 이해할 수 있도록 **핵심 부분에 한국어 주석** 첨부
- 새 라이브러리 도입 시 "왜 이걸 쓰는가" 1~2줄 설명
- "Phase 1 / Phase 2" 식으로 단계 분리해서 부담 줄일 것

### [필수] 항상 쉽게 설명할 것 (Explain-Simply Rule)
이 프로젝트는 이미 사용자의 학업 수준(정치외교학 학부생)을 **넘어선** 방법론을 다룬다
(HARKing·사전등록·이벤트스터디·Granger·합성통제·삼각측량 등 박사/대학원 통계·인과추론 개념).
따라서 모든 설명은 다음을 **기본값**으로 한다:

- **전문용어가 나오면 즉시 일상어 비유로 풀어라.** (예: HARKing → "화살 쏜 뒤 과녁 그리기")
- 영어/통계 약어는 **한 번은 한국어 뜻**을 같이 적는다. (예: pre-registration = "데이터 보기 전 가설 미리 선언")
- **결론을 먼저, 근거는 그 다음.** 어려운 수식·코드는 "이게 왜 중요한가"를 한 문장으로 먼저 말한다.
- 사용자가 "쉽게 설명해줘"라고 하면 **자존심 상하지 않게**, 비유와 그림(표·도식)으로 다시 푼다.
- 사용자가 모른다고 가정하는 게 무례가 아니라 **배려**다. 의심되면 풀어서 설명하는 쪽을 택한다.
- 단, 코드·변수명·파일 경로 등 **정확성이 중요한 것은 쉬운 말로 바꾸지 말고** 정확히 쓰되 옆에 뜻을 단다.

---

## 10. 안티패턴 (절대 금지)

- ❌ 모든 데이터를 클라이언트로 한 번에 전송
- ❌ 외부 API 응답 스키마를 프론트에 직접 노출 (Event 정규화 필수)
- ❌ Cascade 룰을 코드에 하드코딩 (반드시 YAML)
- ❌ 마커 1만 개 직접 추가 (클러스터링/캔버스 사용)
- ❌ 색상·임계값을 컴포넌트에 하드코딩
- ❌ 데이터 없이 시각화 먼저 (Event 모델 먼저 설계)
- ❌ "정치적으로 민감"하다고 데이터를 임의로 검열·왜곡
- ❌ 비전공자가 이해 못 한 채로 코드 진행

---

## 10-A. 버전 관리 규칙

`backend/config/version.json` 은 **단일 진실 공급원(Single Source of Truth)** 이다.

```json
{ "version": "3.0.0", "phase": 3 }
```

### 업데이트 시점
- **Phase 전환 시**: `phase` 번호 올림 + `version` 메이저 버전 올림 (예: 2.x.x → 3.0.0)
- **주요 기능 완료 시**: `version` 마이너 올림 (예: 3.0.0 → 3.1.0)
- **버그 수정 / 소규모 변경**: `version` 패치 올림 (예: 3.0.0 → 3.0.1)

### 절대 하지 말 것
- ❌ `index.html` 또는 JS 파일에 버전 문자열 하드코딩
- ❌ `main.py` FastAPI 앱 `version=` 파라미터를 version.json과 따로 관리

### progress.md 완료 기록 시 함께 할 것
작업 완료를 progress.md에 기록할 때, 해당 작업이 마이너 이상 변경이라면
`version.json`도 함께 bump한 뒤 두 파일을 같은 커밋에 포함한다.

### progress.md 로테이션 규약 (볼트 점검 2026-07-10)
Phase/사이클에 ✅ 완료를 마킹하는 시점에 그 상세 로그를 `docs/archive/progress_history.md`로
즉시 로테이션하고, 본문에는 3줄 요약+포인터만 남긴다 (Phase 0~8 관행의 명문화 —
스냅샷 슬림, 이력은 아카이브). 위반은 geo-os spotcheck 검사 10(30KB 임계)이 감시.

---

## 11. PHASE ROADMAP

> 상세 스펙 아카이브: `docs/archive/phases_3_7_specs.md`

### 완료된 Phase 요약 (Phase 0~7) → 이관: `docs/archive/constitution_annex_20260710.md` (상세 스펙은 기존 `docs/archive/phases_3_7_specs.md`)

### Phase 8 — 박사 수준 추론 (PhD-level reasoning) — ✅ 완료 선언 (2026-07-12 게이트 재정의 비준)

> 〔게이트 재정의 비준 — 2026-07-12 사용자, geo-os [[20260712-phase8-gate-redefinition]]〕
> **Type_B 15% 게이트 폐기** — 목표 달성 수단이 쿼리 회피·측정 치환뿐이라 게이트 자체가 반정직 유인
> (typeB-rerouting 판례와 정의 충돌). 취지("측정불가 H1 남발 억제")는 8-gate(v8.12.0)·조달 게이트
> (v9.34.0)·치환 잠금(v9.46.0) 3종 구조가 대체. **대체 수치 목표 신설 안 함** — Type_B 조달 커버리지는
> report-only 관찰 지표로만(Goodhart 회피). 가드: var_type 분류기 변경=계측기 변경, CHANGELOG splice 의무.
> **완료 게이트 = 3조건 축소, 전 조건 충족 실측**: 종합 ✅(직영 4.39 — 아래 표 3.8은 구 눈금, 구 눈금
> 기준으로도 3.958 충족 이력) · 경쟁이론 ✅(직영 4.18, 구 눈금 이력 4.53) · **Granger ✅**(VERIFIED 3 +
> 구조적 승격 라우팅) → **완료 선언**. 실행은 Phase 9-Q 병행 계속 — 완료는 게이트의 종결이지 추론 개선의 종결이 아님.

목표: 인사이트 분석 엔진을 석사 중반(3.68/5) → 박사 수준(3.8/5+)으로 업그레이드.
**시각화 아님** — 엔진 자체의 추론 깊이를 높인다. (구 Phase 8 시각화는 Phase 12로 이동)

**게이트(착수)**: Phase 7-D 핵심 데이터 적재 ✅ + v7.8.9 측정 완료 (Phase 8 게이트 충족 확인)

**완료 게이트 (박사 수준 선언 — 3조건, 2026-07-12 재정의 비준. 구 4조건 중 Type_B 폐기)**

> 〔2026-06-17 게이트 조정〕 LLM 심판 변동성(±0.2~0.3)·측정 노이즈 현실화. 기존 4.2/4.0은 단기 달성 불가 수준 → 현 최고치(종합 3.58·경쟁이론 3.53) 기준 한 사이클 stretch로 조정.

| 조건 | 현재(v7.8.9) | 목표 |
|------|-------------|------|
| LLM 심판 종합 | 3.68/5 | **3.8/5+** |
| 경쟁이론엄밀 | 3.43/5 | **3.6/5+** |
| ~~Type_B 비율(측정불가 H1)~~ | 41%→37.8% | ~~15% 미만~~ **폐기(07-12 비준)** — 조달 커버리지 report-only 관찰로 대체 |
| Granger | 0 유의 | **2건 유의(p<0.05) 또는 구조적 설명 승격** |

> ⚠️ Granger 정직성 가드 (v8.12.0 개정): 유의가 안 나오면 →
> (a) 변수가 비선형·체제류면 **선형검정 대상에서 제외**하고 구조적 논증으로 명시한다
>     (선형검정 부적합 게이트 — `hypothesis_extractor._classify_linear_testability`).
> (b) 비선형을 주장하려면 **임계회귀(TAR)·체제전환 등 적극적 비선형 검정으로 양성 증거**를 제시한다.
> 선형검정의 실패(p≥0.05) 자체를 비선형의 증거로 쓰지 않는다 (affirming-the-null 금지).
> 점수 위해 유의를 조작하면 기각 (정직성 > 프록시).
>
> 〔개정 배경〕 체제 변수("러시아 체제 구조 → 전쟁 지속")는 임계·체제전환으로 작동하는데
> 선형 Granger에 대리쌍으로 강제 투입한 뒤 그 실패를 "비선형 발견"으로 승격하던 것은
> 논리적으로 affirming the consequent였다. 게이트가 이를 선택 단계에서 차단한다.

**측정 근거·Cycle 이정표(v7.8.9 기준)** → 이관: `docs/archive/constitution_annex_20260710.md`

> ※ 구 8-E(비선형 검정 B안)는 **Phase 9 — 분석틀 다변화의 9-C로 이동**. 비선형 검정도
> "분석틀"이므로 Method Router 체계와 함께 다루는 게 일관됨.

> **8-gate (v8.12.0 완료)**: 선형검정 적합성 게이트 — 체제·임계 변수를 선형 Granger 트랙에서
> 제외하고 "구조적 논증"으로 분류. null→비선형 승격(affirming-the-null) 제거. 그 제외된
> 변수들을 *적극적으로* 비선형 검정하는 것은 **Phase 9-C**(분석틀 다변화)에서 다룬다.

**융합 아키텍처 (병목·할루시네이션 방지, 전 과정 병행)**
1. 관련성 게이트 조립 — "예산 내 전부" → "관련성 상위 N개"
2. Token-Zero 산술 레이어 — 하드룰: Gemini는 서술만, 계산 금지
3. 출처·시점 정합성 린트 — 같은 지표 다른 값 충돌 플래그 + 연도 태그(시대착오 방지)
4. 프록시 가드 레지스트리 — "프록시 X는 A 뜻함, B 아님" 구조화 (ITU IDI·cascade score 등). 새 프록시 = 가드 등록 의무
5. 본문↔검증 정합 (O1) — 현재 Gemini 본문이 검증보다 *먼저* 확정돼 한 카드 안에서 모순 가능
   (`intel_query.py`: full_text 생성 후 가설 추출·검증). **근본 해법은 검증 먼저 → 본문 생성(2-pass)**.
   v8.12.1 interim: 프롬프트 10-b로 체제·비선형 변수의 본문 동사를 서버 8-gate 분류에 사전 정렬.

**범위 결정**: GTD(20만건)·ACLED 전세계 확장은 **8-D에서 필요 시에만**. 8-A~C는 기존 적재 데이터로 점수 선확보 (블라인드 적재 회피).

---

#### Cycle 8-F 세부 — 음성 결과 분류·진단 엔진 (Negative-Result Triage)

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

**탐색형 vs 확증형 2-레인 분리 (p-해킹 방어 핵심)**

| | 탐색형(exploratory) | 확증형(confirmatory) |
|---|---|---|
| 목적 | "다음에 *무엇을* 검증하나" 제안 | 사전 등록 가설 검정 |
| 출력 | 가설·연구공백 제안 (발견 아님) | 등급 부여 가능 |
| 라벨 | 항상 `[탐색적]` 강제 | `[검증포인트] 충족` |
| 등급 상한 | `상관` 초과 금지 | 사다리 전체 |

**자동 재검정을 허용할 경우(선택)의 가드 3종 (없으면 탐색만)**
- 사전 등록: 어떤 후보를 볼지 미리 고정 (탐색트리 동결)
- 다중검정 보정: 전체 탐색트리에 FDR 적용 (`verifier.py:561` 기존 BH 보정 확장)
- 홀드아웃: 발견은 out-of-sample 재현돼야 하며, 무조건 `exploratory=True`

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

### Phase 9 — 분석틀 다변화 (Multi-Method Analytical Engine) ⬅ Phase 8 다음 목표 (2026-06-17 확정)

목표: **Granger-dispatcher → Method-router.** 분류 출구가 "Granger 변종 아니면 폐기"뿐이던
단일 분석 구조를, 쿼리 직후 **데이터 모양으로 최적 방법에 직행**하는 다중 분석 엔진으로 전환한다.
인과추론 사다리의 빈 칸인 **'준실험(quasi-experimental)'**을 채워 인과 신뢰도 천장을 올린다.

**배경** → 이관: `docs/archive/constitution_annex_20260710.md` (순차 fallback 금지의 논거 — 규칙 자체는 아래 3원칙에 현존)

**게이트**: Phase 8(박사 수준 4게이트) 충족 후 착수. 9-C(비선형)·9-E(합성통제)는 데이터 6개월+ 누적 게이트
(단, backfillable 소스는 역사 백필로 즉시 충족 가능 — `backend/config/source_roster.yaml`·판례 20260709-data-audit-committee).

**원전 정독 게이트 (2026-07-09)**: 방법 구현 착수(9-A~E 각 사이클의 코드 작업 시작) 전에 **해당 방법 원전 본문을 정독**한다.
초록 기반 문헌 종합(geo-os wiki/literature)은 "어디로 갈지"(설계 방향·축 신설·공백 선언)까지만 감당하며,
"어떻게 지을지"(모델 스펙·추정량·진단·가정 검증)는 본문이 원천이다. 예: 9-C ⓑ축 착수 = Porter & White 2012,
9-E 착수 = Abadie 2010 + 2021 정독 선행. 초록으로 조달 불가한 수치·세부는 종합 문서 '공백' 절에 명기가 원칙(침묵 위조 금지).

**아키텍처 3원칙 (효율·정직)**
1. **선분류 라우터 + 사전 선언 방법집합** — 데이터 모양으로 *결과 보기 전에* 적용 가능한 방법 **집합
   {주 방법 1개 + 강건성 방법 0~n개}**을 결정. (`일발`의 뜻 = *순차 fallback ❌*, "방법 1개"가 아님.)
2. **방법별 지연 로드** — 집합 내 방법이 필요한 데이터만 로드 (비시계열 가설의 헛Granger 로드 제거).
3. **방법 실패 → 8-F 진단** — 다른 방법으로 점프 ❌, 진단·개선 제안 ✅ (method-level p-해킹 차단).

**다중 방법 = 삼각측량(triangulation), 승자 고르기 아님 [필수]**

둘 이상의 방법이 적용되는 경우는 흔하다(예: 호르무즈→유가는 이벤트스터디+Granger, SIPRI 패널은
횡단회귀+패널FE+Granger). 이때 방법들은 보통 *같은 질문을 중복*하는 게 아니라 **다른 단면**에 답한다
(이벤트스터디=국소·단기 / Granger=전역·lead-lag / 횡단=단위 간 / 패널FE=단위 내 / 합성통제=반사실).
따라서:

- **수렴(convergence)**: 서로 다른 식별 가정을 가진 방법들이 같은 결론 → **강건성↑ (단일 방법보다 강한 추론)**.
- **발산(divergence)**: 엇갈리면 그 엇갈림 자체가 발견 (예: "이벤트스터디 단기효과 有 + Granger 지속예측력 無 → 일시적·과도기 효과").
- 삼각측량의 힘은 방법들이 **서로 다른 가정·약점**을 가질 때 나온다. 같은 데이터·가정이면 일치해도 중복(독립 검증 아님).

**p-해킹 가드 (삼각측량도 이게 없으면 p-해킹)**
1. 방법 집합은 **데이터 모양으로 사전 선언** — 결과 주도 선택 ❌ ("1번 애매하니 2번 돌리자" 금지).
2. 집합 **전부 실행 + 전부 보고**(null 포함) + **FDR 보정**.
3. **수렴/발산을 해석**, 유의한 것만 골라 보고 ❌.
4. **헤드라인 등급 = 집합 내 가장 강한 *유효* 방법의 사다리 칸** (집합의 평균 ❌). 사다리 칸은
   *식별전략*이고 삼각측량 수렴은 *강건성*이라 서로 직교한다 → **수렴해도 칸은 승격하지 않는다**
   (상관적 방법 여러 개가 일치해도 준실험이 되지 않음). 수렴은 그 칸 *안에서 신뢰도(confidence)만* 올린다.

| # | Cycle | 방법 | 데이터 시그니처 | 사다리 칸 | 우선순위 | 상태 |
|---|-------|------|---------------|----------|---------|------|
| 9-P | 토대 수리 (Pre-flight) | 라우터 착수 전 선결 결함 4종(H1추출·진단독립성·방법오선택·출력2계층) | — | — | ★★★ 최선행 | ◐ 9-P-1/3/4 구현(routing_* 필드·2계층 SSE 실존), 9-P-2 매직넘버 config화 잔여 |
| 9-0 | Method Router + 평가계층 일반화 | 데이터모양 판정→**방법집합** 디스패치 + 삼각측량 종합 + **`_classify_inference_grade`를 방법 무관 grader로 일반화**(공통 사다리 계약) | — | — | ★★★ 선행 | ✅ services/methods/router.py·grader.py 구현 (classify_signature·select_method_set·filter_implemented) |
| 9-A | 이벤트 스터디 / ITS | 사건 전후 비정상변동 〔assumptions_met 문헌 명세: ①시장 합리성(사건 효과의 즉시 가격 반영, MacKinlay 1997) ②사건 창 오염(중첩 사건) — 9-A 게이트 시 어댑터에 구현, 문헌채택 20260709〕 | `SINGLE_SHOCK` (특정 날짜 단일사건) | 준실험 | ★★★ | ◐ event_study.py 구현·배선(ticker 전용). ⚠️ "actor_filter 부재 = 9-A 자물쇠" 구서사는 위원회 실측 기각(event_study는 event_archive 미참조, 판례 20260709-typeB-rerouting). 카운트 DV용 ITS는 원전 정독 게이트 후 별도 착수 |
| 9-B | 횡단/패널 회귀 | 고정효과 회귀 〔robustness 추가 항목: FE가 개체 간 안정 차이발 CLPM류 함정(인과 방향·부호 오류, Hamaker 2015)을 이미 차단하는지 민감도 점검 — RI 전면 구현은 과잉설계로 기각, 문헌채택 20260709〕 | `CROSS_SECTION` (국가간 비교·시간축 없음) | 상관~준실험 | ★★★ | ◐ panel_regression.py 구현·배선 + **Type_B CROSS_SECTION 조달 게이트 라우팅(v9.34.0)** — IV·DV가 `_VAR_CATALOG`에 모두 조달될 때만 9-B 진입(조달 실패 = 정직 PENDING, 측정 치환 금지). 라이브 발화 실증(횡단 OLS n_units=24 실검정). 잔여: ACLED/GDELT 카운트 DV 패널 신설(포아송류 — 원전 게이트 대상) |
| 9-C | 비선형 검정 (구 8-E) | ⓐ임계·체제 축: 임계회귀(TAR)·체제전환·전이엔트로피 ⓑ클러스터링·전염 축: 자기여기 점과정(Hawkes/샷노이즈)+허들 〔문헌채택 20260709: episodic 카운트의 적극적 출구, 데이터모양이 ⓐ와 달라 별도 축〕 | `NONLINEAR` (세분은 시그니처 표 참조) | 준실험 | ★★ | ⬜ 데이터누적 |
| 9-D | 네트워크/공간 모형 | 공간자기상관·네트워크 전이 | `NETWORK_DIFFUSION` (전이·확산) | 준실험 | ★★ | ⬜ |
| 9-E | 합성통제법 | 반사실 합성 단위 — 구현 경로 후보 2 **병기**(승자 미선정): 고전 합성통제(Abadie 2010) vs BSTS/CausalImpact(Brodersen 2015). 선택기준 사전선언: 공여자 풀 적합·사전 기간 적합(Abadie 2021) — 게이트 도달 시 기준 적용해 결정 (방법 선택도 결과 보기 전, 문헌채택 20260709) | `COUNTERFACTUAL` (단일단위 정책효과) | 준실험(최강) | ★ | ⬜ 데이터누적 |
| 9-G | 메타 평가(eval) 일반화 | `eval_insight.py`를 Granger-카운팅 → 방법론적 정직성 채점으로 전환 | — | — | ★★ (9-0 후) | ⬜ |

**Cycle 9-P 세부 — 토대 수리 (라우터 착수 전 선결, 설계 검토 미해결분)**

라우터·게이트의 판정 정확도가 이 4종에 달려 있으므로 9-0보다 **먼저** 처리한다.

| 항목 | 결함 | 수정 | 비고 |
|------|------|------|------|
| 9-P-1 | **H1 추출 버그** (DV 미식별, 두 가설 동일결과 붕괴) | `_RE_WHEN_THEN` 강화 + DV 미식별 폴백 + Granger 캐시 중복키 분리 | 게이트·라우터 토대 — **최우선** |
| 9-P-2 | **진단 독립성(L3)** | `theory_grounded` 단일실패점 분리(D3·등급 공유 해소) + `n_obs<40` 등 매직넘버 config화(§10) | 8-F 진단 정합 |
| 9-P-3 | **방법 오선택(L2)** | 라우터 판정 근거 로깅 + 라우팅 신뢰도/대안 플래그 → "성공해도 틀린 방법" 사후 점검 훅 | 9-0에 내장 |
| 9-P-4 | **출력 2계층화(O2)** | 표면(한 줄 결론 + 신뢰 한 단어) / 펼침(전체 진단·caveat) SSE·프론트 계약 | §0 비전공자 판독성 |

**Cycle 9-0 세부 — 평가 계층 일반화 (현재 평가가 Granger에만 묶인 문제 해소)**

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

정직성 가드 2종 (없으면 통합이 거짓동등을 만듦):
- **원본 결과 보존**: 칸으로 뭉개지 말고 native 추정치+방법명 항상 노출 (칸=비교용, 숫자=정직성용).
- **`assumptions_met`가 칸을 게이트**: 합성통제를 *썼다는 이유만으로* 준실험 칸 부여 금지 — 사전적합
  나쁘면 자격 박탈 ("method-type laundering" 차단).

**Cycle 9-G 세부·실행 순서** → 이관: `docs/archive/constitution_annex_20260710.md` (9-G 착수 시 정독. 평가 기준 발췌: 라우팅 일치 80%+·laundering 0·탐색누출 0)

**데이터 시그니처 → 방법 판정 (Token-Zero 결정론)**

| 시그니처 | 판정 신호 (기존 spec/쿼리 필드) | 방법 |
|---------|------------------------------|------|
| `UNQUANTIFIABLE` | linear_testable=False (8-gate) | 과정추적/구조적논증 |
| `SINGLE_SHOCK` | 쿼리/H1에 특정 날짜·명명 사건 (펠로시 방문 등) | 9-A |
| `CROSS_SECTION` | "국가들 사이 / ~일수록", 시간 진화 없음 | 9-B |
| `NONLINEAR` | 임계·체제 키워드이나 정량화 가능 — 세분: ⓐ임계·체제형(TAR류) vs ⓑ클러스터링·전염형(자기여기 점과정류). 판정신호는 8-gate가 이미 산출한 과분산·episodic 플래그 **재사용**(새 검출통계 설계는 9-C 게이트 시 — 데이터구동 라우팅 신설 금지, 문헌채택 20260709) | 9-C |
| `NATURAL_EXPERIMENT` | RDD(회귀단절)·IV(도구변수) 설계군 — **미구현 공백 선언**: COUNTERFACTUAL·SINGLE_SHOCK 어디에도 안 잡히는 설계군(Dunning 2012). 도입 여부 미정, 라우팅 대상 아님 (문헌채택 20260709) | (없음) |
| `NETWORK_DIFFUSION` | dependent_region 존재 + 전이/확산 프레임 | 9-D |
| `COUNTERFACTUAL` | 단일 단위 "X 없었다면" 반사실 (제재·전쟁) | 9-E |
| `PAIRED_TIMESERIES` | 짝지은 정상 시계열 (기본) | Granger (기존) |

**구현 파일**: `services/methods/` 신설 — `router.py`(방법집합 결정 + 삼각측량 종합) · `event_study.py` ·
`panel_regression.py` · `nonlinear.py` · `network.py` · `synthetic_control.py`. `hypothesis_verifier.py`는
라우터 호출로 전환. 인과추론 사다리(`_classify_inference_grade`)에 '준실험' 칸 활성화.
라우터는 방법 1개가 아니라 **방법집합 + 수렴/발산 종합 결과**를 반환.

**평가 기준**
- 방법 라우팅 정확도: 골드셋 수동 라벨과 일치율 80%+ (방법집합 단위)
- '준실험' 등급 도달 인사이트 1건+ (Granger 천장 돌파)
- 삼각측량: 복수 방법 적용 케이스에서 수렴/발산 종합이 출력되는지 (전부 보고 + FDR 확인)
- 효율: 비시계열 가설의 헛Granger 로드 0
- 탐색→확증 누출 0 (8-F 가드 회귀 유지) · 결과 주도 방법 선택 0

---

### Phase 10~12 — 결과 검증·자기개선·시각화 (미래 로드맵) → 이관: `docs/archive/constitution_annex_20260710.md` (착수 시 정독 — Phase 10 게이트: Phase 9 가동 후 / 11: Phase 10 필수 / 12: 8+9+10 후 = NEOUL 착수 지점)
---

## 11-A. 미래 작업: Cascade 룰 체이닝 → 이관: `docs/CASCADE_RULE_CHAINING_PLAN.md`

**착수 전 의무**: 이관 문서의 **구현 조건 게이트 3종**(6개월 데이터 누적·Granger 검증 선행 등) 정독 후 착수 — 게이트 미충족 착수 금지.


---

## 12. 매 응답 자가 점검

- [ ] 6대 섹터(§1) 범위 안에 있는가?
- [ ] Event 모델로 정규화되는가?
- [ ] Cascade 분석에 기여하는가? (장기적으로)
- [ ] 정치외교학 이론과 연결 가능한가?
- [ ] 비전공자가 이해할 수 있게 설명되었는가?
- [ ] Phase에 맞는 작업인가? (단계 건너뛰지 않았는가)
- [ ] 무료/저가 자원만 사용하는가?

---

*이 시스템은 "보는 지도"가 아니라 "추론하는 지도"를 지향한다. 모든 결정은 사용자의 정치외교학 학습에 기여해야 한다.*

---

## 13. 토큰 효율 원칙

### 세션 시작
- progress.md만 읽고 시작 (CLAUDE.md 재정독 불필요)
- 시작 명령: "progress.md 읽고 오늘 시작점 알려줘. 바로 시작하자."

### 작업 중
- 파일 전체 읽기 금지 → 필요한 부분만
- 한 작업 완료 시 /clear로 컨텍스트 초기화
- 코드는 변경 부분만 제시 (전체 파일 덤프 금지)

### 사용자에게
- 매 세션 시작 시 이 원칙을 한 줄로 상기시켜줄 것
  예: "💡 토큰 절약: 작업 완료 시 /clear, 파일은 필요한 부분만 요청하세요"

---

## 14. LLM 사용 원칙 & Token-Zero Tagging Rule

### 14-A. [필수 원칙] Token-Zero Tagging
실시간 첩보(GDELT/RSS) 수집 시 7대 축 태그 부여에 Gemini/Claude API를 절대 호출하지 않는다.
반드시 `backend/utils/cameo_mapper.py`의 Deterministic 파이썬 로직으로 백엔드 1차 태깅을 완료해야 한다.

#### GDELT CAMEO 매핑 기준
| 태그 축 | 입력 필드 | 매핑 규칙 |
|---------|----------|----------|
| `level_of_analysis` | `Actor1Type1Code` | IGO/MNI → systemic, GOV/MIL/COP/LEG → state_domestic, REB/INS/NGO/CVL → non_state |
| `instrument_of_power` | `EventRootCode` | 01~05 → diplomatic, 16 → economic, 17~20 → military, 그 외 → informational |
| `strategic_posture` | `GoldsteinScale` | ≤ -5.0 → revisionist, 그 외 → status_quo |

LLM 호출은 **사용자가 명시적으로 요청한 "AI 설명 SSE"** 또는 **번역** 기능에만 허용된다.

**14-A 부칙 (T6 문헌채택 2026-07-10)**: 이 금지는 결정론 매퍼가 존재하는 모든 축으로 확장한다.
LLM 어노테이션의 crowd worker 대비 우위(Gilardi et al. 2023, 정확도 +25%p·30배 저렴)는 비용 0·재현성
완전의 결정론 매퍼에 대한 대체 근거가 되지 못한다. 도입 검토는 결정론 룰이 원리상 불가능한 축에
한정하며, 그 첫 실태스크에서 [판단필요]로 상정한다(선제 taxonomy 입법 금지 — geo-os 1-B).
근거: geo-os `wiki/literature/T6-llm-instrument-audit.md`

---

## 15. 데이터 모델 고도화 — 7대 축 다차원 태그 매트릭스

모든 `Event` 및 `library/*.md` 프론트매터에 아래 7개 필드를 강제 적용한다.

| 축 | 필드명 | 값 선택지 | 이론적 근거 |
|---|--------|----------|-----------|
| 1 | `form_type` | concept / case_study / norm / data_point | — |
| 2 | `geopol_region` | taiwan_strait / hormuz / bab_el_mandeb / eastern_europe 등 | 지오펜싱 코드 |
| 3 | `sector_lead` | maritime / energy / techno / alliance / gray_zone | 5대 섹터 |
| 4 | `temporal_era` | cold_war / post_cold / us_china_rivalry / **hot** (최근 7일) | 시대 배경 |
| 5 | `level_of_analysis` | systemic / state_domestic / non_state | Waltz 3수준 |
| 6 | `instrument_of_power` | diplomatic / informational / military / economic | DIME 프레임워크 |
| 7 | `strategic_posture` | status_quo / revisionist | Snyder 동맹 딜레마 |

Pydantic 모델: `backend/models/intelligence.py` → `IntelligenceMetadata`

---

## 16. 3단계 지정학 팩트체커 (Verification Funnel)

실시간 첩보는 `is_staging: bool = True` 상태로 버퍼에 먼저 적재된다.
아래 3단계를 통과하여 `confidence_score >= 0.8`에 도달해야 대시보드에 승격된다.

| Stage | 검증 방법 | 점수 보정 |
|-------|----------|---------|
| 1 | ACLED 베이스라인 대조 (지역별 과거 분쟁 패턴) | +0.1 |
| 2 | RSS 4대 매체 교차 검증 (Reuters·BBC·Al Jazeera·AP 중 ≥2개) | +0.2 |
| 3 | 물리 센서 결합 (반경 50km, 12시간 이내 FIRMS/AIS/ADS-B 이상 징후) | +0.1 |

초기값 0.5 → 최대 0.9. 미달 자산은 `is_staging: True` 유지, 3일 후 자동 삭제.
구현 파일: `backend/services/verification_funnel.py`

---

## 17. Stage 8 동맹 확산 (Alliance Diffusion) 알고리즘

글렌 스나이더 '동맹의 딜레마(Alliance Dilemma)' 계량화.

- `Diffusion_Score ≥ 80`: **동맹 연루(Entrapment) 위험** → Actor C의 군사 자산 레이어 점선 하이라이트
- `Diffusion_Score < 50` + 외교 성명 생략: **동맹 방기(Abandonment) 징후** → sanctions.yaml 교차 분석

`pact_intensity` 기준값: NATO=1.0, 조·러조약=0.90, 미·필리핀=0.85
구현 파일: `backend/config/alliance_graph.yaml`, Stage 8 로직은 `backend/services/reasoning/stages.py`

---

## 18. 계층형 데이터 보관 정책 (TTL)

| 소스 | 핫 테이블 보관 | 아카이브 이관 조건 | 완전 삭제 |
|------|-------------|-----------------|---------|
| GDELT/RSS | 3일 (72h) | confidence≥0.8 또는 importance≥0.7 → `event_archive` 영구 보존 | 미검증(≤0.5) 3일 후 자동 삭제 |
| ACLED | 상시 (1년 전 고정) | 인입 즉시 `event_archive` 영구 귀속 (베이스라인 상수) | 없음 |
| FIRMS | 24h | Cascade Link 매칭된 열점만 보존 | 미매칭 48h 후 삭제 |
| AIS/ADS-B | 12h 스냅샷 | 초크포인트·기지 주변 이상 로그만 보존 | 일반 로그 24h 후 소멸 |

구현 파일: `backend/db/archive_manager.py`

---

## 18-A. 소스 용도 경계 (문헌채택 20260709)

이벤트 소스는 **분석 층위**가 다르다. 기존 운용(§16 승격 게이트·§18 TTL 위계)의 명문화 + 층위 구분 1문장 신설:

| 소스 | 용도 층위 | 근거 |
|------|----------|------|
| **GDELT** | 전역 신호·트렌드 층 — **국가·region 이상 집계에서만** 사용 | 하위국가 분석에서 수작업 데이터와 상관 mediocre·심각한 지리 편향 (Hammond & Weidmann 2014) |
| **ACLED** | 하위국가·행위자 층 — 위치·날짜·행위자 정밀 코딩 | 코딩 정밀도가 설계 목적 (Raleigh et al. 2010) |

**신설 제약 (1문장)**: 하위국가 지오코딩 수준 분석에 GDELT를 단독 사용하지 않는다 — §16 게이트는 *이벤트 승격*을 막지만 *region 배정*은 게이트 이전 단계라 이 경계가 별도로 필요하다 (실증: north_korea region 오염, STATUS 큐 1-B).

> 언급(mention)과 발생지(location)를 구분하지 않는 region 배정은 Hammond-Weidmann이 실측한 편향을 엔진 내부에 재현한다. 근거 원문: geo-os `wiki/literature/T2-event-data-validity.md` · 판례: geo-os `wiki/decisions/20260709-wave1-adoption.md`

1. **ACLED 랙 규칙**: ACLED(학술 티어)는 event_date 기준 최대 ~14개월 랙 — **근과거(<14개월) 분석에 이벤트 건수를 증거로 쓰지 않는다** (신선도는 created_at, 분석 가용성은 event_date로 판단. 실측: source_roster.yaml acled 항목).
2. **구조적 미관측 규칙**: 폐쇄국가(북한 등) 내부 데이터갭은 수집 확장 대상이 아니라 **구조적 미관측** — UNQUANTIFIABLE(과정추적·구조적 논증) 트랙으로 라우팅하고 data_gap 수집 우선순위에서 제외한다 (판례 20260709-data-audit-committee).

---

## 19. 인사이트 엔진 생성 원칙 (2026-06 로드맵 반영)

### 19-A. 인사이트 생성 6단계 구조 [필수]

인사이트 분석실(`/api/intel/query`)의 Gemini 프롬프트는 반드시 아래 순서를 따른다.
현상 기술(description)에서 멈추지 말고 **인과 검증(causal verification)** 단계까지 진입할 것.

```
[단계 1] 관찰 — 측정 가능한 현상 서술 (수치·사례 포함)
[단계 2] 변수 — 독립변수·종속변수·통제변수 식별
[단계 3] 가설 — H1 반증 가능 형태로 공식화
          예: "X가 증가할 때, Y가 통계적으로 유의하게 변화한다 (통제변수 Z)"
[단계 4] 경쟁 이론 — 대안 설명 1~2개 나열 후 우선 기각 대상 선정
[단계 5] 데이터 — 사용된 소스 + 수치, 없으면 [UNVERIFIED] 태그 필수
[단계 6] 연쇄 고리 강도 자기평가
          HIGH(>70%) / MEDIUM(40~70%) / LOW(<40%)
          MEDIUM 이하 고리 포함 연쇄 → [SPECULATIVE] 레이블 명시
```

### 19-B. 인사이트 카드 출력 형식 표준 [권장]

※ 신뢰도 숫자 점수는 서버(IA-Engine-C)가 독점 산출 — Gemini 출력에 포함 금지.

```
[헤드라인] 한 줄 요약 (비자명적 발견 — "A가 증가했다" 수준 금지)
데이터기반: 고/중/저  |  이론근거: 고/중/저  |  연쇄강도: HIGH/MEDIUM/LOW

[관찰]      측정 가능한 현상 (수치·날짜·사례 포함, 없으면 [UNVERIFIED])
[주장]      인과 주장 — 방향·강도·조건 명시
[가설]      H1: "X가 증가할 때 Y가 통계적으로 유의하게 변화한다 (통제변수 Z)" 형태
[근거]      데이터 소스명 + 수치 (없으면 [UNVERIFIED])
[한계]      이 분석이 답하지 못하는 것
[경쟁설명]  대안 이론 A: 설명 / 반례: 〜할 경우 설명력 하락
            대안 이론 B: 설명 / 기각 근거: 〜
[검증포인트] 다음 세션에서 확인할 지표·소스
[문헌공백]  기존 연구가 이 패턴을 충분히 다루지 않는 이유
```

### 19-B-3. 시간 역전 탐지 [필수 — v6.0.0 추가]

각 인과 연결 고리에서 원인·결과 이벤트의 날짜를 반드시 확인한다.
결과 이벤트가 원인 이벤트보다 이전에 발생한 경우:
- `[TEMPORAL_REVERSAL]` 태그 필수
- 주장을 "A가 B를 유발" → "공통 구조적 선행 조건" 또는 "B가 A의 선행 지표"로 재공식화
- 인사이트 주장을 수정하지 않은 채 [한계]에만 언급하는 것은 금지

### 19-B-2. 유지·확장할 강점 [필수 보존]

아래 세 가지는 학부 수준 대부분의 분석 도구가 하지 못하는 기능이다.
개선 과정에서 **절대 약화시키지 말 것.**

#### ① 다중 이론 프레임 자동 연결
행위자 프로파일(revisionist·gray_zone 등)에서 방어적 현실주의·동맹 이론·비대칭 위협 이론을 자동 매핑하는 기능.
→ **유지하되, 이론 레이블에 "이 이론으로 설명되지 않는 반례" 필드를 항상 추가할 것.**

```
예시:
이론: Weaponized Interdependence (Farrell & Newman)
설명: 반도체 공급망 집중이 미국의 대중 레버리지로 작동
반례: 중국이 SMIC를 통해 자립화할 경우 이 프레임의 설명력 하락
```

#### ② 다중 도메인 교차 분석
군사·에너지·사이버 도메인을 동시에 포착하는 기능은 단일 도메인 도구 대비 명확한 우위.
→ **인사이트 생성 시 "어떤 도메인이 어떤 경로로 어떤 도메인에 영향을 미치는가"를 명시적으로 서술할 것.**

```
예시:
[사이버 → 에너지] 이란전 사이버전(844호)에서 진화한 PLC 공격 기술이
우크라이나 에너지 인프라 공격에 전이될 경로와 조건
```

#### ③ 독창적 패턴 포착 — 문헌 공백 탐지 [최고 경쟁력]
"유리 턱(Glass Jaw)", "역외균형자 vs 전방배치 헤게몬 긴장", "이란-러시아 전술 전이 가설"처럼
**기존 문헌에서 충분히 검증되지 않은 공백을 겨냥하는 것**이 핵심 경쟁력.
→ **인사이트 생성 프롬프트에 항상 명시적으로 요구할 것:**

```
"기존 주류 문헌이 충분히 다루지 않은 공백(gap)을 탐지하라.
 이미 알려진 사실을 재서술하는 것은 인사이트가 아니다."
```

### 19-C. 절대 금지 패턴

- ❌ "A → B를 시사한다" / "가능성이 높다" 로만 끝내는 것 → 반드시 고리 강도 명시
- ❌ 대안 설명 기각 과정 없이 단일 이론으로 수렴
- ❌ 결과를 곧바로 의도로 귀속 ("강경 정권 온존 = 미국 실패" 형태)
- ❌ 수치 근거 없는 인과 주장 → [UNVERIFIED] 태그 없이 서술

### 19-D. 인사이트 신뢰도 산출 기준

배점의 진실원은 **코드**: `backend/services/confidence_scorer.py` (문서 배점표는 코드와
드리프트가 실측돼 2026-07-10 포인터화 — 1-A "충돌 시 원천 승").
**[필수] 불변 규칙**: 합계 0~100 · **60 미만은 [PROVISIONAL] 레이블**(provisional=True).

---

## 20. IA-Engine-D 계약 (현행 — §20-A H1 스키마 · §20-B 신뢰도 캡 [필수])

### 20-A. H1 자동 생성 출력 스키마

```python
{
  "H1": "X가 증가할 때 Y가 통계적으로 유의하게 감소한다 (통제변수: Z1, Z2)",
  "H0": "X와 Y 사이에 통계적으로 유의한 관계가 없다",
  "independent_var": "미국 CPI",
  "dependent_var": "Kiel Tracker 월별 지원액",
  "control_vars": ["선거 주기", "지정학 위기 강도"],
  "data_sources": ["FRED CPI", "Kiel Institute"],
  "lag_estimate": 3,            # 개월
  "verification_status": "PENDING",  # PENDING → PARTIAL → VERIFIED
  "granger_p": null             # 검증 후 채워짐
}
```

### 20-B. 신뢰도 상한 캡 규칙 [필수]

> ⚠️ 문서-코드 드리프트 (게이트위 실측 2026-07-11): 아래 캡 함수(`apply_verification_cap`)는
> 코드에서 폐기(DEPRECATED, `confidence_scorer.py` — 2축 분리로 대체)돼 더는 호출되지 않는다.
> 1-A "충돌 시 원천 승" — 진실원은 코드. 이 절은 이력 참조용이며, verification_status의 하류
> 소비 규약은 geo-os `wiki/decisions/20260711-granger-substitution-gate.md` 참조.

```python
if verification_status == "PENDING":   confidence_score = min(confidence_score, 75)
if verification_status == "PARTIAL":   confidence_score = min(confidence_score, 88)
if verification_status == "VERIFIED":  # 상한 없음 — Granger p<0.05 자동 충족 시
```

### 20-C. 박사 수준 도달 기준 체크리스트 → 이관: `docs/archive/constitution_annex_20260710.md` (이정표 이력 — 07-09 Korea 재유도 정정 포함)
