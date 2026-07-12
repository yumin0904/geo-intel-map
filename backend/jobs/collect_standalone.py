#!/usr/bin/env python3
"""
collect_standalone.py — 서버 없이 수집 잡을 1회전 실행하는 단독 러너.

왜 필요한가:
    수집 스케줄러(APScheduler)는 FastAPI 서버 프로세스 안에서만 돈다.
    로컬 서버를 안 켜 두면 GDELT(TTL 3일)·FIRMS(24h) 같은 실시간 축이
    영구 손실된다 (실측: 2026-06-21~07-04 약 2주 공백).
    이 스크립트를 launchd가 하루 2회 실행하면 서버 가동 여부와 무관하게
    데이터가 누적된다.

실행:
    cd backend && .venv/bin/python jobs/collect_standalone.py

설계 원칙:
    - 잡 하나가 실패해도 나머지는 계속 실행 (부분 실패 허용, 로그로 보고)
    - LLM 호출 없음 (Token-Zero 태깅 — cameo_mapper 결정론 로직만 사용)
    - 종료 코드: 전체 실패(0건 성공)일 때만 1, 그 외 0
    - 서버가 동시에 켜져 있어도 안전: SQLite 잠금 충돌 시 해당 잡만 실패로
      기록되고 다음 주기에 재시도된다 (launchd가 매일 다시 실행하므로 자가 회복)

관측성 (판례 20260709-os-observability-committee):
    - config/source_roster.yaml이 "수집 대상 전수"의 단일 진실원이다.
      종료 요약은 이 고정 jobs 리스트가 아니라 로스터를 분모로 삼는다 —
      로스터에 있는데 jobs에 없는 live 소스는 "미시도"로 드러나야 빠진
      소스를 방치하지 않는다 (ACLED가 6주간 이렇게 방치됐던 사례).
    - 종료부에서 로스터의 live+max_staleness_hours 지정 소스를 순회해
      DB의 MAX(timestamp_col)을 대조, 임계 초과 시 fail-loud 알림 채널
      (osascript)을 재사용해 경보한다. 경보 로직 자체의 실패가 수집을
      막아선 안 되므로 전체를 try로 감싼다.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# backend/ 를 import 루트로 (launchd는 WorkingDirectory를 backend로 설정하지만,
# 직접 실행 시에도 동작하도록 명시)
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

_ROSTER_PATH = _BACKEND / "config" / "source_roster.yaml"
_INTEL_DB = _BACKEND / "db" / "intel.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("collect_standalone")


def _load_env() -> None:
    """backend/.env 를 os.environ에 로드 (이미 설정된 변수는 존중)."""
    env_file = _BACKEND / ".env"
    if not env_file.exists():
        logger.warning(".env 없음 — FIRMS 등 키 필요 잡은 건너뛸 수 있음")
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _rotate_launchd_log(max_bytes: int = 5 * 1024 * 1024) -> None:
    """launchd StandardOutPath 로그(append 전용, 로테이션 없음)의 무한 증가 방지.

    실행 시작 시 5MB 초과면 .1로 밀어낸다 (백업 1개 유지). 현재 실행분은 이미 열린
    fd를 따라 .1 쪽에 이어 쓰이고, 다음 실행부터 새 파일이 시작된다 — 상한만 보장.
    """
    log = _BACKEND / "logs" / "collect_launchd.log"
    try:
        if log.exists() and log.stat().st_size > max_bytes:
            backup = log.with_suffix(".log.1")
            backup.unlink(missing_ok=True)
            log.rename(backup)
            logger.info("로그 로테이션: %s → %s (%.1fMB)", log.name, backup.name,
                        backup.stat().st_size / 1024 / 1024)
    except OSError as e:
        logger.warning("로그 로테이션 실패 (계속 진행): %s", e)


def _notify(msg: str, title: str = "geo-intel 자동수집") -> None:
    """macOS 알림 발송 공통 채널 — 로그에만 남는 침묵 실패 방지.

    배경: 이 스크립트의 존재 이유였던 6/21~7/4 수집 공백도 침묵 실패였다.
    launchd에는 알림 훅이 없으므로 잡 스스로 알린다.
    """
    import subprocess
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "{title}" sound name "Basso"'],
            timeout=10, check=False,
        )
    except Exception as e:  # 알림 실패가 수집 결과를 바꾸면 안 된다
        logger.warning("알림 발송 불가: %s", e)


def _notify_failure(failed: list[str], total: int) -> None:
    """수집 잡 실패를 macOS 알림으로 표면화 (실패 시에만, 최대 하루 2회)."""
    _notify(f"수집 실패 {len(failed)}/{total}: {', '.join(failed)}")


def _load_roster() -> list[dict]:
    """config/source_roster.yaml을 읽어 소스 목록을 반환한다.

    로스터 자체가 없거나 깨져 있어도 수집 잡 실행을 막으면 안 되므로
    실패 시 빈 리스트를 반환하고 경고만 남긴다 (요약/경보 기능만 저하).
    """
    try:
        import yaml
        data = yaml.safe_load(_ROSTER_PATH.read_text(encoding="utf-8"))
        return data.get("sources", []) or []
    except Exception as e:
        logger.warning("소스 로스터 로드 실패 (%s) — 요약/신선도 경보 생략: %s", _ROSTER_PATH, e)
        return []


def _check_staleness(roster: list[dict]) -> list[dict]:
    """로스터의 live 소스 중 max_staleness_hours가 지정된 것만 신선도를 대조한다.

    seed/manual, 그리고 job이 없어 애초에 경보 대상이 아닌 소스는 건너뛴다
    (roster.yaml에서 max_staleness_hours=null로 명시된 소스가 이에 해당).
    이벤트 timestamp(=event_date)가 아니라 실제 수집 시각을 반영하는
    컬럼(events.created_at, *_releases.fetched_at 등)을 대조한다 — ACLED
    처럼 event_date 자체가 실제 대비 최대 ~14개월 지연되는 소스는 timestamp
    기준으로는 "잡이 최근에 돌았는지"를 원천적으로 판정할 수 없기 때문이다
    (source_roster.yaml 상단 주석 참조).
    """
    stale: list[dict] = []
    if not _INTEL_DB.exists():
        return stale

    con = sqlite3.connect(f"file:{_INTEL_DB}?mode=ro", uri=True)
    try:
        now = datetime.now(timezone.utc)
        for src in roster:
            if src.get("kind") != "live" or not src.get("max_staleness_hours"):
                continue
            table = src.get("db_table")
            col = src.get("timestamp_col")
            if not table or not col:
                continue

            sql = f"SELECT MAX({col}) FROM {table}"
            if src.get("filter"):
                sql += f" WHERE {src['filter']}"

            try:
                row = con.execute(sql).fetchone()
                latest_raw = row[0] if row else None
                if not latest_raw:
                    stale.append({**src, "reason": "데이터 없음"})
                    continue
                latest = datetime.fromisoformat(str(latest_raw).replace("Z", "+00:00"))
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                age_h = (now - latest).total_seconds() / 3600
                if age_h > src["max_staleness_hours"]:
                    stale.append({**src, "reason": f"{age_h:.1f}h 경과(임계 {src['max_staleness_hours']}h)"})
            except sqlite3.Error as e:
                logger.warning("[신선도] %s 조회 실패: %s", src.get("source_id"), e)
    finally:
        con.close()

    return stale


def main() -> int:
    _rotate_launchd_log()
    _load_env()

    # import는 .env 로드 후에 (모듈 상단에서 os.getenv 하는 코드 대비)
    from db.archive_manager import ArchiveManager
    from jobs.gdelt_job import run_gdelt_batch
    from jobs.firms_sensor_job import run_firms_sensor_batch
    from jobs.acled_job import run_acled_batch
    from jobs.press_releases_job import (
        run_nk_press_batch,
        run_un_news_batch,
        run_policy_think_tank_batch,
        run_govinfo_batch,
        run_mofa_press_batch,
        run_bp_provocations_batch,
    )
    from jobs.prediction_scoring_job import run_prediction_scoring_batch
    from jobs.observation_job import run_observation_batch

    archive = ArchiveManager()
    archive.init_schema()

    # (이름, 함수) — 서버 스케줄러와 동일 구성에서 reliefweb 제외
    # (reliefweb 잡은 서버 요청용 캐시 만료라 단독 실행 의미 없음)
    jobs = [
        ("gdelt", run_gdelt_batch),                      # 실시간 첩보 (TTL 3일 — 최우선)
        ("firms", run_firms_sensor_batch),               # 위성 화재/열점
        ("acled", run_acled_batch),                      # 분쟁 이벤트 (판례 20260709 재배선)
        ("nk_press", run_nk_press_batch),                # NKNews·38North
        ("un_news", run_un_news_batch),                  # UN News RSS
        ("policy_think_tank", run_policy_think_tank_batch),
        ("govinfo", run_govinfo_batch),                  # 대통령 성명 (1차 사료)
        ("mofa_press", run_mofa_press_batch),             # 외교부 보도자료 (20일 미배선 배선)
        ("bp_provocations", run_bp_provocations_batch),   # CSIS BP 북한 도발 (CNS 병렬 후속, fail-loud)
        ("archive_cycle", archive.run_full_cycle),       # TTL 이관·삭제
        ("prediction_scoring", run_prediction_scoring_batch),  # Phase 10-2 만기 예측 채점
        ("observation_ledger", run_observation_batch),   # P1 report-only 관찰 원장 (데이터효용위 07-12, 일 1회 자체 스로틀)
    ]

    ok, failed = [], []
    t0 = time.time()
    logger.info("=== 수집 1회전 시작 (%s) ===", datetime.now().isoformat(timespec="seconds"))
    for name, fn in jobs:
        t = time.time()
        try:
            fn()
            ok.append(name)
            logger.info("[%s] 완료 (%.1fs)", name, time.time() - t)
        except Exception as e:  # 부분 실패 허용 — 다음 잡 계속
            failed.append(name)
            logger.error("[%s] 실패: %s", name, e)

    logger.info(
        "=== 수집 1회전 종료: 성공 %d / 실패 %d (%.1fs) %s ===",
        len(ok), len(failed), time.time() - t0,
        ("실패목록=" + ",".join(failed)) if failed else "",
    )
    if failed:
        _notify_failure(failed, total=len(jobs))

    # ── 로스터 대비 집계 (판례 20260709: 분모를 jobs 리스트가 아니라
    # 로스터로 삼아야 "등록조차 안 된" 소스가 드러난다) ─────────────────
    roster = _load_roster()
    if roster:
        live_sources = [s for s in roster if s.get("kind") == "live"]
        attempted_jobs = {name for name, _ in jobs}
        untried = sorted(
            s["source_id"] for s in live_sources
            if not s.get("job") or s["job"] not in attempted_jobs
        )
        logger.info(
            "=== 로스터 대비: live %d개 중 시도 %d·성공 %d·실패 %d·미시도 %d개 %s ===",
            len(live_sources), len(jobs), len(ok), len(failed), len(untried),
            f"미시도목록={untried}" if untried else "",
        )

        # ── 신선도 경보 (A안) — 경보 로직 자체의 실패가 수집을 막으면 안 됨 ──
        try:
            stale = _check_staleness(roster)
            if stale:
                for s in stale:
                    logger.error("[신선도] %s(%s) 경보 — %s", s["source_id"], s["name"], s["reason"])
                _notify(
                    f"신선도 경보 {len(stale)}건: "
                    + ", ".join(f"{s['source_id']}({s['reason']})" for s in stale),
                    title="geo-intel 신선도 경보",
                )
            else:
                logger.info("[신선도] 이상 없음 (경보 대상 %d개 소스 전부 임계 이내)",
                            sum(1 for s in roster if s.get("kind") == "live" and s.get("max_staleness_hours")))
        except Exception as e:
            logger.warning("[신선도] 경보 로직 실패 (수집 결과에는 영향 없음): %s", e)
            _notify(f"신선도 경보 로직 자체가 실패했습니다: {e}", title="geo-intel 신선도 경보")
    else:
        logger.warning("소스 로스터 비어있음 — 로스터 대비 요약·신선도 경보 생략")

    return 1 if not ok else 0


if __name__ == "__main__":
    sys.exit(main())
