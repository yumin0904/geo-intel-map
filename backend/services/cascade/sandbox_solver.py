"""
sandbox_solver.py — 분석실(Sandbox) 사용자 가설 검증 엔진.

사용자가 노드(사건·지표)와 엣지(인과 연결)로 구성한 가설 캔버스를
기존 cascade_rules.yaml의 검증된 룰과 매칭하여 점수 산출.

목표:
1. 사용자 가설이 기존 룰의 부분집합인지 확인 (rule coverage)
2. 지정학적으로 타당한 인과 경로인지 평가 (theory match)
3. 개선 제안: 빠진 노드·엣지 추천
"""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass

from models.cascade import CascadeRule
from models.sandbox import SandboxCanvas, SandboxCanvasFull, SandboxEdge, SandboxNode
from services.cascade.rule_loader import load_rules


@dataclass
class VerificationResult:
    """사용자 가설 검증 결과."""
    canvas_id: str
    total_score: float           # 0-1: 전체 가설과 룰북의 매칭도
    rule_matches: list[RuleMatch]
    gaps: list[str]              # 개선 제안 (빠진 경로)
    theory_tags_found: set[str]  # 사용자 가설에서 찾은 이론 태그
    confidence_level: str        # "high" / "medium" / "low"


@dataclass
class RuleMatch:
    """단일 룰과의 매칭 결과."""
    rule_id: str
    rule_name: str
    match_score: float           # 0-1: 이 룰과의 유사도
    matched_path: list[str]      # 매칭된 노드 경로 (id 리스트)
    missing_nodes: list[str]     # 룰에는 있지만 사용자 가설에 없는 노드
    theory_framework: str


def verify_sandbox_hypothesis(canvas: SandboxCanvasFull | dict) -> VerificationResult:
    """
    사용자 캔버스 가설을 검증하고 점수 산출.

    1단계: 노드·엣지 그래프 추출
    2단계: 각 룰과 그래프 동형 비교
    3단계: 매칭도 + 이론 일관성 점수 계산
    4단계: 빠진 경로 제안
    """
    rules = load_rules()

    # 사용자 캔버스 구조화
    user_graph = _build_graph(canvas.nodes, canvas.edges)
    theory_tags_found = _extract_theory_tags(canvas.nodes)

    # 각 룰과 매칭
    rule_matches = []
    for rule in rules:
        match = _match_rule(user_graph, rule, canvas.nodes)
        if match:
            rule_matches.append(match)

    # 정렬: 점수 내림차순
    rule_matches.sort(key=lambda m: m.match_score, reverse=True)

    # 전체 점수 계산
    total_score = _aggregate_score(rule_matches)
    confidence = _assess_confidence(len(rule_matches), total_score)

    # 개선 제안 (상위 3개 룰에서 빠진 경로)
    gaps = _suggest_improvements(rule_matches, user_graph)

    return VerificationResult(
        canvas_id=canvas.canvas.id,
        total_score=total_score,
        rule_matches=rule_matches,
        gaps=gaps,
        theory_tags_found=theory_tags_found,
        confidence_level=confidence,
    )


def _build_graph(nodes: list[SandboxNode], edges: list[SandboxEdge]) -> dict:
    """
    캔버스 노드·엣지를 인접 리스트 그래프로 변환.
    {node_id: {"type": ..., "neighbors": [target_ids], "label": ...}}
    """
    graph = {}
    for node in nodes:
        graph[node.id] = {
            "type": node.node_type,
            "label": node.label,
            "region_code": node.region_code,
            "theory_tags": node.theory_tags,
            "neighbors": [],
        }

    for edge in edges:
        if edge.source_node_id in graph:
            graph[edge.source_node_id]["neighbors"].append(
                (edge.target_node_id, edge.kind)
            )

    return graph


def _extract_theory_tags(nodes: list[SandboxNode]) -> set[str]:
    """사용자 캔버스의 모든 노드에 붙은 이론 태그 수집."""
    tags = set()
    for node in nodes:
        tags.update(node.theory_tags)
    return tags


def _match_rule(user_graph: dict, rule: CascadeRule, nodes: list[SandboxNode]) -> Optional[RuleMatch]:
    """
    단일 룰과 사용자 가설 그래프의 패턴 매칭.

    1단계: 룰의 trigger region과 일치하는 노드 찾기
    2단계: trigger node에서 시작해 경로 추적
    3단계: 경로 끝이 expected response와 일치하는가?
    """
    # 룰이 요구하는 trigger 지역
    rule_region = rule.trigger.region

    # 사용자 그래프에서 이 지역 노드 찾기
    trigger_candidates = [
        (nid, node) for nid, node in user_graph.items()
        if node["region_code"] == rule_region and node["type"] in ("event", "indicator")
    ]

    if not trigger_candidates:
        return None  # 지역 매칭 실패

    best_path = None
    best_score = 0.0
    matched_node_ids = []

    # 각 후보에서 경로 탐색
    for trigger_id, trigger_node in trigger_candidates:
        # BFS: trigger에서 시작해 response node 찾기
        paths = _find_causal_paths(user_graph, trigger_id, max_depth=3)

        for path_nodes in paths:
            # 경로 끝의 노드가 지표(market indicator)인가?
            terminal_id = path_nodes[-1]
            terminal_node = user_graph[terminal_id]

            if terminal_node["type"] == "indicator":
                # 점수: 경로 길이 · 이론 태그 일관성
                path_score = _compute_path_score(rule, path_nodes, user_graph)

                if path_score > best_score:
                    best_score = path_score
                    best_path = path_nodes
                    matched_node_ids = path_nodes

    if best_path is None or best_score < 0.3:
        return None  # 충분히 좋은 경로 없음

    # 빠진 노드 진단: 룰에서 요구하지만 사용자 그래프에 없는 중간 단계
    missing_nodes = _diagnose_missing_nodes(rule, best_path, user_graph)

    return RuleMatch(
        rule_id=rule.id,
        rule_name=rule.name,
        match_score=best_score,
        matched_path=matched_node_ids,
        missing_nodes=missing_nodes,
        theory_framework=rule.theory.framework,
    )


def _find_causal_paths(graph: dict, start_node_id: str, max_depth: int = 3) -> list[list[str]]:
    """
    BFS를 사용해 start_node에서 도달 가능한 모든 경로 찾기.
    각 경로는 노드 ID 리스트.
    """
    paths = []
    visited = set()

    def dfs(current: str, path: list[str], depth: int):
        if depth > max_depth:
            return

        path.append(current)

        # 경로 저장 (1 이상 길이)
        if len(path) > 1:
            paths.append(path[:])

        # 이웃 탐색
        if current in graph:
            for neighbor_id, _ in graph[current]["neighbors"]:
                if neighbor_id not in visited or depth < 2:  # 약간의 순환 허용 (제한적)
                    old_visited = visited.copy()
                    visited.add(neighbor_id)
                    dfs(neighbor_id, path, depth + 1)
                    visited.clear()
                    visited.update(old_visited)

        path.pop()

    dfs(start_node_id, [], 0)
    return paths


def _compute_path_score(rule: CascadeRule, path: list[str], graph: dict) -> float:
    """
    경로와 룰의 일치도 점수 계산.

    요인:
    - 경로 길이 (1단계 = 1.0, 2단계 = 0.8, ...)
    - 이론 태그 오버랩
    - trigger region 정확도
    """
    # 기본: 경로 길이 패널티
    depth_penalty = max(0.3, 1.0 - (len(path) - 2) * 0.15)

    # 이론 태그 매칭
    theory_overlap = 0.0
    rule_theories = set(rule.theory.framework.split())
    user_theories = set()

    for node_id in path:
        if node_id in graph:
            user_theories.update(graph[node_id]["theory_tags"])

    if rule_theories and user_theories:
        theory_overlap = len(rule_theories & user_theories) / len(rule_theories | user_theories)

    # 최종 점수: 경로 일관성 × 이론 일관성
    score = depth_penalty * (0.7 + 0.3 * theory_overlap)

    return min(1.0, score)


def _diagnose_missing_nodes(rule: CascadeRule, matched_path: list[str], graph: dict) -> list[str]:
    """
    룰에서는 명시된 trigger/response 구조가
    사용자 그래프에 완전히 반영되었는지 진단.

    빠진 것이 있으면 추천 (예: "중간에 공급망 위기 노드 추가 필요")
    """
    missing = []

    # 규칙상 trigger → response의 중간 단계가 있는가?
    if len(matched_path) == 2:
        # 직접 연결: 중간 노드 추가 제안
        missing.append(
            f"'{rule.trigger.region}' 긴장과 '{rule.expected_response.ticker}' 사이에 "
            f"중간 전달 메커니즘(공급망, 시장 심리 등) 노드 추가 권장"
        )

    return missing


def _aggregate_score(rule_matches: list[RuleMatch]) -> float:
    """
    여러 룰 매칭 결과를 종합해 전체 가설 점수 계산.

    상위 3개 룰의 평균 (상위 매칭이 강할수록 높은 점수)
    """
    if not rule_matches:
        return 0.0

    top_n = min(3, len(rule_matches))
    avg_score = sum(m.match_score for m in rule_matches[:top_n]) / top_n

    return avg_score


def _assess_confidence(num_matches: int, total_score: float) -> str:
    """
    검증 신뢰도 평가.

    high: 2개 이상 룰 매칭 + score ≥ 0.7
    medium: 1개 룰 매칭 또는 score ≥ 0.5
    low: 매칭 부족 또는 score < 0.5
    """
    if num_matches >= 2 and total_score >= 0.7:
        return "high"
    elif num_matches >= 1 and total_score >= 0.5:
        return "medium"
    else:
        return "low"


def _suggest_improvements(rule_matches: list[RuleMatch], user_graph: dict) -> list[str]:
    """
    상위 매칭 규칙을 기반으로 사용자 가설 개선 제안.

    예: "대만해협 긴장 → TSMC 주가 차이. 이 사이에 반도체 공급망 위기를 추가해 보세요."
    """
    suggestions = []

    for match in rule_matches[:3]:  # 상위 3개 규칙만
        suggestions.extend(match.missing_nodes)

    # 중복 제거
    suggestions = list(set(suggestions))

    return suggestions[:5]  # 최대 5개 제안
