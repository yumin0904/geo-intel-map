"""
services/intel_analyzer.py

멀티소스 병렬 검색 + 컨텍스트 조립 (Token-Zero).

소스:
  1.  LIKE 검색 — 한국어 키워드로 브리핑·이론 title/body 검색
  2.  섹터 필터 — 섹터별 최신 브리핑
  3.  event_archive 통계 — 지역별 집계
  4.  cascade_links — 지역 발화 실적 + 이론 텍스트
  5.  country_geopolitics.yaml — 행위자 국가 프로파일
  6.  SIPRI Military Expenditure — 국방비 %GDP
  7.  COW Alliances — 공식 동맹
  8.  Kiel Ukraine Support Tracker — 서방 지원액
  9.  EIA Energy — 초크포인트 통과량
  10. CSIS Cyber Incidents — APT 사건 선례
  11. SIPRI Arms Transfers — 무기 의존도·공급망 (Cycle 6-A)
  12. V-DEM Democracy Index — 행위자 체제 유형 정량화 (Cycle 6-A)
  13. COW Wars — 전쟁 선례 시계열 (Cycle 6-A)
  14. 외교부 LOD IFANS — 한반도·동아시아 한국 시각 발간자료 (Cycle 6-A)
  15. 경쟁 이론 비교 프로파일 — 이론 예측값 vs 실측값 편차 컨텍스트 (Cycle 7-B)
"""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import yaml
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from services.entity_parser import ParsedQuery
from services.theory_comparator import build_theory_comparison_context
from services.claim_ledger import build_claim_ledger

logger = logging.getLogger(__name__)

_CONFIG   = Path(__file__).resolve().parent.parent / "config"
_INTEL_DB = Path(__file__).resolve().parent.parent / "db" / "intel.db"
_LIB_DB   = Path(__file__).resolve().parent.parent / "db" / "library.db"

# ACLED 학술 티어 수집 랙 (CLAUDE.md §18-A 규칙 1 — event_date 기준 최대 ~14개월).
# 이 창 안의 월은 백필이 진행 중이므로 건수가 확정되지 않았다. 추세 산출 금지.
_ACLED_LAG_MONTHS = 14

# 브리핑 원문 1개당 최대 포함 글자 수 (토큰 절약)
_BODY_MAX_CHARS = 3000
# [접지 감사 2026-07-13] 브리핑 전문(full body) 주입 자격 문턱 — 쿼리 고유
# 키워드(지역 별칭 제외) 가중 히트합(title 3·summary 2·body 1). 미달은 요약 강등.
# 실측 근거: NLL 쿼리에서 '북한' 별칭 하나로 드론·테러 브리핑이 전문 주입돼
# 컨텍스트 90%를 독점(ENGINE_GROUNDING_AUDIT_20260713 §8-2).
_BRIEF_FULL_MIN = 4
# Gemini 컨텍스트 총 상한 (글자 기준 — 약 30,000 tokens)
_CONTEXT_MAX_CHARS = 20000
# _build_context 섹션 추가 전 예산 검사용 헬퍼
def _over_budget(lines: list[str]) -> bool:
    """현재까지 누적된 컨텍스트가 상한을 초과했는지 확인."""
    return sum(len(l) + 1 for l in lines) >= _CONTEXT_MAX_CHARS


# PERF-3: 정적 소스 모듈 레벨 TTL 캐시
# Polity5·HIIK·ITU·semi_market·EIA·SIPRI milex 등은 CSV 재적재 전까지 불변.
# 5분 TTL로 개발 중 DB 갱신도 반영하면서 중복 SQLite I/O를 방지한다.
import time as _time

_STATIC_CACHE: dict[tuple, tuple[object, float]] = {}
_STATIC_TTL = 300  # 5분


def _scache_key(*args) -> tuple:
    """list를 tuple로 재귀 변환해 hashable 키 생성."""
    return tuple(
        tuple(sorted(a)) if isinstance(a, list) else a
        for a in args
    )


def _scache_get(key: tuple):
    entry = _STATIC_CACHE.get(key)
    if entry is None:
        return None
    value, exp = entry
    if _time.monotonic() > exp:
        del _STATIC_CACHE[key]
        return None
    return value


def _scache_set(key: tuple, value) -> None:
    _STATIC_CACHE[key] = (value, _time.monotonic() + _STATIC_TTL)


@contextmanager
def _db(path: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


# ── 1. LIKE 기반 한국어 키워드 검색 ─────────────────────────────────────────

# 어절 말미 조사 — 벗겨서 2자 이상 남을 때만 채택 (접지 감사 2026-07-13:
# '증가가'·'빈도와'·'도발의'가 그대로 키워드가 되어 브리핑 관련도와 접지 측정을
# 모두 오염시키던 결함. 전수 감사에서 NLL 쿼리가 일반어 히트로 '접지' 오판된 근원)
_JOSA_TAIL = re.compile(
    r"(?:은|는|이|가|을|를|과|와|의|도|만|에|에서|으로|로|보다|까지|부터|처럼|마다|조차|밖에)$")


def _extract_keywords(query: str) -> list[str]:
    """쿼리에서 유의미한 키워드 추출 (한국어 2자+ 조사 제거 / 영어 3자+)."""
    ko: list[str] = []
    for w in re.findall(r"[가-힣]{2,}", query):
        stripped = _JOSA_TAIL.sub("", w)
        w2 = stripped if len(stripped) >= 2 else w
        if w2 not in ko:
            ko.append(w2)
    en = [w.lower() for w in re.findall(r"[a-zA-Z]{3,}", query)
          if w.lower() not in {"the", "and", "for", "with", "this", "that"}]
    return (ko + en)[:8]


def _search_library_like(query: str, regions: list[str],
                          sectors: list[str], limit: int = 10) -> list[dict]:
    """
    LIKE 기반 한국어·영어 혼합 검색.
    title + summary + body 전체에서 키워드 매칭.
    """
    keywords = _extract_keywords(query)

    # 지역 한국어 별칭도 검색 키워드에 추가
    _REGION_KO_SEARCH = {
        "ukraine": ["우크라이나", "러시아"], "taiwan_strait": ["대만", "양안"],
        "hormuz": ["호르무즈", "이란"], "bab_el_mandeb": ["홍해", "후티"],
        "south_china_sea": ["남중국해"], "korean_peninsula": ["한반도", "북한"],
        "middle_east": ["중동", "이스라엘"], "east_china_sea": ["동중국해"],
    }
    for r in regions:
        keywords.extend(_REGION_KO_SEARCH.get(r, []))
    keywords = list(dict.fromkeys(keywords))[:10]  # 중복 제거

    if not keywords:
        return []

    try:
        with _db(_LIB_DB) as con:
            # [밤샘 사이클 2, 2026-07-13] 관련도 랭킹 — 구현은 최신순(published_date)뿐이라
            # 주석("히트 수로 관련도 계산")이 거짓이었다. 최신 화제 브리핑이 전 쿼리에
            # 밀려들어 15개 이질 쿼리의 컨텍스트가 자카드 0.48로 겹침 → IV 표류(후티
            # 쿼리에 이란전 가설)의 상류 원인. 키워드 히트 가중합(title 3·summary 2·
            # body 1)으로 정렬하고 최신순은 동점 타이브레이크로 강등. Token-Zero 결정론.
            conditions = " OR ".join(
                f"(title LIKE ? OR summary LIKE ? OR body LIKE ?)"
                for _ in keywords
            )
            score_expr = " + ".join(
                "((title LIKE ?) * 3 + (summary LIKE ?) * 2 + (body LIKE ?))"
                for _ in keywords
            )
            params: list = []
            for kw in keywords:          # score_expr 파라미터
                pat = f"%{kw}%"
                params.extend([pat, pat, pat])
            for kw in keywords:          # conditions 파라미터
                pat = f"%{kw}%"
                params.extend([pat, pat, pat])
            params.append(limit)

            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary,
                       source_org, geopol_region, asset_type,
                       published_date, body,
                       independent_var, dependent_var, conditions,
                       falsifiable_prediction, known_counterexample, rival_theories,
                       contested_by,
                       ({score_expr}) AS _relevance
                FROM theories
                WHERE {conditions}
                ORDER BY _relevance DESC, published_date DESC NULLS LAST
                LIMIT ?
                """,
                params,
            ).fetchall()
        # [접지 감사 2026-07-13] 자체 관련도: 지역 별칭('북한'·'한반도')을 뺀
        # 쿼리 고유 키워드만으로 재채점. 별칭 한 단어만 겹친 브리핑(드론·테러)이
        # 전문 주입 자격을 얻어 컨텍스트 90%를 독점하던 경로의 판별 신호 —
        # _build_context가 이 값으로 전문/요약을 가른다.
        own_kws = [k.lower() for k in _extract_keywords(query)]
        # 문서빈도(DF) 할인 — 라이브러리 문서의 30%+에 등장하는 일반어('구조'·
        # '이후'·'공백')는 판별력이 없어 가중치 0. 일반어 body 히트가 쌓여 무관
        # 브리핑(우크라 전장 루프 등)이 전문 주입 문턱을 넘던 것을 결정론 차단
        # (반박석 공격 실증 후 보강, 2026-07-13). 94행 테이블이라 비용 무시 가능.
        with _db(_LIB_DB) as con:
            n_docs = con.execute("SELECT COUNT(*) FROM theories").fetchone()[0] or 1
            distinctive = []
            for k in own_kws:
                pat = f"%{k}%"
                df = con.execute(
                    "SELECT COUNT(*) FROM theories WHERE title LIKE ? "
                    "OR summary LIKE ? OR body LIKE ?", (pat, pat, pat)
                ).fetchone()[0]
                if df / n_docs <= 0.30:
                    distinctive.append(k)
        items = []
        for r in rows:
            it = {k: v for k, v in dict(r).items() if k != "_relevance"}
            t = (it.get("title") or "").lower()
            s = (it.get("summary") or "").lower()
            b = (it.get("body") or "").lower()
            it["_own_relevance"] = sum(
                (k in t) * 3 + (k in s) * 2 + (k in b) for k in distinctive)
            # 제목/요약 전용 점수 — body-only 누적으로 무관 브리핑이 전문 자격을
            # 얻는 잔여 경로 차단(이란전·테러 브리핑 실측, 2026-07-13)
            it["_own_rel_ts"] = sum(
                (k in t) * 3 + (k in s) * 2 for k in distinctive)
            items.append(it)
        return items
    except Exception as e:
        logger.warning("[intel] LIKE 검색 실패: %s", e)
        return []


# ── 2. 섹터 필터 검색 ────────────────────────────────────────────────────────

def _search_library_by_sector(sectors: list[str], limit: int = 6) -> list[dict]:
    """섹터 필터로 최신 브리핑·이론 조회 (body 포함)."""
    if not sectors:
        return []
    placeholders = ",".join("?" * len(sectors))
    try:
        with _db(_LIB_DB) as con:
            rows = con.execute(
                f"""
                SELECT theory_id, title, sector_tag, summary,
                       source_org, geopol_region, asset_type,
                       published_date, body,
                       independent_var, dependent_var, conditions,
                       falsifiable_prediction, known_counterexample, rival_theories,
                       contested_by
                FROM theories
                WHERE sector_tag IN ({placeholders})
                ORDER BY published_date DESC NULLS LAST
                LIMIT ?
                """,
                (*sectors, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] sector 검색 실패: %s", e)
        return []


# ── 3. event_archive 통계 ────────────────────────────────────────────────────

_REGION_KO: dict[str, list[str]] = {
    "ukraine":          ["우크라이나"],
    "taiwan_strait":    ["대만", "대만해협"],
    "hormuz":           ["호르무즈"],
    "bab_el_mandeb":    ["바브엘만데브", "홍해"],
    "south_china_sea":  ["남중국해"],
    "korean_peninsula": ["한반도", "북한"],
    "malacca":          ["말라카"],
    "suez":             ["수에즈"],
    "middle_east":      ["중동"],
    "east_china_sea":   ["동중국해"],
}


# [큐 10] 월간 변화율 산출의 분모 하한 — 미만이면 %·방향이 수집 아티팩트에 지배됨
_TREND_MIN_BASE = 30


def _get_event_stats(regions: list[str]) -> dict:
    if not regions:
        return {}
    placeholders = ",".join("?" * len(regions))
    try:
        with _db(_INTEL_DB) as con:
            # [변수 타당도 감사 2026-07-13] 구 쿼리는 source_type("conflict")으로
            # 그룹핑해 "유형: conflict(8265건)"이라는 무의미한 줄을 만들었다. 그
            # 8,265건의 98.8%가 남한 국내 시위인데 컨텍스트는 그 사실을 한 번도
            # 말하지 않았고, 그래서 "한반도 분쟁 이벤트"가 가설의 독립변수가 됐다.
            # 실제 ACLED event_type + 사망자를 조달한다 — 숫자를 압축하지 말고
            # 구성을 보여준다.
            #
            # [하류 오염 위원회 2026-07-13 · 계량석] data_source='ACLED' 필터 신설.
            # 이 절의 제목은 "ACLED 이벤트 통계"인데 쿼리는 event_archive 전체를
            # 긁어 GDELT 행까지 세고 있었다. GDELT 행은 event_type이 NULL이라
            # COALESCE로 '미분류'가 되고, 분자(시위·소요)에는 원리상 못 들어가면서
            # 분모만 불린다 — 순수 희석재다. 호르무즈: ACLED 305 + GDELT 337 = 642가
            # 분모가 돼 구성비가 94.8% → 45.0%로 내려앉았고, 그래서 강경고(≥50%)를
            # 빠져나갔다. 그 GDELT 337건의 정체가 n_material_conflict — 같은 감사가
            # 오염이라 선고한 바로 그 변수다(행위자 국적 키·모나코 F1 사건).
            # **오염을 잡는 게이트의 분모가 오염으로 채워져 있었다.**
            # 희석은 언제나 한 방향(비율을 낮춤)이라 거짓음성만 만들고, 피해는
            # ACLED 기반이 얇은 초크포인트(호르무즈·수에즈·말라카)에 집중된다 —
            # 게이트가 가장 필요한 곳에서 가장 약했다.
            acled = "json_extract(payload, '$.data_source') = 'ACLED'"
            rows = con.execute(
                f"""
                SELECT region_code,
                       COALESCE(json_extract(payload, '$.event_type'), '미분류') AS etype,
                       COUNT(*) AS cnt,
                       SUM(CAST(COALESCE(json_extract(payload, '$.fatalities'), 0) AS INT))
                           AS deaths
                FROM event_archive
                WHERE region_code IN ({placeholders}) AND {acled}
                GROUP BY region_code, etype
                ORDER BY cnt DESC
                """,
                tuple(regions),
            ).fetchall()
            # [변수 타당도 감사 2026-07-13] AVG/MAX(severity) 조달 중단.
            # severity는 위해 척도가 아니라 event_type 조회표라(connectors/acled.py
            # 정의부 참조) 권역 평균은 "사건 유형 구성비"를 숫자로 재진술한 것이다.
            # total만 남긴다 — 구성과 사망자는 위 rows 쿼리가 조달한다.
            sev_rows = con.execute(
                f"""
                SELECT region_code, COUNT(*) as total
                FROM event_archive
                WHERE region_code IN ({placeholders}) AND {acled}
                GROUP BY region_code
                """,
                tuple(regions),
            ).fetchall()
            # [큐 10 — 시계열 형태 공백 처방 2026-07-11] 총량·평균만 주면 모델이 총량으로
            # 추세를 창작한다(전수 감사 검증비약 ~12건의 구조 원인). 월별 배열을 Token-Zero로
            # 사전계산 조달 — 추세 서술의 유일 허용 원천.
            # ACLED 필터가 여기에도 필요한 이유: GDELT 행은 2026-05~06 적재 버스트에
            # 몰려 있어, 수년치 ACLED 월별 배열에 2개월치 GDELT를 섞으면 그 두 달만
            # 인위적으로 부풀어 "최근 급증"이라는 추세를 창작한다.
            month_rows = con.execute(
                f"""
                SELECT region_code, substr(timestamp, 1, 7) AS ym, COUNT(*) AS cnt
                FROM event_archive
                WHERE region_code IN ({placeholders}) AND {acled}
                GROUP BY region_code, ym
                ORDER BY ym DESC
                """,
                tuple(regions),
            ).fetchall()

        stats: dict = {}
        for r in rows:
            rc = r["region_code"]
            if rc not in stats:
                stats[rc] = {"event_types": {}, "deaths": 0}
            stats[rc]["event_types"][r["etype"]] = r["cnt"]
            stats[rc]["deaths"] = stats[rc].get("deaths", 0) + (r["deaths"] or 0)
        for r in sev_rows:
            rc = r["region_code"]
            if rc not in stats:
                stats[rc] = {"event_types": {}}
            stats[rc]["total_events"] = r["total"]
        # 월별 추이: 지역별 최근 6개 버킷(ym 내림차순 조회분을 오름차순 보관).
        # 변화율은 '완결월' 두 개 사이만 — 당월은 진행 중이라 비교 대상에서 제외.
        this_ym = datetime.now(timezone.utc).strftime("%Y-%m")
        # [변수 타당도 감사 2026-07-13] ACLED 수집 랙 집행 — CLAUDE.md §18-A 규칙 1
        # ("ACLED 학술 티어는 event_date 기준 최대 ~14개월 랙. 근과거(<14개월) 분석에
        # 이벤트 건수를 증거로 쓰지 않는다")은 선언만 있고 집행이 없었다. 랙 구간의
        # 월은 백필이 아직 들어오는 중이라 건수가 낮게 나오고, 그것을 완결월로 취급해
        # 추세를 만들면 아티팩트가 된다 — 실측 사례: 한반도 "1,348건→2건 급감"(NLL
        # 인사이트), 우크라이나 "110건→1,058건 +861.8%". 둘 다 실제 변화가 아니다.
        _now = datetime.now(timezone.utc)
        _lag_cut = (_now.year * 12 + _now.month) - _ACLED_LAG_MONTHS
        def _in_lag(ym: str) -> bool:
            return (int(ym[:4]) * 12 + int(ym[5:7])) > _lag_cut

        monthly: dict[str, list] = {}
        for r in month_rows:
            monthly.setdefault(r["region_code"], []).append((r["ym"], r["cnt"]))
        for rc, series in monthly.items():
            if rc not in stats:
                continue
            series = sorted(series)
            stats[rc]["lag_months"] = [ym for ym, _ in series if _in_lag(ym)]
            # 랙 구간 월은 추세 산출에서 제외 — 렌더러가 별도로 '미확정'이라 표시한다.
            settled = [(ym, c) for ym, c in series if not _in_lag(ym)]
            stats[rc]["monthly"] = settled[-6:]
            stats[rc]["monthly_lag"] = [(ym, c) for ym, c in series if _in_lag(ym)][-3:]
            series = settled[-6:]
            complete = [(ym, c) for ym, c in series if ym != this_ym]
            if len(complete) >= 2:
                (ym_p, prev), (ym_l, last) = complete[-2], complete[-1]
                # 달력상 인접한 완결월 사이만 변화율 산출 — 수집 공백을 건너뛴 비교는
                # 그 자체가 추세 위조다. 절대 건수는 렌더러가 병기(분모 자기 노출).
                yp, mp = int(ym_p[:4]), int(ym_p[5:7])
                adjacent = (yp * 12 + mp + 1) == (int(ym_l[:4]) * 12 + int(ym_l[5:7]))
                # 분모 소표본(<_TREND_MIN_BASE)이면 변화율·방향 미산출 — 1건→62건의
                # '+6100% ▲'는 수집 아티팩트를 추세로 위조한다(hormuz·taiwan 실측).
                if adjacent and prev >= _TREND_MIN_BASE:
                    stats[rc]["trend_from"] = prev
                    stats[rc]["trend_to"] = last
                    stats[rc]["trend_pct"] = round((last - prev) / prev * 100, 1)
                    stats[rc]["trend_dir"] = ("▲" if last > prev
                                              else "▼" if last < prev else "↔")
        return stats
    except Exception as e:
        logger.warning("[intel] event_stats 실패: %s", e)
        return {}


# ── 4. cascade_links + cascade_rules 이론 텍스트 ─────────────────────────────

def _get_cascade_context(regions: list[str]) -> dict:
    """cascade_links 발화 실적 + 관련 룰의 이론 텍스트."""
    result: dict = {"links": [], "rules": []}
    if not regions:
        return result

    # cascade_links 조회
    ko_keywords: list[str] = []
    for r in regions:
        ko_keywords.extend(_REGION_KO.get(r, [r]))
    try:
        with _db(_INTEL_DB) as con:
            conditions = " OR ".join(f"rule_name LIKE ?" for _ in ko_keywords)
            params     = [f"%{kw}%" for kw in ko_keywords] + [8]
            rows = con.execute(
                f"""
                SELECT rule_name,
                       ROUND(AVG(correlation_score), 2) AS correlation_score,
                       MIN(depth) AS depth,
                       COUNT(*)   AS fires
                FROM cascade_links
                WHERE {conditions}
                GROUP BY rule_name
                ORDER BY fires DESC LIMIT ?
                """,
                params,
            ).fetchall()
            # [변수 타당도 감사 2026-07-13] 분모·신선도 자기 노출.
            # cascade_links는 적중만 적재된다 — _evaluate_trigger가 시장이 예측대로
            # 안 움직이면 None을 반환해 INSERT 자체가 없다. 그래서 전 건이 '적중'이고
            # 79%가 정확히 1.0이다. 게다가 이 쿼리는 ORDER BY score DESC라 그중에서도
            # 최상위만 보여준다(이중 생존편향). 또 링크는 요청 시점 pull로만 생성돼
            # 오래 정체할 수 있다(실측 26일 유휴). 셋 다 컨텍스트가 자백하게 한다.
            #
            # ⚠️ [B31 수리 2026-07-14] 위 `COUNT(*) AS fires`는 **2026-07-14 이전에
            # 재삽입 횟수를 세고 있었다.** 합성 시장 이벤트 id가 `uuid4()` 랜덤이라
            # UNIQUE(source,target,rule)가 무력화됐고, 같은 트리거를 다시 평가할 때마다
            # 새 행이 INSERT됐다. 실측: 3,012행 중 진짜 링크는 315개(89.5% 중복).
            #   malacca_to_lng 730회 → 실제 10회(×73) · hormuz 63회 → 1회(×63)
            # **"이 룰이 730번 발화했다"가 LLM 컨텍스트에 들어가고 있었다.**
            # 근인 수리: cascade/engine.py::_synthetic_event_id (uuid5 결정론).
            # 불변식: tests/test_cascade_idempotency.py가 (source,rule)당 1행을 강제한다.
            # → 이제 `fires`는 **정직한 발화 횟수**다.
            total, mx = con.execute(
                "SELECT COUNT(*), MAX(created_at) FROM cascade_links").fetchone()
        result["links"] = [dict(r) for r in rows]
        result["ledger_total"] = total or 0
        result["ledger_latest"] = str(mx or "")[:10]
    except Exception as e:
        logger.warning("[intel] cascade_links 실패: %s", e)

    # cascade_rules.yaml에서 관련 룰 이론 텍스트 추출
    try:
        with open(_CONFIG / "cascade_rules.yaml", encoding="utf-8") as f:
            rules = yaml.safe_load(f) or []

        region_set = set(regions)
        for rule in rules:
            trigger = rule.get("trigger", {})
            rule_region = trigger.get("region", "")
            if rule_region in region_set or not region_set:
                theory = rule.get("theory", {})
                if theory:
                    result["rules"].append({
                        "name":       rule.get("name", rule.get("id", "")),
                        "framework":  theory.get("framework", ""),
                        "reference":  theory.get("reference", ""),
                        "learning":   theory.get("learning_note", ""),
                    })
    except Exception as e:
        logger.warning("[intel] cascade_rules 로드 실패: %s", e)

    return result


# ── 5. SIPRI 국방비 ──────────────────────────────────────────────────────────

def _get_sipri_data(actors: list[str], regions: list[str]) -> dict[str, list[dict]]:
    """SIPRI 국방비 — 행위자 국가의 최근 5년 추이."""
    # 지역 → 관련 국가 추가 매핑
    _REGION_ACTORS: dict[str, list[str]] = {
        "ukraine":          ["UKR", "RUS"],
        "taiwan_strait":    ["CHN", "USA", "TWN"],
        "hormuz":           ["IRN", "SAU", "USA", "ISR"],
        "bab_el_mandeb":    ["SAU", "USA"],
        "south_china_sea":  ["CHN", "USA", "VNM", "PHL"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "middle_east":      ["ISR", "IRN", "SAU", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS.get(r, []))

    # NATO 핵심 회원국 감지 — 방위비 분담 분석 시 비교 기준 확보
    # USA+DEU+FRA+GBR 중 2개 이상이면 NATO 분담 맥락 → DB에 실제 있는 회원국 보완
    _NATO_CORE = {"USA", "DEU", "FRA", "GBR"}
    if len(iso3_set & _NATO_CORE) >= 2:
        iso3_set.update(["TUR"])  # DB 확인된 추가 NATO 회원국

    if not iso3_set:
        return {}

    placeholders = ",".join("?" * len(iso3_set))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT iso3, country_name, year, gdp_pct, usd_mn_2022
                FROM sipri_milex
                WHERE iso3 IN ({placeholders})
                  AND year >= (SELECT MAX(year)-4 FROM sipri_milex)
                  AND gdp_pct IS NOT NULL
                ORDER BY iso3, year DESC
                """,
                tuple(iso3_set),
            ).fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            iso3 = r["iso3"]
            if iso3 not in result:
                result[iso3] = []
            result[iso3].append({
                "year":       r["year"],
                "gdp_pct":    r["gdp_pct"],
                "usd_mn":     r["usd_mn_2022"],
                "country":    r["country_name"],
            })
        return result
    except Exception as e:
        logger.warning("[intel] sipri_data 실패: %s", e)
        return {}


def _get_cow_alliances(actors: list[str], regions: list[str] | None = None) -> list[dict]:
    """COW 동맹 — 행위자 국가의 현재 활성 동맹 관계."""
    # SIPRI와 동일한 region → ISO3 확장 매핑 활용
    _REGION_ACTORS: dict[str, list[str]] = {
        "ukraine":          ["UKR", "RUS", "USA", "GBR", "DEU", "FRA", "POL"],
        "taiwan_strait":    ["CHN", "USA", "JPN", "KOR"],
        "hormuz":           ["IRN", "SAU", "USA", "GBR"],
        "bab_el_mandeb":    ["SAU", "USA"],
        "south_china_sea":  ["CHN", "USA", "PHL"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "middle_east":      ["ISR", "IRN", "SAU", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
    }
    iso3_set = set(actors)
    for r in (regions or []):
        iso3_set.update(_REGION_ACTORS.get(r, []))

    if not iso3_set:
        return []
    placeholders = ",".join("?" * len(iso3_set))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT iso3_a, iso3_b, name_a, name_b,
                       start_year, end_year, alliance_type
                FROM cow_alliances
                WHERE (iso3_a IN ({placeholders}) OR iso3_b IN ({placeholders}))
                  AND (end_year IS NULL OR end_year >= 2020)
                ORDER BY alliance_type, start_year
                """,
                (*iso3_set, *iso3_set),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] cow_alliances 실패: %s", e)
        return []


def _get_kiel_data(regions: list[str]) -> list[dict]:
    """Kiel Ukraine Support Tracker — 우크라이나 지역 쿼리 시만 반환."""
    ukraine_regions = {"ukraine", "eastern_europe", "bab_el_mandeb"}
    if not any(r in ukraine_regions for r in regions):
        return []
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                """
                SELECT donor_name, donor_iso3,
                       military_eur_bn, financial_eur_bn,
                       humanitarian_eur_bn, total_eur_bn, data_period
                FROM kiel_ukraine_support
                ORDER BY total_eur_bn DESC
                LIMIT 12
                """,
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] kiel_data 실패: %s", e)
        return []


def _get_press_releases(regions: list[str]) -> dict:
    """미배선 텍스트 소스 3종(govinfo·nk_press·un_news) — region_hint 게이트 조달.

    큐 10① census 수리(2026-07-11): 적재 실존(155·376·72행)·인용 0이던 공백.
    mofa_press는 의도적 미배선 유지(source_roster 명시 — 수동 CLI).
    pub_date 동봉 필수 — govinfo는 1966년 사료까지 있어 연도 태그가 시대착오 방지선.
    """
    if not regions:
        return {}
    placeholders = ",".join("?" * len(regions))
    tables = {"govinfo": "govinfo_releases",
              "nknews": "nk_press_releases",
              "un_news": "un_news_releases"}
    out: dict[str, list[dict]] = {}
    try:
        with _db(_INTEL_DB) as con:
            for key, table in tables.items():
                rows = con.execute(
                    f"""
                    SELECT title, pub_date, description
                    FROM {table}
                    WHERE region_hint IN ({placeholders})
                    ORDER BY pub_date DESC LIMIT 4
                    """,
                    tuple(regions),
                ).fetchall()
                if rows:
                    out[key] = [dict(r) for r in rows]
        return out
    except Exception as e:
        logger.warning("[intel] press_releases 실패: %s", e)
        return {}


# ── 6. EIA 에너지 통계 ───────────────────────────────────────────────────────

def _get_eia_data(actors: list[str], regions: list[str]) -> dict:
    """EIA 에너지 통계 — 행위자 국가 생산량 + 관련 초크포인트 통과량."""
    _REGION_CHOKEPOINTS: dict[str, list[str]] = {
        "hormuz":        ["HORMUZ", "IRN", "SAU", "IRQ", "ARE", "KWT", "QAT"],
        "malacca":       ["MALACCA", "SAU", "IRQ"],
        "bab_el_mandeb": ["BABELM", "SAU"],
        "suez":          ["SUEZ"],
        "taiwan_strait": ["MALACCA"],
        "south_china_sea": ["MALACCA"],
        "ukraine":       ["RUS", "NOR"],
        "korean_peninsula": ["RUS", "CHN"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_CHOKEPOINTS.get(r, []))

    if not iso3_set:
        return {}

    placeholders = ",".join("?" * len(iso3_set))
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT iso3, country_name, crude_prod_mbpd,
                       natgas_prod_bcfd, oil_export_mbpd, data_year
                FROM eia_energy
                WHERE iso3 IN ({placeholders})
                ORDER BY crude_prod_mbpd DESC NULLS LAST
                """,
                tuple(iso3_set),
            ).fetchall()
        return {r["iso3"]: dict(r) for r in rows}
    except Exception as e:
        logger.warning("[intel] eia_data 실패: %s", e)
        return {}


def _get_csis_incidents(actors: list[str], regions: list[str],
                        sectors: list[str]) -> list[dict]:
    """CSIS 사이버 사건 — 행위자·지역·섹터 기반 필터링."""
    _REGION_COUNTRIES: dict[str, list[str]] = {
        "ukraine":          ["UKR", "RUS"],
        "taiwan_strait":    ["CHN", "USA", "TWN"],
        "hormuz":           ["IRN", "SAU", "USA"],
        "korean_peninsula": ["PRK", "KOR", "USA"],
        "middle_east":      ["IRN", "ISR", "USA"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
    }
    # cyber 또는 techno 섹터 포함 시 더 넓은 범위 조회
    is_cyber = "cyber" in sectors or "techno" in sectors

    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_COUNTRIES.get(r, []))

    try:
        with _db(_INTEL_DB) as con:
            if iso3_set:
                placeholders = ",".join("?" * len(iso3_set))
                rows = con.execute(
                    f"""
                    SELECT incident_id, incident_date, actor_iso3, actor_group,
                           victim_iso3, victim_sector, incident_type, title, description
                    FROM csis_cyber_incidents
                    WHERE actor_iso3 IN ({placeholders})
                       OR victim_iso3 IN ({placeholders})
                    ORDER BY incident_date DESC
                    LIMIT 15
                    """,
                    (*iso3_set, *iso3_set),
                ).fetchall()
            elif is_cyber:
                # cyber 섹터 쿼리지만 특정 행위자 없으면 최신 15건
                rows = con.execute(
                    """
                    SELECT incident_id, incident_date, actor_iso3, actor_group,
                           victim_iso3, victim_sector, incident_type, title, description
                    FROM csis_cyber_incidents
                    ORDER BY incident_date DESC LIMIT 15
                    """,
                ).fetchall()
            else:
                rows = []
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[intel] csis_incidents 실패: %s", e)
        return []


# ── Cycle 6-A 신규 소스 ────────────────────────────────────────────────────

def _get_sipri_arms(actors: list[str], regions: list[str]) -> list[dict]:
    """SIPRI Arms Transfers — 행위자 관련 무기 공급망 조회.
    techno/cyber 섹터 전용 쿼리에는 미주입 (무관한 주장 유발 방지).
    """
    if not actors:
        return []
    try:
        placeholders = ",".join("?" * len(actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT supplier_iso3, supplier_name, recipient_iso3, recipient_name,
                           year, tiv_mn, weapon_category, notes
                    FROM sipri_arms_transfers
                    WHERE supplier_iso3 IN ({placeholders})
                       OR recipient_iso3 IN ({placeholders})
                    ORDER BY year DESC
                    LIMIT 10""",
                actors * 2,
            ).fetchall()
        return [
            {
                "supplier": r[1] or r[0], "recipient": r[3] or r[2],
                "year": r[4], "tiv_mn": r[5],
                "category": r[6], "notes": r[7],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] sipri_arms 실패: %s", e)
        return []


def _get_vdem(actors: list[str]) -> list[dict]:
    """V-DEM 민주주의 지수 — 행위자 체제 유형 정량화."""
    if not actors:
        return []
    try:
        placeholders = ",".join("?" * len(actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, v2x_libdem, v2x_regime,
                           v2x_polyarchy, v2x_corr, notes
                    FROM vdem_index
                    WHERE iso3 IN ({placeholders})
                    ORDER BY year DESC""",
                actors,
            ).fetchall()
        regime_labels = {0: "폐쇄권위주의", 1: "선거권위주의", 2: "선거민주주의", 3: "자유민주주의"}
        return [
            {
                "iso3": r[0], "country": r[1] or r[0], "year": r[2],
                "libdem": r[3], "regime_type": regime_labels.get(r[4], "미분류"),
                "polyarchy": r[5], "corruption": r[6], "notes": r[7],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] vdem 실패: %s", e)
        return []


def _get_cow_wars(regions: list[str], actors: list[str]) -> list[dict]:
    """COW Wars — 지역·행위자 관련 전쟁 선례 조회."""
    try:
        conditions: list[str] = []
        params: list = []
        if regions:
            ph = ",".join("?" * len(regions))
            conditions.append(f"relevance_tag IN ({ph})")
            params.extend(regions)
        if actors:
            actor_conds = [
                "(side_a_iso3 LIKE ? OR side_b_iso3 LIKE ?)"
                for _ in actors
            ]
            conditions.append("(" + " OR ".join(actor_conds) + ")")
            for a in actors:
                params.extend([f"%{a}%", f"%{a}%"])
        if not conditions:
            return []
        where = " OR ".join(conditions)
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT war_name, start_year, end_year,
                           side_a_iso3, side_b_iso3, region,
                           battle_deaths, outcome, relevance_tag
                    FROM cow_wars WHERE {where}
                    ORDER BY start_year DESC LIMIT 8""",
                params,
            ).fetchall()
        outcome_labels = {1: "A측 승", 2: "B측 승", 3: "협상 타결", 4: "정전", 5: "진행 중"}
        return [
            {
                "name": r[0],
                "period": f"{r[1]}~{r[2] or '진행중'}",
                "sides": f"{r[3]} vs {r[4]}",
                "region": r[5],
                "battle_deaths": r[6],
                "outcome": outcome_labels.get(r[7], "?"),
                "tag": r[8],
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[intel] cow_wars 실패: %s", e)
        return []


def _get_ifans_publications(actors: list[str], regions: list[str]) -> list[dict]:
    """외교부 LOD IFANS 발간자료 — 한반도·동아시아 한국 시각 컨텍스트."""
    try:
        from connectors.mofa_lod import fetch_ifans_publications
        return fetch_ifans_publications(actors, regions)
    except Exception as e:
        logger.warning("[intel] ifans_publications 실패: %s", e)
        return []


# ── 16. FRED 경제 시계열 (Cycle 7-D-1) ───────────────────────────────────────

_REGION_FRED_SERIES: dict[str, list[str]] = {
    "hormuz":           ["DCOILWTICO", "DCOILBRENTEU", "MHHNGSP"],
    "eastern_europe":   ["PNGASEUUSDM", "DCOILWTICO", "GOLDAMGBD228NLBM"],
    "korean_peninsula": ["KOREUS", "DCOILWTICO"],
    "taiwan_strait":    ["EXCHUS", "EXJPUS", "DCOILWTICO"],
    "indo_pacific":     ["EXJPUS", "EXCHUS", "USMC"],
    "energy":           ["DCOILWTICO", "DCOILBRENTEU", "PNGASEUUSDM", "MHHNGSP"],
    "gray_zone":        ["GOLDAMGBD228NLBM", "DCOILWTICO"],
}

from services.theory_comparator import _FRED_MAX_STALE_DAYS   # 임계는 하나다 — 두 곳이 갈라지면 그게 병이다


def _get_fred_data(regions: list[str], sectors: list[str]) -> list[dict]:
    """FRED 경제 지표 시계열 — 지역·섹터 기반 스마트 라우팅."""
    series_ids: set[str] = set()
    for r in regions:
        series_ids.update(_REGION_FRED_SERIES.get(r, []))
    if "energy" in sectors:
        series_ids.update(_REGION_FRED_SERIES["energy"])
    if "gray_zone" in sectors:
        series_ids.update(_REGION_FRED_SERIES["gray_zone"])
    if not series_ids:
        # 지역·섹터 미매칭 시 무관한 유가·금 데이터를 주입하지 않는다.
        # (사이버·기술 쿼리에 유가가 섞이면 Gemini가 근거 없는 상관 주장을 만들 수 있음)
        return []

    try:
        placeholders = ",".join("?" * len(series_ids))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT series_id, series_name, date, value, unit
                    FROM fred_indicators
                    WHERE series_id IN ({placeholders})
                    ORDER BY series_id, date DESC""",
                list(series_ids),
            ).fetchall()
        # ── 신선도 게이트 (B30 재수리, 2026-07-14) ──────────────────────────────
        #
        # ⚠️ **B30의 첫 수리는 죽은 경로를 막았다.** 18-①위원회가 오염원으로 지목한 것은
        #    `theory_comparator._get_fred_for_theories`였는데, 그 함수는 **수리 전에도
        #    빈 dict를 반환했다**(cc2a0af에서 실측 0개). 게이트를 달아도 막을 게 없었다.
        #
        #    **살아 있는 주입 경로는 여기다.** `build_intel_context`(intel_analyzer:2196)가
        #    이 함수를 불러 LLM 프롬프트에 넣는다. 그리고 이 함수는 게이트가 없었다 —
        #    2026-07-14 실측: `Brent Crude Oil Price · 2024-01-01 · 80.22` **12행 반환**.
        #    위원회가 인용한 바로 그 줄이다. **"고쳤다"는 말이 두 달 가까이 틀려 있었다.**
        #
        #    fred_indicators는 시리즈당 연간값이고 2024-01-01에 멈춰 있다(925일).
        #    그 값을 "실측 · 최근 추세"로 LLM에 먹이면 LLM이 그것을 **독립변수로 되받아 쓴다**
        #    (→ IV "WTI 유가" → target CL=F. 동어반복 8건의 발원지).
        #
        #    ⚠️ 재는 것은 **"오늘 주입이 0건이다"가 아니라 불변식**이다 —
        #    FRED가 최신화되면 주입이 되살아나야 **맞다.**
        today = date.today()
        result: dict[str, list] = {}
        for r in rows:
            sid = r[0]
            stale_days = (today - date.fromisoformat(r[2])).days
            if stale_days > _FRED_MAX_STALE_DAYS:
                if sid not in result:
                    logger.warning(
                        "[ctx] FRED %s(%s) %d일 낡음 — 프롬프트 주입 차단(임계 %d일).",
                        sid, r[2], stale_days, _FRED_MAX_STALE_DAYS,
                    )
                    result[sid] = []          # 로그 1회만
                continue
            if sid not in result:
                result[sid] = []
            if len(result[sid]) < 3:
                result[sid].append({
                    "series_id": sid, "series_name": r[1],
                    "date": r[2], "value": r[3], "unit": r[4],
                })
        return [item for items in result.values() for item in items]
    except Exception as e:
        logger.warning("[intel] fred_data 실패: %s", e)
        return []


# ── 17. World Bank WGI 거버넌스 지수 (Cycle 7-D-2) ──────────────────────────

def _get_world_bank_wgi(actors: list[str], regions: list[str]) -> list[dict]:
    """World Bank WGI — 행위자 국가 거버넌스 지수 (gray_zone·사헬·북극 공백 해소)."""
    _REGION_ACTORS_WB: dict[str, list[str]] = {
        "sahel":            ["MLI", "NER", "BFA", "ETH", "NGA"],
        "bab_el_mandeb":    ["ETH", "SOM", "YEM", "SAU"],
        "hormuz":           ["IRN", "SAU", "QAT", "ARE"],
        "eastern_europe":   ["UKR", "RUS", "BLR"],
        "korean_peninsula": ["PRK", "KOR"],
        "taiwan_strait":    ["CHN", "TWN", "USA"],
        "arctic":           ["RUS", "NOR", "USA", "CAN"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS_WB.get(r, []))
    if not iso3_set:
        return []

    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, pv_score, cc_score,
                           rl_score, ge_score, rq_score, va_score
                    FROM world_bank_wgi
                    WHERE iso3 IN ({placeholders})
                    ORDER BY iso3, year DESC""",
                list(iso3_set),
            ).fetchall()
        seen = set()
        result = []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                result.append({
                    "iso3": r[0], "country": r[1] or r[0], "year": r[2],
                    "political_stability": r[3], "corruption_control": r[4],
                    "rule_of_law": r[5], "gov_effectiveness": r[6],
                    "regulatory_quality": r[7], "voice_accountability": r[8],
                })
        return result
    except Exception as e:
        logger.warning("[intel] world_bank_wgi 실패: %s", e)
        return []


# ── 18. Polity5 정치체제 지수 (Cycle 7-D-4) ─────────────────────────────────

def _get_polity5(actors: list[str]) -> list[dict]:
    """Polity5 — 행위자 국가 체제 분류 강화 (V-DEM 보완)."""
    if not actors:
        return []
    _ck = _scache_key("polity5", actors)
    _cv = _scache_get(_ck)
    if _cv is not None:
        return _cv
    try:
        placeholders = ",".join("?" * len(actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, polity_score, polity2_score, regime_type
                    FROM polity5
                    WHERE iso3 IN ({placeholders})
                    ORDER BY iso3, year DESC""",
                actors,
            ).fetchall()
        seen = set()
        result = []
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                result.append({
                    "iso3": r[0], "country": r[1] or r[0], "year": r[2],
                    "polity_score": r[3], "polity2": r[4], "regime_type": r[5],
                })
        _scache_set(_ck, result)
        return result
    except Exception as e:
        logger.warning("[intel] polity5 실패: %s", e)
        return []


# ── 19. ITU ICT 개발 지수 (Cycle 7-D-5) ─────────────────────────────────────

def _get_itu_ict(actors: list[str], sectors: list[str]) -> list[dict]:
    """ITU ICT 개발 지수 — cyber/techno 섹터 국가별 역량 수치화."""
    if not actors and "cyber" not in sectors and "techno" not in sectors:
        return []
    target_actors = list(actors)
    if "cyber" in sectors or "techno" in sectors:
        for iso3 in ["USA", "CHN", "RUS", "PRK", "IRN"]:
            if iso3 not in target_actors:
                target_actors.append(iso3)
    if not target_actors:
        return []
    _ck = _scache_key("itu", target_actors)
    _cv = _scache_get(_ck)
    if _cv is not None:
        return _cv
    try:
        placeholders = ",".join("?" * len(target_actors))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT iso3, country_name, year, idi_score, global_rank, cyber_tier
                    FROM itu_ict
                    WHERE iso3 IN ({placeholders})
                    ORDER BY idi_score DESC""",
                target_actors,
            ).fetchall()
        result = [
            {"iso3": r[0], "country": r[1] or r[0], "year": r[2],
             "idi_score": r[3], "rank": r[4], "tier": r[5]}
            for r in rows
        ]
        _scache_set(_ck, result)
        return result
    except Exception as e:
        logger.warning("[intel] itu_ict 실패: %s", e)
        return []


# ── 20. HIIK 분쟁 강도 바로미터 (Cycle 7-D-6) ──────────────────────────────

def _get_hiik_conflict(regions: list[str]) -> list[dict]:
    """HIIK — 지역별 최신 분쟁 강도 (ACLED 보완, 분쟁 수치화)."""
    if not regions:
        return []
    _ck = _scache_key("hiik", regions)
    _cv = _scache_get(_ck)
    if _cv is not None:
        return _cv
    try:
        placeholders = ",".join("?" * len(regions))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT conflict_id, conflict_name, primary_country_iso3,
                           region, year, intensity, intensity_label, involved_actors
                    FROM hiik_conflict
                    WHERE region IN ({placeholders})
                    ORDER BY intensity DESC, year DESC
                    LIMIT 8""",
                regions,
            ).fetchall()
        result = [
            {"id": r[0], "name": r[1], "country": r[2], "region": r[3],
             "year": r[4], "intensity": r[5], "label": r[6], "actors": r[7]}
            for r in rows
        ]
        _scache_set(_ck, result)
        return result
    except Exception as e:
        logger.warning("[intel] hiik_conflict 실패: %s", e)
        return []


# ── 21. 반도체·기술 시장 데이터 (Cycle 7-D-7) ────────────────────────────────

def _get_semi_market(sectors: list[str], regions: list[str]) -> list[dict]:
    """SIA 반도체 시장 데이터 — techno/cyber 섹터 HHI·점유율 수치화."""
    if "techno" not in sectors and "cyber" not in sectors and "taiwan_strait" not in regions:
        return []
    _ck = _scache_key("semi", sectors, regions)
    _cv = _scache_get(_ck)
    if _cv is not None:
        return _cv
    try:
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                """SELECT category, metric, value, unit, year, source, region_hint, notes
                   FROM semi_market_data
                   ORDER BY category, year DESC
                   LIMIT 60""",
            ).fetchall()
        result = [
            {"category": r[0], "metric": r[1], "value": r[2], "unit": r[3],
             "year": r[4], "source": r[5], "region_hint": r[6], "notes": r[7]}
            for r in rows
        ]
        _scache_set(_ck, result)
        return result
    except Exception as e:
        logger.warning("[intel] semi_market 실패: %s", e)
        return []


# ── 22. Our World in Data 군사비·핵탄두 (Cycle 7-D-3) ──────────────────────

def _get_owid_data(actors: list[str], regions: list[str], sectors: list[str]) -> list[dict]:
    """OWID 군사비 %GDP·핵탄두 — indo_pacific 군사력 비교 수치화."""
    # 군사 비교가 의미있는 쿼리만: indo_pacific·maritime 섹터 또는 행위자 지정
    _REGION_ACTORS_MIL: dict[str, list[str]] = {
        "taiwan_strait":    ["CHN", "USA", "TWN", "JPN"],
        "korean_peninsula": ["PRK", "KOR", "USA", "CHN"],
        "south_china_sea":  ["CHN", "USA", "VNM", "PHL"],
        "east_china_sea":   ["CHN", "JPN", "USA"],
        "eastern_europe":   ["RUS", "UKR", "USA"],
    }
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_ACTORS_MIL.get(r, []))
    # 군사 관련 섹터가 아니고 행위자도 없으면 스킵
    if not iso3_set and not ({"indo_pacific", "maritime"} & set(sectors)):
        return []
    if not iso3_set:
        iso3_set = {"USA", "CHN", "RUS"}  # 군사 섹터 기본 비교군

    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""SELECT dataset, iso3, country, year, value, unit
                    FROM owid_data
                    WHERE iso3 IN ({placeholders})
                    ORDER BY dataset, iso3, year DESC""",
                list(iso3_set),
            ).fetchall()
        # dataset+iso3별 최신값만
        seen = set()
        result = []
        for r in rows:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                result.append({
                    "dataset": r[0], "iso3": r[1], "country": r[2],
                    "year": r[3], "value": r[4], "unit": r[5],
                })
        return result
    except Exception as e:
        logger.warning("[intel] owid_data 실패: %s", e)
        return []


# ── 23. UN Comtrade 무역 의존도 (AR-1b) ──────────────────────────────────────
# Weaponized Interdependence(Farrell & Newman) 독립변수 직접 수치화.
# HS 8542(반도체)·27(에너지)·26(희토류) 양자 dependency_ratio → 비대칭 의존 구조 포착.

_HS_LABEL = {"8542": "반도체", "27": "에너지(원유·가스)", "26": "희토류·광물"}

# 지역 → 핵심 행위자 매핑 (Comtrade 전용 — 무역쌍 구성용)
_REGION_TRADE_ACTORS: dict[str, list[str]] = {
    "taiwan_strait":    ["TWN", "CHN", "USA", "JPN", "KOR"],
    "korean_peninsula": ["KOR", "PRK", "CHN", "USA", "JPN"],
    "hormuz":           ["IRN", "SAU", "ARE", "CHN", "USA"],
    "eastern_europe":   ["RUS", "DEU", "NLD", "UKR", "CHN"],
    "south_china_sea":  ["CHN", "USA", "VNM", "PHL", "JPN"],
    "east_china_sea":   ["CHN", "JPN", "USA", "KOR"],
    "bab_el_mandeb":    ["SAU", "ARE", "CHN", "IND", "ETH"],
    "indo_pacific":     ["CHN", "USA", "JPN", "KOR", "IND", "AUS"],
}


def _get_trade_dependency(actors: list[str], regions: list[str]) -> list[dict]:
    """
    UN Comtrade 무역 의존도 조회 — Weaponized Interdependence IV 수치화.
    dependency_ratio 0.1(10%) 이상 쌍만 반환 (의미있는 비대칭 의존 구조).
    """
    # 조회 대상 ISO3 수집
    iso3_set = set(actors)
    for r in regions:
        iso3_set.update(_REGION_TRADE_ACTORS.get(r, []))
    if not iso3_set:
        return []

    try:
        placeholders = ",".join("?" * len(iso3_set))
        with _db(_INTEL_DB) as con:
            rows = con.execute(
                f"""
                SELECT period, reporter_iso, partner_iso, hs_code, trade_flow,
                       trade_value_usd, dependency_ratio
                FROM historical_trade_matrix
                WHERE reporter_iso IN ({placeholders})
                  AND partner_iso  IN ({placeholders})
                  AND partner_iso  != 'WLD'
                  AND dependency_ratio >= 0.1
                ORDER BY dependency_ratio DESC, period DESC
                """,
                (*list(iso3_set), *list(iso3_set)),
            ).fetchall()

        # reporter·partner·hs_code 조합별 최신연도만 유지 (중복 제거)
        seen: set[tuple] = set()
        result: list[dict] = []
        for r in rows:
            key = (r[0], r[1], r[2], r[3], r[4])
            if key not in seen:
                seen.add(key)
                result.append({
                    "period": r[0],
                    "reporter": r[1],
                    "partner": r[2],
                    "hs_code": r[3],
                    "hs_label": _HS_LABEL.get(r[3], r[3]),
                    "flow": "수입" if r[4] == "M" else "수출",
                    "value_usd": r[5],
                    "dependency_ratio": r[6],
                })
        return result[:20]   # 상위 20쌍으로 제한
    except Exception as e:
        logger.warning("[intel] trade_dependency 실패: %s", e)
        return []


# ── 7. 국가 프로파일 ──────────────────────────────────────────────────────────

def _get_country_profiles(actors: list[str]) -> dict:
    if not actors:
        return {}
    try:
        with open(_CONFIG / "country_geopolitics.yaml", encoding="utf-8") as f:
            cg = yaml.safe_load(f)
        profiles = cg.get("profiles", {})
        return {iso3: profiles[iso3] for iso3 in actors if iso3 in profiles}
    except Exception as e:
        logger.warning("[intel] country_profiles 실패: %s", e)
        return {}


# ── 컨텍스트 조립 ─────────────────────────────────────────────────────────────

# ── 융합1: 관련성 게이트 (Phase 8) ────────────────────────────────────────────
# 섹터 친화도: key=소스 식별자, sectors=주 관련 섹터(비어있으면 범용)
_SOURCE_SPECS: dict[str, dict] = {
    # bp: _get_bp_provocations가 이중언어 토픽·지역으로 조달을 게이트 — kiel·press와
    # 동일 원리로 범용 (접지 감사 2026-07-13)
    "bp":            {"sectors": set()},
    "sipri_milex":   {"sectors": {"indo_pacific", "alliance"}},
    "cow_alliances": {"sectors": {"indo_pacific", "alliance"}},
    # kiel: _get_kiel_data가 우크라이나 지역 쿼리에만 조달하므로 지역 게이트가 이미
    # 관련성을 보장 — 섹터 이중 게이트는 off-domain 페널티→예산 기아만 낳았다
    # (큐 10① census 실측: 배선 실존·인용 0, 2026-07-11 수리)
    "kiel":          {"sectors": set()},
    # press: _get_press_releases가 region_hint로 조달을 게이트 — kiel과 동일 원리로 범용
    "press":         {"sectors": set()},
    "eia":           {"sectors": {"energy", "maritime"}},
    "csis":          {"sectors": {"cyber"}},
    "sipri_arms":    {"sectors": {"indo_pacific", "alliance", "techno"}},
    "vdem":          {"sectors": {"gray_zone"}},
    "cow_wars":      {"sectors": set()},   # 범용(역사 선례)
    "ifans":         {"sectors": set()},   # 범용(한국 시각)
    "fred":          {"sectors": {"energy"}},
    "wbk":           {"sectors": {"gray_zone"}},
    "polity5":       {"sectors": {"gray_zone"}},
    "itu":           {"sectors": {"cyber", "techno"}},
    "hiik":          {"sectors": {"gray_zone"}},
    "semi":          {"sectors": {"techno"}},
    "owid":          {"sectors": set()},   # 범용(다지표)
    "trade":         {"sectors": {"techno", "energy"}},
}


def _coverage_bonus(records, regions: list[str], actors: list[str]) -> float:
    """레코드가 쿼리 지역·행위자 토큰을 실제 포함하면 보너스. 순위용 상대값."""
    if not records:
        return 0.0
    text = str(records).lower()
    bonus = 0.0
    for r in regions:
        if r.lower() in text:
            bonus += 0.5
    for a in actors:
        if a.lower() in text:
            bonus += 0.3
    return min(bonus, 2.0)


def _score_source(spec: dict, records, pq: "ParsedQuery") -> float:
    """data 소스 블록의 관련성 점수.
    주제 적합성(섹터·지역·행위자 밀도)만 사용 — 가설 지지 여부 금지(정직성 가드).
    """
    if not records:
        return -1.0
    score = 1.0
    src_sectors = spec.get("sectors", set())
    if src_sectors and pq.sectors:
        if src_sectors & set(pq.sectors):
            score += 2.0   # 섹터 적중
        else:
            score -= 1.0   # off-domain 페널티
    score += _coverage_bonus(records, pq.regions, pq.actors)
    return score


# ── emitter 함수: 각 data 소스 → list[str] (포맷 1글자도 변경 금지) ──────────

def _emit_sipri_milex(sipri_data) -> list[str]:
    if not sipri_data:
        return []
    out = ["## 국방비 추이 (SIPRI 2023, % of GDP / USD billion)"]
    for iso3, records in sipri_data.items():
        if not records:
            continue
        latest = records[0]
        name   = latest.get("country", iso3)
        gdp    = latest.get("gdp_pct")
        usd    = latest.get("usd_mn")
        year   = latest.get("year")
        trend  = " → ".join(
            f"{r['year']}:{r['gdp_pct']}%"
            for r in reversed(records) if r.get("gdp_pct")
        )
        usd_bn = f"${usd/1000:.1f}bn" if usd else ""
        out.append(f"- **{name}** ({iso3}): {year}년 GDP {gdp}% {usd_bn}")
        if len(records) > 1:
            out.append(f"  5년 추이: {trend}")
    out.append("  출처: SIPRI Military Expenditure Database 2024")
    out.append("")
    return out


def _emit_cow_alliances(cow_alliances) -> list[str]:
    if not cow_alliances:
        return []
    defense = [a for a in cow_alliances if a.get("alliance_type") == "defense"]
    others  = [a for a in cow_alliances if a.get("alliance_type") != "defense"]
    out = ["## 공식 동맹 관계 (COW Formal Alliances v4.1)"]
    if defense:
        out.append("**방위조약 (Defense Pact)**")
        for a in defense[:10]:
            end_str = f"~{a['end_year']}" if a.get("end_year") else "~현재"
            out.append(
                f"- {a.get('name_a') or a['iso3_a']} ↔ "
                f"{a.get('name_b') or a['iso3_b']} "
                f"({a.get('start_year', '?')}{end_str})"
            )
    by_type: dict[str, list] = {}
    for a in others:
        by_type.setdefault(a.get("alliance_type", "other"), []).append(a)
    for t, alist in by_type.items():
        pairs = [
            f"{a.get('name_a') or a['iso3_a']}↔{a.get('name_b') or a['iso3_b']}"
            for a in alist
        ]
        out.append(f"**{t}**: {', '.join(pairs[:5])}")
    out.append("  출처: Correlates of War Formal Alliances v4.1")
    out.append("")
    return out


def _emit_kiel(kiel_data) -> list[str]:
    if not kiel_data:
        return []
    out = [
        "## 우크라이나 지원 현황 (Kiel Ukraine Support Tracker 2024)",
        "단위: EUR 십억 (군사/재정/인도적/합계)",
    ]
    for d in kiel_data[:8]:
        mil  = d.get("military_eur_bn", 0) or 0
        fin  = d.get("financial_eur_bn", 0) or 0
        hum  = d.get("humanitarian_eur_bn", 0) or 0
        tot  = d.get("total_eur_bn", 0) or 0
        out.append(
            f"- **{d['donor_name']}**: 군사 {mil:.1f} / 재정 {fin:.1f} / "
            f"인도적 {hum:.1f} / **합계 {tot:.1f}bn€**"
        )
    period = kiel_data[0].get("data_period", "") if kiel_data else ""
    out.append(f"  기간: {period} | 출처: Kiel Institute Ukraine Support Tracker")
    out.append("")
    return out


def _emit_press(press_data) -> list[str]:
    if not press_data:
        return []
    label = {"govinfo": "GovInfo·미 정부 문서", "nknews": "NK 동향(북한 발표·보도)",
             "un_news": "UN News"}
    out = ["## 정부·국제기구 발표 (1차 사료 — 발행일과 함께 인용, 발행연도 확인 필수)"]
    for key, rows in press_data.items():
        for r in rows:
            out.append(f"- [{label.get(key, key)}] {r.get('pub_date', '?')} — "
                       f"{(r.get('title') or '')[:90]}")
            desc = (r.get("description") or "").strip().replace("\n", " ")
            if desc:
                out.append(f"  {desc[:110]}")
    out.append("")
    return out


def _emit_eia(eia_data) -> list[str]:
    if not eia_data:
        return []
    chokepoints = {k: v for k, v in eia_data.items() if len(k) > 3}
    producers   = {k: v for k, v in eia_data.items() if len(k) == 3}
    out = ["## 에너지 생산·수출 현황 (EIA International Energy Statistics 2023)"]
    if chokepoints:
        out.append("**전략 초크포인트 통과량 (백만 배럴/일)**")
        for key, d in chokepoints.items():
            out.append(f"- {d['country_name']}: {d.get('crude_prod_mbpd', '?')} Mbpd")
    if producers:
        out.append("**주요 산유국 생산량 / 수출량 (Mbpd)**")
        for iso3, d in producers.items():
            prod = d.get("crude_prod_mbpd", "?")
            exp  = d.get("oil_export_mbpd")
            gas  = d.get("natgas_prod_bcfd")
            row  = f"- **{d.get('country_name', iso3)}** ({iso3}): 원유 {prod}"
            if exp:
                row += f" / 수출 {exp}"
            if gas:
                row += f" / 천연가스 {gas} Bcfd"
            out.append(row)
    out.append("  출처: EIA International Energy Statistics 2024")
    out.append("")
    return out


def _emit_csis(csis_incidents) -> list[str]:
    if not csis_incidents:
        return []
    out = ["## 주요 사이버 사건 (CSIS Significant Cyber Incidents DB)"]
    for inc in csis_incidents[:8]:
        actor  = inc.get("actor_group") or inc.get("actor_iso3") or "미귀속"
        victim = inc.get("victim_iso3", "?")
        sector = inc.get("victim_sector", "")
        itype  = inc.get("incident_type", "")
        date   = (inc.get("incident_date") or "")[:7]
        out.append(
            f"- [{date}] **{inc.get('title', '')}**"
            f" | 행위자: {actor} → 피해: {victim}({sector}) | 유형: {itype}"
        )
        desc = (inc.get("description") or "")[:120]
        if desc:
            out.append(f"  {desc}")
    out.append("  출처: CSIS Strategic Technologies Program 2024")
    out.append("")
    return out


def _emit_sipri_arms(sipri_arms) -> list[str]:
    if not sipri_arms:
        return []
    out = ["## 무기 공급망 (SIPRI Arms Transfers Database)"]
    for arm in sipri_arms[:6]:
        out.append(
            f"- {arm.get('year')} | {arm.get('supplier')} → {arm.get('recipient')}"
            f" | {arm.get('category', '')} | TIV {arm.get('tiv_mn', '?')}mn"
        )
        if arm.get("notes"):
            out.append(f"  {arm['notes'][:100]}")
    out.append("  출처: SIPRI Arms Transfers Database 2020-2024")
    out.append("")
    return out


def _emit_vdem(vdem_data) -> list[str]:
    if not vdem_data:
        return []
    out = ["## 행위자 체제 유형 (V-Dem Democracy Index v14)"]
    for v in vdem_data:
        libdem = f"{v['libdem']:.2f}" if v.get("libdem") is not None else "?"
        corr   = f"{v['corruption']:.2f}" if v.get("corruption") is not None else "?"
        out.append(
            f"- **{v.get('country')}** ({v.get('iso3')}, {v.get('year')}): "
            f"{v.get('regime_type')} | 자유민주주의 지수: {libdem} | 부패지수: {corr}"
        )
        if v.get("notes"):
            out.append(f"  {v['notes'][:80]}")
    out.append("  출처: V-Dem Institute, University of Gothenburg 2024")
    out.append("")
    return out


def _emit_cow_wars(cow_wars) -> list[str]:
    if not cow_wars:
        return []
    out = ["## 관련 전쟁 선례 (COW Inter-State/Intra-State Wars)"]
    for w in cow_wars[:5]:
        deaths = f"{w['battle_deaths']:,}" if w.get("battle_deaths") else "미집계"
        out.append(
            f"- **{w.get('name')}** ({w.get('period')}) | "
            f"{w.get('sides')} | 사망: {deaths} | 결과: {w.get('outcome')}"
        )
    out.append("  출처: Correlates of War Project v4.0")
    out.append("")
    return out


def _emit_ifans(ifans_pubs) -> list[str]:
    if not ifans_pubs:
        return []
    out = ["## 한국 외교부 IFANS 발간자료 (국립외교원 학술 분석)"]
    for pub in ifans_pubs[:4]:
        date = str(pub.get("date", ""))
        date_fmt = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
        out.append(f"- [{date_fmt}] **{pub.get('title', '')}**")
        abstract = (pub.get("abstract") or "")[:300]
        if abstract:
            out.append(f"  {abstract}")
        out.append(f"  출처: {pub.get('source', '외교부 IFANS')}")
    out.append("")
    return out


def _emit_fred(fred_data) -> list[str]:
    if not fred_data:
        return []
    out = ["## 주요 경제 지표 시계열 (FRED — Federal Reserve Economic Data)"]
    by_series: dict[str, list] = {}
    for d in fred_data:
        sid = d.get("series_id", "?")
        by_series.setdefault(sid, []).append(d)
    for sid, records in list(by_series.items())[:6]:
        name = records[0].get("series_name", sid)
        unit = records[0].get("unit", "")
        trend = " → ".join(
            f"{r['date'][:4]}:{r['value']}" for r in reversed(records) if r.get("value") is not None
        )
        out.append(f"- **{name}** ({sid}): {trend} [{unit}]")
    out.append("  출처: FRED St. Louis Federal Reserve (fred.stlouisfed.org)")
    out.append("")
    return out


def _emit_wbk(wbk_data) -> list[str]:
    if not wbk_data:
        return []
    out = [
        "## 국가 거버넌스 지수 (World Bank WGI 2022)",
        "점수 범위: -2.5(최하) ~ +2.5(최상)",
    ]
    for d in wbk_data[:8]:
        pv = f"{d['political_stability']:.2f}" if d.get("political_stability") is not None else "?"
        cc = f"{d['corruption_control']:.2f}" if d.get("corruption_control") is not None else "?"
        rl = f"{d['rule_of_law']:.2f}" if d.get("rule_of_law") is not None else "?"
        out.append(
            f"- **{d['country']}** ({d['iso3']}): "
            f"정치안정={pv} | 부패통제={cc} | 법치={rl}"
        )
    out.append("  출처: World Bank Worldwide Governance Indicators 2023")
    out.append("")
    return out


def _emit_polity5(polity5_data) -> list[str]:
    if not polity5_data:
        return []
    out = [
        "## 정치체제 지수 (Polity5 2022)",
        "점수: -10(완전권위) ~ +10(완전민주)",
    ]
    for d in polity5_data[:8]:
        score  = d.get("polity_score")
        regime = d.get("regime_type", "?")
        out.append(f"- **{d['country']}** ({d['iso3']}): {score}점 ({regime})")
    out.append("  출처: Center for Systemic Peace, Polity5 Dataset")
    out.append("")
    return out


def _emit_itu(itu_data) -> list[str]:
    if not itu_data:
        return []
    # IDI = 보급·접근성 지표. 사이버 방어력 직접 동치 금지 선제 경고.
    out = [
        "## ICT 발전 지수 (ITU IDI 2023) "
        "⚠️ 보급·접근성 지표 — 사이버 방어력과 직접 동치 금지",
        "IDI 점수: 0-100 (인터넷 보급·접근성·이용 종합). "
        "사이버 역량 주장 시 반드시 '간접 proxy'임을 명시할 것. "
        "방어력 직접 근거로는 GCI·NCSI가 더 타당함.",
    ]
    for d in itu_data[:8]:
        score = d.get("idi_score")
        rank  = d.get("rank")
        tier  = d.get("tier", "?")
        out.append(
            f"- **{d['country']}** ({d['iso3']}): IDI {score} (전세계 {rank}위, {tier}티어)"
        )
    out.append("  출처: ITU ICT Development Index 2023")
    out.append("")
    return out


def _emit_hiik(hiik_data) -> list[str]:
    if not hiik_data:
        return []
    out = [
        "## 분쟁 강도 바로미터 (HIIK Conflict Barometer 2024)",
        "강도: 1=분쟁 / 2=비폭력위기 / 3=폭력위기 / 4=제한전 / 5=전쟁",
    ]
    for d in hiik_data[:6]:
        out.append(
            f"- **{d['name']}** ({d['year']}): 강도 {d['intensity']} [{d['label']}]"
            f" | 행위자: {d.get('actors', '?')}"
        )
    out.append("  출처: HIIK Heidelberg Institute for International Conflict Research")
    out.append("")
    return out


def _emit_semi(semi_data) -> list[str]:
    if not semi_data:
        return []
    _PRIORITY_CATS = [
        "china_self_sufficiency",
        "foundry_share",
        "advanced_nodes",
        "critical_mineral",
        "equipment_dominance",
        "export_control",
        "memory_market",
        "defense_tech",
        "market_size",
    ]
    by_cat: dict[str, list] = {}
    for d in semi_data:
        by_cat.setdefault(d.get("category", "misc"), []).append(d)
    ordered_cats = [c for c in _PRIORITY_CATS if c in by_cat] + \
                   [c for c in by_cat if c not in _PRIORITY_CATS]
    out = ["## 반도체·기술 시장 데이터 (SIA/TechInsights 2023-2024)"]
    for cat in ordered_cats[:7]:
        items = by_cat[cat]
        out.append(f"**{cat}**")
        for d in items[:5]:
            val_str  = f"{d['value']}" if d.get("value") is not None else "?"
            unit_str = d.get("unit", "")
            out.append(f"  - {d['metric']}: {val_str} {unit_str} ({d.get('year', '?')})")
            if d.get("notes"):
                out.append(f"    {d['notes'][:100]}")
    out.append("  출처: SIA, TechInsights, USGS, ASML Annual Report, BIS")
    out.append("")
    return out


def _emit_owid(owid_data) -> list[str]:
    if not owid_data:
        return []
    milex = [d for d in owid_data if d.get("dataset") == "military_exp_gdp"]
    nukes = [d for d in owid_data if d.get("dataset") == "nuclear_warheads"]
    out = ["## 군사력 비교 (Our World in Data, SIPRI/FAS 원천)"]
    if milex:
        out.append("**국방비 (% of GDP, 최신연도)**")
        for d in sorted(milex, key=lambda x: -(x.get("value") or 0))[:8]:
            v = f"{d['value']:.2f}" if d.get("value") is not None else "?"
            out.append(f"- {d['country']} ({d['iso3']}): {v}% ({d.get('year')})")
    if nukes:
        out.append("**핵탄두 보유량 (최신연도)**")
        for d in sorted(nukes, key=lambda x: -(x.get("value") or 0))[:6]:
            v = int(d['value']) if d.get("value") is not None else "?"
            out.append(f"- {d['country']} ({d['iso3']}): {v}기 ({d.get('year')})")
    out.append("  출처: Our World in Data (ourworldindata.org)")
    out.append("")
    return out


def _emit_trade(trade_dep_data) -> list[str]:
    if not trade_dep_data:
        return []
    out = [
        "## 무역 의존도 (UN Comtrade — Weaponized Interdependence IV)",
        "dependency_ratio: 해당 양자 무역액 ÷ 보고국 전체 무역액 (0~1). "
        "0.1 이상 = 10%+ 의존 → 비대칭 구조. "
        "이 수치가 높을수록 Farrell & Newman의 '공급망 집중 → 레버리지' 예측 지지.",
    ]
    by_hs: dict[str, list] = {}
    for d in trade_dep_data:
        by_hs.setdefault(d["hs_code"], []).append(d)
    for hs_code, items in by_hs.items():
        label = _HS_LABEL.get(hs_code, hs_code)
        out.append(f"**{label} (HS {hs_code})**")
        for d in items[:6]:
            ratio_pct = f"{d['dependency_ratio']*100:.1f}%"
            out.append(
                f"- {d['reporter']} {d['flow']} ← {d['partner']}: "
                f"의존도 {ratio_pct} ({d['period']})"
            )
    out.append("  출처: UN Comtrade Database (2020-2025, HS 8542·27·26)")
    out.append("")
    return out


# ── [접지 감사 2026-07-13] 북한 도발 원장 (bp_provocations) 배선 ─────────────
# 반박석 판정 반영: 별칭의 region 승격(서해→korean_peninsula) 대신 이중언어 토픽
# 매핑 — 원장이 영문 코딩(NLL 20·West Sea 14·Yellow Sea 28건)이라 한국어 쿼리
# ("서해")는 LIKE 0건이었다. 유일한 진짜 서해 데이터원의 언어 격벽을 여기서 푼다.
# 이론 연결: 회색지대 전략(gray zone)의 국지 도발 시계열 — 반복·공백·재점화 구조.
_BP_TOPIC_EN: dict[str, list[str]] = {
    "서해":   ["West Sea", "Yellow Sea", "NLL", "Yeonpyeong", "Baengnyeong"],
    "nll":    ["NLL", "West Sea", "Yellow Sea"],
    "연평":   ["Yeonpyeong"],
    "백령":   ["Baengnyeong"],
    "천안함": ["Cheonan"],
    "판문점": ["Panmunjom", "JSA"],
    "미사일": ["Missile"],
    "핵실험": ["Nuclear"],
    "위성":   ["Satellite"],
    "포격":   ["Artillery"],
    "드론":   ["drone", "UAV"],
    "무인기": ["drone", "UAV"],
    "풍선":   ["Balloon"],
    "잠수함": ["Submarine", "SLBM"],
    "재밍":   ["Jamming"],
}


def _get_bp_provocations(regions: list[str], actors: list[str],
                         raw_query: str) -> dict:
    """도발 원장 조달 — 연도 집계 + 이중언어 토픽 매칭 이벤트 (예산 ~1,200자)."""
    kws = [k.lower() for k in _extract_keywords(raw_query)]
    en_terms: list[str] = []
    ko_hits: list[str] = []
    for k in kws:
        for ko, ens in _BP_TOPIC_EN.items():
            if ko in k or k in ko:
                en_terms.extend(ens)
                ko_hits.append(ko)
    en_terms = list(dict.fromkeys(en_terms))
    ko_hits = list(dict.fromkeys(ko_hits))

    triggered = ("korean_peninsula" in regions or "north_korea" in regions
                 or "PRK" in actors or bool(en_terms))
    if not triggered:
        return {}
    try:
        with _db(_INTEL_DB) as con:
            total, dmin, dmax = con.execute(
                "SELECT COUNT(*), MIN(event_date), MAX(event_date) "
                "FROM bp_provocations").fetchone()
            yearly = con.execute(
                "SELECT substr(event_date,1,4) y, COUNT(*) n FROM bp_provocations "
                "WHERE event_date >= date('now','-12 years') "
                "GROUP BY 1 ORDER BY 1").fetchall()
            matched, match_years = [], {}
            if en_terms:
                like = " OR ".join(
                    "(title LIKE ? OR description LIKE ?)" for _ in en_terms)
                params: list = []
                for t in en_terms:
                    params.extend([f"%{t}%", f"%{t}%"])
                matched = con.execute(
                    f"SELECT event_date, prov_type, title FROM bp_provocations "
                    f"WHERE {like} ORDER BY event_date DESC LIMIT 8",
                    params).fetchall()
                match_years = dict(con.execute(
                    f"SELECT substr(event_date,1,4) y, COUNT(*) n "
                    f"FROM bp_provocations WHERE {like} "
                    f"GROUP BY 1 ORDER BY 1", params).fetchall())
        return {"total": total, "dmin": dmin, "dmax": dmax,
                "yearly": [tuple(r) for r in yearly],
                "matched": [tuple(r) for r in matched],
                "match_years": match_years,
                "en_terms": en_terms, "ko_terms": ko_hits}
    except Exception as e:
        logger.warning("[intel] bp_provocations 조달 실패: %s", e)
        return {}


def _emit_bp(data: dict) -> list[str]:
    """도발 원장 렌더. 매칭 연도 분포는 공백 연도(0건)도 명시 — 침묵도 신호다."""
    if not data or not data.get("total"):
        return []
    out = [f"## 북한 도발 원장 (Beyond Parallel · "
           f"{str(data['dmin'])[:4]}~{str(data['dmax'])[:4]} · 총 {data['total']}건 · "
           f"출처 URL 전건 보유)"]
    if data.get("ko_terms"):
        out.append(f"- 주제 매핑(한↔영): {', '.join(data['ko_terms'])} → "
                   f"{', '.join(data['en_terms'][:6])}")
    my = data.get("match_years") or {}
    if my:
        y0, y1 = int(min(my)), int(max(my))
        seq = " ".join(f"{y}:{my.get(str(y), 0)}" for y in range(y0, y1 + 1))
        out.append(f"- 주제 매칭 연도 분포(총 {sum(my.values())}건, 0=기록 공백): {seq}")
    if data.get("matched"):
        out.append("- 주제 매칭 최근 이벤트:")
        for d_, pt, ti in data["matched"]:
            out.append(f"    {d_} | {pt} | {ti}")
    if data.get("yearly"):
        out.append("- 전체 원장 연도별(최근 12년): "
                   + " ".join(f"{y}:{n}" for y, n in data["yearly"]))
    out.append("")
    return out


# emitter 매핑 테이블 (키 → 함수)
_SOURCE_EMITTERS = {
    "bp":            _emit_bp,
    "sipri_milex":   _emit_sipri_milex,
    "cow_alliances": _emit_cow_alliances,
    "kiel":          _emit_kiel,
    "press":         _emit_press,
    "eia":           _emit_eia,
    "csis":          _emit_csis,
    "sipri_arms":    _emit_sipri_arms,
    "vdem":          _emit_vdem,
    "cow_wars":      _emit_cow_wars,
    "ifans":         _emit_ifans,
    "fred":          _emit_fred,
    "wbk":           _emit_wbk,
    "polity5":       _emit_polity5,
    "itu":           _emit_itu,
    "hiik":          _emit_hiik,
    "semi":          _emit_semi,
    "owid":          _emit_owid,
    "trade":         _emit_trade,
}


def _build_context(
    pq:               ParsedQuery,
    like_items:       list[dict],
    sector_items:     list[dict],
    event_stats:      dict,
    cascade_ctx:      dict,
    country_profiles: dict,
    sipri_data:       dict | None = None,
    cow_alliances:    list[dict] | None = None,
    kiel_data:        list[dict] | None = None,
    eia_data:         dict | None = None,
    csis_incidents:   list[dict] | None = None,
    sipri_arms:       list[dict] | None = None,
    vdem_data:        list[dict] | None = None,
    cow_wars:         list[dict] | None = None,
    ifans_pubs:       list[dict] | None = None,
    # Cycle 7-D 신규 소스
    fred_data:        list[dict] | None = None,
    wbk_data:         list[dict] | None = None,
    polity5_data:     list[dict] | None = None,
    itu_data:         list[dict] | None = None,
    hiik_data:        list[dict] | None = None,
    semi_data:        list[dict] | None = None,
    owid_data:        list[dict] | None = None,
    trade_dep_data:   list[dict] | None = None,
    press_data:       dict | None = None,
    # Phase 8 융합1: 경쟁이론 비교 컨텍스트 (priority tier)
    theory_cmp_ctx:   str = "",
    # [접지 감사 2026-07-13] 도발 원장 (이중언어 조달)
    bp_data:          dict | None = None,
    # [접지 감사 2026-07-13] True면 라이브러리 유래(브리핑 전문·요약·이론 프로파일·
    # 문헌공백 원장·이론비교)를 전부 생략한 순수 데이터 조립 — 접지 측정 전용.
    # 브리핑 히트가 접지로 계수되던 미탐(반박석 공격 2)을 막는 분모 정의다.
    data_only:        bool = False,
) -> str:
    lines: list[str] = []
    total_chars = 0

    # ── 쿼리 요약 ──────────────────────────────────────────────────────────
    lines.append("## 분석 쿼리 요약")
    lines.append(f"- 지역: {', '.join(pq.regions) or '미지정'}")
    lines.append(f"- 행위자: {', '.join(pq.actors) or '미지정'}")
    lines.append(f"- 섹터: {', '.join(pq.sectors) or '전체'}")
    lines.append("")

    # ── 브리핑·이론 원문 (상위 3개 full body) ─────────────────────────────
    # LIKE 검색 결과 우선, 섹터 필터로 보완, 중복 제거
    seen_ids: set[str] = set()
    all_items: list[dict] = []
    for item in like_items + sector_items:
        tid = item.get("theory_id", "")
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            all_items.append(item)

    # [접지 감사 2026-07-13] 정렬을 body 길이에서 자체 관련도 우선으로 교체 —
    # "긴 글이 곧 관련 글"이라는 가정이 드론·테러 브리핑 전문 주입의 공범이었다.
    all_items.sort(key=lambda x: (x.get("_own_relevance", 0),
                                  len(x.get("body") or "")), reverse=True)

    body_count = 0
    meta_items = []

    for item in all_items:
        body = (item.get("body") or "").strip()
        org  = f"[{item.get('source_org', '')}] " if item.get("source_org") else ""
        title = item.get("title", "")

        if data_only:
            continue  # 순수 데이터 조립 — 브리핑층 전체 생략
        # [접지 감사 2026-07-13] 전문 주입 자격 = 자체 관련도 문턱. 지역 별칭
        # ('북한' 등) 한 단어만 겹친 브리핑은 요약으로 강등 — 데이터 우선·브리핑 보조.
        # 섹터 채움분(_own_relevance 부재)은 0으로 취급되어 자동 강등된다.
        if (body and body_count < 3 and total_chars < _CONTEXT_MAX_CHARS
                and item.get("_own_relevance", 0) >= _BRIEF_FULL_MIN
                and item.get("_own_rel_ts", 0) >= 2):
            # 원문 포함 (최대 3개, 각 3000자)
            truncated = body[:_BODY_MAX_CHARS]
            if len(body) > _BODY_MAX_CHARS:
                truncated += "\n...(이하 생략)"
            section = f"### {org}{title}\n{truncated}\n"
            lines.append(section)
            total_chars += len(section)
            body_count += 1
        else:
            # 원문 초과·관련도 미달 시 제목+요약만
            meta_items.append(item)

    if body_count > 0:
        lines.insert(2, f"## 브리핑·이론 원문 ({body_count}개 전문 포함)\n")

    # 나머지는 제목+요약만
    if meta_items and not data_only:
        lines.append("## 추가 관련 브리핑 (요약)")
        for item in meta_items[:5]:
            org   = f"[{item.get('source_org', '')}] " if item.get("source_org") else ""
            lines.append(f"- {org}{item.get('title', '')}")
            summary = (item.get("summary") or "")[:150]
            if summary:
                lines.append(f"  {summary}")
        lines.append("")

    # ── Phase 7 이론 프로파일 (예측변수·반례·경쟁이론) ────────────────────
    # asset_type=theory이면서 프로파일 필드가 있는 항목만 추출
    import json as _json
    theory_profiles = [
        item for item in all_items
        if item.get("asset_type") == "theory" and item.get("independent_var")
    ]
    if theory_profiles and not data_only:
        lines.append("## 이론 프로파일 (예측 도구)")
        for tp in theory_profiles[:4]:
            lines.append(f"### {tp.get('title', tp.get('theory_id', ''))}")
            lines.append(f"- 독립변수: {tp['independent_var']}")
            lines.append(f"- 종속변수: {tp.get('dependent_var', '?')}")
            if tp.get("falsifiable_prediction"):
                lines.append(f"- 반증 가능 예측: {tp['falsifiable_prediction']}")
            if tp.get("known_counterexample"):
                lines.append(f"- 알려진 반례: {tp['known_counterexample']}")
            if tp.get("rival_theories"):
                try:
                    rivals = _json.loads(tp["rival_theories"])
                    lines.append(f"- 경쟁 이론: {', '.join(rivals)}")
                except Exception:
                    pass
        lines.append("")

    # ── Cascade 룰 이론 텍스트 ────────────────────────────────────────────
    cascade_rules = cascade_ctx.get("rules", [])
    if cascade_rules:
        lines.append("## Cascade 인과 룰 (이론 근거)")
        for rule in cascade_rules[:4]:
            lines.append(f"- **{rule['name']}**")
            if rule.get("framework"):
                lines.append(f"  이론: {rule['framework']} ({rule.get('reference', '')})")
            if rule.get("learning"):
                lines.append(f"  해석: {rule['learning']}")
        lines.append("")

    # ── Cascade 발화 실적 ─────────────────────────────────────────────────
    cascade_links = cascade_ctx.get("links", [])
    if cascade_links:
        lines.append("## Cascade 발화 실적 (룰 기반 — 통계 상관계수 아님)")
        # [변수 타당도 감사 2026-07-13] 룰명 기준 접기. 구 쿼리는 링크 행을 그대로
        # 나열해 같은 룰이 5번 중복 출력됐다 — 한 룰의 5회 발화가 5개의 독립 증거처럼
        # 보였다(증거 부풀리기). 발화 횟수로 정직하게 표시한다.
        for lnk in cascade_links[:5]:
            fires = lnk.get("fires", 1)
            lines.append(
                f"- [예측 규칙(실측 아님)] {lnk['rule_name']} "
                f"(룰매칭강도 평균 {lnk['correlation_score']}, {lnk.get('depth', 1)}단계, "
                f"발화 {fires}회)"
            )
        lines.append(
            "  ⚠️ '룰 발화 점수'는 cascade_rules.yaml 규칙이 매칭된 강도(0~1)이며, "
            "교란 통제된 통계적 상관계수가 아니다. 이 값을 '상관계수'로 인용하지 말 것."
        )
        _tot = cascade_ctx.get("ledger_total")
        _lat = cascade_ctx.get("ledger_latest")
        if _tot:
            lines.append(
                f"  ⚠️ **분모 없음(생존편향)**: 이 원장은 **적중만 적재한다** — 룰이 예측한 "
                f"방향으로 시장이 움직이지 않으면 링크 자체가 생성되지 않는다. 그래서 "
                f"{_tot:,}건 전부가 '적중'이고, 위 목록은 그중에서도 점수 상위만 보여준다. "
                f"**적중률·예측력의 근거로 인용하지 마라 — 빗나간 횟수를 우리는 모른다.**"
            )
        if _lat:
            lines.append(
                f"  ⚠️ **신선도**: 최근 링크 생성 {_lat}. 링크는 요청 시점에만 생성되므로 "
                f"이 목록은 재고일 수 있다 — 현재 상황의 증거로 쓰지 마라."
            )
        lines.append("")

    # ── 이벤트 통계 ───────────────────────────────────────────────────────
    if event_stats:
        lines.append("## ACLED 이벤트 통계 (구성 공개 — 압축 금지)")
        for region, stats in event_stats.items():
            total = stats.get("total_events", 0) or 0
            deaths = stats.get("deaths", 0) or 0
            lines.append(f"- **{region}**: 총 {total:,}건 · 사망 {deaths:,}명")
            et = stats.get("event_types", {})
            ordered = sorted(et.items(), key=lambda x: -x[1])
            if ordered and total:
                lines.append("  구성: " + " · ".join(
                    f"{t} {n:,}건({n / total * 100:.1f}%)" for t, n in ordered[:6]))
                # [변수 타당도 감사 2026-07-13] 구성 타당도 자동 경고.
                # "분쟁 이벤트"라는 이름과 내용이 어긋나는 권역을 컨텍스트가 스스로
                # 고발한다 — 한반도 99.5%·대만해협 99.6%가 국내 시위인데 그 숫자가
                # 북한 도발 가설의 독립변수로 쓰이던 사고(8호)의 재발 봉쇄.
                #
                # [하류 오염 위원회 2026-07-13] 두 가지를 고쳤다.
                #
                # ① 시위·소요와 '전략적 전개'(SD)를 분리한다. 구판은 셋을 한 통에
                #    넣어 soft로 셌는데, SD는 ACLED 정의상 "비폭력 전략적 전개"이고
                #    **북한 미사일 시험이 정확히 거기 코딩된다**(north_korea 권역
                #    122건 중 112건이 SD, 전부 "Military Forces of North Korea").
                #    즉 구판 게이트에 물으면 북한 도발 원장이 "91.8% 오염"으로 나온다 —
                #    잡으려던 신호를 오염으로 판정한다. **구성 타당도는 질문에 상대적**이다:
                #    "무력분쟁이 있었나"를 물으면 SD는 잡음이고, "북한이 신호를 보내나"를
                #    물으면 SD가 바로 그 신호다. 게이트는 질문을 모르므로 판정하지 않고
                #    **구성을 분해해서 보여주고 판단을 소비자에게 넘긴다.**
                #
                # ② 경고 등급은 시위·소요 비율(domestic)로만 매긴다 — 그것이 이름과
                #    내용이 어긋나는 유일한 축이다. SD는 별도 줄로 항상 노출한다.
                domestic = sum(n for t, n in et.items() if t in ("Protests", "Riots"))
                strat = sum(n for t, n in et.items() if t == "Strategic developments")
                ratio = domestic / total if total else 0.0
                # 문턱은 이진 50%로 되돌린다. 구판의 20% "주의" 단계는 호르무즈가
                # 45.0%로 강경고를 빠져나간다는 관측 위에 세워졌는데, 그 45.0%는
                # 게이트가 자기 분모를 GDELT로 희석해 만든 인공물이었다(위 _get_event_stats
                # 주석). 진값은 94.8% — 원래의 50% 문턱이 정상 발화했어야 했다.
                # 단계식 패치는 없는 병을 고치면서 호르무즈를 "주의"(약) 구간에
                # 안착시켜 **과소경고를 제도화했다.** 분모를 고쳤으니 패치를 걷는다.
                if ratio >= 0.5:
                    lines.append(
                        f"  ⚠️ **구성 타당도 경고(강)**: 이 권역 ACLED 이벤트의 "
                        f"{ratio * 100:.1f}%가 국내 시위·소요다(사망 {deaths:,}명). 이것은 "
                        f"**군사 충돌 지표가 아니다** — '분쟁 이벤트 건수'를 무력 충돌·도발의 "
                        f"대리변수로 인용하지 마라. 국내 정치 시위를 지정학 긴장으로 오독하는 "
                        f"것이 이 경고의 표적이다. 무력 충돌을 말하려면 Battles·Explosions "
                        f"하위 건수나 사망자 수를 인용하라."
                    )
                elif ratio >= 0.2:
                    lines.append(
                        f"  ⚠️ **구성 타당도 주의**: 이 권역 ACLED 이벤트의 {ratio * 100:.1f}%가 "
                        f"국내 시위·소요다(사망 {deaths:,}명) — 상당 부분이 국내 정치 사건이다. "
                        f"'분쟁 이벤트 건수'를 **순수 군사 지표로 쓰지 마라**."
                    )
                if strat:
                    lines.append(
                        f"  ℹ️ 이 중 **전략적 전개(Strategic developments) {strat:,}건"
                        f"({strat / total * 100:.1f}%)** — ACLED 정의상 비폭력 사건이며 "
                        f"미사일 시험·부대 이동·무력시위가 여기 코딩된다. **무력 충돌을 "
                        f"물으면 이것은 잡음이고, 군사적 신호(도발·억지 시그널링)를 물으면 "
                        f"이것이 바로 그 신호다.** 어느 쪽인지는 가설이 정한다 — 자동 판정하지 않는다."
                    )
            # [큐 10] 추이 사전계산 — 추세 서술은 이 배열·변화율만 인용 가능(창작 금지)
            monthly = stats.get("monthly")
            if monthly:
                parts, prev_ym = [], None
                for ym, c in monthly:
                    if prev_ym is not None:
                        py, pm = int(prev_ym[:4]), int(prev_ym[5:7])
                        gap = (int(ym[:4]) * 12 + int(ym[5:7])) - (py * 12 + pm) > 1
                        parts.append(" ‖ " if gap else " → ")   # ‖ = 수집 단절 구간
                    parts.append(f"{ym[:7]} {c}건")
                    prev_ym = ym
                lines.append("  월별 추이(확정월, 사전계산): " + "".join(parts))
            # 랙 구간은 별도 표시 — 숫자를 보여주되 '추세 아님'을 못박는다.
            lag = stats.get("monthly_lag")
            if lag:
                lines.append(
                    "  ⚠️ **수집 랙 구간(건수 미확정)**: "
                    + " · ".join(f"{ym} {c}건" for ym, c in lag)
                    + f" — ACLED 학술 티어는 event_date 기준 최대 {_ACLED_LAG_MONTHS}개월 랙이라 "
                      "이 달들은 백필이 진행 중이다. **이 숫자로 증감·추세를 서술하지 마라** "
                      "(낮게 보이는 것은 사건이 줄어서가 아니라 아직 안 들어와서다)."
                )
                if stats.get("trend_dir"):
                    pct = stats.get("trend_pct")
                    pct_s = f" ({pct:+.1f}%)" if pct is not None else ""
                    lines.append(
                        f"  직전 완결월 대비: {stats['trend_from']}건→{stats['trend_to']}건"
                        f"{pct_s} {stats['trend_dir']} — ⚠️ 수집 커버리지 변동 가능, "
                        "위 배열 밖 추세 서술 금지"
                    )
        lines.append("")

    # ── 국가 프로파일 ─────────────────────────────────────────────────────
    if country_profiles:
        lines.append("## 행위자 국가 프로파일")
        for iso3, profile in country_profiles.items():
            posture  = profile.get("strategic_posture", "?")
            position = profile.get("strategic_position", "?")
            inst     = profile.get("instrument_of_power", "?")
            risks    = profile.get("key_risks", [])
            lines.append(f"- **{iso3}**: {position}")
            lines.append(f"  포지션={posture} | 주요수단={inst}")
            if risks:
                lines.append(f"  주요위험: {', '.join(str(r) for r in risks[:3])}")
        lines.append("")

    # ── Phase 8 융합1: priority tier — theory_cmp_ctx 우선 확보 ─────────────────
    # backbone 직후 경쟁이론 수치비교 블록을 먼저 넣어 잔량 누락 방지.
    if theory_cmp_ctx and not data_only:
        block_chars = len(theory_cmp_ctx) + 2
        used = sum(len(l) + 1 for l in lines)
        if used + block_chars <= _CONTEXT_MAX_CHARS:
            lines.append("")
            lines.append(theory_cmp_ctx)
        elif _CONTEXT_MAX_CHARS - used > 500:
            lines.append("")
            lines.append(theory_cmp_ctx[:_CONTEXT_MAX_CHARS - used - 1])

    # ── Phase 8 Cycle 8-D: priority tier — 문헌 공백 원장 ───────────────────────
    # 라이브러리 주장에서 결정론적으로 추출한 공백 신호(반례·경쟁이론·밀도).
    # [문헌공백] 섹션이 추측이 아니라 실측 주장 지도에 근거하도록 만든다.
    ledger_block = [] if data_only else build_claim_ledger(pq, all_items)
    if ledger_block:
        block_chars = len(ledger_block) + 2
        used = sum(len(l) + 1 for l in lines)
        if used + block_chars <= _CONTEXT_MAX_CHARS:
            lines.append("")
            lines.append(ledger_block)

    # ── Phase 8 융합1: data tier — 관련성 점수순 조립 ───────────────────────────
    # ⚠️ 정직성 가드: 점수는 '이 소스가 이 쿼리 주제에 관한가'만 판단한다.
    #   '이 데이터가 가설을 지지하는가'는 절대 점수에 넣지 않는다 (체리피킹=환각).
    _source_records = {
        "bp":            bp_data,
        "sipri_milex":   sipri_data,
        "cow_alliances": cow_alliances,
        "kiel":          kiel_data,
        "eia":           eia_data,
        "csis":          csis_incidents,
        "sipri_arms":    sipri_arms,
        "vdem":          vdem_data,
        "cow_wars":      cow_wars,
        "ifans":         ifans_pubs,
        "fred":          fred_data,
        "wbk":           wbk_data,
        "polity5":       polity5_data,
        "itu":           itu_data,
        "hiik":          hiik_data,
        "semi":          semi_data,
        "owid":          owid_data,
        "trade":         trade_dep_data,
        "press":         press_data,
    }

    scored: list[tuple[float, str]] = []
    for key, spec in _SOURCE_SPECS.items():
        records = _source_records.get(key)
        s = _score_source(spec, records, pq)
        if s >= 0:
            scored.append((s, key))
        logger.debug("[fusion1] key=%s score=%.2f", key, s)
    scored.sort(key=lambda x: -x[0])

    for _, key in scored:
        block = _SOURCE_EMITTERS[key](_source_records[key])
        if not block:
            continue
        block_chars = sum(len(l) + 1 for l in block)
        used = sum(len(l) + 1 for l in lines)
        if used + block_chars > _CONTEXT_MAX_CHARS:
            continue   # 이 블록이 초과하면 건너뜀 — 더 작은 다음 블록은 들어갈 수 있음
        lines.extend(block)

    result = "\n".join(lines)
    # 혹시 예산을 초과한 경우 마지막 완전 섹션 경계에서 절단
    if len(result) > _CONTEXT_MAX_CHARS:
        cut = result[:_CONTEXT_MAX_CHARS]
        boundary = cut.rfind("\n## ")
        if boundary > _CONTEXT_MAX_CHARS // 2:
            cut = cut[:boundary]
        result = cut + "\n\n[컨텍스트 예산 초과 — 이후 섹션 생략]"
    return result


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

async def build_intel_context(pq: ParsedQuery) -> dict:
    loop = asyncio.get_event_loop()

    results = await asyncio.gather(
        loop.run_in_executor(None, _search_library_like,
                             pq.raw_query, pq.regions, pq.sectors),
        loop.run_in_executor(None, _search_library_by_sector, pq.sectors),
        loop.run_in_executor(None, _get_event_stats, pq.regions),
        loop.run_in_executor(None, _get_cascade_context, pq.regions),
        loop.run_in_executor(None, _get_country_profiles, pq.actors),
        loop.run_in_executor(None, _get_sipri_data, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_cow_alliances, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_kiel_data, pq.regions),
        loop.run_in_executor(None, _get_eia_data, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_csis_incidents, pq.actors, pq.regions, pq.sectors),
        # Cycle 6-A 신규 소스
        # Arms: 섹터가 techno·cyber 전용일 때만 미주입 (무관한 주장 유발 방지)
        # 빈 섹터(일반 쿼리)는 포함, 멀티섹터(techno+energy 등)는 포함
        loop.run_in_executor(None, _get_sipri_arms,
                             pq.actors if not (
                                 bool(pq.sectors) and
                                 all(s in {"techno", "cyber"} for s in pq.sectors)
                             ) else [],
                             pq.regions),
        loop.run_in_executor(None, _get_vdem, pq.actors),
        loop.run_in_executor(None, _get_cow_wars, pq.regions, pq.actors),
        loop.run_in_executor(None, _get_ifans_publications, pq.actors, pq.regions),
        # Cycle 7-B: 경쟁 이론 비교 프로파일 (예측값 vs 실측값)
        loop.run_in_executor(None, build_theory_comparison_context,
                             pq.sectors, pq.regions, pq.actors),
        # Cycle 7-D: 신규 소스 6개
        loop.run_in_executor(None, _get_fred_data, pq.regions, pq.sectors),
        loop.run_in_executor(None, _get_world_bank_wgi, pq.actors, pq.regions),
        loop.run_in_executor(None, _get_polity5, pq.actors),
        loop.run_in_executor(None, _get_itu_ict, pq.actors, pq.sectors),
        loop.run_in_executor(None, _get_hiik_conflict, pq.regions),
        loop.run_in_executor(None, _get_semi_market, pq.sectors, pq.regions),
        loop.run_in_executor(None, _get_owid_data, pq.actors, pq.regions, pq.sectors),
        # AR-1b: Comtrade 무역 의존도 (Weaponized Interdependence IV)
        loop.run_in_executor(None, _get_trade_dependency, pq.actors, pq.regions),
        # 큐 10① 배선 (2026-07-11): govinfo·nk_press·un_news — region_hint 게이트
        loop.run_in_executor(None, _get_press_releases, pq.regions),
        # 접지 감사 배선 (2026-07-13): 도발 원장 — 이중언어 토픽 게이트
        loop.run_in_executor(None, _get_bp_provocations,
                             pq.regions, pq.actors, pq.raw_query),
        return_exceptions=True,
    )

    def _safe(r, default):
        return r if not isinstance(r, Exception) else default

    like_items        = _safe(results[0], [])
    sector_items      = _safe(results[1], [])
    event_stats       = _safe(results[2], {})
    cascade_ctx       = _safe(results[3], {"links": [], "rules": []})
    country_profiles  = _safe(results[4], {})
    sipri_data        = _safe(results[5], {})
    cow_alliances     = _safe(results[6], [])
    kiel_data         = _safe(results[7], [])
    eia_data          = _safe(results[8], {})
    csis_incidents    = _safe(results[9], [])
    sipri_arms        = _safe(results[10], [])
    vdem_data         = _safe(results[11], [])
    cow_wars          = _safe(results[12], [])
    ifans_pubs        = _safe(results[13], [])
    theory_cmp_ctx    = _safe(results[14], "")
    fred_data         = _safe(results[15], [])
    wbk_data          = _safe(results[16], [])
    polity5_data      = _safe(results[17], [])
    itu_data          = _safe(results[18], [])
    hiik_data         = _safe(results[19], [])
    semi_data         = _safe(results[20], [])
    owid_data         = _safe(results[21], [])
    trade_dep_data    = _safe(results[22], [])
    press_data        = _safe(results[23], {})
    bp_data           = _safe(results[24], {})

    context_text = _build_context(
        pq, like_items, sector_items, event_stats, cascade_ctx, country_profiles,
        sipri_data, cow_alliances, kiel_data, eia_data, csis_incidents,
        sipri_arms, vdem_data, cow_wars, ifans_pubs,
        fred_data, wbk_data, polity5_data, itu_data, hiik_data, semi_data,
        owid_data, trade_dep_data, press_data,
        theory_cmp_ctx=theory_cmp_ctx,  # Phase 8 융합1: priority tier로 이동
        bp_data=bp_data,
    )

    # ── [접지 감사 2026-07-13] 접지(grounding) 측정 ──────────────────────────
    # 같은 조달 결과로 라이브러리 유래(브리핑·이론·문헌공백)를 뺀 순수 데이터
    # 컨텍스트를 재조립(추가 SQL 없음 — 문자열 조립만)해, 쿼리 키워드가 '데이터'에
    # 실제로 등장하는지 항별로 센다. 브리핑 히트를 접지로 오인하던 미탐(반박석
    # 공격 2)과 키워드 합계의 일반어 인플레이션(전수 감사 실측)을 함께 막는다.
    data_text = _build_context(
        pq, like_items, sector_items, event_stats, cascade_ctx, country_profiles,
        sipri_data, cow_alliances, kiel_data, eia_data, csis_incidents,
        sipri_arms, vdem_data, cow_wars, ifans_pubs,
        fred_data, wbk_data, polity5_data, itu_data, hiik_data, semi_data,
        owid_data, trade_dep_data, press_data,
        theory_cmp_ctx="", bp_data=bp_data, data_only=True,
    )
    _g_terms = _extract_keywords(pq.raw_query)
    # 지역어 한↔영 별칭 — 데이터 텍스트가 영문 코드(hormuz·taiwan_strait)로 흐르는
    # 소스가 많아 한국어 키워드만 세면 정상 접지 쿼리가 SPARSE 오탐된다(반박석
    # 예견 → 호르무즈 실측). 별칭 히트도 그 항의 접지로 계수한다.
    _GROUNDING_KO_EN = {
        "호르무즈": ["hormuz"], "대만": ["taiwan"], "우크라이나": ["ukraine"],
        "발트": ["baltic"], "홍해": ["red sea", "bab_el_mandeb"],
        "서해": ["west sea", "yellow sea", "nll"], "수에즈": ["suez"],
        "남중국해": ["south_china_sea", "south china sea"],
        "동중국해": ["east_china_sea"], "말라카": ["malacca"],
        "한반도": ["korean_peninsula", "korea"],
        "북한": ["north korea", "dprk", "prk"], "중동": ["middle_east"],
    }
    _dt_low = data_text.lower()
    def _g_count(term: str) -> int:
        n = data_text.count(term)
        for ko, ens in _GROUNDING_KO_EN.items():
            if ko in term:
                n += sum(_dt_low.count(e) for e in ens)
        return n
    _g_hits = {t: _g_count(t) for t in _g_terms}
    _grounded = [t for t, v in _g_hits.items() if v > 0]
    _g_ratio = round(len(_grounded) / len(_g_terms), 2) if _g_terms else 0.0
    grounding = {
        "terms": _g_hits,
        "grounded_ratio": _g_ratio,
        # SPARSE 문턱 0.25 — 0.34는 일반어가 많은 쿼리(호르무즈 8키워드 중
        # 접지 3항 = 0.33)를 오탐했다(경계 실측 2026-07-13). 개체층 부재
        # (베르베라 0.12)와 완전 부재(발트 0.0)는 0.25에서도 그대로 잡힌다.
        "flag": ("TOPIC_ABSENT" if _g_ratio == 0.0
                 else "TOPIC_SPARSE" if _g_ratio < 0.25 else "GROUNDED"),
        "basis": "data-only context (브리핑·이론·문헌공백 제외)",
        "data_context_chars": len(data_text),
    }

    logger.debug(
        "[intel] 컨텍스트 조립 — LIKE=%d sector=%d SIPRI=%d COW=%d Kiel=%d "
        "EIA=%d CSIS=%d Arms=%d VDEM=%d Wars=%d IFANS=%d Theory=%d "
        "FRED=%d WBK=%d P5=%d ITU=%d HIIK=%d SEMI=%d Trade=%d 총%d자",
        len(like_items), len(sector_items),
        len(sipri_data), len(cow_alliances), len(kiel_data),
        len(eia_data), len(csis_incidents),
        len(sipri_arms), len(vdem_data), len(cow_wars), len(ifans_pubs),
        len(theory_cmp_ctx),
        len(fred_data), len(wbk_data), len(polity5_data),
        len(itu_data), len(hiik_data), len(semi_data),
        len(trade_dep_data),
        len(context_text),
    )

    return {
        "context_text": context_text,
        "grounding": grounding,
        "source_counts": {
            "fts_items":           len(like_items),
            "sector_items":        len(sector_items),
            "event_stats_regions": len(event_stats),
            "cascade_links":       len(cascade_ctx.get("links", [])),
            "country_profiles":    len(country_profiles),
            "sipri_countries":     len(sipri_data),
            "cow_alliances":       len(cow_alliances),
            "kiel_donors":         len(kiel_data),
            "eia_entries":         len(eia_data),
            "csis_incidents":      len(csis_incidents),
            "sipri_arms":          len(sipri_arms),
            "vdem_entries":        len(vdem_data),
            "cow_wars":            len(cow_wars),
            "ifans_pubs":          len(ifans_pubs),
            "theory_cmp_chars":    len(theory_cmp_ctx),
            # Cycle 7-D 신규 정형 수치 소스 (L1-c — data_void_penalty 보정용)
            "fred":                len(fred_data),
            "wbk":                 len(wbk_data),
            "polity5":             len(polity5_data),
            "itu":                 len(itu_data),
            "hiik":                len(hiik_data),
            "semi":                len(semi_data),
            "owid":                len(owid_data),
            "press":               sum(len(v) for v in press_data.values()),
            # 접지 감사 2026-07-13: 도발 원장 (주제 매칭 건수)
            "bp_provocations":     sum((bp_data or {}).get("match_years", {}).values())
                                   or (1 if bp_data else 0),
        },
        "like_items":        like_items,
        "sector_items":      sector_items,
        "event_stats":       event_stats,
        "cascade_ctx":       cascade_ctx,
        "country_profiles":  country_profiles,
        "sipri_data":        sipri_data,
        "cow_alliances":     cow_alliances,
        "kiel_data":         kiel_data,
        "eia_data":          eia_data,
        "csis_incidents":    csis_incidents,
        "sipri_arms":        sipri_arms,
        "vdem_data":         vdem_data,
        "cow_wars":          cow_wars,
        "ifans_pubs":        ifans_pubs,
    }
