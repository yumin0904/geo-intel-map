"""
services/methods/iv_construct.py — IV 구성타당도 게이트 (Construct Validity Gate).

목표(2026-07-05, geo-os/docs/ENGINE_CONSTRUCT_VALIDITY.md): 검정에 들어가는 독립변수가
질문이 지목한 대상을 실제로 측정하는지 검사한다. 못 하면 검정을 성립시키지 않는다.

배경(실측): 7호 쿼리 "북한 미사일 도발"에서 IV로 쓴 korean_peninsula conflict 4,758건의
실제 구성은 South Korea 98%·North Korea 0건(ACLED가 폐쇄국가 북한 미커버). 큰 표본이
그럴듯한 p=0.064를 만들었으나, 변수가 질문 대상을 전혀 측정하지 못하는 구성타당도 붕괴였다.

원칙(엔진 헌법 "정직성 > 프록시"의 IV판): 필터로 검정을 성립시키는 게 목표가 아니라,
변수가 질문을 측정하지 못한다는 사실을 드러내는 게 목표다. Token-Zero — 순수 SQL+키워드.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "intel.db"

# 명시된 대상이 실제 이벤트 표본에서 이 비율 미만이면 '질문 대상 미측정'으로 판정.
# 보수적 하한 — 대상이 10%도 안 되면 그 대상에 대한 검정이라 볼 수 없다. (2단계 config화 대상)
_MIN_TARGET_SHARE = 0.10   # (참고값) 표본 오염도 — meta에만 보존, 판정은 절대량 기준
# 필터 후 검정 가능한 최소 대상 이벤트 수. 이 이상이면 country 필터로 순수 시계열을 뽑는다.
_MIN_TARGET_N = 30

# 국가 별칭 사전 — canonical은 event_archive payload의 country 표기와 동일하게 맞춘다.
# 한국어 별칭과 영문 '완전형'만 사용: 부분문자열 오염 방지(예: 'korea'만 쓰면
# 'korean_peninsula'·'North Korea'가 모두 걸린다 → 반드시 'south korea' 완전형).
_COUNTRY_ALIASES: dict[str, list[str]] = {
    "North Korea": ["북한", "조선민주주의", "north korea", "dprk", "평양", "김정은"],
    "South Korea": ["남한", "대한민국", "한국", "south korea", "서울"],
    "China":       ["중국", "china", "베이징", "시진핑"],
    "Japan":       ["일본", "japan", "도쿄"],
    "Russia":      ["러시아", "russia", "모스크바", "푸틴"],
    "Iran":        ["이란", "iran", "테헤란"],
    "Israel":      ["이스라엘", "israel"],
    "Taiwan":      ["대만", "taiwan", "타이완", "타이베이"],
    "Ukraine":     ["우크라이나", "ukraine", "키이우", "키예프"],
    "United States": ["미국", "united states", "워싱턴"],
}


@dataclass
class ConstructVerdict:
    """구성타당도 판정. ok=False면 검정을 진행하지 않는다.
    filter_country: ok=True이고 단일 국가 지목 시, 검정에서 그 국가만 필터하라는 지시
    (A-1 — 순수 대상 시계열). None이면 필터 없이 region 전체."""
    ok: bool
    reason: str = ""
    meta: dict = field(default_factory=dict)
    filter_country: str | None = None


def probe_event_iv(region: str, start: date, end: date) -> dict | None:
    """event_archive에서 region 이벤트의 country·event_type 분포를 집계 (순수 SQL)."""
    if not region:
        return None
    try:
        con = sqlite3.connect(_DB_PATH)
        rows = con.execute(
            """
            SELECT json_extract(payload, '$.country')    AS country,
                   json_extract(payload, '$.event_type') AS etype,
                   COUNT(*)                               AS n
            FROM event_archive
            WHERE region_code = ?
              AND DATE(timestamp) BETWEEN ? AND ?
            GROUP BY country, etype
            """,
            (region, start.isoformat(), end.isoformat()),
        ).fetchall()
        con.close()
    except Exception:
        return None

    country_dist: dict[str, int] = {}
    etype_dist: dict[str, int] = {}
    total = 0
    for country, etype, n in rows:
        total += n
        key_c = country if country else "(미상)"
        country_dist[key_c] = country_dist.get(key_c, 0) + n
        key_e = etype if etype else "(미상)"
        etype_dist[key_e] = etype_dist.get(key_e, 0) + n

    if total == 0:
        return None
    return {"n_events": total, "country_dist": country_dist, "event_type_dist": etype_dist}


def _named_countries(iv_text: str) -> list[str]:
    """IV 텍스트가 명시적으로 지목한 국가(canonical) 목록. 한국어·영문 완전형 매칭."""
    low = iv_text.lower()
    named = []
    for canonical, aliases in _COUNTRY_ALIASES.items():
        if any(a in low for a in aliases):
            named.append(canonical)
    return named


def assess_construct(iv_text: str, probe: dict | None) -> ConstructVerdict | None:
    """
    IV가 명시한 대상 국가가 실제 이벤트 표본에 충분히 있는지 판정.

    반환:
      None                — 게이트 미적용 (프로브 불가 또는 IV가 국가를 특정하지 않음).
                            국가를 밝히지 않은 IV는 이 게이트의 대상이 아니다(오탐 방지).
      ConstructVerdict.ok=True  — 대상이 표본에 충분히 존재. 검정 진행.
      ConstructVerdict.ok=False — 대상이 표본에 거의 없음. 검정 미수행 권고.
    """
    if not probe or not iv_text:
        return None
    named = _named_countries(iv_text)
    if not named:
        return None  # 국가 특정 없음 — 게이트 대상 아님

    total = probe["n_events"]
    dist = probe["country_dist"]
    named_n = sum(dist.get(c, 0) for c in named)
    share = named_n / total if total else 0.0

    # 표본 최다 국가 (대비 노출용)
    top_country = max(dist, key=dist.get)
    top_share = dist[top_country] / total if total else 0.0

    # 단일 국가 지목이면 그 국가만 필터해 순수 시계열을 뽑을 수 있다(A-1).
    filter_country = named[0] if len(named) == 1 else None

    meta = {
        "named_countries": named,
        "named_share": round(share, 3),
        "named_n": named_n,
        "top_country": top_country,
        "top_share": round(top_share, 3),
        "n_events": total,
        "country_dist": dist,
        "filter_country": filter_country,
    }

    # 판정 기준: share가 아니라 '필터 후 절대량'. 대상 이벤트가 검정할 만큼(≥_MIN_TARGET_N)
    # 있으면, 표본에 다른 국가가 섞여 있어도 country 필터로 순수 시계열을 뽑아 검정한다.
    # 부족하면(수집 안 됨) 검정 미수행 — 데이터 갭. (share는 오염도 참고값으로만 meta에 보존.)
    # 배경: 7호는 North Korea 0건이라 FAIL이었으나, CNS 미사일 DB 적재 후 185건 → PASS.
    if named_n < _MIN_TARGET_N:
        reason = (
            f"[구성타당도] IV 지목 대상({'·'.join(named)}) 이벤트 {named_n}건 < {_MIN_TARGET_N} — "
            f"검정 표본 부족(데이터 미수집). 표본 최다는 {top_country}({top_share:.0%}). "
            f"필터해도 순수 시계열이 안 나옴 → 해당 대상 소스 수집 필요(data_gap)."
        )
        return ConstructVerdict(ok=False, reason=reason, meta=meta, filter_country=None)

    # 충분 — filter_country로 순수 검정. 표본 오염(share 낮음)은 필터로 해소되므로 통과.
    return ConstructVerdict(ok=True, reason="", meta=meta, filter_country=filter_country)
