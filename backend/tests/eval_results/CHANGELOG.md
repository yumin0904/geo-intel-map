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
