"""
8단계 지정학 추론 엔진.

사용자가 이벤트를 선택하면 8개 분석 단계를 병렬/순차로 실행하고
구조화된 ReasoningReport를 반환한다.

각 단계는 독립적으로 실패할 수 있다 (partial report 허용).
"""
from .engine import ReasoningEngine, run_reasoning

__all__ = ["ReasoningEngine", "run_reasoning"]
