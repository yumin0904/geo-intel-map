"""
tests/test_construct_validity_guards.py — 2026-07-13 변수 타당도 감사의 회귀 방어.

왜 이 파일이 있는가:
    2026-07-13에 엔진의 변수 층이 무너져 있는 것이 드러났다 — "분쟁 이벤트"의
    98.8%가 남한 국내 시위였고, "물리적 충돌"이 포뮬러 1 그랑프리 보도였으며,
    "회색지대"가 키이우 미사일에 붙어 있었다. 전부 수리했다.

    그런데 수리는 조용히 되돌아간다. 리팩터 한 번, 쿼리 최적화 한 번이면
    AVG(severity)가 다시 컨텍스트에 들어가고 gray_zone이 다시 미사일에 붙는다.
    **이 파일은 그 되돌아감을 막는 그물이다.**

    각 테스트는 "무엇이 무너지면 이 테스트가 깨지는가"를 docstring에 적는다 —
    미래의 누군가가 이 테스트를 지우려 할 때 그 대가를 알 수 있도록.

원문: geo-os/docs/ENGINE_VARIABLE_AUDIT_20260713.md
판례: geo-os/wiki/decisions/20260713-variable-validity-committee.md
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

_DB = _BACKEND / "db" / "intel.db"


def _ctx(query: str) -> str:
    from services.entity_parser import parse_query
    from services.intel_analyzer import build_intel_context
    return asyncio.run(build_intel_context(parse_query(query)))["context_text"]


def _warned_total(ctx: str) -> str:
    """경고가 붙은 권역의 총건수를 **컨텍스트에서 읽어온다**.

    수치를 테스트에 하드코딩하지 않는다 — 구판은 "8,265"를 박아뒀는데, 하류 오염
    위원회가 게이트 분모의 GDELT 희석을 걷어내자(진값 8,207) 픽스처가 낡아 게이트가
    멀쩡한데도 테스트만 깨졌다. 가드가 지키는 대상은 '그때 그 숫자'가 아니라
    '지금 컨텍스트가 경고한 숫자'다. 테스트도 그렇게 물어야 한다.
    """
    from services.caveat_gate import _warned_regions
    warned = _warned_regions(ctx)
    assert warned, "컨텍스트에 구성 타당도 경고가 없다 — 픽스처 전제 붕괴"
    return next(iter(warned.values()))


# ── 1. 이벤트 구성 타당도 ────────────────────────────────────────────────────

def test_context_exposes_event_composition_not_avg_severity():
    """컨텍스트는 'AVG(severity)'가 아니라 **구성**을 보여줘야 한다.

    무너지면: 구 컨텍스트가 LLM에게 "korean_peninsula 평균 심각도 15.9/100"이라
    말했고, 15는 정확히 Protests의 기본점수였다. 데이터는 "이건 시위다"라고
    속삭였고 라벨은 "분쟁"이라 외쳤다. severity는 위해 척도가 아니라 event_type
    조회표다(사망 0명 전투 70 > 사망 36명 폭동 65).
    """
    ctx = _ctx("북한 미사일 도발과 한국 방산주")
    assert "심각도" not in ctx, "severity가 추론 층에 되살아났다"
    assert "구성:" in ctx and "Protests" in ctx, "event_type 구성이 컨텍스트에 없다"
    assert "사망" in ctx, "사망자 실수가 컨텍스트에 없다"


def test_composition_warning_fires_for_protest_dominated_region():
    """시위가 지배적인 권역에는 **구성 타당도 경고**가 떠야 한다.

    무너지면: "한반도 분쟁·충돌 이벤트 8,265건"(98.8%가 남한 국내 시위)이 북한
    도발 가설의 독립변수가 된다 — 8호 사고와 예측 원장 293건의 오염 경로.
    """
    ctx = _ctx("북한 미사일 도발과 한국 방산주")
    assert "구성 타당도 경고" in ctx, "한반도(99.3% 시위)에 경고가 안 떴다"
    assert "군사 충돌 지표가 아니다" in ctx


def test_composition_warning_silent_for_real_war():
    """진짜 전쟁에는 경고가 뜨면 안 된다 — 오탐하면 경고가 무시된다.

    무너지면: 우크라이나(폭발 64%·전투 30%·사망 113,730명)에 "군사 지표가
    아니다"라는 경고가 뜨면 경고 자체의 신뢰가 무너지고 아무도 안 읽는다.
    """
    ctx = _ctx("우크라이나 전황과 에너지 인프라")
    assert "구성 타당도 경고" not in ctx, "진짜 전쟁에 오탐 경고가 떴다"


def test_borderline_region_gets_caution():
    """문턱 바로 아래가 가장 위험하다 — 단계식 경고여야 한다.

    무너지면: 호르무즈(시위 45.0%)가 이진 문턱(50%)을 빠져나간다. 그 45%가
    이란 국내 시위이고, 하필 그 권역이 전문가 패킷 가설("월간 200건 초과 시
    유가 상승" — 전 기간 1회 발화, 그 1회가 이란 시위 270건)의 무대다.
    """
    ctx = _ctx("호르무즈 해협 봉쇄가 유가에 미치는 영향")
    assert re.search(r"구성 타당도 (경고|주의)", ctx), "호르무즈 45%에 아무 경고도 없다"


# ── 2. ACLED 수집 랙 ─────────────────────────────────────────────────────────

def test_acled_lag_months_quarantined_from_trend():
    """수집 랙 구간의 월은 추세 산출에서 격리돼야 한다.

    무너지면: CLAUDE.md §18-A 규칙 1("근과거 <14개월 건수를 증거로 쓰지 않는다")이
    다시 선언만 남는다. 실측 아티팩트 2건이 되살아난다 —
      한반도 "1,348건→2건 급감"(NLL 인사이트가 실제 감소로 오독한 그것)
      우크라이나 "110→1,058건 +861.8% ▲"(전쟁 중인데 월 110건일 리 없다)
    """
    ctx = _ctx("우크라이나 전황과 에너지 인프라")
    assert "수집 랙 구간" in ctx, "랙 구간 격리 표시가 사라졌다"
    assert "이 숫자로 증감·추세를 서술하지 마라" in ctx
    # 랙 구간 수치가 '직전 완결월 대비' 산출에 들어가면 안 된다
    m = re.search(r"직전 완결월 대비: ([\d,]+)건→([\d,]+)건", ctx)
    if m:
        a, b = (int(x.replace(",", "")) for x in m.groups())
        assert a > 5000 and b > 5000, (
            f"우크라이나 추세가 랙 구간 수치({a}→{b})로 산출됐다 — 아티팩트 부활"
        )


# ── 3. theory_tags 배타성 ────────────────────────────────────────────────────

def test_gray_zone_never_coexists_with_armed_conflict():
    """회색지대는 무력분쟁 문턱 **아래**를 뜻한다 — 재래식전과 공존할 수 없다.

    무너지면: 우크라이나의 미사일·포격 69,800건이 다시
    ["conventional_warfare", "gray_zone", "hybrid_warfare"]가 된다. 같은 사건이
    "재래식 정규전"이면서 "전쟁 문턱 아래의 강압"이라는 정의상 모순.
    수리 전 실측: 모순 동시 태깅 88,227건.
    """
    con = sqlite3.connect(_DB)
    n = con.execute(
        "SELECT COUNT(*) FROM event_archive "
        "WHERE theory_tags LIKE '%gray_zone%' "
        "  AND (theory_tags LIKE '%conventional_warfare%' "
        "    OR theory_tags LIKE '%civil_war%' "
        "    OR theory_tags LIKE '%insurgency%')"
    ).fetchone()[0]
    con.close()
    assert n == 0, f"회색지대∧무력분쟁 동시 태깅 {n:,}건 부활 (수리 전 88,227건)"


def test_gray_zone_fallback_is_not_a_theory_tag():
    """분류 실패를 '회색지대'라 부르면 미분류가 이론 태그로 승격된다.

    무너지면: _build_theory_tags의 폴백이 다시 ["gray_zone"]이 되어, 아무 이론에도
    안 걸리는 사건이 전부 '회색지대 전략'으로 태깅된다.
    """
    from connectors.acled import _build_theory_tags
    tags = _build_theory_tags("알 수 없는 유형", "", 0, 0, None, country="", fatalities=0)
    assert "gray_zone" not in tags, "폴백이 다시 gray_zone이 됐다"
    assert tags == ["unclassified"]


def test_lethal_event_is_not_gray_zone():
    """사망자가 나온 사건은 정의상 '무력분쟁 문턱 아래'가 아니다."""
    from connectors.acled import _build_theory_tags
    tags = _build_theory_tags("Explosions/Remote violence", "shelling",
                              1, 1, "ukraine", country="Ukraine", fatalities=12)
    assert "gray_zone" not in tags, "사망 12명 사건에 gray_zone이 붙었다"


# ── 4. cascade 생존편향 ──────────────────────────────────────────────────────

def test_cascade_confesses_survivorship_and_staleness():
    """cascade_links는 **적중만 적재된다** — 컨텍스트가 그 사실을 자백해야 한다.

    무너지면: _evaluate_trigger가 miss에 None을 반환하므로 3,012건 전부 '적중'이고
    79%가 정확히 1.0인 **분모 없는 기록**이 '상관 점수'로 LLM에 제시된다.
    게다가 링크는 요청 시점 pull로만 생성돼 26일 이상 정체할 수 있다.
    """
    ctx = _ctx("호르무즈 해협 긴장이 유가에 미치는 영향")
    if "## Cascade 발화 실적" not in ctx:
        pytest.skip("이 쿼리에 cascade 블록 없음")
    assert "분모 없음" in ctx, "생존편향 자백이 사라졌다"
    assert "빗나간 횟수를 우리는 모른다" in ctx
    assert "신선도" in ctx, "신선도 경고가 사라졌다"


# ── 5. 채점기 오염 격리 ──────────────────────────────────────────────────────

def test_scorer_quarantines_contaminated_sources():
    """오염된 소스에 신뢰도 크레딧을 주면 안 된다.

    무너지면: 2026-07-13 오전에 신설한 T1 티어가 event_stats(오염된 severity·건수
    기반)를 '순수 데이터'로 계수하고 cascade_links(생존편향)에 +10 보너스를 줬다.
    **오염된 입력에 만점 신뢰를 주는 계기**를 그날 새로 만든 것이었다.
    """
    from services.confidence_scorer import score_confidence
    r = score_confidence("", {"event_stats_regions": 1, "cascade_links": 8},
                         {"flag": "GROUNDED", "grounded_ratio": 0.5})
    q = r["breakdown"]["quarantined"]
    assert "event_stats_regions" in q and "cascade_links" in q, "격리가 해제됐다"
    assert r["confidence"] <= 40, f"오염 소스만으로 conf={r['confidence']} (≤40이어야)"


def test_scorer_has_no_prose_shape_points():
    """산문의 생김새를 채점하면 안 된다 — 주제를 못 본 글이 100점을 받는다.

    무너지면: 구 score_output이 '숫자가 등장하는가(+30)', '기관명 문자열이
    있는가(+20)', '[경쟁설명] 섹션이 있는가(+15)'로 채점했다. 서해를 한 번도
    못 본 인사이트가 드론 브리핑의 숫자를 인용하고 "MEDIUM"이라 쓰면 100점이었다.
    """
    from services.confidence_scorer import score_confidence
    fake = "숫자 30%. ACLED. H1: 반증 가능. [경쟁설명] 대안. 연쇄강도 MEDIUM."
    r = score_confidence(fake, {}, {"flag": "TOPIC_ABSENT", "grounded_ratio": 0.0})
    assert r["confidence"] <= 40, "산문 형태만으로 고득점 — 구 계기 부활"
    assert r["provisional"] is True


# ── 6. 접지 가드 ─────────────────────────────────────────────────────────────

def test_grounding_measured_on_data_layer_only():
    """접지는 **데이터층**에서 재야 한다 — 브리핑 히트를 세면 자기 표적을 놓친다.

    무너지면: 컨텍스트 전체에서 주제어를 세면 브리핑 본문 히트가 접지로 계수된다.
    실측: "도발"이 브리핑 9편에 등장 → 서해 데이터가 0건인 인사이트가 grounded=True로
    **초록불 통과**. 반박석이 '설계 기각급'으로 판정한 미탐이다.
    """
    from services.entity_parser import parse_query
    from services.intel_analyzer import build_intel_context
    ctx = asyncio.run(build_intel_context(parse_query("대만해협 긴장과 반도체 공급망")))
    g = ctx["grounding"]
    assert "브리핑" in g["basis"] and "제외" in g["basis"], "접지 분모가 데이터층이 아니다"
    assert g["flag"] in ("GROUNDED", "TOPIC_SPARSE", "TOPIC_ABSENT")


# ── 7. 변수 카탈로그 등재 강제 ──────────────────────────────────────────────

def _catalog_keys() -> set[str]:
    """yaml 없이 파싱 — 이 테스트가 pyyaml 부재로 조용히 skip되면 안 된다."""
    txt = (_BACKEND / "config" / "variable_catalog.yaml").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*-\s*key:\s*(\S+)", txt, re.M))


def test_all_context_sources_are_cataloged():
    """**LLM 컨텍스트에 들어가는 모든 숫자는 신원이 밝혀져 있어야 한다.**

    무너지면: 2026-07-13 오염 변수들의 공통점이 정확히 이것이었다 — 아무도
    "이 숫자가 실제로 무엇을 재는가"를 적어두지 않았다. 이름을 믿었고, 그
    이름이 가설의 독립변수가 됐다(예측 원장 974건 중 293건이 오염된 IV).

    새 소스를 컨텍스트에 넣으려면 config/variable_catalog.yaml에 등재하고
    `measures`(실제로 무엇을 재는가)를 **실측으로** 적어야 한다.
    "이름이 그럴듯해서" 통과할 수 없다.
    """
    from services.entity_parser import parse_query
    from services.intel_analyzer import build_intel_context

    cataloged = _catalog_keys()
    assert cataloged, "변수 카탈로그가 비었다 — 파싱 실패 가능성"

    seen: set[str] = set()
    for q in ("호르무즈 해협 봉쇄가 유가에 미치는 영향",
              "북한 미사일 도발과 한국 방산주",
              "대만해협 긴장과 반도체 공급망"):
        ctx = asyncio.run(build_intel_context(parse_query(q)))
        seen |= {k for k, v in ctx["source_counts"].items() if v}

    # 순수 계측 키(신원 대상 아님)
    METRICS_ONLY = {"event_stats_regions"} & set()  # placeholder — 아래 명시 제외 없음
    missing = seen - cataloged - METRICS_ONLY
    assert not missing, (
        f"미등재 소스가 컨텍스트에 주입되고 있다: {sorted(missing)}\n"
        f"  → config/variable_catalog.yaml에 등재하고 'measures'(실제로 무엇을 재는가)를 "
        f"실측으로 적어라. 2026-07-13 감사의 재발 방지 장치다."
    )


def test_retired_variables_stay_out_of_context():
    """퇴역 변수가 컨텍스트에 되살아나면 안 된다.

    무너지면: severity(사건유형 조회표)·GDELT 톤 평균(전쟁을 못 봄)·
    importance_score(전건 0.0)가 다시 LLM에게 제시된다.
    """
    txt = (_BACKEND / "config" / "variable_catalog.yaml").read_text(encoding="utf-8")
    retired = re.findall(r"-\s*key:\s*(\S+)(?:(?!\n\s*-\s*key:).)*?validity:\s*retired",
                         txt, re.S)
    assert retired, "퇴역 목록 파싱 실패"

    from services.entity_parser import parse_query
    from services.intel_analyzer import build_intel_context
    ctx = asyncio.run(build_intel_context(parse_query("북한 미사일 도발과 한국 방산주")))
    for key in retired:
        assert not ctx["source_counts"].get(key), f"퇴역 변수 {key}가 부활했다"


# ── 8. 경고 준수 게이트 ──────────────────────────────────────────────────────

def test_caveat_gate_catches_ignored_warning():
    """컨텍스트가 경고했는데 출력이 무시하면 **강등**돼야 한다.

    무너지면: "말했다"와 "지켜졌다"가 다르다는 것을 놓친다. 컨텍스트에
    "이 건수는 군사 충돌 지표가 아니다"라고 심어놓고 LLM이 그대로 무시하면
    아무것도 막지 못한다 — 그날 아침 회수한 1호와 같은 병(페이지엔 배지가
    있었는데 기계 표면엔 없었다).

    ⚠️ 초판 게이트가 **자기 표적을 놓쳤다**(검출 0건). 버그 2개:
      ① 정규식이 "**구성 타당도 경고(강)**"의 (강)을 예상 못 함
      ② \\b 단어경계 — 파이썬에서 한글은 단어 문자라 "8,265건"의 5와 건 사이에
         경계가 없다. 숫자 경계로 교체.
    음성 테스트가 둘 다 잡았다 (폐기 원장 패턴 E).
    """
    from services.caveat_gate import apply_gate
    ctx = _ctx("북한 미사일 도발과 한국 방산주")
    n = _warned_total(ctx)
    bad = f"[관찰] 한반도의 긴장은 {n}건에 달한다. 북한의 무력 도발이 잦다."
    out, acts = apply_gate(bad, ctx)
    assert acts, "경고를 무시한 인용을 못 잡았다 — 가드가 자기 표적을 놓쳤다"
    assert "경고게이트" in out, "강등 스탬프가 안 박혔다"


def test_caveat_gate_allows_qualified_citation():
    """자격 표시가 있으면 **서술은** 정상 인용이다 — 오탐하면 게이트가 무시된다."""
    from services.caveat_gate import apply_gate
    ctx = _ctx("북한 미사일 도발과 한국 방산주")
    n = _warned_total(ctx)
    for ok in (f"[관찰] 한반도 이벤트 {n}건 중 99.5%가 국내 시위다.",
               f"[관찰] 한반도 이벤트는 총 {n}건 수집됐다."):
        _, acts = apply_gate(ok, ctx)
        assert not acts, f"정상 인용을 오탐했다: {ok}"


def test_caveat_gate_blocks_qualified_causal_citation():
    """**자격 표시를 달아도 인과 주장의 근거로 쓰면 위반이다.** (하류 오염위 2026-07-13)

    무너지면: 판례 폐기 #1(캐비엇 달고 라이브 유지 = C안)이 코드에서 부활한다.
    8호가 정확히 이것을 했다 — 한계 절에 "ACLED 이벤트는 미사일 도발만이 아니라
    한반도 긴장 전반을 포괄하므로"라고 자격을 표시하는 시늉을 하고, 그 숫자 위에
    Granger 검정을 세우고, 「도발의 가격」이라는 제목으로 발행했다.

    **알면서 쓴 것이 모르고 쓴 것보다 낫지 않다.** 오염된 건수는 서술의 대상은
    되어도 추론의 근거는 될 수 없다.
    """
    from services.caveat_gate import apply_gate
    ctx = _ctx("북한 미사일 도발과 한국 방산주")
    n = _warned_total(ctx)
    # 자격 표시(국내 시위)가 **있는데도** 인과 프레임이라 막혀야 한다.
    bad = (f"[가설] 한반도 분쟁 이벤트 {n}건(99.5%가 국내 시위)이 증가할 때 "
           f"방산 ETF가 유의하게 상승한다.")
    out, acts = apply_gate(bad, ctx)
    assert acts, "자격 표시가 붙은 인과 인용을 통과시켰다 — 판례 C안이 코드에서 부활했다"
    assert acts[0]["code"] == "construct_invalid_iv", f"코드 오분류: {acts[0]['code']}"
    assert "자격 표시가 구제하지 못한다" in out, "강등 사유가 안 박혔다"
    # 스탬프가 수치를 쪼개지 않는다 — "99.5%"의 소수점을 문장 끝으로 오인하던 버그.
    assert "99.5%가 국내 시위" in out, "강등 스탬프가 문장 중간(소수점)에 박혀 본문을 훼손했다"


def test_caveat_gate_silent_when_no_warning():
    """경고가 없던 권역(진짜 전쟁)에는 게이트가 발화하면 안 된다."""
    from services.caveat_gate import apply_gate
    ctx = _ctx("우크라이나 전황과 에너지 인프라")
    txt = "[관찰] 우크라이나 분쟁 이벤트 108,417건이 전쟁 강도를 보여준다."
    _, acts = apply_gate(txt, ctx)
    assert not acts, "경고 없는 권역에 게이트가 오발화했다"
