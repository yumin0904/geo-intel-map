"""
gdelt_job.py — GDELT 파이프라인 15분 배치 잡.

APScheduler BackgroundScheduler(스레드 컨텍스트)에서 실행된다.
asyncio.run()으로 비동기 파이프라인을 동기 래핑.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def run_gdelt_batch() -> None:
    """GDELT 3-Stage Funnel 실행 후 승격 이벤트 DB 저장.

    BackgroundScheduler 스레드에서 호출되므로 asyncio.run()으로 새 이벤트 루프 생성.
    실패해도 서버 프로세스에 영향 없도록 예외를 로그만 남기고 삼킨다.
    """
    try:
        from services.gdelt_pipeline import run_gdelt_pipeline
        from api.layers import save_gdelt_events

        events = asyncio.run(run_gdelt_pipeline())
        if events:
            save_gdelt_events(events)
            promoted = sum(1 for e in events if not e.is_staging)
            logger.info("[GdeltJob] 완료 — 총 %d건, 승격 %d건 DB 저장", len(events), promoted)
        else:
            logger.info("[GdeltJob] 이번 회차 결과 없음")
    except Exception as exc:
        logger.warning("[GdeltJob] 실패 (다음 회차 재시도): %s", exc)
