"""
claim_ledger.py — 문헌 공백 탐지 원장 (Phase 8 Cycle 8-D)

목적
----
인사이트 엔진의 [문헌공백] 섹션이 그동안 **순수 LLM 생성**이었다.
엔진이 라이브러리 94개 문서가 실제로 무엇을 주장하는지 구조적으로 모른 채
Gemini에게 "기존 문헌이 못 다루는 이유를 써라"고 시키니, 막연한
'추가 연구 필요'류로 흘러 비자명성이 3.43에 고착됐다.

이 모듈은 **Token-Zero 원칙**(§14)을 지켜, Python이 라이브러리의 이미
구조화된 필드에서 3종 공백 신호를 결정론적으로 추출한다. Gemini는 이
지도를 **근거로 인용**해 공백을 짚을 뿐, 추출 자체에는 LLM을 호출하지 않는다.

3종 공백 신호
-------------
① 반례 클러스터    — known_counterexample 모음. 반례가 몰린 지점 = 학계 논쟁 중
② 경쟁이론 미해결  — rival_theories가 명시됐으나 라이브러리가 수치 판정 미제공
③ 교차도메인 밀도  — 섹터별 주장 건수 집계. 한 도메인은 포화인데 연결고리는 0건

확장성 (8-D 설계 결정)
----------------------
모든 추출은 md_indexer가 인덱싱하는 기존 DB 필드 기반 → 새 라이브러리 문서를
추가하면 자동으로 원장에 합류(유지보수 0). 추가로 미래 대비 `contested_by`
필드(직접 모순 연결)가 채워지면 코드 수정 없이 자동 활용한다.

정치외교학 연결
---------------
§19-B-2 ③ "독창적 패턴 포착 — 문헌 공백 탐지"는 이 도구의 최고 경쟁력이다.
"유리 턱", "역외균형자 vs 전방배치 헤게몬 긴장"처럼 기존 문헌이 충분히
검증하지 않은 공백을 겨냥하는 능력을, 추측이 아니라 라이브러리 실측 주장에
근거하도록 만든다.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.entity_parser import ParsedQuery

logger = logging.getLogger(__name__)

# 라이브러리 DB (intel_analyzer와 동일 경로)
_LIB_DB = Path(__file__).resolve().parent.parent / "db" / "library.db"

# 원장 블록의 최대 길이 (임계값 라인 추가로 2400으로 확대)
_LEDGER_MAX_CHARS = 2400

# 각 신호별 표시 상한 (컨텍스트 비대 방지)
_MAX_COUNTEREXAMPLES = 5
_MAX_RIVAL_PAIRS = 4
_MAX_CONTESTED_EDGES = 5

# 섹터 한국어 라벨 (밀도 표에 사용)
_SECTOR_KO: dict[str, str] = {
    "maritime":     "해양",
    "energy":       "에너지",
    "techno":       "기술패권",
    "indo_pacific": "인도태평양",
    "gray_zone":    "회색지대",
    "cyber":        "사이버",
}


def _loads(val) -> list:
    """JSON 배열 문자열 → list. 실패 시 빈 리스트 (None-safe)."""
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        parsed = json.loads(val)
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except (json.JSONDecodeError, TypeError):
        return [str(val)]


def _short(text: str, limit: int = 160) -> str:
    """긴 주장 텍스트를 표시용으로 자른다."""
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fetch_theory_claims(sectors: list[str], limit: int = 8) -> list[dict]:
    """
    이론 문서의 반례·경쟁이론 프로파일을 **직접** 조회한다.

    배경: 라이브러리 검색(search_theories)은 published_date DESC로 정렬돼
    날짜 있는 브리핑만 반환하고, 날짜 없는 이론 문서(반례·경쟁이론 보유)는
    LIMIT에서 밀려난다. 신호 ①·②는 이론 문서에만 있으므로, 검색 순위에
    의존하지 않도록 여기서 별도로 끌어온다.

    섹터 미지정 쿼리는 반례·경쟁이론이 있는 모든 이론에서 상위 N개를 반환.
    """
    try:
        con = sqlite3.connect(_LIB_DB)
        con.row_factory = sqlite3.Row
        base = """
            SELECT theory_id, title, sector_tag,
                   known_counterexample, rival_theories, contested_by,
                   falsifiable_prediction, conditions
            FROM theories
            WHERE asset_type = 'theory'
              AND (known_counterexample IS NOT NULL OR rival_theories IS NOT NULL)
        """
        if sectors:
            placeholders = ",".join("?" * len(sectors))
            rows = con.execute(
                base + f" AND sector_tag IN ({placeholders}) LIMIT ?",
                (*sectors, limit),
            ).fetchall()
        else:
            rows = con.execute(base + " LIMIT ?", (limit,)).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[claim_ledger] 이론 프로파일 조회 실패: %s", e)
        return []


def build_claim_ledger(pq: "ParsedQuery", items: list[dict]) -> str:
    """
    라이브러리 검색 결과(items)에서 3종 공백 신호를 결정론적으로 추출해
    [문헌공백] 근거 블록(텍스트)을 만든다.

    Args:
        pq:    파싱된 쿼리 (지역·행위자·섹터)
        items: search_theories / list_db_theories 결과 (중복 제거된 dict 목록).
               각 dict는 theory_id·title·sector_tag·summary·
               known_counterexample·rival_theories·contested_by 등을 포함.

    Returns:
        원장 텍스트 블록. 추출할 신호가 전혀 없으면 "" (주입 생략).
    """
    # 신호 ①·② 재료: 이론 프로파일을 검색 순위와 무관하게 직접 조회.
    # (검색은 브리핑 위주 → 반례·경쟁이론은 이론 문서에만 있어 별도 확보 필요)
    theory_claims = _fetch_theory_claims(pq.sectors)

    if not items and not theory_claims:
        return ""

    # ── 신호 ① 반례 클러스터 ─────────────────────────────────────────────
    # 이론이 스스로 인정한 '알려진 반례'를 모은다. 반례가 존재한다는 것 자체가
    # 그 이론이 무조건 성립하지 않는 경계가 있다는 뜻 → 비자명한 [문헌공백]의 출발점.
    counterexamples: list[tuple[str, str, str]] = []  # (title, counterexample, falsifiable_prediction)
    seen_ce: set[str] = set()
    for it in theory_claims:
        ce = (it.get("known_counterexample") or "").strip()
        if ce and ce not in seen_ce:
            seen_ce.add(ce)
            title = it.get("title") or it.get("theory_id") or "?"
            fp    = (it.get("falsifiable_prediction") or "").strip()
            counterexamples.append((title, ce, fp))

    # ── 신호 ② 경쟁이론 미해결 ───────────────────────────────────────────
    # rival_theories가 명시된 이론들. 라이브러리는 "A vs B 경쟁"이라고 적었지만
    # 어느 문서도 수치로 판정하지 않은 미해결 충돌을 노출한다.
    rival_pairs: list[tuple[str, list[str]]] = []
    seen_rival: set[str] = set()
    for it in theory_claims:
        rivals = _loads(it.get("rival_theories"))
        if not rivals:
            continue
        own = it.get("title") or it.get("theory_id") or "?"
        if own in seen_rival:
            continue
        seen_rival.add(own)
        rival_pairs.append((own, rivals))

    # ── 신호 ③ 교차도메인 밀도 공백 ──────────────────────────────────────
    # 섹터별 주장 건수를 센다. 쿼리가 2개 이상 섹터를 다루는데 한쪽은 풍부하고
    # 다른 쪽(특히 둘을 잇는 교차 경로)은 희박하면, 그 비대칭이 곧 공백이다.
    sector_counts: dict[str, int] = {}
    for it in items:
        tag = it.get("sector_tag")
        if tag:
            sector_counts[tag] = sector_counts.get(tag, 0) + 1

    # ── 확장 훅: contested_by 직접 모순 연결 (미래 대비) ──────────────────
    # 오늘은 대부분 비어 있다. 문서가 채우면 코드 수정 없이 자동 노출.
    contested_edges: list[tuple[str, list[str]]] = []
    seen_edge: set[str] = set()
    for it in list(items) + theory_claims:
        cb = _loads(it.get("contested_by"))
        if cb:
            own = it.get("title") or it.get("theory_id") or "?"
            if own in seen_edge:
                continue
            seen_edge.add(own)
            contested_edges.append((own, cb))

    # ── 블록 조립 ────────────────────────────────────────────────────────
    lines: list[str] = ["## 문헌 공백 원장 (결정론적 추출 — [문헌공백] 작성 근거)"]
    lines.append(
        "  ⚠️ 아래는 라이브러리가 실제로 담은 주장·반례 지도다. [문헌공백]은 "
        "반드시 이 원장의 구체적 항목을 인용해 작성하라. 원장에 없는 막연한 "
        "'추가 연구 필요'는 금지."
    )
    has_signal = False

    if counterexamples:
        has_signal = True
        lines.append("\n### ① 반례 클러스터 (이론이 깨지는 경계 — 논쟁 지점)")
        for title, ce, fp in counterexamples[:_MAX_COUNTEREXAMPLES]:
            line = f"- 〈{_short(title, 50)}〉"
            if fp:
                # 예측 임계값을 앞에 붙여 "어느 조건에서 깨지는가"를 명시
                line += f" 예측 임계: {_short(fp, 100)}"
            line += f" | 반례: {_short(ce, 120)}"
            lines.append(line)

    if rival_pairs:
        has_signal = True
        lines.append("\n### ② 경쟁이론 미해결 (라이브러리가 충돌만 적고 판정 안 함)")
        for own, rivals in rival_pairs[:_MAX_RIVAL_PAIRS]:
            rv = ", ".join(rivals[:3])
            lines.append(f"- 〈{_short(own, 50)}〉 ↔ {rv}")
        lines.append(
            "  → 위 이론쌍 중 본 분석 쿼리에 해당하는 충돌을 실측으로 판정하면 그것이 기여."
        )

    if sector_counts:
        # 밀도 표는 쿼리가 멀티섹터이거나 명시 섹터가 있을 때만 의미 있음
        dense = sorted(sector_counts.items(), key=lambda x: -x[1])
        if len(dense) >= 2 or (pq.sectors and len(pq.sectors) >= 2):
            has_signal = True
            lines.append("\n### ③ 교차도메인 밀도 (섹터별 주장 건수)")
            density_str = ", ".join(
                f"{_SECTOR_KO.get(s, s)} {c}건" for s, c in dense
            )
            lines.append(f"- 분포: {density_str}")
            # 쿼리 섹터 중 주장이 희박(0~1건)한 곳을 명시 — 교차 공백 후보
            sparse = [
                _SECTOR_KO.get(s, s)
                for s in pq.sectors
                if sector_counts.get(s, 0) <= 1
            ]
            if sparse:
                lines.append(
                    f"  → 희박 섹터: {', '.join(sparse)} (쿼리가 다루나 라이브러리 주장 ≤1건). "
                    "포화 섹터와 이 희박 섹터를 잇는 교차 경로가 문헌 공백일 가능성."
                )
            elif len(dense) >= 2:
                top = _SECTOR_KO.get(dense[0][0], dense[0][0])
                bottom = _SECTOR_KO.get(dense[-1][0], dense[-1][0])
                lines.append(
                    f"  → {top}(포화) ↔ {bottom}(상대 희박)을 잇는 교차도메인 인과 경로가 "
                    "단일도메인 문헌의 사각지대일 수 있음."
                )

    if contested_edges:
        has_signal = True
        lines.append("\n### ④ 직접 모순 연결 (contested_by — 저자 태깅)")
        for own, cb in contested_edges[:_MAX_CONTESTED_EDGES]:
            lines.append(f"- 〈{_short(own, 50)}〉 ⟂ {', '.join(cb[:3])}")

    if not has_signal:
        return ""

    block = "\n".join(lines)
    if len(block) > _LEDGER_MAX_CHARS:
        block = block[: _LEDGER_MAX_CHARS - 1] + "…"
    return block
