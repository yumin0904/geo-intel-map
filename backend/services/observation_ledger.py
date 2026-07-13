"""
[P1] Report-only 변화 관찰 원장 — 데이터가 분석 호출 없이 먼저 입을 여는 지점.

데이터효용위(2026-07-12, geo-os [[20260712-data-utility-committee]]) 채택안 P1.
적재된 시계열을 **각 계열 자신의 과거 기준선**에 대조해 통계적으로 이례적인
변화만 원장 1행으로 남긴다. 산출은 발견도 등급도 인과도 아니다 — 날짜 찍힌
관찰("계열 X: 기준선 대비 +N%, p=…, 가드 통과")이 전부다.

위원회 채택 조건(6게이트)의 코드 반영:
  ① report-only  — 이 모듈은 observation_ledger·observation_runs 두 테이블 외에
     어떤 것도 쓰지 않는다. 라우터·게이트·등급 어디서도 참조 금지(타깃화 금지).
  ② 검정 자동 실행 없음 — 관찰이 가설 검정을 트리거하지 않는다(그건 P2, 별도
     사전등록 동결트리 전제).
  ③ 다중비교 사전 통제 — 스캔 가족(_FAMILIES)은 코드 상수로 사전 선언되고,
     매 런 전체 후보에 Benjamini-Hochberg FDR(q=0.05)을 적용해 통과분만 기록.
     family_size·p_value를 행에 병기(다중성 자기 노출).
  ④ 해석 없음 — 행에는 계열·델타·기준선·가드 결과만. 인과 동사 없는 순수 기술.
  ⑤ 증식 방지 신원 키 — identity_key(가족|계열|관측월) UNIQUE. 재실행은 기존
     행의 확인 횟수만 올린다(PENDING 605→807 문구 변형 증식 병리의 선반영).
  ⑥ 비용 상한 — Token-Zero(LLM 無)·기존 launchd 수집 잡에 편승·일 1회 자체
     스로틀(observation_runs 날짜 마커).

수집 아티팩트 가드 (intel_analyzer._get_event_stats의 봉인 로직 이식 —
hormuz·taiwan '+6100%' 위조 억제 실측 계보):
  - 당월(진행 중) 제외 — 완결월만 비교.
  - 관측월~기준선 창이 달력상 연속이어야 함(수집 공백을 건너뛴 비교는 추세 위조).
  - 기준선 평균 ≥ _MIN_BASE(30) — 소분모의 % 폭발 차단.
  - 기준선 완결월 ≥ _MIN_BASELINE_MONTHS(3).

통계 정직성: 분쟁류 카운트는 과산포(overdispersion)가 상례라 순수 포아송 꼬리는
유의를 과장한다. 기준선 n≥4이고 표본분산>평균이면 경험분산 정규 꼬리와
포아송 꼬리 중 **보수적인 쪽(max p)** 을 취한다 — 허위 신호 양산(반박석 판정 2a)
방어. 남는 것은 FDR이 가족 단위로 통제.

v2 스캔 가족(2026-07-13 GDELT 구성 타당도 수리): event_archive 지역별 월간 카운트 ·
gdelt_geo_country_daily **발생지** 기준 국가별 월간 시위/물리충돌 카운트.
  구 가족(gdelt_country_* = 행위자 국적 키)은 은퇴 — 상세 근거는 _FAMILIES 주석.
확장(연속지표 z·빈티지 도착 관찰)은 가족 상수에 등록하는 방식으로만 —
등록 = 검정 가족 사전 선언의 갱신이므로 커밋 메시지에 명시.

실행: cd backend && .venv/bin/python services/observation_ledger.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NamedTuple

from scipy.stats import norm, poisson

logger = logging.getLogger(__name__)

_DB = Path(__file__).resolve().parent.parent / "db" / "intel.db"

_MIN_BASE = 30              # intel_analyzer._TREND_MIN_BASE와 동일 근거
_MIN_BASELINE_MONTHS = 3
_MAX_BASELINE_MONTHS = 6
_FDR_Q = 0.05


class _Family(NamedTuple):
    name: str
    metric: str
    sql: str        # (series_key, ym, cnt) 를 반환해야 한다


# 스캔 가족 — 사전 선언(게이트 ③). 여기 없는 계열은 스캔하지 않는다.
#
# ── GDELT 가족 교체 (엔진수리위 2026-07-13, 구성 타당도 수리) ──────────────────
# 구 가족(gdelt_country_*)은 `gdelt_country_daily`(= Actor1CountryCode, **행위자 국적**)를
# 셌다. 그건 "어디서 일어났나"가 아니라 "누가 등장했나"다. 그 결과 원장에
# "모나코의 물리적 충돌 +76%(p=1e-10)"가 관찰로 등재됐다 — 실체는 **포뮬러 1
# 모나코 그랑프리 기사**였다(CAMEO 코더가 "MONACO vs POLE"을 물리적 충돌로 코딩).
#
# 신 가족은 두 자물쇠를 모두 건다:
#   ① 발생지 키 — gdelt_geo_country_daily(ActionGeo_CountryCode → ISO3).
#   ② 행위자 유형 필터 — 물리충돌은 n_material_conflict_pol(국가기구·무장조직 쌍만).
#      실측 2026-06: 모나코 279→2, 룩셈부르크 208→0, 바티칸 76→1,
#      우크라이나 30,999→1,065, 이스라엘 45,002→1,553 (소국 잡음 소거·전쟁국 신호 유지).
#
# ⚠️ 시위는 **원본(n_protest)** 을 쓴다. 필터를 시위에 걸면 신호가 죽는다 —
#    시위 행위자는 통상 민간(CVL)이라 actor1 국가기구 요구에 걸린다
#    (실측: 인도네시아 2026-06 시위 648 → 필터 후 22). 시위의 위치 오염은
#    발생지 키 전환만으로 이미 해소된다. 구성개념별로 다른 자물쇠가 필요하다.
#
# 가족명을 바꾼 이유: 가족명은 identity_key의 일부이자 **계측기의 이름**이다.
# 계측기가 바뀌었는데 이름을 물려주면 옛 관측(모나코)이 새 관측인 척 살아남는다.
# 폐기된 가족의 기존 행은 --retire-family로 observation_ledger_retired에 이관한다
# (삭제 아님 — 결함의 감사 흔적은 보존).
_FAMILIES: list[_Family] = [
    _Family(
        "event_archive_region", "monthly_event_count",
        """
        SELECT region_code AS series_key, substr(timestamp,1,7) AS ym,
               COUNT(*) AS cnt
        FROM event_archive
        WHERE region_code IS NOT NULL AND region_code != ''
        GROUP BY region_code, ym
        """,
    ),
    _Family(
        "gdelt_geo_protest", "monthly_protest_count",
        """
        SELECT country_iso3 AS series_key, substr(day,1,7) AS ym,
               SUM(n_protest) AS cnt
        FROM gdelt_geo_country_daily
        WHERE country_iso3 IS NOT NULL
        GROUP BY country_iso3, ym
        """,
    ),
    _Family(
        "gdelt_geo_material_conflict_pol", "monthly_material_conflict_count",
        """
        SELECT country_iso3 AS series_key, substr(day,1,7) AS ym,
               SUM(n_material_conflict_pol) AS cnt
        FROM gdelt_geo_country_daily
        WHERE country_iso3 IS NOT NULL
        GROUP BY country_iso3, ym
        """,
    ),
]

# 폐기된 가족 — 계측기 결함으로 은퇴. 재스캔 대상이 아니며, 기존 행은 은퇴 테이블로.
_RETIRED_FAMILIES = ("gdelt_country_protest", "gdelt_country_material_conflict")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observation_ledger (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_key      TEXT NOT NULL UNIQUE,   -- 가족|계열|관측월 (게이트 ⑤)
    family            TEXT NOT NULL,
    series_key        TEXT NOT NULL,
    bucket            TEXT NOT NULL,          -- 관측월 YYYY-MM (완결월)
    metric            TEXT NOT NULL,
    value             REAL NOT NULL,
    baseline_mean     REAL NOT NULL,
    baseline_n        INTEGER NOT NULL,
    baseline_window   TEXT NOT NULL,          -- 'YYYY-MM..YYYY-MM'
    delta_pct         REAL NOT NULL,
    direction         TEXT NOT NULL,          -- '▲' | '▼'
    p_value           REAL NOT NULL,
    family_size       INTEGER NOT NULL,       -- 이 런의 전체 후보 수 (다중성 자기 노출)
    artifact_checks   TEXT NOT NULL,          -- 통과 가드 JSON
    first_observed_at TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL,
    runs_confirmed    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS observation_runs (
    run_date    TEXT PRIMARY KEY,             -- YYYY-MM-DD (일 1회 스로틀 마커)
    ran_at      TEXT NOT NULL,
    families    INTEGER NOT NULL,
    candidates  INTEGER NOT NULL,             -- FDR 가족 크기
    passed      INTEGER NOT NULL
);
"""


class _Candidate(NamedTuple):
    family: str
    metric: str
    series_key: str
    bucket: str
    value: float
    baseline_mean: float
    baseline_n: int
    baseline_window: str
    delta_pct: float
    direction: str
    p_value: float
    dispersion: float


def _two_sided_count_p(x: float, baseline: list[float]) -> tuple[float, float]:
    """카운트 관측치의 양측 p — 포아송 꼬리와 경험분산 정규 꼬리 중 보수(max).

    반환: (p, dispersion=var/mean). 과산포 계열에서 포아송 단독은 유의 과장.
    """
    lam = sum(baseline) / len(baseline)
    if lam <= 0:
        return 1.0, 0.0
    # 포아송 양측: 상방은 P(X>=x), 하방은 P(X<=x)
    p_pois = 2.0 * min(poisson.sf(x - 1, lam), poisson.cdf(x, lam))
    p_pois = min(1.0, p_pois)
    n = len(baseline)
    var = sum((b - lam) ** 2 for b in baseline) / (n - 1) if n >= 2 else lam
    dispersion = var / lam if lam > 0 else 0.0
    if n >= 4 and var > lam:
        sd = var ** 0.5
        p_norm = min(1.0, 2.0 * norm.sf(abs(x - lam) / sd))
        return max(p_pois, p_norm), round(dispersion, 2)
    return p_pois, round(dispersion, 2)


def _consecutive(yms: list[str]) -> bool:
    """월 문자열 리스트가 달력상 연속인가 (수집 공백 가드)."""
    idx = [int(y[:4]) * 12 + int(y[5:7]) for y in yms]
    return all(b - a == 1 for a, b in zip(idx, idx[1:]))


def _scan_family(con: sqlite3.Connection, fam: _Family, now_ym: str) -> list[_Candidate]:
    """가족 1개 스캔 — 가드 통과 계열의 최신 완결월을 후보로."""
    series: dict[str, list[tuple[str, float]]] = {}
    try:
        for key, ym, cnt in con.execute(fam.sql):
            if key is None or ym is None:
                continue
            series.setdefault(str(key), []).append((ym, float(cnt or 0)))
    except sqlite3.OperationalError as exc:   # 테이블 부재 등 — 가족 단위 스킵
        logger.warning("[관찰원장] 가족 %s 스캔 불가: %s", fam.name, exc)
        return []

    out: list[_Candidate] = []
    for key, rows in series.items():
        complete = sorted((ym, c) for ym, c in rows if ym < now_ym)
        window = complete[-(_MAX_BASELINE_MONTHS + 1):]
        if len(window) < _MIN_BASELINE_MONTHS + 1:
            continue                                    # 가드: 기준선 월수 부족
        yms = [ym for ym, _ in window]
        if not _consecutive(yms):
            continue                                    # 가드: 수집 공백
        baseline = [c for _, c in window[:-1]]
        obs_ym, obs = window[-1]
        base_mean = sum(baseline) / len(baseline)
        if base_mean < _MIN_BASE:
            continue                                    # 가드: 소분모
        p, dispersion = _two_sided_count_p(obs, baseline)
        out.append(_Candidate(
            family=fam.name, metric=fam.metric, series_key=key, bucket=obs_ym,
            value=obs, baseline_mean=round(base_mean, 1), baseline_n=len(baseline),
            baseline_window=f"{yms[0]}..{yms[-2]}",
            delta_pct=round((obs - base_mean) / base_mean * 100, 1),
            direction="▲" if obs > base_mean else "▼",
            p_value=p, dispersion=dispersion,
        ))
    return out


def _bh_pass(cands: list[_Candidate], q: float = _FDR_Q) -> list[_Candidate]:
    """Benjamini-Hochberg — 가족 전체(모든 스캔 가족 합산)에 적용."""
    if not cands:
        return []
    ranked = sorted(cands, key=lambda c: c.p_value)
    m = len(ranked)
    cutoff = 0
    for i, c in enumerate(ranked, start=1):
        if c.p_value <= q * i / m:
            cutoff = i
    return ranked[:cutoff]


def run_scan(db_path: Path | str = _DB, *, now_ym: str | None = None,
             dry_run: bool = False, force: bool = False) -> dict:
    """전 가족 스캔 → FDR → 원장 기록. 반환: 런 요약 dict.

    now_ym 주입은 테스트용(완결월 판정 기준). dry_run은 기록 없이 후보만.
    force는 일 1회 스로틀 무시(수동 실행용).
    """
    now = datetime.now(timezone.utc)
    now_ym = now_ym or now.strftime("%Y-%m")
    today = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    con = sqlite3.connect(str(db_path))
    try:
        con.executescript(_SCHEMA)
        if not force and not dry_run:
            already = con.execute(
                "SELECT 1 FROM observation_runs WHERE run_date = ?", (today,)
            ).fetchone()
            if already:
                return {"skipped": "already_ran_today", "run_date": today}

        candidates: list[_Candidate] = []
        for fam in _FAMILIES:
            candidates.extend(_scan_family(con, fam, now_ym))
        passed = _bh_pass(candidates)
        family_size = len(candidates)

        inserted = updated = 0
        if not dry_run:
            for c in passed:
                ikey = f"{c.family}|{c.series_key}|{c.bucket}"
                checks = json.dumps({
                    "completed_month_only": True, "consecutive_window": True,
                    "min_base_30": True, "dispersion_var_over_mean": c.dispersion,
                }, ensure_ascii=False)
                con.execute(
                    """
                    INSERT INTO observation_ledger
                      (identity_key, family, series_key, bucket, metric, value,
                       baseline_mean, baseline_n, baseline_window, delta_pct,
                       direction, p_value, family_size, artifact_checks,
                       first_observed_at, last_confirmed_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(identity_key) DO UPDATE SET
                       value = excluded.value,
                       delta_pct = excluded.delta_pct,
                       p_value = excluded.p_value,
                       last_confirmed_at = excluded.last_confirmed_at,
                       runs_confirmed = runs_confirmed + 1
                    """,
                    (ikey, c.family, c.series_key, c.bucket, c.metric, c.value,
                     c.baseline_mean, c.baseline_n, c.baseline_window, c.delta_pct,
                     c.direction, c.p_value, family_size, checks, ts, ts),
                )
                rc = con.execute(
                    "SELECT runs_confirmed FROM observation_ledger WHERE identity_key=?",
                    (ikey,),
                ).fetchone()[0]
                if rc == 1:
                    inserted += 1
                else:
                    updated += 1
            con.execute(
                "INSERT OR REPLACE INTO observation_runs VALUES (?,?,?,?,?)",
                (today, ts, len(_FAMILIES), family_size, len(passed)),
            )
            con.commit()

        summary = {
            "run_date": today, "families": len(_FAMILIES),
            "candidates": family_size, "passed": len(passed),
            "inserted": inserted, "updated": updated,
            "observations": [
                f"{c.family}/{c.series_key} {c.bucket}: {c.value:.0f} "
                f"(기준선 {c.baseline_mean:.0f}×{c.baseline_n}개월, "
                f"{c.delta_pct:+.1f}% {c.direction}, p={c.p_value:.4g})"
                for c in passed[:20]
            ],
        }
        return summary
    finally:
        con.close()


def retire_family(family: str, reason: str, db_path: Path | str = _DB) -> dict:
    """폐기된 계측기의 관측 행을 observation_ledger_retired로 이관한다 (삭제 아님).

    왜 이관인가: 원장의 한 행은 "세계에 대한 주장"이고, 그 주장은 특정 계측기가
    만들었다. 계측기가 무효로 판명되면 그 주장은 **살아 있는 관찰로 남아 있으면
    안 된다**(모나코 F1 기사를 '물리적 충돌 +76%'로 계속 주장하게 된다).
    그렇다고 지우면 결함의 감사 흔적이 사라진다 — 그래서 은퇴 테이블로 옮긴다.

    run_scan은 이 테이블을 만들지도 읽지도 않는다 (게이트 ⑥ report-only 불변).
    """
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS observation_ledger_retired (
                identity_key TEXT, family TEXT, series_key TEXT, bucket TEXT,
                metric TEXT, value REAL, baseline_mean REAL, delta_pct REAL,
                p_value REAL, retired_at TEXT NOT NULL, retired_reason TEXT NOT NULL
            )
        """)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = con.execute(
            "SELECT identity_key, family, series_key, bucket, metric, value, "
            "baseline_mean, delta_pct, p_value FROM observation_ledger WHERE family = ?",
            (family,),
        ).fetchall()
        con.executemany(
            "INSERT INTO observation_ledger_retired VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(*r, ts, reason) for r in rows],
        )
        con.execute("DELETE FROM observation_ledger WHERE family = ?", (family,))
        con.commit()
        return {"family": family, "retired": len(rows),
                "series": [f"{r[2]} {r[3]} ({r[7]:+.1f}%)" for r in rows]}
    finally:
        con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="P1 report-only 변화 관찰 원장")
    ap.add_argument("--db", default=str(_DB))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="일 1회 스로틀 무시")
    ap.add_argument("--retire-legacy-gdelt", action="store_true",
                    help="행위자 국적 키 GDELT 가족(_RETIRED_FAMILIES)의 행을 은퇴 테이블로 이관")
    args = ap.parse_args()

    if args.retire_legacy_gdelt:
        for fam in _RETIRED_FAMILIES:
            r = retire_family(
                fam,
                "계측기 결함: Actor1CountryCode(행위자 국적)를 발생지로 오독 + CAMEO "
                "스포츠 오탐 미필터. 엔진수리위 2026-07-13. 후속 가족: gdelt_geo_*",
                args.db,
            )
            print(json.dumps(r, ensure_ascii=False))
        raise SystemExit(0)

    s = run_scan(args.db, dry_run=args.dry_run, force=args.force)
    print(json.dumps({k: v for k, v in s.items() if k != "observations"},
                     ensure_ascii=False, indent=1))
    for line in s.get("observations", []):
        print(" ", line)
