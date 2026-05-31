#!/usr/bin/env python3
"""
cascade_rule_draft.py — P4-4 Cascade 룰 자동 후보 생성 CLI

사용:
  python3 scripts/cascade_rule_draft.py              # 상위 10개 후보 출력
  python3 scripts/cascade_rule_draft.py --top 20     # 상위 20개
  python3 scripts/cascade_rule_draft.py --p 0.05     # Granger p < 0.05 엄격 기준
  python3 scripts/cascade_rule_draft.py --save       # YAML 파일 저장 (아래 경로)

출력 파일: backend/config/cascade_rules_draft.yaml
★ 인간 승인 필수: 각 룰을 직접 검토·수정 후 cascade_rules.yaml로 이동할 것.
    status: draft 라인을 제거해야 엔진이 해당 룰을 활성화한다.

이론 연결:
  Granger (1969): "X의 과거값이 Y 예측에 유의하게 기여하면 X→Y 인과 존재"
  지정학 적용: 분쟁 강도 시계열 → 시장 지표 변동의 시간 선행성 측정
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# 백엔드 루트를 sys.path에 추가 (스크립트 단독 실행 시)
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from services.cascade.correlation import (
    run_candidate_scan,
    generate_yaml_draft,
    _START_DATE,
    _END_DATE,
)

_DRAFT_PATH = _ROOT / "config" / "cascade_rules_draft.yaml"


def _print_summary(candidates: list[dict]) -> None:
    """후보 목록을 콘솔에 요약 출력한다."""
    print(f"\n{'═' * 70}")
    print(f"  Cascade 룰 후보 스캔 결과 — {date.today().isoformat()}")
    print(f"  분석 기간: {_START_DATE} ~ {_END_DATE}")
    print(f"  발굴된 후보 수: {len(candidates)}")
    print(f"{'═' * 70}\n")

    if not candidates:
        print("  후보 없음 — 기준을 완화하거나 데이터 누적 후 재시도하세요.")
        return

    # Granger 유의 후보 (p < 0.05)
    sig = [c for c in candidates if c.get("p_value") is not None and c["p_value"] < 0.05]
    # 극단 이벤트 방향 일치 후보
    extreme = [
        c for c in candidates
        if c.get("extreme_return_pct") is not None
        and c.get("normal_return_pct") is not None
        and c.get("n_extreme_events", 0) >= 5
    ]

    print(f"  Granger 유의 (p<0.05):     {len(sig)}개")
    print(f"  극단 이벤트 방향 일치:      {len(extreme)}개")
    print()

    # 상세 테이블
    header = f"{'#':<4} {'rule_id':<40} {'p값':<8} {'lag':<5} {'극단%':>7} {'일반%':>7} {'n_ext':>6}"
    print(header)
    print("-" * len(header))

    for i, c in enumerate(candidates):
        p_str   = f"{c['p_value']:.4f}" if c.get("p_value") is not None else " N/A  "
        ext_str = f"{c['extreme_return_pct']:+.2f}" if c.get("extreme_return_pct") is not None else "  N/A"
        nrm_str = f"{c['normal_return_pct']:+.2f}"  if c.get("normal_return_pct")  is not None else "  N/A"
        lag_str = str(c.get("best_lag") or "-")
        print(
            f"{i+1:<4} {c['rule_id']:<40} {p_str:<8} {lag_str:<5} "
            f"{ext_str:>7} {nrm_str:>7} {c.get('n_extreme_events', 0):>6}"
        )
    print()


async def _run(args: argparse.Namespace) -> None:
    print("⏳ 후보 스캔 실행 중 (region × ticker 조합 전체 검정)...")
    print("   예상 소요: 30~120초 (티커 yfinance fallback 포함 시 더 길 수 있음)")

    candidates = await run_candidate_scan(p_threshold=args.p)
    _print_summary(candidates)

    yaml_text = generate_yaml_draft(candidates, top_n=args.top)

    if args.save:
        _DRAFT_PATH.write_text(yaml_text, encoding="utf-8")
        print(f"✅ YAML draft 저장: {_DRAFT_PATH}")
        print("   ★ 인간 승인 필수: 파일을 검토 후 cascade_rules.yaml로 이동할 것")
    else:
        print("─" * 70)
        print(yaml_text)
        print("─" * 70)
        print("\n💡 --save 옵션으로 YAML 파일을 저장할 수 있습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P4-4 Cascade 룰 자동 후보 생성 (Granger 스캔)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--top",  type=int,   default=10,
        help="YAML draft에 포함할 상위 후보 수 (기본: 10)",
    )
    parser.add_argument(
        "--p",    type=float, default=0.10,
        help="Granger p값 임계치 (기본: 0.10, 엄격: 0.05)",
    )
    parser.add_argument(
        "--save", action="store_true",
        help=f"YAML draft를 파일로 저장 ({_DRAFT_PATH.name})",
    )
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
