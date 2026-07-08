# eval baseline 이력

> `latest.json`은 git이 추적하는 유일 슬롯이라 덮어쓰면 이전 baseline이 diff 한 줄로 압축된다.
> judge(계측기)가 바뀌면 점수가 통째로 흔들리므로, **baseline 리셋 지점을 여기 기록**해
> 미래에 "judge 교체발 변화"를 "엔진 개선발 변화"로 오독하지 않게 한다.
> (날짜별 스냅샷 `YYYYMMDD_HHMM.json`은 gitignore — 로컬 전용. git 감사추적은 이 파일 + latest.json.)

## 2026-07-06 — DeepSeek judge baseline 리셋 (평가 위원회 채택)

- **런**: `20260706_1614` (33/33 pass, 서버 confidence 평균 91).
- **judge 전환**: 이전 커밋본(`20260704_0130`)은 `quality: null`(구 Gemini judge 구조, 점수 부재)
  → 신규는 **NIM DeepSeek-v4-pro** 4축 채점. **이전과 점수 절대 비교 불가**(계측기 교체).
  이 지점 이후 DeepSeek judge끼리만 비교한다.
- **4축 종합 4.00** (non_obviousness 4.0 · inference_honesty 3.58 · competing_rigor 4.67 · falsifiability 3.75).
  이 값은 평가 위원회가 이미 분석한 baseline과 정확히 일치.
- **성격**: 위원회 채택 개선 3건(①감사→eval fail 배선 ②H1/경쟁이론 대칭 UNVERIFIED ③H1추출 논평분리)
  **적용 이전** 스냅샷 = 개선 효과 측정의 "before" 기준선.
- **⚠️ 채택 시 병기된 caveat (위원회 조건부 YES)**:
  1. **4축 quality = n=12/33 확률표본** — 당시 judge `max_tokens=800`이 추론모델 `<think>`에
     소진돼 21건이 채점 실패(None). 종합 4.00을 하드 임계값으로 쓰지 말 것. (하네스 v9.26.0에서
     max_tokens 4000으로 수정 — **다음 런부터 커버리지 안정**.)
  2. **routing_low=7은 라우터 회귀 아님** — 정직한 unmappable Type_A 4건 + 논평혼입 아티팩트 3건
     (채택 ③ 미구현 증상). **실질 라우팅 이상 0**. 채택 ③ 구현 후엔 7→4로 떨어지므로,
     개선 측정 기준은 "실질 4건"으로 못박는다.

## 2026-07-08 — v9.28 재측정 (20260708_1252): 천장효과 붕괴, eval에 이빨

- **런**: 33케이스, `--parallel 6` 첫 병렬 실행. judge nim/deepseek-v4-pro (아티팩트에 신원 기록 — v9.26.0 수정 검증).
- **31/33 pass — 의도된 FAIL 2건** (houthi_red_sea_sloc·hormuz_redsea_contagion): 신규 비대칭 게이트
  (no_verdict_on_unverified)가 라이브로 잡은 실제 위반. **최초의 변별력 있는 eval** — 천장효과(항상 33/33) 종료.
- **v9.25~28 변경 전부 검증**: routing_low 7→4(논평분리 예측 적중) · 가설 65→55 · 비대칭 위반 5→2(프롬프트
  재유도 효과) · laundering/construct_launder/누출 0.
- **judge 사고와 수습**: 병렬 실행에서 judged 0/33 — 생성엔 재시도가 있고 judge엔 없던 비대칭으로 NIM 동시성
  충돌을 조용히 삼킴 → 재시도 3회 백오프 배선 + 저장 full_text 오프라인 백필(judge_backfill).
- **정성 baseline (백필 후, n=30/33)**: 종합 **3.958** — 비자명 3.80 · **정직성 3.83**(구 3.58, ②③ 표적 축 상승) ·
  경쟁엄밀 4.53 · 반증 3.67. 구 4.00은 n=12 절단 로터리 표본이라 절대 비교 금지 — **이 런이 실질 첫
  full-coverage 정성 baseline.**
- **후속 (v9.28.2)**: 잔존 FAIL 2건 검시 — 위반이 "정성 관찰(타당) + 가짜 수치 변환('0건') + UNVERIFIED·열세
  한 줄 공존" 하이브리드. 프롬프트 세칙 추가(정성 반대증거는 별도 기재 허용, 수치 변환·판정 근거 사용 금지)
  후 2케이스 재검 **2/2 PASS·위반 0**. 비대칭 위반 클래스 5→2→0 소멸. latest.json은 v9.28.0 정직
  스냅샷(31/33) 유지 — 혼합 런 프랑켄슈타인 방지. 차기 풀런에서 33/33 + 게이트 유지 기대.
