"""전건 판정기 — B28. **"X가 일어났는가"를 기계가 물을 수 있게 한다.**

## 왜 없었나

예측의 DV는 **정량 7필드**다 — `target`·`target_kind`·`direction`·`threshold_pct`·
`horizon_days`·`resolve_by`·`realized_direction`. 그런데 IV는 **`independent_var` TEXT 한 칸**이다.

    "호르무즈 (hormuz) 지역의 ACLED 분쟁 건수가 월간 100 건 이상"     ← 판정 가능한데
    "korean_peninsula ACLED 분쟁 이벤트 월별 건수 증가에도 불구하고…"  ← 문장이 통째로
    "WTI 유가"                                                      ← 명사구
    "2024년 12월 3일 비상계엄 선포"                                   ← 이미 일어난 과거

**명사구로는 참·거짓을 물을 수 없다.** 그래서 `prediction_scorer`는 IV를 **한 번도 안 읽었고**
(자기 주석에 자백해 놨다: *"전건의 발생 여부를 판정할 계기가 없다"*), 채점된 82건
(HIT 49 · MISS 33)이 **전부 무효**가 됐다. 간판 = **0/0**.

## 공허한 참 (vacuous truth) — 이게 병의 이름이다

*"X가 증가하면 Y가 오른다"*에서 **X가 안 일어났으면 그 예측은 참도 거짓도 아니다.**
그런데 채점기는 X를 무시하고 **Y만 봤다.** 그래서 「호르무즈 긴장 → 유가 상승」 예측이
**호르무즈에서 아무 일도 없었는데** 유가가 올랐다는 이유로 **HIT**가 됐다.

**적중률 59.8%가 그렇게 만들어졌다.**

## 계약

- **계량은 닫힌 목록이다**(`_IV_METRICS`) — D2 위원회 비준 2종 + 권역위 1종.
  LLM이 명사구를 지어내도 **이 목록 밖이면 IV가 아니다.** Token-Zero.
- **판정은 결정론이다** — DB에 묻는다. LLM은 관여하지 않는다.
- **못 판정하면 «못 판정한다»고 말한다** — 「안 일어났다」로 바꿔치기하지 않는다.
  ("못 쟀다"를 "관계 없다"로 바꿔치기하는 것이 이 엔진의 고질병이다)
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

# ── 전건으로 쓸 수 있는 계량 — **닫힌 목록** ──────────────────────────────────
#
# D2 위원회(2026-07-14, geo-os [[20260714-d2-iv-committee]])가 비준한 2종 병기 +
# 권역위(v9.66)가 north_korea용으로 만든 1종.
#
# ⚠️ **여기 없는 것은 IV가 될 수 없다.** `severity` 합은 은퇴했다 —
#    r(SUM(severity), 행수) = ukraine 1.000 · 전역 0.984, **IV의 정체가 적재 행 수**였다.
_IV_METRICS: dict[str, str] = {
    "violence_count": "ACLED 무력폭력 건수 (Battles · Explosions/Remote violence · Violence against civilians)",
    "fatalities": "ACLED 사망자 수 (payload.fatalities 합)",
    "provocation_count": "CSIS Beyond Parallel 북한 도발 건수 (north_korea 전용)",
}

_ACLED_VIOLENT = ("Battles", "Explosions/Remote violence", "Violence against civilians")

Verdict = Literal["MET", "NOT_MET", "UNDECIDABLE"]


@dataclass(frozen=True)
class Antecedent:
    """반증 가능한 전건. **DV와 대칭이다.**

    `baseline` 모드: 임계가 없고 "증가/감소"만 말한 경우 — **직전 동일 창**과 비교한다.
    (그냥 "증가"는 판정 불가처럼 보이지만, 비교 기준을 사전에 못 박으면 판정 가능해진다.
     기준을 결과 보고 정하면 그게 forking paths다 — 그래서 **여기서 미리 정한다.**)
    """

    metric: str            # _IV_METRICS 중 하나
    region: str
    direction: Literal["up", "down"]
    window_days: int
    threshold: float | None = None   # None이면 baseline 모드

    @property
    def mode(self) -> str:
        return "absolute" if self.threshold is not None else "baseline"

    def as_sentence(self) -> str:
        m = _IV_METRICS[self.metric]
        arrow = "이상" if self.direction == "up" else "이하"
        if self.threshold is not None:
            return f"{self.region}의 {m}이(가) {self.window_days}일 창에서 {self.threshold:g} {arrow}"
        chg = "증가" if self.direction == "up" else "감소"
        return f"{self.region}의 {m}이(가) 직전 {self.window_days}일 대비 {chg}"


# ── 파서 — LLM의 IV 텍스트에서 **결정론적으로** 전건을 뽑는다 ─────────────────

_METRIC_PAT = [
    ("fatalities", re.compile(r"사망자|사망\s*수|fatalit", re.I)),
    # BP의 실체는 **미사일 발사**다 — "Strategic cruise missile" · "Short-range Ballistic
    # Missile Launch" · "Mixed Tactical Weapons Test". LLM은 이걸 «도발»·«미사일 발사»·
    # «미사일 시험» 등으로 부른다. 초판은 "도발 건수"만 찾아서 **"북한 미사일 발사 건수"를
    # 놓쳤다** — 완벽한 전건인데.
    ("provocation_count", re.compile(
        r"도발|미사일\s*(발사|시험|도발)|탄도\s*미사일|무기\s*시험|provocation|missile", re.I)),
    ("violence_count", re.compile(r"분쟁|무력|폭력|충돌|교전|violence|conflict|battle", re.I)),
]
_THRESHOLD_PAT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:건|명|회)?\s*(이상|초과|이하|미만)")
_DIR_UP = re.compile(r"증가|상승|급증|확대|이상|초과|늘어")
_DIR_DOWN = re.compile(r"감소|하락|축소|이하|미만|줄어")
_WINDOW_PAT = [
    (30, re.compile(r"월간|월별|한\s*달|30\s*일")),
    (7, re.compile(r"주간|주별|일주일|7\s*일")),
    (90, re.compile(r"분기|90\s*일|3\s*개월")),
    (365, re.compile(r"연간|1\s*년|365\s*일")),
]
_DEFAULT_WINDOW = 30


# **보도량은 전건이 아니다** — 이 가드가 없으면 "GDELT 물리충돌 **보도** 건수"가
# `violence_count`로 위장해 들어온다("물리충돌"이 패턴에 걸린다). 음성 테스트가 잡았다.
#
# 실측 2026-07-14: GDELT `n_material_conflict`의 정체
#   r(분쟁, 보도총량)          = **0.959** (IRN)   ← severity IV(0.984)와 같은 병
#   r(GDELT 분쟁, ACLED 폭력)  = **0.019** (IRN)   ← 실제 폭력과 **아무 관계 없다**
# 즉 그것은 «이란 뉴스가 얼마나 많았나»다. 그리고 유가가 오르면 이란 뉴스가 늘어난다 —
# **역인과까지 딸려온다.**
_PRESS_VOLUME = re.compile(r"GDELT|보도|언급|기사|mention|coverage|news", re.I)


def parse(independent_var: str | None, region_code: str | None) -> Antecedent | None:
    """IV 텍스트 → 전건. **못 뽑으면 None** — 그러면 그 예측은 `scorable=0`이다.

    ⚠️ **지어내지 않는다.** 계량을 못 찾으면 None. 권역이 없으면 None.
    「그럴듯하게 채우기」가 이 엔진이 죽는 방식이다.
    """
    if not independent_var or not region_code:
        return None
    iv = independent_var.strip()

    if _PRESS_VOLUME.search(iv):
        return None                       # 보도량은 사건이 아니다 (실측: r=0.959 부피 동행)

    metric = next((k for k, pat in _METRIC_PAT if pat.search(iv)), None)
    if metric is None:
        return None                       # 목록 밖 계량 = IV가 아니다
    # BP는 **북한의 도발**을 센다. 그 전건이 **한국 시장**(KRW·KOSPI·방산주)에 영향을 준다는
    # 것이 가설이다 — **전건의 지리와 DV의 지리가 다른 것이 정상이고, 그게 인과의 방향이다.**
    # (권역위가 north_korea를 분리한 이유는 `korean_peninsula` ACLED 표본에 북한이 0건이라서다.
    #  그건 «폭력을 어디서 세나»의 문제였지 «누가 도발했나»의 문제가 아니다.)
    if metric == "provocation_count" and region_code not in ("north_korea", "korean_peninsula"):
        return None

    window = next((d for d, pat in _WINDOW_PAT if pat.search(iv)), _DEFAULT_WINDOW)

    tm = _THRESHOLD_PAT.search(iv)
    if tm:
        thr = float(tm.group(1).replace(",", ""))
        direction = "up" if tm.group(2) in ("이상", "초과") else "down"
        return Antecedent(metric, region_code, direction, window, thr)

    # 임계가 없으면 방향어라도 있어야 한다 — 방향조차 없으면 명사구다
    if _DIR_UP.search(iv):
        return Antecedent(metric, region_code, "up", window, None)
    if _DIR_DOWN.search(iv):
        return Antecedent(metric, region_code, "down", window, None)
    return None


# ── 관측 — DB에 묻는다. LLM은 관여하지 않는다 ────────────────────────────────

def observe(con: sqlite3.Connection, ant: Antecedent, end: date) -> float | None:
    """`end` 기준 창 안의 실측값. 데이터가 없으면 **None**(0이 아니다).

    ⚠️ **0과 None은 다르다.** "폭력 0건"과 "수집이 안 됐다"를 같은 값으로 만들면
    그게 `fill_value=0`이 저지른 짓이다(B01 — 수집 공백을 "전쟁 없음"으로 위조).
    """
    start = end - timedelta(days=ant.window_days)
    if ant.metric == "provocation_count":
        row = con.execute(
            "SELECT COUNT(*) FROM bp_provocations "
            "WHERE date(event_date) > ? AND date(event_date) <= ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()
        return float(row[0]) if row else None

    # ACLED 커버리지가 창 안에 존재하는가 — 없으면 판정 불가다
    cover = con.execute(
        "SELECT COUNT(*) FROM event_archive "
        "WHERE json_extract(payload,'$.data_source')='ACLED' "
        "  AND date(timestamp) > ? AND date(timestamp) <= ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    if not cover or cover[0] == 0:
        return None                       # 수집이 없다 ≠ 사건이 0이다

    if ant.metric == "violence_count":
        expr = (
            "SUM(CASE WHEN json_extract(payload,'$.event_type') IN (?,?,?) THEN 1 ELSE 0 END)"
        )
        args = (*_ACLED_VIOLENT, ant.region, start.isoformat(), end.isoformat())
    else:  # fatalities
        expr = "COALESCE(SUM(json_extract(payload,'$.fatalities')),0)"
        args = (ant.region, start.isoformat(), end.isoformat())

    row = con.execute(
        f"SELECT {expr} FROM event_archive "
        "WHERE json_extract(payload,'$.data_source')='ACLED' AND region_code = ? "
        "  AND date(timestamp) > ? AND date(timestamp) <= ?",
        args,
    ).fetchone()
    return float(row[0] or 0)


def verify(con: sqlite3.Connection, ant: Antecedent, as_of: date) -> tuple[Verdict, float | None]:
    """**전건이 실제로 일어났는가.** → (판정, 관측값)

    - `MET`         — 일어났다. **이제서야 DV를 채점할 자격이 생긴다.**
    - `NOT_MET`     — 안 일어났다. **그 예측은 참도 거짓도 아니다**(공허한 참).
                      적중으로도 오답으로도 세지 않는다.
    - `UNDECIDABLE` — 못 판정한다. **「안 일어났다」로 바꿔치기하지 않는다.**
    """
    obs = observe(con, ant, as_of)
    if obs is None:
        return "UNDECIDABLE", None

    if ant.mode == "absolute":
        met = obs >= ant.threshold if ant.direction == "up" else obs <= ant.threshold
        return ("MET" if met else "NOT_MET"), obs

    base = observe(con, ant, as_of - timedelta(days=ant.window_days))
    if base is None:
        return "UNDECIDABLE", obs         # 비교 기준이 없으면 «증가»를 판정할 수 없다
    met = obs > base if ant.direction == "up" else obs < base
    return ("MET" if met else "NOT_MET"), obs
