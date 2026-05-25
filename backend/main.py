"""
geo-intel-map 백엔드 진입점 (Entry Point)
FastAPI 앱을 초기화하고 기본 엔드포인트를 등록한다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cascade import router as cascade_router
from api.layers import router as layers_router
from api.library import router as library_router
from api.news import router as news_router
from api.sandbox import router as sandbox_router
from api.sandbox import seed_tutorial_canvas
from api.stats import router as stats_router
from api.study import router as study_router
from api.translate import router as translate_router
from api.version import router as version_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 sandbox.db가 비어있으면 튜토리얼 캔버스를 자동 생성한다."""
    seed_tutorial_canvas()
    yield


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
    ],
    allow_methods=["*"],           # GET, POST 등 모든 HTTP 메서드 허용
    allow_headers=["*"],
)

app.include_router(layers_router)
app.include_router(cascade_router)
app.include_router(library_router)
app.include_router(news_router)
app.include_router(sandbox_router)
app.include_router(stats_router)
app.include_router(study_router)
app.include_router(translate_router)
app.include_router(version_router)

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
    return {
        "status": "ok",
        "service": "geo-intel-map",
        "version": "0.0.1",
    }
