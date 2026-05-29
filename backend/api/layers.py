"""
layers.py — 지도 레이어 GeoJSON 서빙 라우터
각 레이어(군사기지, 파이프라인 등)를 GeoJSON으로 반환한다.
CLAUDE.md 아키텍처: backend/api/layers.py
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from connectors.acled import AcledConnector
from connectors.aisstream import AISStreamConnector
from connectors.nasa_firms import NasaFirmsConnector
from connectors.opensky import OpenSkyConnector
from models.event import Event
from services.gdelt_pipeline import run_gdelt_pipeline, to_geojson as gdelt_to_geojson
from connectors.sanctions_connector import load_sanctions
from services.importance_scorer import cluster_events, score_events, score_gdelt_events

router = APIRouter(prefix="/api/layers", tags=["layers"])

_INTEL_DB = Path(__file__).resolve().parents[1] / "db" / "intel.db"

# ACLED 응답 1시간 캐시 — 분쟁 데이터는 실시간 불필요 (CLAUDE.md 성능 원칙)
_CONFLICT_TTL = timedelta(hours=1)


def _load_events_from_db() -> list[Event] | None:
    """intel.db events 테이블에서 ACLED 이벤트를 로드한다.

    DB에 최근 30일 데이터가 충분히 있으면 live API 호출을 생략한다.
    ACLED 학술 계정은 1년 지연 데이터를 제공하므로 DB가 primary source 역할.
    반환값이 None이면 호출자가 live API로 fallback한다.
    """
    if not _INTEL_DB.exists():
        return None
    try:
        _KEY_REGIONS = (
            "taiwan_strait", "south_china_sea", "east_china_sea",
            "korean_peninsula", "north_korea",
            "hormuz", "bab_el_mandeb", "suez", "persian_gulf",
            "eastern_europe", "ukraine",
            "middle_east", "malacca",
        )
        placeholders = ",".join("?" * len(_KEY_REGIONS))
        _cols = ("id, timestamp, source_type, region_code, severity, "
                 "confidence_score, importance_score, is_staging, "
                 "title, description, lat, lon, payload, theory_tags")

        with sqlite3.connect(_INTEL_DB) as con:
            con.row_factory = sqlite3.Row

            # ① 5대 섹터 핵심 지역 이벤트 전체 (최근 12개월)
            key_rows = con.execute(
                f"""
                SELECT {_cols}
                FROM events
                WHERE source_type = 'conflict'
                  AND confidence_score >= 1.0
                  AND region_code IN ({placeholders})
                ORDER BY timestamp DESC
                LIMIT 8000
                """,
                _KEY_REGIONS,
            ).fetchall()

            # ② 최신 일반 이벤트 (지역 무관, 지도 배경 밀도용)
            general_rows = con.execute(
                f"""
                SELECT {_cols}
                FROM events
                WHERE source_type = 'conflict'
                  AND confidence_score >= 1.0
                ORDER BY timestamp DESC
                LIMIT 3000
                """
            ).fetchall()

        # 중복 제거 — key_rows 우선, general_rows 보충
        seen: set[str] = set()
        rows = []
        for r in (*key_rows, *general_rows):
            if r["id"] not in seen:
                seen.add(r["id"])
                rows.append(r)

        if len(rows) < 100:
            return None  # 데이터 부족 → live API fallback

        events: list[Event] = []
        for r in rows:
            try:
                from models.event import Event, IntelligenceMetadata
                payload = json.loads(r["payload"] or "{}")
                theory_tags = json.loads(r["theory_tags"] or "[]")
                lat = r["lat"] or 0.0
                lon = r["lon"] or 0.0
                evt = Event(
                    id=r["id"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    source_type=r["source_type"],
                    source_id=payload.get("source_id", r["id"]),
                    location=(lat, lon),
                    region_code=r["region_code"],
                    severity=r["severity"] or 0,
                    title=r["title"] or "",
                    description=r["description"] or "",
                    payload=payload,
                    theory_tags=theory_tags,
                    confidence_score=r["confidence_score"] or 1.0,
                    importance_score=r["importance_score"] or 0.0,
                )
                events.append(evt)
            except Exception:
                continue
        return events if events else None
    except Exception:
        return None
_conflict_cache: dict = {
    "geojson":     None,
    "expires_at":  datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# FIRMS NRT는 위성 주기마다 갱신(~3시간). 10분 캐시로 불필요한 중복 API 호출 방지.
_FIRE_TTL = timedelta(minutes=10)
_fire_cache: dict = {
    "geojson":    None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# AIS는 45초 수집 + 처리. 5분 캐시 — 초크포인트 선박 밀집도는 수분 단위로 충분.
_NAVAL_TTL = timedelta(minutes=5)
_naval_cache: dict = {
    "geojson":    None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# ADS-B 군용기: OpenSky 무료 크레딧 절약 + 항공기 위치는 수분 이내 이동이 미미.
_ADSB_TTL = timedelta(minutes=5)
_adsb_cache: dict = {
    "geojson":    None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# GDELT: 15분 주기 갱신 소스에 맞춰 15분 캐시
_GDELT_TTL = timedelta(minutes=15)
_gdelt_cache: dict = {
    "geojson":    None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# 제재 데이터: 정적 YAML 기반 — 24시간 캐시 (UN SC·OFAC 결의는 매일 바뀌지 않음)
_SANCTIONS_TTL = timedelta(hours=24)
_sanctions_cache: dict = {
    "geojson":    None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# 프로젝트 루트 기준으로 data/ 폴더 경로 계산
# 이 파일: backend/api/layers.py → 루트: 두 단계 위
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load_geojson(filename: str) -> dict:
    """
    data/ 폴더에서 GeoJSON 파일을 읽어 dict로 반환한다.
    파일이 없으면 404, JSON 파싱 실패 시 500을 반환한다.
    """
    path = DATA_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} 파일을 찾을 수 없습니다.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"GeoJSON 파싱 오류: {e}") from e


@router.get("/conflict-events")
async def get_conflict_events():
    """
    인도-태평양 분쟁 이벤트 GeoJSON 반환.
    1시간 캐시 적용 — 두 번째 요청부터 즉시 반환.

    데이터 소스 우선순위:
      1) intel.db events 테이블 (ACLED 학술 계정 = 1년 지연, DB가 primary)
      2) live ACLED API fallback (DB 데이터 부족 시)
    연관 이론: Gray Zone Strategy, Hybrid Warfare (CLAUDE.md 섹터 4·5)
    """
    now = datetime.now(timezone.utc)
    if _conflict_cache["geojson"] is not None and now < _conflict_cache["expires_at"]:
        return _conflict_cache["geojson"]

    # 1) DB 우선 로드
    events = _load_events_from_db()
    _source = "db"

    # 2) DB 미충족 시 live API fallback
    if events is None:
        _source = "api"
        connector = AcledConnector()
        try:
            events = await connector.fetch()
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ACLED API 연결 실패: {e}") from e

    import logging as _log
    _log.getLogger(__name__).info("[conflict-events] source=%s events=%d", _source, len(events))

    # GDELT 캐시에서 지역 코드 추출 — gdelt_confirmed 점수 계산용
    gdelt_regions: frozenset[str] = frozenset()
    if _gdelt_cache["geojson"] is not None:
        gdelt_regions = frozenset(
            f["properties"].get("region_code", "")
            for f in _gdelt_cache["geojson"].get("features", [])
            if f["properties"].get("region_code")
        )

    events = cluster_events(events)
    events = score_events(events, gdelt_regions)
    result = _events_to_geojson(events)
    _conflict_cache["geojson"] = result
    _conflict_cache["expires_at"] = now + _CONFLICT_TTL
    return result


def _events_to_geojson(events: list[Event]) -> dict:
    """Event 리스트 → Leaflet이 바로 소비할 GeoJSON FeatureCollection."""
    features = []
    for e in events:
        lat, lon = e.location
        if lat == 0.0 and lon == 0.0:
            continue  # 좌표 없는 이벤트 제외

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                # GeoJSON 표준: [경도, 위도] 순서 (Leaflet과 반대이므로 주의)
                "coordinates": [lon, lat],
            },
            "properties": {
                "id":               e.id,
                "timestamp":        e.timestamp.isoformat(),
                "source_type":      e.source_type,
                "source_id":        e.source_id,
                "region_code":      e.region_code,      # tension / news 집계용
                "severity":         e.severity,
                "title":            e.title,
                "description":      e.description,
                "theory_tags":      e.theory_tags,
                "confidence_score": e.confidence_score, # news 필터용 (ACLED=1.0)
                "importance_score": e.importance_score,
                "cluster_count":    e.cluster_count,
                **e.payload,
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count":     len(features),
            "source":    "ACLED",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/fire")
async def get_fire_hotspots():
    """
    NASA FIRMS VIIRS S-NPP NRT 위성 화재/열점 GeoJSON 반환.
    분쟁 지역 9개 bbox 병렬 조회, 10분 캐시.
    연관 이론: Resource Weaponization (Hirschman), Food Security, Gray Zone Strategy
    """
    now = datetime.now(timezone.utc)
    if _fire_cache["geojson"] is not None and now < _fire_cache["expires_at"]:
        return _fire_cache["geojson"]

    try:
        connector = NasaFirmsConnector()
    except ValueError as e:
        # FIRMS_MAP_KEY 미설정 — 빈 레이어 반환(키 없어도 앱 전체가 죽으면 안 됨)
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        events = await connector.fetch()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NASA FIRMS API 연결 실패: {e}") from e

    result = _fire_events_to_geojson(events)
    _fire_cache["geojson"] = result
    _fire_cache["expires_at"] = now + _FIRE_TTL
    return result


def _fire_events_to_geojson(events: list[Event]) -> dict:
    """화재 Event 리스트 → GeoJSON FeatureCollection.

    기존 _events_to_geojson과 달리 region_code를 properties에 포함한다
    (프론트엔드 TheoryPanel이 지역 필터링에 사용).
    """
    features = []
    for e in events:
        lat, lon = e.location
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id":          e.id,
                "timestamp":   e.timestamp.isoformat(),
                "source_type": e.source_type,
                "source_id":   e.source_id,
                "region_code": e.region_code,
                "severity":    e.severity,
                "title":       e.title,
                "description": e.description,
                "theory_tags": e.theory_tags,
                **e.payload,
            },
        })

    return {
        "type":     "FeatureCollection",
        "features": features,
        "metadata": {
            "count":     len(features),
            "source":    "NASA FIRMS VIIRS_SNPP_NRT",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/naval")
async def get_naval_vessels():
    """
    전략 해역 실시간 선박 AIS 데이터 GeoJSON 반환.
    AISStream.io WebSocket에서 45초 수집 후 정규화, 5분 캐시.
    대상 해역: 호르무즈·바브엘만데브·말라카·대만해협·남중국해

    연관 이론: Mahan 해양력 이론 — SLOC 통제 = 해양 패권.
    유조선·LNG선 밀집도가 Resource Weaponization의 실시간 지표가 된다.
    호르무즈 룰 자동 활성화 (source_type: naval).
    """
    now = datetime.now(timezone.utc)
    if _naval_cache["geojson"] is not None and now < _naval_cache["expires_at"]:
        return _naval_cache["geojson"]

    try:
        connector = AISStreamConnector()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        events = await connector.fetch()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AISStream 연결 실패: {e}") from e

    result = _naval_events_to_geojson(events)
    _naval_cache["geojson"] = result
    _naval_cache["expires_at"] = now + _NAVAL_TTL
    return result


def _naval_events_to_geojson(events: list[Event]) -> dict:
    """선박 Event 리스트 → GeoJSON FeatureCollection.

    프론트엔드가 선박 유형별 마커 스타일·필터링에 필요한 필드를 포함한다.
    """
    features = []
    for e in events:
        lat, lon = e.location
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id":          e.id,
                "timestamp":   e.timestamp.isoformat(),
                "source_type": e.source_type,
                "source_id":   e.source_id,
                "region_code": e.region_code,
                "severity":    e.severity,
                "title":       e.title,
                "description": e.description,
                "theory_tags": e.theory_tags,
                **e.payload,
            },
        })

    return {
        "type":     "FeatureCollection",
        "features": features,
        "metadata": {
            "count":     len(features),
            "source":    "AISStream.io",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/adsb")
async def get_adsb_aircraft():
    """
    OpenSky Network 실시간 군용기 ADS-B GeoJSON 반환.
    대만해협·남중국해·동중국해 bbox 병렬 조회, 5분 캐시.

    연관 이론:
      - A2/AD (Anti-Access/Area Denial) — 군용기 밀도가 접근거부 압박 지표
      - Weaponized Interdependence (Farrell & Newman 2019) — 대만해협 군사 긴장
        → TSMC 주가 cascade (taiwan_strait_to_tsm·soxx 룰 트리거)
    """
    now = datetime.now(timezone.utc)
    if _adsb_cache["geojson"] is not None and now < _adsb_cache["expires_at"]:
        return _adsb_cache["geojson"]

    try:
        connector = OpenSkyConnector()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        events = await connector.fetch()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OpenSky API 연결 실패: {e}") from e

    result = _adsb_events_to_geojson(events)
    _adsb_cache["geojson"] = result
    _adsb_cache["expires_at"] = now + _ADSB_TTL
    return result


def _adsb_events_to_geojson(events: list[Event]) -> dict:
    """군용기 ADS-B Event 리스트 → GeoJSON FeatureCollection."""
    features = []
    for e in events:
        lat, lon = e.location
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id":          e.id,
                "timestamp":   e.timestamp.isoformat(),
                "source_type": e.source_type,
                "source_id":   e.source_id,
                "region_code": e.region_code,
                "severity":    e.severity,
                "title":       e.title,
                "description": e.description,
                "theory_tags": e.theory_tags,
                **e.payload,
            },
        })

    return {
        "type":     "FeatureCollection",
        "features": features,
        "metadata": {
            "count":     len(features),
            "source":    "OpenSky Network",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/military-bases")
async def get_military_bases():
    """
    인도-태평양 주요 군사기지 GeoJSON 반환.
    Phase 0 첫 번째 정적 레이어 — 미군/중국/러시아/동맹 기지 약 20개.
    연관 이론: Forward Deployment, A2/AD, String of Pearls
    """
    return _load_geojson("military_bases.geojson")


@router.get("/energy-pipelines")
async def get_energy_pipelines():
    """
    주요 에너지 파이프라인 GeoJSON 반환 (정적 데이터).
    가스관·송유관 10개 — 러시아-유럽, 러시아-중국, 중앙아시아-중국, 중동 경로.
    연관 이론: Weaponized Interdependence (Farrell & Newman), Resource Weaponization
    """
    return _load_geojson("energy_pipelines.geojson")


@router.get("/submarine-cables")
async def get_submarine_cables():
    """
    전략적 해저 광케이블 GeoJSON 반환 (정적 데이터, 18개).
    strategic_risk(high/medium/low)로 중국 주도 vs 미국/동맹 케이블을 구분한다.
    연관 이론: Techno-nationalism, Digital Iron Curtain, Platform Power
    """
    return _load_geojson("submarine_cables.geojson")


@router.get("/chokepoints")
async def get_chokepoints():
    """
    전략적 해상 초점(Chokepoints) GeoJSON 반환 (정적 폴리곤 데이터).
    10개 — 말라카·호르무즈·바브엘만데브·대만해협·루손·수에즈 등.
    연관 이론: Mahan 해양력 이론, SLOC 통제, Resource Weaponization
    """
    return _load_geojson("chokepoints.geojson")


@router.get("/gdelt")
async def get_gdelt():
    """
    GDELT 3-Stage Funnel 결과 GeoJSON 반환 (15분 캐시).

    Stage 1: QuadClass≥3·GoldsteinScale≤-5·NumMentions≥20 필터
    Stage 2: RSS 교차검증 (≥2매체 → confidence_score 0.8)
    confidence_score < 0.8 이벤트는 'unverified': true 프로퍼티 포함.

    연관 이론: 정보전 (Information Warfare), Gray Zone Strategy
    무검열 원칙: 정치적 민감성과 무관하게 필터 통과 데이터 그대로 반환.
    """
    now = datetime.now(timezone.utc)
    if _gdelt_cache["geojson"] is not None and now < _gdelt_cache["expires_at"]:
        return _gdelt_cache["geojson"]

    try:
        events = await run_gdelt_pipeline()
        events = score_gdelt_events(events)  # importance_score 계산
        result = gdelt_to_geojson(events)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[GDELT endpoint] 파이프라인 오류: %s", exc)
        result = {"type": "FeatureCollection", "features": []}

    _gdelt_cache["geojson"]    = result
    _gdelt_cache["expires_at"] = now + _GDELT_TTL
    return result


@router.get("/sanctions")
async def get_sanctions():
    """
    제재 레짐 GeoJSON 반환 (24시간 캐시).

    정적 sanctions.yaml 기반 — UN SC·미국 OFAC·EU 제한 조치·BIS Entity List.
    15개 레짐, 5대 섹터 전체 커버.
    confidence_score=1.0 (공개 결의 기반 완전 검증 데이터).

    연관 이론:
      - Weaponized Interdependence (Farrell & Newman 2019)
      - Economic Coercion (Drezner 2011)
    """
    now = datetime.now(timezone.utc)
    if _sanctions_cache["geojson"] is not None and now < _sanctions_cache["expires_at"]:
        return _sanctions_cache["geojson"]

    events = load_sanctions()
    result = _sanctions_to_geojson(events)
    _sanctions_cache["geojson"]    = result
    _sanctions_cache["expires_at"] = now + _SANCTIONS_TTL
    return result


def _sanctions_to_geojson(events) -> dict:
    """제재 Event 리스트 → GeoJSON FeatureCollection."""
    features = []
    for e in events:
        lat, lon = e.location
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id":          e.id,
                "title":       e.title,
                "description": e.description,
                "source_type": e.source_type,
                "region_code": e.region_code,
                "severity":    e.severity,
                "theory_tags": e.theory_tags,
                **e.payload,
            },
        })

    return {
        "type":     "FeatureCollection",
        "features": features,
        "metadata": {
            "count":     len(features),
            "source":    "sanctions.yaml (UN SC·OFAC·EU)",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
    }
