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


def run_govinfo_batch() -> None:
    """GovInfo CPD 최근 7일치 대통령 성명 수집 → govinfo_releases 저장."""
    try:
        from connectors.govinfo_connector import collect_recent
        n = collect_recent(days_back=7)
        logger.info("[PressJob/GovInfo] 완료 — %d건 신규", n)
    except Exception as exc:
        logger.warning("[PressJob/GovInfo] 실패 (다음 회차 재시도): %s", exc)


def run_mofa_press_batch() -> None:
    """외교부 보도자료(공공데이터포털) 전체 수집 → mofa_press_releases 저장.

    20일간 CLI 전용으로 방치되어 launchd 주기 수집에 배선되지 않았던 소스
    (source_roster.yaml 감사에서 발견). collect_all()은 전체 페이지를
    재순회하되 INSERT OR IGNORE로 중복을 걸러 매 회차 신규분만 실효 반영된다.
    """
    try:
        from connectors.mofa_press import collect_all
        n = collect_all()
        logger.info("[PressJob/MOFA] 완료 — %d건 처리", n)
    except Exception as exc:
        logger.warning("[PressJob/MOFA] 실패 (다음 회차 재시도): %s", exc)


def run_bp_provocations_batch() -> None:
    """CSIS Beyond Parallel 북한 도발 DB 수집 → bp_provocations 저장.

    CNS 미사일 DB 단종(2026-04)의 병렬 후속 (채택위 2026-07-11).
    의도적으로 예외를 삼키지 않는다 — 커넥터의 fail-loud 가드(행수·최신일자
    assert)가 collect_standalone 실패 목록에 잡혀야 silent failure가 안 된다.
    """
    from connectors.bp_provocations_connector import collect
    n = collect()
    logger.info("[PressJob/BP] 완료 — %d건 신규", n)
