"""
cascade.py — Cascade(연쇄 분석) API 라우터.

엔진이 만든 CascadeLink와 관련 이벤트(trigger·response)를 반환한다.
프론트엔드는 이 응답으로 지도 위 trigger→response 점선 화살표를 그린다.

ACLED + yfinance 호출이 느리므로 1시간 캐시(CLAUDE.md 성능 원칙: 매번 재계산 금지).
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from services.cascade.engine import build_cascade
from services.cascade.correlation import (
    run_correlation_analysis,
    run_candidate_scan,
    generate_yaml_draft,
    summarize_results,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cascade", tags=["cascade"])

# Cascade 결과 1시간 캐시 — ACLED(분쟁) + yfinance(유가) 호출 비용이 크다.
_CASCADE_TTL = timedelta(hours=1)
_cache: dict = {
    "result":     None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# Granger 분석은 계산 비용이 크므로 24시간 캐시
_CORR_TTL = timedelta(hours=24)
_corr_cache: dict = {
    "result":     None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}

# 후보 스캔은 더 오래 캐시 (region × ticker 전체 조합이라 계산 비용 큼)
_CANDIDATES_TTL = timedelta(hours=24)
_candidates_cache: dict = {
    "result":     None,
    "expires_at": datetime(1970, 1, 1, tzinfo=timezone.utc),
}


@router.get("/links")
async def get_cascade_links():
    """활성 룰을 평가해 인과 링크 + 관련 이벤트를 반환한다.

    응답 구조: {"links": [...], "events": [...], "metadata": {...}}
    연관 이론: Resource Weaponization (호르무즈 긴장 → 유가)
    """
    now = datetime.now(timezone.utc)
    if _cache["result"] is not None and now < _cache["expires_at"]:
        return _cache["result"]

    result = await build_cascade()
    _cache["result"] = result
    _cache["expires_at"] = now + _CASCADE_TTL
    return result


@router.get("/correlation")
async def get_correlation():
    """Cascade 룰의 Granger 인과성 사후 검증 결과를 반환한다.

    각 룰에 대해 "분쟁 강도 시계열 → 시장 지표" Granger F-test를 수행한다.
    계산 비용이 크므로 24시간 캐시.

    이론 연결:
      Granger (1969) — 시간 선행성 기반 인과 추론
      적용: 지정학적 충격이 시장 변동을 통계적으로 예측하는가를 검증
    """
    now = datetime.now(timezone.utc)
    if _corr_cache["result"] is not None and now < _corr_cache["expires_at"]:
        return _corr_cache["result"]

    results = await run_correlation_analysis()
    summary = summarize_results(results)
    payload = {"summary": summary, "rules": results}

    _corr_cache["result"] = payload
    _corr_cache["expires_at"] = now + _CORR_TTL
    return payload


@router.get("/candidates")
async def get_cascade_candidates():
    """P4-4: Granger 스캔으로 신규 Cascade 룰 후보를 자동 생성한다.

    모든 region × ticker 조합을 Granger 검정해 유망한 쌍을 발굴한다.
    기존 8개 검증 페어는 제외. p < 0.10 또는 극단 이벤트 방향 일치 기준.

    ★ 인간 승인 필수: yaml_draft를 검토 후 cascade_rules.yaml에 수동 추가.
    status: draft 라인을 제거해야 엔진이 해당 룰을 인식한다.

    이론 연결: Granger (1969) 시간 선행성 인과 추론 — 새 룰의 통계적 타당성 근거 제공
    """
    now = datetime.now(timezone.utc)
    if _candidates_cache["result"] is not None and now < _candidates_cache["expires_at"]:
        return _candidates_cache["result"]

    candidates = await run_candidate_scan()
    yaml_draft = generate_yaml_draft(candidates, top_n=10)

    payload = {
        "candidates": candidates,
        "yaml_draft": yaml_draft,
        "total":      len(candidates),
        "note":       "★ 인간 승인 필수: cascade_rules.yaml에 추가 전 반드시 검토",
    }

    _candidates_cache["result"] = payload
    _candidates_cache["expires_at"] = now + _CANDIDATES_TTL
    return payload
