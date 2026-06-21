"""
[9-Q 우선순위 3] 과정추적 스캐폴딩 어댑터 (Process Tracing Scaffold)

UNQUANTIFIABLE 가설(비선형·체제 변수, 질적 질문)에 대해
Van Evera(1997) 4검정 틀을 제공한다.

핵심 원칙 (질적 p-해킹 방어):
  - 틀(Van Evera 4검정)과 증거 배치(DB 조회)는 Token-Zero Python이 담당.
  - LLM(Gemini)은 이 스캐폴딩을 읽고 [관찰]/[변수] 서술만.
  - 최종 판정은 연구자 몫 — AI가 "가설 지지/기각" 결론 내리면 안 됨.
  - 스캐폴딩은 유도질문이지 정답이 아님.

Van Evera 4검정 요약 (쉬운 말):
  후프 검정   — "이게 없으면 가설 탈락" (필수 조건 확인)
  흡연총 검정 — "이게 있으면 가설 거의 확실" (결정적 단서)
  밀짚 검정   — "약한 방향 신호, 없어도 탈락 아님"
  이중결정    — "있으면 확실·없으면 탈락 동시 충족" (가장 강력)
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.hypothesis_extractor import HypothesisSpec

from .base import MethodResult

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "db" / "intel.db"

# Van Evera 4검정 정의 (Token-Zero 상수)
_VAN_EVERA_TESTS: list[dict] = [
    {
        "id": "hoop",
        "name": "후프 검정 (Hoop Test)",
        "meaning": (
            "가설이 사실이라면 반드시 존재해야 할 선행 조건·사실 확인. "
            "이 조건이 없으면 가설은 탈락합니다 (필요조건, 낮은 특수성)."
        ),
        "evidence_prompt": "가설의 인과 연결이 성립하려면 반드시 선행해야 할 사건·제도·행위자는 무엇입니까?",
        "guiding_question": (
            "이 선행 조건이 실제로 관찰됩니까? "
            "없다면 가설은 이 단계에서 탈락합니다."
        ),
    },
    {
        "id": "smoking_gun",
        "name": "흡연총 검정 (Smoking Gun Test)",
        "meaning": (
            "가설만 설명할 수 있는 독특한 증거 탐색. "
            "이 증거가 존재하면 가설이 거의 확실하지만, "
            "없어도 탈락은 아닙니다 (높은 특수성, 낮은 필요성)."
        ),
        "evidence_prompt": (
            "오직 이 가설의 인과 메커니즘만이 설명할 수 있는 "
            "독특한 행동·문서·패턴·내부 발언은 무엇입니까?"
        ),
        "guiding_question": (
            "대안 설명(경쟁 이론)으로는 이 증거가 나타나지 않습니까? "
            "그렇다면 이 검정은 통과입니다."
        ),
    },
    {
        "id": "straw_in_wind",
        "name": "밀짚 검정 (Straw-in-the-Wind Test)",
        "meaning": (
            "가설 방향을 살짝 가리키는 약한 신호. "
            "단독으로는 결정적이지 않지만, "
            "누적되면 힘을 얻습니다 (낮은 특수성·낮은 필요성)."
        ),
        "evidence_prompt": (
            "인과 연결이 작동한다면 주변에서 관찰될 수 있는 "
            "약한 방향 신호(간접 지표·주변 언급)는 무엇입니까?"
        ),
        "guiding_question": (
            "이 신호들이 가설이 예측하는 방향과 일치합니까? "
            "일치하면 약한 지지 근거로 기록하세요."
        ),
    },
    {
        "id": "doubly_decisive",
        "name": "이중결정 검정 (Doubly Decisive Test)",
        "meaning": (
            "존재하면 가설 거의 확실, 없으면 가설 탈락 — 동시 충족. "
            "가장 강력한 검정이지만 실제로 찾기 어렵습니다 (높은 특수성·높은 필요성)."
        ),
        "evidence_prompt": (
            "단 하나의 증거·사건이 "
            "가설을 동시에 확인하고 대안 이론을 배제할 수 있다면 무엇입니까? "
            "(예: 내부 결정문서, 직접 인과 경로 추적)"
        ),
        "guiding_question": (
            "이 증거가 실제로 존재합니까? "
            "존재하면 이 단 하나가 전체 과정추적을 결정합니다."
        ),
    },
]


def _fetch_region_evidence(region: str | None, limit: int = 5) -> list[dict]:
    """ACLED event_archive에서 지역 분쟁·사건 이벤트 조회 (후프·밀짚 검정용)."""
    if not region or not _DB_PATH.exists():
        return []
    try:
        con = sqlite3.connect(str(_DB_PATH))
        cur = con.cursor()
        cur.execute(
            """
            SELECT title, timestamp, source_type, severity
            FROM event_archive
            WHERE region_code = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (region, limit),
        )
        rows = cur.fetchall()
        con.close()
        return [
            {
                "title":       r[0] or "",
                "date":        (r[1] or "")[:10],
                "source_type": r[2] or "",
                "severity":    r[3],
                "source_db":   "ACLED",
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("[process_tracing] ACLED 조회 실패 region=%s: %s", region, exc)
        return []


def _extract_keywords(h1: str) -> list[str]:
    """H1 문자열에서 명사/핵심어 추출 (Token-Zero 단순 분절)."""
    import re
    # 조사·어미 제거 후 2자 이상 단어 추출
    tokens = re.findall(r"[가-힣a-zA-Z]{2,}", h1)
    stopwords = {"할수록", "할때", "하면", "증가할", "감소할", "변화할", "통계적", "유의하게", "통제변수"}
    return [t for t in tokens if t not in stopwords][:6]


def _fetch_nk_evidence(h1: str, limit: int = 4) -> list[dict]:
    """
    NKNews + 38 North에서 H1 키워드 관련 기사 조회.
    korean_peninsula 가설 전용 — 흡연총 보강.
    """
    if not _DB_PATH.exists():
        return []
    keywords = _extract_keywords(h1)
    if not keywords:
        return []
    try:
        con = sqlite3.connect(str(_DB_PATH))
        cur = con.cursor()
        kw = keywords[0]
        cur.execute(
            """SELECT title, pub_date, source, description
               FROM nk_press_releases
               WHERE title LIKE ? OR description LIKE ?
               ORDER BY pub_date DESC LIMIT ?""",
            (f"%{kw}%", f"%{kw}%", limit),
        )
        rows = cur.fetchall()
        # 키워드 매칭 부족하면 38North 전체로 보충
        if len(rows) < 2:
            cur.execute(
                """SELECT title, pub_date, source, description
                   FROM nk_press_releases
                   WHERE source='38North'
                   ORDER BY pub_date DESC LIMIT ?""",
                (limit,),
            )
            seen = {r[0] for r in rows}
            rows += [r for r in cur.fetchall() if r[0] not in seen]
        con.close()
        return [
            {
                "title":       r[0] or "",
                "date":        r[1] or "",
                "source_db":   r[2] or "NKNews",
                "description": (r[3] or "")[:120],
            }
            for r in rows[:limit]
        ]
    except Exception as exc:
        logger.debug("[process_tracing] NK evidence 조회 실패: %s", exc)
        return []


def _fetch_policy_evidence(region: str | None, h1: str, limit: int = 4) -> list[dict]:
    """
    Atlantic Council + Arms Control Association에서 관련 기사 조회.

    미국 외교정책 싱크탱크 시각 — 흡연총·이중결정 검정 보강용.
    한국(MOFA)과 미국(Atlantic Council) 양측이 같은 메커니즘 언급 = 이중결정 증거.
    """
    if not _DB_PATH.exists():
        return []
    keywords = _extract_keywords(h1) if h1 else []
    try:
        con = sqlite3.connect(str(_DB_PATH))
        cur = con.cursor()
        if region and keywords:
            kw = keywords[0]
            cur.execute(
                """SELECT source, title, pub_date, description
                   FROM policy_releases
                   WHERE (region_hint = ? OR title LIKE ? OR description LIKE ?)
                   ORDER BY pub_date DESC LIMIT ?""",
                (region, f"%{kw}%", f"%{kw}%", limit),
            )
        elif region:
            cur.execute(
                """SELECT source, title, pub_date, description
                   FROM policy_releases
                   WHERE region_hint = ?
                   ORDER BY pub_date DESC LIMIT ?""",
                (region, limit),
            )
        else:
            cur.execute(
                """SELECT source, title, pub_date, description
                   FROM policy_releases
                   ORDER BY pub_date DESC LIMIT ?""",
                (limit,),
            )
        rows = cur.fetchall()
        con.close()
        return [
            {
                "title":       r[1] or "",
                "date":        r[2] or "",
                "source_db":   r[0] or "Atlantic Council",
                "description": (r[3] or "")[:120],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("[process_tracing] Policy think tank 조회 실패: %s", exc)
        return []


def _fetch_govinfo_evidence(region: str | None, h1: str, limit: int = 3) -> list[dict]:
    """
    GovInfo CPD(대통령 성명·기자회견 원문) 온디맨드 검색.

    미국 정부 1차 사료 중 최고 권위 — 이중결정 검정 핵심 증거.
    예: "트럼프 싱가포르 정상회담 공동성명", "바이든 워싱턴 선언(확장억제)" 등.
    API 호출 결과를 DB에 캐싱 → 재호출 시 DB 조회.
    """
    if not _DB_PATH.exists():
        # DB 없으면 온라인 검색만
        pass
    keywords = _extract_keywords(h1) if h1 else []
    # 지역 + H1 핵심어로 쿼리 구성
    region_terms: dict[str, str] = {
        "korean_peninsula": "North Korea DPRK nuclear alliance deterrence",
        "taiwan_strait":    "Taiwan South China Sea Indo-Pacific",
        "hormuz":           "Iran nuclear Hormuz sanctions",
        "eastern_europe":   "Ukraine Russia NATO alliance",
        "bab_el_mandeb":    "Houthi Red Sea maritime security",
        "techno_supply_chain": "semiconductor chips supply chain China",
    }
    base_query = region_terms.get(region or "", "nuclear alliance security")
    if keywords:
        kw_str = " ".join(keywords[:3])
        query = f"{base_query} {kw_str}"
    else:
        query = base_query

    # 1순위: 로컬 DB 검색 (캐시)
    local = []
    try:
        con = sqlite3.connect(str(_DB_PATH))
        if region:
            cur = con.execute(
                """SELECT title, pub_date, description
                   FROM govinfo_releases
                   WHERE region_hint=?
                   ORDER BY pub_date DESC LIMIT ?""",
                (region, limit),
            )
        else:
            cur = con.execute(
                """SELECT title, pub_date, description
                   FROM govinfo_releases
                   ORDER BY pub_date DESC LIMIT ?""",
                (limit,),
            )
        local = [
            {
                "title":       r[0] or "",
                "date":        (r[1] or "")[:10],
                "source_db":   "CPD (White House)",
                "description": (r[2] or "")[:120],
            }
            for r in cur.fetchall()
        ]
        con.close()
    except Exception:
        pass

    if len(local) >= limit:
        return local

    # 2순위: 온라인 검색 (로컬 부족 시)
    try:
        from connectors.govinfo_connector import online_search
        online = online_search(query, region=region, limit=limit)
        seen = {r["title"] for r in local}
        for item in online:
            if item["title"] not in seen:
                local.append({
                    "title":       item.get("title", ""),
                    "date":        item.get("date", ""),
                    "source_db":   item.get("source_db", "CPD (White House)"),
                    "description": (item.get("description", ""))[:120],
                })
    except Exception as exc:
        logger.debug("[process_tracing] GovInfo 온라인 검색 실패: %s", exc)

    return local[:limit]


def _fetch_un_evidence(region: str | None, h1: str, limit: int = 3) -> list[dict]:
    """
    UN News에서 관련 기사 조회 — 이중결정 검정 다자 소스.
    지역 태그 + H1 키워드로 검색.
    """
    if not _DB_PATH.exists():
        return []
    try:
        con = sqlite3.connect(str(_DB_PATH))
        cur = con.cursor()
        keywords = _extract_keywords(h1)

        if region and keywords:
            kw = keywords[0]
            cur.execute(
                """SELECT title, pub_date, description
                   FROM un_news_releases
                   WHERE (region_hint = ? OR title LIKE ? OR description LIKE ?)
                   ORDER BY pub_date DESC LIMIT ?""",
                (region, f"%{kw}%", f"%{kw}%", limit),
            )
        elif region:
            cur.execute(
                """SELECT title, pub_date, description
                   FROM un_news_releases
                   WHERE region_hint = ?
                   ORDER BY pub_date DESC LIMIT ?""",
                (region, limit),
            )
        else:
            cur.execute(
                """SELECT title, pub_date, description
                   FROM un_news_releases
                   ORDER BY pub_date DESC LIMIT ?""",
                (limit,),
            )
        rows = cur.fetchall()
        con.close()
        return [
            {
                "title":       r[0] or "",
                "date":        r[1] or "",
                "source_db":   "UN News",
                "description": (r[2] or "")[:120],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("[process_tracing] UN News 조회 실패: %s", exc)
        return []


def _fetch_mofa_evidence(region: str | None, h1: str, limit: int = 5) -> list[dict]:
    """
    외교부 보도자료(mofa_press_releases)에서 관련 문서를 조회한다.

    흡연총 검정용: 공식 정책 결정·회의·협약을 담은 1차 사료.
    지역 태그 + H1 키워드 교차 검색으로 관련성 높은 문서 우선 반환.
    DB 없거나 에러 시 빈 리스트 (graceful degradation).
    """
    if not _DB_PATH.exists():
        return []

    keywords = _extract_keywords(h1) if h1 else []

    try:
        con = sqlite3.connect(str(_DB_PATH))
        cur = con.cursor()

        if region and keywords:
            # 1순위: 지역 태그 + 첫 키워드 매칭
            kw = keywords[0]
            cur.execute(
                """
                SELECT title, pub_date, creator
                FROM mofa_press_releases
                WHERE region_hint = ?
                  AND (title LIKE ? OR content_text LIKE ?)
                ORDER BY pub_date DESC
                LIMIT ?
                """,
                (region, f"%{kw}%", f"%{kw}%", limit),
            )
            rows = cur.fetchall()
            # 부족하면 지역 태그만으로 보충
            if len(rows) < limit:
                cur.execute(
                    """
                    SELECT title, pub_date, creator
                    FROM mofa_press_releases
                    WHERE region_hint = ?
                    ORDER BY pub_date DESC
                    LIMIT ?
                    """,
                    (region, limit - len(rows)),
                )
                seen = {r[0] for r in rows}
                rows += [r for r in cur.fetchall() if r[0] not in seen]
        elif region:
            cur.execute(
                """
                SELECT title, pub_date, creator
                FROM mofa_press_releases
                WHERE region_hint = ?
                ORDER BY pub_date DESC
                LIMIT ?
                """,
                (region, limit),
            )
            rows = cur.fetchall()
        else:
            rows = []

        con.close()
        return [
            {
                "title":       r[0] or "",
                "date":        r[1] or "",
                "creator":     r[2] or "",
                "source_db":   "외교부 보도자료",
            }
            for r in rows
        ]
    except Exception as exc:
        logger.debug("[process_tracing] MOFA 조회 실패 region=%s: %s", region, exc)
        return []


def process_tracing_adapt(spec: "HypothesisSpec") -> MethodResult:
    """
    UNQUANTIFIABLE 가설 → Van Evera 4검정 스캐폴딩 반환.

    Token-Zero: LLM 호출 없음.
    evidence는 DB에서 결정론적으로 배치 (없으면 빈 슬롯 — graceful).
    판정 필드(actual_rung)는 "기술적"으로 고정 — 판정은 연구자 몫.
    """
    region = getattr(spec, "region_code", None) or getattr(spec, "dependent_region", None)
    h1_text = getattr(spec, "h1", "")

    # 증거 소스별 조회 (Token-Zero 결정론)
    acled_evidence  = _fetch_region_evidence(region)           # ACLED 분쟁 사건 (후프·밀짚)
    mofa_evidence   = _fetch_mofa_evidence(region, h1_text)    # 외교부 공문·성명 (흡연총)
    policy_evidence  = _fetch_policy_evidence(region, h1_text)  # Atlantic Council·ACA (흡연총 미국 시각)
    govinfo_evidence = _fetch_govinfo_evidence(region, h1_text) # CPD 대통령 성명 (이중결정 최고 권위)
    # 한반도 가설이면 NK 전문 소스 추가 (NKNews + 38 North)
    nk_evidence = (
        _fetch_nk_evidence(h1_text)
        if region == "korean_peninsula" else []
    )
    # UN News — 이중결정 검정의 다자적 확인 소스
    un_evidence = _fetch_un_evidence(region, h1_text)

    # Van Evera 검정별 증거 배치 원칙:
    #   후프(0)   — ACLED 사건(선행 조건) + MOFA 성명(정책 선언 존재 여부)
    #   흡연총(1) — MOFA(한국 1차) + NKNews/38North(전문 분석) + Atlantic Council(미국 시각)
    #   밀짚(2)   — ACLED 사건(주변 신호)
    #   이중결정(3)— CPD 대통령 성명(★★★★★, 최고 권위) + UN News(다자) + Atlantic Council(분석)
    #               → 한국(MOFA)·미국 대통령(CPD)·UN 3각 일치 = 이중결정 가장 강한 증거
    _ev_map: dict[int, list[dict]] = {
        0: acled_evidence + mofa_evidence[:2],
        1: mofa_evidence + nk_evidence + policy_evidence[:2],
        2: acled_evidence,
        3: govinfo_evidence + un_evidence + policy_evidence[2:4],
    }

    def _note(i: int) -> str:
        ev = _ev_map[i]
        if i == 0:
            a = len(acled_evidence)
            m = len(mofa_evidence[:2])
            if a or m:
                return f"ACLED 사건 {a}건 + 외교부 보도자료 {m}건 배치됨"
            return "DB 증거 없음 — 1차 사료(보도자료·외교문서)로 직접 탐색 필요"
        if i == 1:
            m = len(mofa_evidence)
            n = len(nk_evidence)
            p = len(policy_evidence[:2])
            if m or n or p:
                parts = []
                if m: parts.append(f"외교부 보도자료 {m}건")
                if n: parts.append(f"NK 전문소스 {n}건")
                if p: parts.append(f"Atlantic Council/ACA {p}건(미국 정책 시각)")
                return " + ".join(parts) + " 배치됨"
            return "1차 사료 없음 — 미 국무부·UN 문서·회의록으로 직접 탐색 필요"
        if i == 2:
            a = len(acled_evidence)
            return (
                f"ACLED 분쟁 사건 {a}건 배치됨 (약한 방향 신호)"
                if a else
                "DB 증거 없음 — 언론 보도·통계 동향으로 탐색 필요"
            )
        if i == 3:
            g  = len(govinfo_evidence)
            u  = len(un_evidence)
            p2 = len(policy_evidence[2:4])
            if g or u or p2:
                parts = []
                if g:  parts.append(f"CPD 대통령 성명 {g}건(★★★★★)")
                if u:  parts.append(f"UN News {u}건")
                if p2: parts.append(f"Atlantic Council/ACA {p2}건")
                return (
                    " + ".join(parts)
                    + " — 한(MOFA)·미(CPD)·UN 3각 관점 일치 여부 검토 (이중결정 핵심)"
                )
            return "공식 소스 없음 — 대통령 성명·UN 결의·공동성명으로 직접 탐색 필요"
        return ""

    _note_map: dict[int, str] = {i: _note(i) for i in range(4)}

    tests_with_evidence: list[dict] = []
    for i, test in enumerate(_VAN_EVERA_TESTS):
        ev_block = _ev_map[i]
        tests_with_evidence.append({
            **test,
            "db_evidence":   ev_block,
            "evidence_note": _note_map[i],
        })

    scaffold = {
        "scaffold_type": "process_tracing",
        "framework": "Van Evera (1997) 4검정 — Guide to Methods for Students of Political Science",
        "h1": getattr(spec, "h1", ""),
        "region": region,
        "tests": tests_with_evidence,
        "judgment_note": (
            "각 검정의 통과·실패를 기록한 뒤 종합 판단은 연구자 본인이 내립니다. "
            "AI는 틀과 증거 배치만 담당합니다."
        ),
        "next_steps": [
            "후프·흡연총 검정 모두 통과 → '상관' 수준 주장 가능 (단, 반례 탐색 병행)",
            "이중결정 검정 통과 → 강한 인과 주장 가능 (1차 사료 인용 필수)",
            "검정 실패가 많으면 → 가설 수정 또는 경쟁 이론 채택",
            "1차 사료 부족 → 외교부 보도자료 API / UN 문서 / 외교 전문 활용",
        ],
    }

    logger.info(
        "[process_tracing] region=%s acled=%d mofa=%d nk=%d un=%d h1=%.60s",
        region, len(acled_evidence), len(mofa_evidence),
        len(nk_evidence), len(un_evidence), h1_text,
    )

    return MethodResult(
        method="process_tracing",
        signature=getattr(spec, "data_signature", "UNQUANTIFIABLE"),
        effect_estimate=0.0,
        effect_size_label="해당없음",
        significance=1.0,
        ci_low=0.0,
        ci_high=0.0,
        reachable_rung="기술적",  # 과정추적 단독 → 기술적 수준
        actual_rung="기술적",     # 판정은 연구자 — 엔진이 상향 금지
        assumptions_met=True,     # 질적 방법은 UNQUANTIFIABLE에 적용 가능
        assumption_caveat=(
            "과정추적은 통계 검정이 아닙니다. "
            "판정(가설 지지·기각)은 연구자가 4검정 결과를 종합해 내립니다."
        ),
        robustness={},
        confidence_within_rung=40,  # 과정추적 초기 단계는 낮은 내부 신뢰도
        native_stats=scaffold,
        exploratory=getattr(spec, "exploratory", True),
    )
