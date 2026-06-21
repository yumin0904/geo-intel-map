"""
geo-intel-map 백엔드 진입점 (Entry Point)
FastAPI 앱을 초기화하고 기본 엔드포인트를 등록한다.
"""

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cascade import router as cascade_router
from api.country import router as country_router
from api.layers import router as layers_router
from api.library import router as library_router
from api.news import router as news_router
from api.reasoning import router as reasoning_router
from api.sandbox import router as sandbox_router
from api.sandbox import seed_tutorial_canvas
from api.stats import router as stats_router
from api.study import router as study_router
from api.translate import router as translate_router
from api.version import router as version_router
from api.intel_query import router as intel_router
from db.archive_manager import ArchiveManager
from jobs.gdelt_job import run_gdelt_batch
from jobs.reliefweb_job import run_reliefweb_batch
from jobs.firms_sensor_job import run_firms_sensor_batch
from jobs.press_releases_job import run_nk_press_batch, run_un_news_batch, run_policy_think_tank_batch

# ── 글로벌 싱글톤 ─────────────────────────────────────────────────────────
_archive_mgr = ArchiveManager()
_scheduler   = BackgroundScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 초기화 및 정리 작업."""
    # DB 스키마 초기화 (테이블 없으면 생성)
    _archive_mgr.init_schema()

    # IA-Engine-C: confidence_score 컬럼 마이그레이션 (기존 DB 호환)
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    _intel_db = _Path(__file__).parent / "db" / "intel.db"
    with _sqlite3.connect(_intel_db) as _con:
        try:
            _con.execute(
                "ALTER TABLE intel_analyses ADD COLUMN confidence_score INTEGER DEFAULT NULL"
            )
            _con.commit()
        except _sqlite3.OperationalError:
            pass  # 컬럼이 이미 존재하면 무시

    # GDELT 3-Stage Funnel — 15분마다 실행 (실시간 첩보 수집)
    _scheduler.add_job(
        run_gdelt_batch,
        trigger="interval",
        minutes=15,
        id="gdelt_pipeline",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # ReliefWeb UN OCHA — 30분마다 캐시 만료 (다음 요청 시 fresh fetch)
    _scheduler.add_job(
        run_reliefweb_batch,
        trigger="interval",
        minutes=30,
        id="reliefweb_pipeline",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # NASA FIRMS 화재/열점 → sensor_snapshots — 6시간마다 실행
    # verification_funnel Stage 3 (_stage3_sensor) 데이터 공급원
    _scheduler.add_job(
        run_firms_sensor_batch,
        trigger="interval",
        hours=6,
        id="firms_sensor",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # 아카이브 TTL 사이클 — 1시간마다 실행
    _scheduler.add_job(
        _archive_mgr.run_full_cycle,
        trigger="interval",
        hours=1,
        id="archive_cycle",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # NKNews + 38 North — 6시간마다 (한반도 과정추적 흡연총 소스)
    _scheduler.add_job(
        run_nk_press_batch,
        trigger="interval",
        hours=6,
        id="nk_press",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # UN News RSS — 6시간마다 (이중결정 검정 다자 소스, 30건/회 누적)
    _scheduler.add_job(
        run_un_news_batch,
        trigger="interval",
        hours=6,
        id="un_news",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Atlantic Council + Arms Control Assoc — 6시간마다 (미국 외교정책 시각, State Dept 대안)
    _scheduler.add_job(
        run_policy_think_tank_batch,
        trigger="interval",
        hours=6,
        id="policy_think_tank",
        replace_existing=True,
        misfire_grace_time=300,
    )

    _scheduler.start()

    seed_tutorial_canvas()
    yield

    _scheduler.shutdown(wait=False)


# ── 앱 인스턴스 생성 ──────────────────────────────────────────────
# FastAPI()는 전체 백엔드 앱의 "몸통"이다.
# docs_url="/docs" 로 접근하면 자동 생성된 API 문서를 브라우저에서 볼 수 있다.
app = FastAPI(
    title="geo-intel-map API",
    description="지정학 인텔리전스 지도 백엔드",
    version="0.0.1",
    lifespan=lifespan,
)

# ── CORS 미들웨어 ────────────────────────────────────────────────
# 브라우저 보안 정책(Same-Origin Policy) 때문에, 프론트엔드(포트 5500)가
# 백엔드(포트 8000)를 호출하려면 서버가 명시적으로 허용해야 한다.
# 개발 중에는 localhost 전체를 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",   # VS Code Live Server 기본 포트
        "http://127.0.0.1:5500",
        "http://localhost:3000",   # 다른 로컬 개발 서버 대비
        "http://localhost:8080",   # python -m http.server 검증용
        "http://127.0.0.1:8080",
    ],
    allow_methods=["*"],           # GET, POST 등 모든 HTTP 메서드 허용
    allow_headers=["*"],
)

app.include_router(country_router)
app.include_router(layers_router)
app.include_router(cascade_router)
app.include_router(library_router)
app.include_router(news_router)
app.include_router(reasoning_router)
app.include_router(sandbox_router)
app.include_router(stats_router)
app.include_router(study_router)
app.include_router(translate_router)
app.include_router(version_router)
app.include_router(intel_router)

# ── 엔드포인트 ───────────────────────────────────────────────────
# @app.get("/...") : HTTP GET 요청을 처리하는 함수 등록
# 함수가 dict를 반환하면 FastAPI가 자동으로 JSON으로 변환해준다.

@app.get("/")
async def root():
    """API 루트 — 살아있는지 확인용"""
    return {"message": "Welcome to geo-intel-map API"}


@app.get("/api/health")
async def health_check():
    """
    헬스체크 엔드포인트.
    프론트엔드가 백엔드가 살아있는지 주기적으로 확인할 때 사용한다.
    모니터링 도구나 배포 플랫폼도 이 경로를 기준으로 상태를 판단한다.
    """
    import json as _json
    from pathlib import Path as _Path
    _ver = _json.loads((_Path(__file__).parent / "config" / "version.json").read_text()).get("version", "?")
    return {
        "status": "ok",
        "service": "geo-intel-map",
        "version": _ver,
    }
