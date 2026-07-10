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

# [확증]과 [SPECULATIVE]가 최종판정 인접부(600자 창)에 공존 — 인식론 모드와
# 연쇄강도 라벨의 프롬프트 충돌 산물(intel_query 431·497행, 실측석 확정).
_DUAL_WINDOW = 600

_HHI_NUM = re.compile(r"HHI[^\d\n]{0,20}(\d[\d,]{2,})")
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

    for m in re.finditer(r"\[확증\]", text):
        window = text[m.start(): m.start() + _DUAL_WINDOW]
        if "[SPECULATIVE]" in window:
            problems.append({"code": "dual_label", "detail": "[확증]+[SPECULATIVE] 공존(최종판정 절)"})
            break

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

    return problems


def strip_scaffold(text: str) -> tuple[str, int]:
    """스캐폴드 지시문 줄 제거(내용 무손실·가역) — 안전한 유일 자동 수정."""
    new, n = _SCAFFOLD_LINE.subn("", text or "")
    return new, n
