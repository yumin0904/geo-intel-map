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
_ZERO_DEVIATION = re.compile(r"편차[^\d\n]{0,8}0(?:\.0+)?(?![\d.,%])")
_VERDICT_UNVERIFIED = re.compile(r"판정[:：]\s*(우세|열세)[^\n]{0,120}(미검증|\[UNVERIFIED\])")


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

    for m in _VERDICT_UNVERIFIED.finditer(text):
        problems.append({"code": "verdict_on_unverified_stamp",
                         "detail": f"'{m.group(1)}' 판정과 미검증 선언 동시 발급"})

    for m in _ZERO_DEVIATION.finditer(text):
        problems.append({"code": "zero_deviation",
                         "detail": f"편차 0 주장 — 위조 의심 감사 대상: '{text[m.start():m.start()+30]}'"})

    return problems


def strip_scaffold(text: str) -> tuple[str, int]:
    """스캐폴드 지시문 줄 제거(내용 무손실·가역) — 안전한 유일 자동 수정."""
    new, n = _SCAFFOLD_LINE.subn("", text or "")
    return new, n
