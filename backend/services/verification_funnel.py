"""
verification_funnel.py — 3단계 지정학 팩트체커 (Verification Funnel)

CLAUDE.md §16 기준:
  Stage 1: ACLED 베이스라인 대조                → +0.1
  Stage 2: RSS 4대 매체 교차검증 (≥2매체)       → +0.2
  Stage 3: 물리 센서 결합 (반경 50km, 12h 이내)  → +0.1
  초기값 0.5 → 최대 0.9, 승격 임계값 0.8

이론적 근거:
  ACH(Analysis of Competing Hypotheses) 방법론 — 다중 독립 소스의 교차 확인이
  인텔리전스 신뢰도의 핵심 원칙 (Sherman Kent, CIA 정보분석 교범).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models.event import Event

logger = logging.getLogger(__name__)

# ── 상수 ─────────────────────────────────────────────────────────────────────
_DB_PATH = Path(__file__).parent.parent / "db" / "intel.db"

_SENSOR_RADIUS_KM   = 50.0
_SENSOR_WINDOW_H    = 12
_PROMOTE_THRESHOLD  = 0.8

# broad region → event_archive에 실제 저장된 region_code 목록
# (ACLED 커넥터가 국가 단위로 매핑하므로 별칭 확장 필요)
_REGION_ALIASES: dict[str, list[str]] = {
    "eastern_europe": ["ukraine", "eastern_europe", "belarus", "moldova"],
    "middle_east":    ["middle_east", "hormuz", "levant", "iraq", "syria"],
    "indo_pacific":   ["taiwan_strait", "south_china_sea", "east_china_sea",
                       "malacca", "korean_peninsula", "indo_pacific"],
    "africa":         ["bab_el_mandeb", "suez", "africa", "sahel"],
}

# Stage 보너스 가중치 (CLAUDE.md §16)
_SCORE_BASELINE     = 0.5
_BONUS_STAGE1       = 0.1
_BONUS_STAGE2       = 0.2
_BONUS_STAGE3       = 0.1


async def enrich_with_funnel(events: list[Event]) -> list[Event]:
    """3단계 팩트체커를 통해 confidence_score와 is_staging을 갱신한다.

    RSS 피드는 한 번만 fetch해 모든 이벤트에 재사용 (네트워크 비용 최소화).
    DB 연결도 단일 컨텍스트에서 열고 모든 이벤트에 재사용.

    gdelt_pipeline.py의 cross_validate() 호출을 이 함수로 교체한다.
    """
    if not events:
        return events

    # RSS 기사 배치 fetch (Stage 2용 — 실패해도 이후 Stage 1·3 계속 진행)
    from connectors.news_cross_validator import fetch_rss_articles, check_rss_match
    try:
        articles = await fetch_rss_articles()
    except Exception as exc:
        logger.warning("[Funnel] RSS fetch 실패, Stage 2 skip: %s", exc)
        articles = []

    # DB 연결 준비 (Stage 1·3용 — 테이블 없으면 각 stage가 0.0 반환)
    con = _open_db()

    enriched: list[Event] = []
    for evt in events:
        score = _SCORE_BASELINE

        # Stage 1: ACLED 베이스라인 — region_code로 과거 분쟁 이력 조회
        s1 = _stage1_baseline(evt.region_code, con)
        score += s1

        # Stage 2: RSS 교차검증 — 이미 fetch된 articles 재사용
        s2 = _BONUS_STAGE2 if (articles and check_rss_match(evt, articles)) else 0.0
        score += s2

        # Stage 3: 물리 센서 결합 — FIRMS·AIS·ADS-B 반경 50km, 12h 이내
        lat, lon = evt.location
        s3 = _stage3_sensor(lat, lon, evt.timestamp, con)
        score += s3

        final = min(round(score, 2), 1.0)
        is_staging = final < _PROMOTE_THRESHOLD

        logger.debug(
            "[Funnel] %s  s1=%.1f s2=%.1f s3=%.1f → %.2f %s",
            evt.source_id, s1, s2, s3, final,
            "⚠staging" if is_staging else "✓promoted",
        )

        enriched.append(evt.model_copy(update={
            "confidence_score": final,
            "is_staging": is_staging,
        }))

    if con:
        con.close()

    promoted  = sum(1 for e in enriched if not e.is_staging)
    staging   = len(enriched) - promoted
    logger.info(
        "[Funnel] 완료 — 승격=%d, 버퍼=%d / 합계=%d",
        promoted, staging, len(enriched),
    )
    return enriched


# ── Stage 구현체 ──────────────────────────────────────────────────────────────

def _stage1_baseline(region_code: str | None, con: sqlite3.Connection | None) -> float:
    """ACLED 베이스라인: event_archive의 acled_baseline 이력 존재 시 +0.1.

    archive_reason='acled_baseline'만 확인 (GDELT 고가치 자산과 분리).
    - 시간 제한 없음: 베이스라인은 "이 지역에 분쟁 역사가 있는가?"를 묻는 것이므로
      최근 N개월로 좁히면 오래된 분쟁 지역이 누락됨.
    - 광역 region alias 확장: eastern_europe → [ukraine, ...] 등 커넥터 저장값과 매핑.
    - 테이블이 없으면(archive_manager.py 미실행 상태) 0.0 반환.
    """
    if not region_code or con is None:
        return 0.0

    # 검색 대상 region_code 목록 (자신 + alias 확장)
    targets = _REGION_ALIASES.get(region_code, [region_code])
    if region_code not in targets:
        targets = [region_code] + targets

    placeholders = ",".join("?" * len(targets))
    try:
        row = con.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM event_archive
             WHERE region_code IN ({placeholders})
               AND archive_reason = 'acled_baseline'
            """,
            targets,
        ).fetchone()
        return _BONUS_STAGE1 if row and row["cnt"] > 0 else 0.0
    except sqlite3.OperationalError:
        # event_archive 테이블 미생성 — archive_manager.py 실행 전 상태
        return 0.0
    except Exception as exc:
        logger.warning("[Funnel S1] 조회 실패: %s", exc)
        return 0.0


def _stage3_sensor(
    lat: float,
    lon: float,
    timestamp: datetime,
    con: sqlite3.Connection | None,
) -> float:
    """물리 센서 결합: 반경 50km·12h 이내 FIRMS·AIS·ADS-B 이상 징후 시 +0.1.

    sensor_snapshots 테이블이 없으면(archive_manager.py 미실행 상태) 0.0 반환.
    위경도 근사 필터: 1도 ≈ 111km → 0.45도 이내 ≈ 50km.
    """
    if lat == 0.0 and lon == 0.0 or con is None:
        return 0.0

    deg = _SENSOR_RADIUS_KM / 111.0
    window_start = (timestamp - timedelta(hours=_SENSOR_WINDOW_H)).isoformat()

    try:
        row = con.execute(
            """
            SELECT COUNT(*) AS cnt FROM sensor_snapshots
             WHERE source_type IN ('fire', 'naval', 'military_flight')
               AND timestamp >= ?
               AND ABS(lat - ?) < ?
               AND ABS(lon - ?) < ?
            """,
            (window_start, lat, deg, lon, deg),
        ).fetchone()
        return _BONUS_STAGE3 if row and row["cnt"] > 0 else 0.0
    except sqlite3.OperationalError:
        # sensor_snapshots 테이블 미생성 — archive_manager.py 실행 전 상태
        return 0.0
    except Exception as exc:
        logger.warning("[Funnel S3] 조회 실패: %s", exc)
        return 0.0


def _open_db() -> sqlite3.Connection | None:
    """intel.db에 연결한다. DB 파일 없으면 None 반환 (Stage 1·3 graceful skip)."""
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(_DB_PATH)
        con.row_factory = sqlite3.Row
        return con
    except Exception as exc:
        logger.warning("[Funnel] DB 연결 실패: %s", exc)
        return None
