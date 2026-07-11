"""결정론 산출물 린트 — 전수 감사(48케이스, 2026-07-10)가 실증한 기계 검출 가능 결함.

개선위 판정: judge(LLM)가 형식 완비 케이스에서 놓친 하드 오류의 절반은 정규식이
비용 0·완전 재현으로 잡는다 — "감사의 엄격함은 judge 교체 근거가 아니라 결정론화
근거"(반박석). 생성 파이프라인(intel_query._finalize)과 eval(eval_insight) 양쪽에서
같은 모듈을 import — 기존의 'eval에만 검출기가 있는 비대칭'을 해소한다.

주의: 이 린트를 eval 채점에 편입하는 것은 계측기 변경 — CHANGELOG splice 규약 기재
(방법론석). 검출은 표면화가 기본, 자동 수정은 스캐폴드 스트립(가역·내용 무손실)만.
"""
from __future__ import annotations

import re

# 실측 코퍼스 기준: 정당한 한자 사용은 전부 단일 자(正·美·高 등, 괄호 병기).
# 2+ 연속 CJK런은 전량 중국어/일본어 혼입이었다(不再是·真正·攻击·欧州·側の 등 17건).
# 반박석 유보: 한국어 한자 병기(制裁 등)가 미래에 정당 사용되면 아래 allowlist에 등재.
_CJK_RUN = re.compile(r"[一-鿿぀-ヿ]{2,}")
_CJK_ALLOWLIST: set[str] = set()

_SCAFFOLD = re.compile(r"↳\s*\[[^\]]*?(재료|쓰라)[^\]]*\]|비자명기여 재료 —")
_SCAFFOLD_LINE = re.compile(r"^.*(↳\s*\[비자명기여 재료|중 1개를 ③ 범위조건으로 쓰라).*$", re.M)

# [계측위 2026-07-11] dual_label 재정의 — 구 정의([확증]+[SPECULATIVE] 600자 창 공존)는
# 정상 층분리(모드 표기 "[확증] 지지/반증" + 하위 연쇄에만 [SPECULATIVE])까지 잡는 오탐:
# 07-11 런 13건 중 최소 7건이 오탐 실측(6건 층분리 정상 + 1건 각주 인용). 진짜 자기모순은
# 모드 토큰이 결과 신뢰로 오독되는 "[확증] 불확실" 조합뿐이라 이것만 잡는다.
# 눈금 변경(splice): 구·신 정의 건수는 종단 비교 불가 — eval_results/CHANGELOG 기재.
_DUAL_CONTRADICTION = re.compile(r"\[확증\]\s*[*_]{0,2}\s*불확실")

_HHI_NUM = re.compile(r"HHI[^\d\n]{0,20}(\d[\d,]{2,})")

# [계측위 2026-07-11] 골드 v2_nk 실패모드(편차 0 위조 — 예측·실측 완전일치를 주장해 판정
# 근거를 제조). 정확한 0 편차는 원리상 가능하나 실코퍼스 전례 없음 — report-only 감사 표면화.
# 간격 {0,3}: '편차 0'·'편차: 0'만 — '편차: 예측치 0건 vs 실측 1,228건' 같은
# 정직한 편차 서술(수식어 개입)은 제외 (1101 소급 오탐 실측으로 조정).
# [최종검토위 2026-07-11] %·%p는 단위로 허용 — 구 룩어헤드가 %계열 전체를 배제해
# 표적 골드 표기 "편차 0%p"(v2_nk)를 놓치던 미탐 수리(반박석 2c). '편차 0.5%'는
# 소수부 비영으로 계속 배제.
_ZERO_DEVIATION = re.compile(r"편차[^\d\n]{0,3}0(?:\.0+)?\s*%?p?(?![\d.])")
# [계측위 2026-07-11] verdict_on_unverified 재정의 — 구 정의(판정 라인 120자 내 '미검증'
# 토큰 존재)는 실측 수치에 기반한 판정이 보조 캐비엇("단, 세부 수치는 [UNVERIFIED]")을
# 정직하게 단 것까지 잡는 오탐(6 entry 중 4 — 캐비엇 처벌은 정직성 역유인). 표적 구성물은
# "미검증 DV 위의 결단"(affirming despite unverified) — 두 형태만 잡는다:
# (a) 실측 필드 자체가 [UNVERIFIED]인 이론 블록의 결단 판정 (규칙 문면 그대로)
# (b) 판정 라인 내 양보 구문 — "미검증이나/[UNVERIFIED]임에도 …" 뒤 판정 유지
# 동일 매치 문자열은 1회만 계수(본문 반복 블록의 이중 계수 방지, india 실측).
_UNVERIFIED_MEASURE_VERDICT = re.compile(
    r"실측[:：][^\n]*\[UNVERIFIED\][^\n]*\n[^\n]{0,40}판정[:：]\s*(우세|열세)")
_VERDICT_DESPITE_UNVERIFIED = re.compile(
    r"판정[:：]\s*(우세|열세)[^\n]{0,120}(?:미검증|\[UNVERIFIED\])\s*(?:이나|이지만|임에도|에도\s*불구)")


def lint(text: str) -> list[dict]:
    """결함 목록 반환: [{code, detail}]. 비어 있으면 클린."""
    if not text:
        return []
    problems: list[dict] = []

    for m in _CJK_RUN.finditer(text):
        if m.group(0) not in _CJK_ALLOWLIST:
            problems.append({"code": "cjk_mix", "detail": m.group(0)[:20]})

    if _SCAFFOLD.search(text):
        problems.append({"code": "scaffold_leak", "detail": "지시문 잔존(↳ 비자명기여 재료…쓰라)"})

    if _DUAL_CONTRADICTION.search(text):
        problems.append({"code": "dual_label", "detail": "[확증] 불확실 — 모드 표기를 결과 신뢰로 오용한 자기모순"})

    for m in _HHI_NUM.finditer(text):
        try:
            v = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if v > 10000:
            problems.append({"code": "impossible_hhi", "detail": f"HHI {v} > 상한 10,000"})

    seen_verdicts: set[str] = set()
    for pat, form in ((_UNVERIFIED_MEASURE_VERDICT, "실측=[UNVERIFIED] 블록"),
                      (_VERDICT_DESPITE_UNVERIFIED, "미검증 양보 구문")):
        for m in pat.finditer(text):
            if m.group(0) in seen_verdicts:
                continue
            seen_verdicts.add(m.group(0))
            problems.append({"code": "verdict_on_unverified_stamp",
                             "detail": f"'{m.group(1)}' 판정을 미검증 위에 발급({form})"})

    for m in _ZERO_DEVIATION.finditer(text):
        problems.append({"code": "zero_deviation",
                         "detail": f"편차 0 주장 — 위조 의심 감사 대상: '{text[m.start():m.start()+30]}'"})

    # [최종검토위 2026-07-11] 백스톱 2종 (report-only) — verify 산출물('최종 판정' 실존) 한정:
    # ① 모드 표기 누락 — v2_milex 실증("[확증]을 붙이지 않고 [불확실]로 표기"): 모드↔판정
    #    혼용의 역형태(모드 탈락). ② 연쇄강도 MEDIUM/LOW 자기평가가 있는데 [SPECULATIVE]
    #    레이블 부재 — speculative 게이트 키의 FN 우회(방법론석 C-2 권고).
    if "최종 판정" in text:
        if "[확증" not in text:
            problems.append({"code": "mode_label_missing",
                             "detail": "verify 산출물에 [확증 모드] 표기 부재(모드 탈락)"})
        if re.search(r"\bMEDIUM\b|\bLOW\b", text) and "[SPECULATIVE]" not in text:
            problems.append({"code": "speculative_label_missing",
                             "detail": "연쇄강도 MEDIUM/LOW 자기평가에 [SPECULATIVE] 레이블 부재"})

    return problems


def strip_scaffold(text: str) -> tuple[str, int]:
    """스캐폴드 지시문 줄 제거(내용 무손실·가역) — 안전한 유일 자동 수정."""
    new, n = _SCAFFOLD_LINE.subn("", text or "")
    return new, n
