"""
stats.py — 상단 바 집계 통계 API.

GET /api/stats/tension  — 섹터별 긴장도 (이벤트 유형·최근성 가중 + 드라이버 top 3)
GET /api/stats/markets  — WTI·금·반도체·원달러 시장 지표 (5분 캐시)

긴장도 계산 방식 (v3.27.0):
  1. ACLED (event_archive, 30일): 이벤트 유형 × 최근성 가중 severity 평균
  2. GDELT (events hot table, 72h, confidence≥0.8): 실시간 신호
  3. 혼합: ACLED × 0.65 + GDELT × 0.35 (실시간 신호 반영)
  4. 빈도 보정: log(이벤트 수) 기반 최대 ×1.3
  5. 0-100 정규화

이벤트 유형 가중치 (ACLED event_type):
  Battles / Explosions·Remote violence → ×1.5  (직접 군사 충돌)
  Violence against civilians            → ×1.3  (전쟁범죄·강도 상승)
  Riots                                 → ×0.7  (사회 불안)
  Protests                              → ×0.4  (정치 행위, 시장 영향 미미)
  Strategic developments                → ×0.3  (선언·협정)
  GDELT (event_type 없음)               → ×1.0  (실시간 신호 중립)

최근성 가중치:
  0-3일 → ×1.8  4-7일 → ×1.4  8-14일 → ×1.1  15-30일 → ×1.0
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf
from fastapi import APIRouter

router = APIRouter(prefix="/api/stats", tags=["stats"])
logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# ── 캐시 ──────────────────────────────────────────────────────────────────────
_tension_cache: dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}
_market_cache:  dict = {"data": None, "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc)}

_TENSION_TTL = timedelta(minutes=10)
_MARKET_TTL  = timedelta(minutes=5)

# ── 섹터 정의 ─────────────────────────────────────────────────────────────────
_SECTORS = ["중동", "인태", "유럽", "아프리카"]

_PIZZA_WEIGHTS: dict[str, float] = {
    "중동":    0.4,
    "인태":    0.3,
    "유럽":    0.2,
    "아프리카": 0.1,
}

_REGION_SECTOR: dict[str, str] = {
    "bab_el_mandeb":    "중동",
    "hormuz":           "중동",
    "middle_east":      "중동",
    "suez":             "중동",
    "taiwan_strait":    "인태",
    "south_china_sea":  "인태",
    "east_china_sea":   "인태",
    "malacca":          "인태",
    "korean_peninsula": "인태",
    "north_korea":      "인태",
    "ukraine":          "유럽",
    "eastern_europe":   "유럽",
}

_COUNTRY_SECTOR: dict[str, str] = {
    # 중동
    "iran": "중동", "iraq": "중동", "israel": "중동", "lebanon": "중동",
    "syria": "중동", "saudi arabia": "중동", "yemen": "중동", "jordan": "중동",
    "egypt": "중동", "turkey": "중동", "palestine": "중동", "oman": "중동",
    "qatar": "중동", "bahrain": "중동", "kuwait": "중동",
    # 인태
    "myanmar": "인태", "philippines": "인태", "vietnam": "인태", "taiwan": "인태",
    "south korea": "인태", "north korea": "인태", "japan": "인태", "china": "인태",
    "indonesia": "인태", "malaysia": "인태", "thailand": "인태",
    "cambodia": "인태", "india": "인태", "bangladesh": "인태", "pakistan": "인태",
    # 유럽
    "ukraine": "유럽", "russia": "유럽", "belarus": "유럽", "moldova": "유럽",
    "georgia": "유럽", "armenia": "유럽", "azerbaijan": "유럽",
    "serbia": "유럽", "kosovo": "유럽", "poland": "유럽",
    # 아프리카
    "nigeria": "아프리카", "ethiopia": "아프리카", "somalia": "아프리카",
    "democratic republic of congo": "아프리카", "sudan": "아프리카",
    "mali": "아프리카", "burkina faso": "아프리카", "mozambique": "아프리카",
    "cameroon": "아프리카", "central african republic": "아프리카",
    "south sudan": "아프리카", "libya": "아프리카", "chad": "아프리카",
    "niger": "아프리카", "kenya": "아프리카", "tanzania": "아프리카",
    "zimbabwe": "아프리카", "congo": "아프리카",
}

# 이벤트 유형 가중치 (ACLED event_type 기준)
_EVENT_TYPE_WEIGHT: dict[str, float] = {
    "battles":                    1.5,
    "explosions/remote violence": 1.5,
    "violence against civilians": 1.3,
    "riots":                      0.7,
    "protests":                   0.4,
    "strategic developments":     0.3,
}

# 이벤트 유형 → 한국어 레이블 (드라이버 표시용)
_EVENT_TYPE_KO: dict[str, str] = {
    "battles":                    "전투",
    "explosions/remote violence": "폭발·원격타격",
    "violence against civilians": "민간인 공격",
    "riots":                      "폭동",
    "protests":                   "시위",
    "strategic developments":     "전략적 동향",
}


def _recency_weight(days_ago: float) -> float:
    if days_ago <= 3:   return 1.8
    if days_ago <= 7:   return 1.4
    if days_ago <= 14:  return 1.1
    return 1.0


def _event_type_weight(event_type: str) -> float:
    return _EVENT_TYPE_WEIGHT.get(event_type.lower().strip(), 1.0)


def _region_to_sector(region_code: str, country: str) -> str | None:
    for k, sec in _REGION_SECTOR.items():
        if k in (region_code or "").lower():
            return sec
    for k, sec in _COUNTRY_SECTOR.items():
        if k in (country or "").lower():
            return sec
    return None


def _severity_level(score: float) -> str:
    if score >= 75: return "critical"
    if score >= 55: return "high"
    if score >= 35: return "medium"
    return "low"


def _shorten_actor(name: str) -> str:
    """ACLED/GDELT actor 명칭 표시용 축약."""
    if not name or len(name) < 2:
        return ""
    # "Military Forces of X (year-year)" → "X 군"
    m = re.search(r"Military Forces of ([^(,]+)", name)
    if m:
        return m.group(1).strip()[:20] + " 군"
    m = re.search(r"Police Forces of ([^(,]+)", name)
    if m:
        return m.group(1).strip()[:20] + " 경찰"
    # 괄호 제거 + 20자 제한
    clean = re.sub(r"\([^)]*\)", "", name).strip()
    return clean[:25] + ("…" if len(clean) > 25 else "")


def _make_driver(row_dict: dict, days_ago: float, weighted_sev: float) -> dict:
    """드라이버 표시용 dict 생성 (ACLED/GDELT 통일 형식)."""
    payload = row_dict["payload"]
    data_src = payload.get("data_source", "ACLED")
    event_type = payload.get("event_type", "")
    event_type_ko = _EVENT_TYPE_KO.get(event_type.lower().strip(), "")

    # GDELT 이벤트: title에서 "[GDELT] 위치: " 접두사 제거 후 표시
    if data_src == "GDELT":
        raw_title = (row_dict.get("title") or "")
        # "[GDELT] 도시, 지역, 국가: ..." → 콜론 이후 추출
        clean = re.sub(r"^\[GDELT\]\s*", "", raw_title)
        if ": " in clean:
            location, rest = clean.split(": ", 1)
            country_hint = location.rsplit(",", 1)[-1].strip()
            display = f"{rest} [{country_hint}]"
        else:
            display = clean
        return {
            "display":        display[:60],
            "event_type_ko":  "GDELT 실시간",
            "raw_sev":        row_dict["severity"],
            "weighted_sev":   round(weighted_sev, 1),
            "days_ago":       round(days_ago, 1),
            "data_source":    "GDELT",
        }
    else:
        a1 = _shorten_actor(payload.get("actor1", ""))
        a2 = _shorten_actor(payload.get("actor2", ""))
        display = f"{a1} vs {a2}" if a2 else a1
        if not display or len(display) < 3:
            display = (row_dict.get("title") or "")[:50]
        return {
            "display":        display[:50],
            "event_type_ko":  event_type_ko or event_type[:10],
            "raw_sev":        row_dict["severity"],
            "weighted_sev":   round(weighted_sev, 1),
            "days_ago":       round(days_ago, 1),
            "data_source":    "ACLED",
            "fatalities":     payload.get("fatalities", 0),
        }


def _calc_sector_score(events: list[dict]) -> float:
    """가중 severity → 0-100 섹터 점수."""
    if not events:
        return 0.0
    total_w = sum(e["weighted_sev"] for e in events)
    count = len(events)
    w_mean = total_w / count
    # 이벤트 많을수록 최대 ×1.3 보정
    freq_factor = min(math.log1p(count) / math.log1p(15), 1.3)
    raw = w_mean * freq_factor
    # sev(≤100) × type_weight(≤1.5) × recency(≤1.8) = max 270 → 나누기 2.7
    return min(raw / 2.7, 100.0)


def _calc_tensions_from_db(now: datetime) -> dict[str, dict]:
    """
    event_archive (ACLED 30일) + events hot table (GDELT 72h) 에서
    섹터별 가중 긴장도 점수와 드라이버 top 3를 계산한다.

    ACLED과 GDELT를 별도 쿼리로 분리 → 중복 집계 방지.
    region_code가 없는 이벤트는 payload.country로 섹터 매핑.
    """
    # ACLED: 400일 (1년치 bulk ingest 전체, 구조적 베이스라인)
    acled_cutoff = (now - timedelta(days=400)).isoformat()
    # GDELT: 72h (실시간 신호)
    gdelt_cutoff = (now - timedelta(hours=72)).isoformat()
    # 드라이버 표시용 ACLED: 최근 90일 이내 (더 관련성 높은 최근 사건)
    driver_cutoff = (now - timedelta(days=90)).isoformat()

    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row

    # 1) ACLED: event_archive, 400일 이내 (점수 계산용)
    acled_rows = con.execute(
        """
        SELECT timestamp, region_code, severity, title, payload
        FROM event_archive
        WHERE source_type = 'conflict'
          AND json_extract(payload, '$.data_source') = 'ACLED'
          AND timestamp >= ?
        """,
        (acled_cutoff,),
    ).fetchall()

    # 2) GDELT: events hot table, 72h 이내, confidence≥0.8
    gdelt_rows = con.execute(
        """
        SELECT timestamp, region_code, severity, title, payload
        FROM events
        WHERE source_type = 'conflict'
          AND json_extract(payload, '$.data_source') = 'GDELT'
          AND confidence_score >= 0.8
          AND created_at >= ?
        """,
        (gdelt_cutoff,),
    ).fetchall()
    con.close()

    # 섹터별 이벤트 수집
    acled_events: dict[str, list[dict]] = {s: [] for s in _SECTORS}
    gdelt_events: dict[str, list[dict]] = {s: [] for s in _SECTORS}

    def _process_row(row, target_dict: dict[str, list]):
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}

        region_code = row["region_code"] or ""
        country = payload.get("country", "")
        sector = _region_to_sector(region_code, country)
        if sector is None:
            return

        ts_str = row["timestamp"] or ""
        try:
            ts = datetime.fromisoformat(ts_str)
            ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = now
        days_ago = max(0.0, (now - ts).total_seconds() / 86400)

        event_type = payload.get("event_type", "")
        tw = _event_type_weight(event_type)
        rw = _recency_weight(days_ago)
        sev = float(row["severity"] or 0)
        weighted = sev * tw * rw

        row_dict = {
            "timestamp": ts_str,
            "region_code": region_code,
            "severity": sev,
            "title": row["title"],
            "payload": payload,
        }

        target_dict[sector].append({
            "weighted_sev": weighted,
            "days_ago":     days_ago,
            "is_recent":    days_ago <= 90,    # 드라이버 우선 선정 기준
            "driver":       _make_driver(row_dict, days_ago, weighted),
        })

    for row in acled_rows:
        _process_row(row, acled_events)
    for row in gdelt_rows:
        _process_row(row, gdelt_events)

    # 섹터별 점수 계산 + 드라이버 top 3 추출
    result: dict[str, dict] = {}
    for sector in _SECTORS:
        ae = acled_events[sector]
        ge = gdelt_events[sector]

        acled_score = _calc_sector_score(ae)
        gdelt_score = _calc_sector_score(ge)

        if ae and ge:
            score = acled_score * 0.65 + gdelt_score * 0.35
        elif ae:
            score = acled_score
        elif ge:
            score = gdelt_score
        else:
            score = 0.0

        # 드라이버 선정 우선순위:
        # 1) GDELT 72h (실시간 신호) → 가중 severity 내림차순
        # 2) ACLED 90일 이내 (최근 베이스라인) → 가중 severity 내림차순
        # 3) ACLED 전체 중 최신 순 (폴백)
        gdelt_sorted = sorted(ge, key=lambda x: x["weighted_sev"], reverse=True)
        acled_recent = sorted([e for e in ae if e["is_recent"]],
                               key=lambda x: x["weighted_sev"], reverse=True)
        acled_fallback = sorted(ae, key=lambda x: x["days_ago"])[:3]

        candidates = gdelt_sorted + acled_recent + acled_fallback
        # 중복 제거 (display 기준)
        seen: set[str] = set()
        drivers: list[dict] = []
        for e in candidates:
            key = e["driver"]["display"]
            if key not in seen:
                seen.add(key)
                drivers.append(e["driver"])
            if len(drivers) >= 3:
                break

        result[sector] = {
            "score":       round(score, 1),
            "count":       len(ae) + len(ge),
            "acled_count": len(ae),
            "gdelt_count": len(ge),
            "drivers":     drivers,
        }

    return result


@router.get("/tension")
async def get_tension():
    """섹터별 긴장도 — 이벤트 유형·최근성 가중 + 드라이버 top 3.

    응답에 pizza_weight 포함 → 프론트엔드가 가중 평균으로 피자지수 산출.

    이론 연결:
      단순 severity 평균의 문제: 저강도 시위(sev=15)가 다수 발생 시
      고강도 전투(sev=90)를 희석시킨다.
      이벤트 유형 가중치(전투 ×1.5, 시위 ×0.4)로 '군사 충격'을 반영하고
      최근성 가중치(0-3일 ×1.8)로 '현재 진행 상황'을 강조한다.
    """
    now = datetime.now(timezone.utc)
    if _tension_cache["data"] is not None and now < _tension_cache["expires_at"]:
        return _tension_cache["data"]

    tensions = await asyncio.to_thread(_calc_tensions_from_db, now)

    result = []
    for sector in _SECTORS:
        t = tensions.get(sector, {"score": 0.0, "count": 0,
                                   "acled_count": 0, "gdelt_count": 0, "drivers": []})
        score = t["score"]
        result.append({
            "sector":       sector,
            "avg_severity": score,
            "event_count":  t["count"],
            "acled_count":  t["acled_count"],
            "gdelt_count":  t["gdelt_count"],
            "level":        _severity_level(score),
            "pizza_weight": _PIZZA_WEIGHTS[sector],
            "drivers":      t["drivers"],
        })

    _tension_cache["data"] = result
    _tension_cache["expires_at"] = now + _TENSION_TTL
    return result


# ── 시장 지표 ────────────────────────────────────────────────────────────────
_MARKET_TICKERS = [
    {"ticker": "CL=F",  "name": "WTI",    "unit": "$",  "emoji": "⛽"},
    {"ticker": "GLD",   "name": "금",      "unit": "$",  "emoji": "🥇"},
    {"ticker": "SOXX",  "name": "반도체",  "unit": "$",  "emoji": "💾"},
    {"ticker": "KRW=X", "name": "원/달러", "unit": "₩",  "emoji": "💴"},
]


def _fetch_quote_sync(ticker: str) -> dict | None:
    try:
        fi = yf.Ticker(ticker).fast_info
        price = float(fi.last_price)
        prev  = float(fi.previous_close)
        if prev == 0:
            return None
        change_pct = (price - prev) / prev * 100
        return {
            "price":      round(price, 2),
            "change_pct": round(change_pct, 2),
            "direction":  "up" if change_pct >= 0 else "down",
        }
    except Exception as e:
        logger.warning("[markets] %s 조회 실패: %s", ticker, e)
        return None


@router.get("/markets")
async def get_markets():
    """WTI·금·반도체·원달러 시장 지표 (4개 티커 병렬 조회, 5분 캐시)."""
    now = datetime.now(timezone.utc)
    if _market_cache["data"] is not None and now < _market_cache["expires_at"]:
        return _market_cache["data"]

    tasks = [asyncio.to_thread(_fetch_quote_sync, m["ticker"]) for m in _MARKET_TICKERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    items = []
    for meta, result in zip(_MARKET_TICKERS, results):
        if isinstance(result, Exception) or result is None:
            items.append({**meta, "price": None, "change_pct": None, "direction": None})
        else:
            items.append({**meta, **result})

    _market_cache["data"] = items
    _market_cache["expires_at"] = now + _MARKET_TTL
    return items
