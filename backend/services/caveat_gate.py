"""
caveat_gate.py — 경고 준수 게이트 (2026-07-13 변수 타당도 감사).

═══════════════════════════════════════════════════════════════════════════════
 왜 필요한가 — "말했다"와 "지켜졌다"는 다르다
═══════════════════════════════════════════════════════════════════════════════
 2026-07-13 감사에서 컨텍스트에 구성 타당도 경고를 심었다:

   ⚠️ 이 권역 이벤트의 99.3%가 시위·소요다(사망 0명). 이것은 **군사 충돌 지표가
      아니다** — '분쟁 이벤트 건수'를 무력 충돌·도발의 대리변수로 인용하지 마라.

 **그런데 LLM이 그 경고를 무시하고 이렇게 쓰면 아무것도 막지 못했다:**

   "한반도의 긴장은 8,265건에 달한다. 북한의 도발 빈도가 증가할 때…"

 우리는 **말했을 뿐 확인하지 않았다.** 이것은 그날 아침 회수한 1호와 같은 병이다 —
 페이지엔 "예시 데이터" 배지가 있었는데 기계 표면엔 없었다. **사람에게만 알리고
 기계에게 알리지 않은 라벨은 라벨이 아니다.** 마찬가지로 **컨텍스트에만 있고
 준수 검사가 없는 경고는 경고가 아니다.**

 이 게이트는 dv_gate와 같은 위상이다: 출력을 사후 검사해 **결정론적으로 강등**한다.
 재생성하지 않는다(원본 결과 보존 원칙). LLM 검증기를 쓰지 않는다(Token-Zero).

═══════════════════════════════════════════════════════════════════════════════
 무엇을 검사하는가
═══════════════════════════════════════════════════════════════════════════════
 컨텍스트에 **구성 타당도 경고/주의**가 있었다면:
   ① 그 경고가 붙은 권역의 **이벤트 총건수**를 컨텍스트에서 추출한다(결정론).
   ② 출력에서 그 숫자를 찾는다.
   ③ 그 숫자가 **군사·도발·충돌 프레임**으로 인용됐는데
      **시위·국내 정치라는 자격 표시가 같은 문장에 없으면** → 위반.
   ④ 위반 문장 끝에 강등 스탬프를 박는다.

 오탐 방지: 자격 표시(시위·소요·국내·구성 타당도 등)가 같은 문장에 있으면 통과.
           즉 "8,265건(98.8%가 국내 시위)"은 정상 인용이다.

 원문: geo-os/docs/ENGINE_VARIABLE_AUDIT_20260713.md
 판례: geo-os/wiki/decisions/20260713-variable-validity-committee.md
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 컨텍스트의 경고 블록 — 권역 헤더와 총건수를 함께 추출한다.
#   - **korean_peninsula**: 총 8,265건 · 사망 0명
#     구성: Protests 8,122건(98.3%) …
#     ⚠️ **구성 타당도 경고**: …
_REGION_BLOCK = re.compile(
    r"-\s*\*\*(?P<region>[a-z_]+)\*\*:\s*총\s*(?P<total>[\d,]+)건.*?"
    # ⚠️ 실제 텍스트는 "**구성 타당도 경고(강)**" — (강)이 굵게 표시 *안쪽*에 있다.
    # 초판 정규식이 `경고\*\*`로 끝나는 것만 찾아 **자기 표적을 놓쳤다**(검출 0건).
    # 음성 테스트가 잡았다 — 폐기 원장 패턴 E("자기 표적을 놓치는 가드")의 실사례.
    r"(?P<warn>⚠️\s*\*\*구성 타당도 (?:경고|주의)[^*]*\*\*)",
    re.S,
)

# 출력에서 그 숫자가 '군사·도발' 프레임으로 쓰였는가
_MILITARY_FRAME = re.compile(
    r"도발|무력|군사|교전|충돌|분쟁|긴장|공격|침공|위협|미사일|포격|전쟁"
)

# 같은 문장에 자격 표시가 있으면 정상 인용 — 오탐 방지
_QUALIFIER = re.compile(
    r"시위|소요|국내|집회|프로테스트|구성 타당도|시위·소요|"
    r"군사 충돌 지표가 아니|정치 시위|Protests"
)

# 문장 분할 (한국어 종결 + 개행)
_SENT = re.compile(r"[^\n。.!?]*[。.!?]|[^\n]+")

_STAMP = " [경고게이트: {code} — 컨텍스트가 '{region} 건수는 군사 충돌 지표가 아니다'라고 경고했으나 자격 표시 없이 인용됨]"


def _warned_regions(context_text: str) -> dict[str, str]:
    """컨텍스트에서 경고가 붙은 권역 → 총건수(원문 표기) 매핑."""
    out: dict[str, str] = {}
    for m in _REGION_BLOCK.finditer(context_text or ""):
        out[m.group("region")] = m.group("total")
    return out


def check(full_text: str, context_text: str | None = None) -> list[dict]:
    """위반 검출. 반환: [{code, region, number, sentence, span}] (강등 미적용)."""
    if not full_text or not context_text:
        return []
    warned = _warned_regions(context_text)
    if not warned:
        return []

    actions: list[dict] = []
    for region, total in warned.items():
        # 숫자를 콤마 유무 양쪽으로 찾는다 (LLM이 8,265 / 8265 둘 다 쓴다).
        # ⚠️ \b(단어경계)를 쓰면 안 된다 — 파이썬 정규식에서 **한글은 단어 문자**라
        # "8,265건"의 '5'와 '건' 사이에 경계가 없어 매치가 실패한다. 초판이 이 버그로
        # 자기 표적을 놓쳤다(음성 테스트가 잡음). 숫자 경계(?<!\d)(?!\d)를 쓴다.
        bare = total.replace(",", "")
        num_re = re.compile(
            rf"(?<![\d,]){re.escape(total)}(?![\d,])|(?<!\d){re.escape(bare)}(?!\d)")

        for sm in _SENT.finditer(full_text):
            sent = sm.group(0)
            if not num_re.search(sent):
                continue
            if not _MILITARY_FRAME.search(sent):
                continue          # 군사 프레임이 아니면 위반 아님
            if _QUALIFIER.search(sent):
                continue          # 자격 표시가 있으면 정상 인용
            actions.append({
                "code": "caveat_ignored",
                "region": region,
                "number": total,
                "detail": f"{region} 총 {total}건을 군사·도발 프레임으로 자격 표시 없이 인용",
                "span": (sm.start(), sm.end()),
            })
    return actions


def apply_gate(full_text: str, context_text: str | None = None) -> tuple[str, list[dict]]:
    """검출 + 강등 스탬프 적용. (정화된 텍스트, 강등 목록) 반환.

    dv_gate와 동일 규약: 재생성 없음, 원본 서술 보존, 스탬프만 추가.
    뒤에서부터 치환해 앞 span이 밀리지 않게 한다.
    """
    actions = check(full_text, context_text)
    for a in sorted(actions, key=lambda x: x["span"][0], reverse=True):
        s, e = a["span"]
        stamp = _STAMP.format(code=a["code"], region=a["region"])
        full_text = full_text[:s] + full_text[s:e].rstrip() + stamp + full_text[e:]
    return full_text, actions
