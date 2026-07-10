"""DV 출처 게이트 — 판정 스탬프 결정론 강등 (개선위 P4, 판례 20260710-engine-improvement-committee).

전수 감사(48케이스)가 실증한 DV 프록시 오용(~24건: 드론 사안 판정에 미국 테러 통계,
HHI 자리에 수입재 비중 등)을 후처리에서 기계 검출한다. 검출 시 해당 '판정: 우세/열세'
스탬프를 '전제충족(DV 미검증)'으로 강등한다 — 재생성 없음, 증거 텍스트는 보존
(원본 결과 보존 원칙). LLM 검증기는 쓰지 않는다(eval 보조만 — 위원회 확정).

검사 2종:
  ① dv_mismatch  — 판정 라인의 예측 구간과 실측 구간을 dv_spec.yaml 클래스로 분류,
                    서로소면 강등. 예측 구간이 무클래스면 이론 프로파일 dv_classes로 폴백
                    (이론 식별은 판정 앞 창의 이론명 별칭 매칭 — 미식별 시 게이트 불발화).
  ② provenance   — 실측 구간의 숫자가 서버 <context>에 실존해야 한다(절대값·오차 2%).
                    context 미제공 시(eval 사후 점검 등) 이 검사는 생략.

스코프 밖(잔여 결함): 같은 클래스 안의 주체 오귀속(러 국방비를 목표국 대응 증거로) —
엔티티 귀속은 정규식 원리상 불가, judge·감사 몫으로 남긴다.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_SPEC_PATH = Path(__file__).resolve().parent.parent / "config" / "dv_spec.yaml"

# 판정 스탬프: '판정: 우세 — …' / '판정: 열세 — …' (전제충족·미검증 판정은 게이트 대상 아님)
_VERDICT = re.compile(r"판정[:：]\s*(우세|열세)")
# 예측 '…' / 실측 '…' 구간 — 따옴표 우선, 없으면 다음 구분자까지
_PRED_SEG = re.compile(r"예측\s*['\"‘“]([^'\"’”\n]{2,120})")
_MEAS_SEG = re.compile(r"실측\s*['\"‘“]([^'\"’”\n]{2,160})")
_PRED_SEG_BARE = re.compile(r"예측\s+([^'\"‘“\n](?:[^\n—;(]{1,100}))")
_MEAS_SEG_BARE = re.compile(r"실측\s+([^'\"‘“\n](?:[^\n—;(]{1,140}))")

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
# 판정 앞 이론 식별 창(문자) — 직전 판정 이후로 캡되므로 블록 경계를 넘지 않는다
_THEORY_WINDOW = 900
# provenance 검사에서 무시하는 소수(서수·목록 번호 류) 절대값 하한
_NUM_MIN_ABS = 3.0


@lru_cache(maxsize=1)
def _spec() -> dict:
    try:
        with open(_SPEC_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001 — 스펙 부재 시 게이트 전체 불발화(fail-open)
        logger.warning("[dv_gate] dv_spec.yaml 로드 실패(게이트 비활성): %s", e)
        return {}


def _classify(seg: str) -> set[str]:
    """텍스트 구간 → 매칭 DV 클래스 집합."""
    low = (seg or "").lower()
    return {cid for cid, c in (_spec().get("classes") or {}).items()
            if any(a in low for a in c.get("aliases", []))}


def _compatible(pred_cls: set[str], meas_cls: set[str]) -> bool:
    """교집합 또는 호환 그룹(같은 DV 차원의 양극단·인접 지표) 공유면 True."""
    if pred_cls & meas_cls:
        return True
    for members in (_spec().get("compat_groups") or {}).values():
        g = set(members)
        if pred_cls & g and meas_cls & g:
            return True
    return False


def _find_theory(window: str) -> tuple[str | None, set[str]]:
    """판정 앞 창에서 이론명 별칭 매칭 — 가장 마지막(가까운) 언급 승."""
    low = (window or "").lower()
    best: tuple[int, str, set[str]] | None = None
    for tid, t in (_spec().get("theories") or {}).items():
        for a in t.get("aliases", []):
            pos = low.rfind(a.lower())
            if pos >= 0 and (best is None or pos > best[0]):
                best = (pos, tid, set(t.get("dv_classes", [])))
    return (best[1], best[2]) if best else (None, set())


def _nums(seg: str) -> list[float]:
    out = []
    for m in _NUM.finditer(seg or ""):
        try:
            v = abs(float(m.group(0).replace(",", "")))
        except ValueError:
            continue
        if v >= _NUM_MIN_ABS:
            out.append(v)
    return out


def _seg(text: str, quoted: re.Pattern, bare: re.Pattern) -> str:
    m = quoted.search(text) or bare.search(text)
    return m.group(1).strip() if m else ""


def check(full_text: str, context_text: str | None = None) -> list[dict]:
    """강등 대상 목록 반환: [{code, verdict, span, detail}] — 텍스트는 건드리지 않는다."""
    if not full_text or not _spec():
        return []
    ctx_nums = set(_nums(context_text)) if context_text else None

    actions: list[dict] = []
    matches = list(_VERDICT.finditer(full_text))
    for i, m in enumerate(matches):
        line_end = full_text.find("\n", m.end())
        line = full_text[m.end(): line_end if line_end > 0 else len(full_text)]
        pred = _seg(line, _PRED_SEG, _PRED_SEG_BARE)
        meas = _seg(line, _MEAS_SEG, _MEAS_SEG_BARE)
        if not meas:
            continue          # 실측 구간이 없으면 검사 불가 — 다른 린트 소관

        # ① 구성개념 정합: 예측 클래스 ∩ 실측 클래스 = ∅ 이면 강등
        pred_cls = _classify(pred)
        meas_cls = _classify(meas)
        if not pred_cls:
            # 예측 구간 무클래스 → 이론 프로파일 dv_classes 폴백
            w_start = max(matches[i - 1].end() if i else 0, m.start() - _THEORY_WINDOW)
            _tid, pred_cls = _find_theory(full_text[w_start: m.start()])
        if pred_cls and meas_cls and not _compatible(pred_cls, meas_cls):
            actions.append({
                "code": "dv_mismatch", "verdict": m.group(1), "span": m.span(),
                "detail": f"예측{sorted(pred_cls)} vs 실측{sorted(meas_cls)} 구성개념 서로소",
            })
            continue          # 한 판정에 강등은 1회

        # ② 출처: 실측 숫자가 context에 없으면 강등
        if ctx_nums is not None:
            missing = [v for v in _nums(meas)
                       if not any(abs(v - c) <= max(0.02 * c, 0.01) for c in ctx_nums)]
            if missing:
                actions.append({
                    "code": "provenance_missing", "verdict": m.group(1), "span": m.span(),
                    "detail": f"실측 수치 {missing[:3]} context 미실존",
                })
    return actions


def apply_gate(full_text: str, context_text: str | None = None) -> tuple[str, list[dict]]:
    """검출 + 스탬프 강등 적용. (정화된 텍스트, 강등 목록) 반환."""
    actions = check(full_text, context_text)
    # 뒤에서부터 치환해야 앞 판정들의 span이 안 밀린다
    for a in sorted(actions, key=lambda x: x["span"][0], reverse=True):
        s, e = a["span"]
        full_text = (full_text[:s]
                     + f"판정: 전제충족(DV 미검증) [DV게이트: {a['code']} 자동 강등]"
                     + full_text[e:])
    return full_text, actions
