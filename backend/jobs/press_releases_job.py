"""
press_releases_job.py — NK News / 38 North / UN News / Atlantic Council 주기 수집 잡

BackgroundScheduler(스레드 컨텍스트)에서 6시간마다 실행.
  - NKNews + 38 North → nk_press_releases (한반도 전문)
  - UN News → un_news_releases (다자적 시각)
  - Atlantic Council + Arms Control Assoc → policy_releases (미국 외교정책 시각)

신뢰도:
  38 North              ★★★★★ Stimson Center 학술 분석 — 흡연총 핵심
  MOFA                  ★★★★★ 한국 정부 1차 사료 (별도 수집)
  UN News               ★★★★☆ UN 공식 뉴스 — 이중결정 다자 소스
  Atlantic Council      ★★★★☆ 워싱턴 1위 지정학 싱크탱크 — 미국 시각 (State Dept 대안)
  Arms Control Assoc    ★★★★☆ 핵·군비통제 전문 (1945년 창설)
  NKNews                ★★★☆☆ 북한 전문 상업 매체, NYT 인용
"""
import logging

logger = logging.getLogger(__name__)


def run_nk_press_batch() -> None:
    """NKNews + 38 North RSS 수집 → nk_press_releases 저장."""
    try:
        from connectors.nk_news_connector import collect_all
        n = collect_all()
        logger.info("[PressJob/NK] 완료 — %d건 처리", n)
    except Exception as exc:
        logger.warning("[PressJob/NK] 실패 (다음 회차 재시도): %s", exc)


def run_un_news_batch() -> None:
    """UN News RSS 수집 → un_news_releases 저장."""
    try:
        from connectors.un_news_connector import collect_all
        n = collect_all()
        logger.info("[PressJob/UN] 완료 — %d건 처리", n)
    except Exception as exc:
        logger.warning("[PressJob/UN] 실패 (다음 회차 재시도): %s", exc)


def run_policy_think_tank_batch() -> None:
    """Atlantic Council + Arms Control Association 수집 → policy_releases 저장."""
    try:
        from connectors.policy_think_tank_connector import collect_all
        n = collect_all()
        logger.info("[PressJob/Policy] 완료 — %d건 신규", n)
    except Exception as exc:
        logger.warning("[PressJob/Policy] 실패 (다음 회차 재시도): %s", exc)
