# 융합1 — 관련성 게이트 조립 (구현 핸드오프)

> 설계: Opus (2026-06-07). 구현: Sonnet 세션용. Phase 8 첫 사이클.
> **목표**: 23소스를 "예산 내 고정순서 전부" → "관련성 점수 상위 N개만" 주입.
> **측정**: 레이턴시↓. 가드: PASS율·경쟁이론 수치비교율 무회귀.

---

## 0. 대상 파일

- `backend/services/intel_analyzer.py` (단일 파일 작업)
  - `_build_context()` (L1008~) — 조립 로직
  - `build_intel_context()` (L1505~) — `theory_cmp_ctx` append 부분 (L1582~1586)
- 버전: `backend/config/version.json` 마이너 bump (7.8.9 → 7.9.0)

## 1. 진단 (왜 하는가)

`_build_context`는 23소스를 **하드코딩 고정 순서**로 budget(`_CONTEXT_MAX_CHARS=20000`자)
찰 때까지 채운다. 결과:

1. **순서 = 우선순위** 고착. 쿼리가 cyber인데 CSIS(11번째)·ITU(18번째)는 앞쪽
   무관 소스가 budget 먹은 뒤 잘림. 무관한데 앞에 있는 소스는 전문 주입 → 환각.
2. **`theory_cmp_ctx`(경쟁이론 수치비교)가 맨 끝 잔량 append**(`intel_analyzer.py:1583`,
   `remaining > 500`). Phase 8 핵심 블록인데 23소스가 budget 다 먹으면 통째 누락.
   → v7.8.9 경쟁이론 점수(3.43) 들쭉날쭉의 구조적 원인.

## 2. 설계 — 3-tier + 관련성 점수

### 2-A. 소스 3-tier

| tier | 소스 | budget 취급 |
|------|------|-----------|
| **backbone** | 쿼리요약·브리핑원문·이론프로파일·cascade룰·cascade실적·이벤트통계·국가프로파일 | 무조건 먼저, gate 없음 (기존 인라인 유지) |
| **priority** | `theory_cmp_ctx` (경쟁이론 수치비교) | backbone 직후 **우선 확보** (잔량 append 폐지) |
| **data** | sipri_milex·cow_alliances·kiel·eia·csis·sipri_arms·vdem·cow_wars·ifans·fred·wbk·polity5·itu·hiik·semi·owid·trade (17개) | **관련성 점수순**으로 잔여 budget 경쟁 |

### 2-B. data 소스를 emitter 함수로 추출

현재 각 data 섹션은 `if x and not _over_budget(lines): lines.append(...)` 형태.
이를 **블록을 만들어 반환하는 순수 함수**로 분리한다 (lines를 직접 안 건드림):

```python
def _emit_sipri(sipri_data) -> list[str]:
    """SIPRI 국방비 블록 생성. 빈 입력이면 []."""
    if not sipri_data:
        return []
    out = ["## 국방비 추이 (SIPRI 2023, % of GDP / USD billion)"]
    # ... 기존 로직 그대로, lines.append → out.append ...
    out.append("")
    return out
```

17개 data 소스 전부 동일 패턴으로 추출. **블록 내부 텍스트 포맷은 1글자도 바꾸지 말 것**
(eval 회귀 방지 — 내용 동일, 순서·포함여부만 달라져야 함).

### 2-C. 소스 스펙 테이블 (모듈 레벨, `_SOURCE_SPECS`)

각 data 소스의 섹터 친화도 선언. 섹터 값은 CLAUDE.md §1 sector_tag 사용
(maritime·energy·techno·indo_pacific/alliance·gray_zone·cyber).

```python
# key: 소스 식별자 / sectors: 주 관련 섹터(빈 set=범용) / emitter: 블록 생성 함수
_SOURCE_SPECS: dict[str, dict] = {
    "sipri_milex":   {"sectors": {"indo_pacific", "alliance"}},
    "cow_alliances": {"sectors": {"indo_pacific", "alliance"}},
    "kiel":          {"sectors": {"alliance"}},          # 우크라 지원=동맹
    "eia":           {"sectors": {"energy", "maritime"}},
    "csis":          {"sectors": {"cyber"}},
    "sipri_arms":    {"sectors": {"indo_pacific", "alliance", "techno"}},
    "vdem":          {"sectors": {"gray_zone"}},         # 체제유형=취약국
    "cow_wars":      {"sectors": set()},                 # 범용(역사선례)
    "ifans":         {"sectors": set()},                 # 범용(한국시각)
    "fred":          {"sectors": {"energy"}},
    "wbk":           {"sectors": {"gray_zone"}},         # 거버넌스
    "polity5":       {"sectors": {"gray_zone"}},
    "itu":           {"sectors": {"cyber", "techno"}},
    "hiik":          {"sectors": {"gray_zone"}},
    "semi":          {"sectors": {"techno"}},
    "owid":          {"sectors": set()},                 # 범용(다지표)
    "trade":         {"sectors": {"techno", "energy"}},  # Comtrade HHI
}
```

> 친화도 확신 안 서면 `set()`(범용)으로. 범용은 페널티 없이 중립 점수.

### 2-D. 관련성 점수 함수 (Token-Zero — LLM 호출 절대 금지)

```python
def _score_source(spec: dict, records, pq) -> float:
    """data 소스 블록의 관련성 점수. 주제 적합성만 사용 — 가설 지지 여부 금지(§정직성)."""
    if not records:           # 빈 소스 = 제외
        return -1.0
    score = 1.0               # 데이터 존재 기본점
    src_sectors = spec.get("sectors", set())
    if src_sectors and pq.sectors:
        if src_sectors & set(pq.sectors):
            score += 2.0      # 섹터 적중
        else:
            score -= 1.0      # off-domain 페널티 (범용 소스는 src_sectors 비어 페널티 없음)
    score += _coverage_bonus(records, pq.regions, pq.actors)
    return score
```

`_coverage_bonus`: 반환 레코드(dict/list)를 문자열화해 pq.regions/actors 토큰이
실제 등장하면 region당 +0.5, actor당 +0.3 (상한 +2.0). 단순 substring 매칭으로 충분.
ISO3·한국어 별칭까지 정밀 매칭 불필요 — 점수는 **순위용 상대값**이지 절대 임계가 아님.

### 2-E. 게이트 조립 (정직성 가드 필수)

```python
# ⚠️ 정직성 가드 (메모리 feedback_honesty_over_judge):
#   관련성 점수는 '이 소스가 이 쿼리 주제에 관한가'만 판단한다.
#   '이 데이터가 결론/가설을 지지하는가'는 절대 점수에 넣지 않는다.
#   가설에 불리한 데이터를 관련성 낮다고 떨구면 체리피킹 = 환각이다.

# 1) backbone 인라인 emit (기존 코드 유지) → lines
# 2) priority: theory_cmp_ctx를 backbone 직후 우선 emit (budget 차감)
# 3) data: 점수순 정렬 후 budget 한도까지 emit
scored = []
for key, spec in _SOURCE_SPECS.items():
    records = _source_records[key]            # 아래 매핑
    s = _score_source(spec, records, pq)
    if s < 0:                                 # 빈 소스 제외
        continue
    scored.append((s, key))
scored.sort(key=lambda x: -x[0])             # 점수 내림차순

for _, key in scored:
    block = _SOURCE_EMITTERS[key](_source_records[key])
    if sum(len(l) + 1 for l in lines) + sum(len(l) + 1 for l in block) > _CONTEXT_MAX_CHARS:
        continue                              # 이 블록 넣으면 초과 → 건너뜀(다음 소스가 더 작으면 들어갈 수 있음)
    lines.extend(block)
```

> `_source_records`/`_SOURCE_EMITTERS`: key → 원본데이터 / key → emitter 함수 매핑 dict.
> `_build_context` 시그니처(23개 인자)는 그대로 두고 내부에서 이 두 dict로 묶으면 호출부 무변경.

### 2-F. theory_cmp 잔량 append 폐지

`build_intel_context` L1582~1586의 "잔량 append" 블록 제거.
대신 `theory_cmp_ctx`를 `_build_context`에 인자로 넘겨 **priority tier**로 budget 내 우선 emit.
(현재 `_build_context`는 theory_cmp를 안 받음 → 인자 추가 필요. 호출부 1곳만 수정.)

## 3. 2단계 budget 정책 (사용자 확정 2026-06-07)

- **1단계 (이 작업)**: `_CONTEXT_MAX_CHARS=20000` **유지**. 관련성 순서만 바꿈(품질 무손실).
  → eval로 PASS·경쟁이론 무회귀 확인 + theory_cmp 누락 해소 확인.
- **2단계 (1단계 eval 통과 후 별도)**: 로그로 무관 소스 실제 탈락 확인 후
  budget을 14~16k로 점진 축소 → 레이턴시 측정.

**이번 세션은 1단계까지만.** 2단계는 eval 결과 보고 결정.

## 4. 정직성·안티패턴 가드 (필수 준수)

- 점수 신호 = 주제 적합성(지역·행위자·섹터·밀도)만. 가설 지지 여부 금지 (§2-E 주석).
- 블록 텍스트 포맷 불변 — 내용 동일, 순서·포함여부만 변경.
- LLM 호출 0 (Token-Zero, CLAUDE.md §14-A).
- backbone은 절대 gate하지 않음 (분석 척추).

## 5. 검증 단계

1. `python -c "import backend.services.intel_analyzer"` — import·문법 확인.
2. 단일 쿼리 1개로 `build_intel_context` 호출 → 로그에서 data 소스 점수·탈락 확인
   (디버그 로그에 `[fusion1] key=score` 한 줄 추가 권장).
3. cyber 쿼리에서 CSIS·ITU가 상위에, energy 쿼리에서 EIA·FRED가 상위에 오는지 육안 확인.
4. **골드셋 eval**: `python backend/eval_insight.py --gold --judge --fast`
   - 가드: PASS율 ≥ 12/15, 경쟁이론 수치비교 ≥ 기존(100% [엄격] 무회귀).
   - 기대: theory_cmp 누락 0 → 경쟁이론 일관성↑.
5. 통과 시 progress.md 진행현황 `[융합1] ✅` + version.json 7.9.0 + 같은 커밋.

## 6. 완료 후 다음

융합2(Token-Zero 산술 레이어). 본 문서와 독립.
