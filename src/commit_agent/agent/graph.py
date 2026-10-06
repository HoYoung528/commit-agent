"""에이전트 그래프 조립과 실행.

흐름은 분석 → 유사 사례 검색 → 메시지 생성 → 이슈 매핑으로 이어지며,
매핑되는 이슈가 없을 때만 신규 이슈 초안을 만드는 쪽으로 갈라진다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from commit_agent.agent.nodes import (
    analyze_diff_node,
    generate_message_node,
    map_issue_node,
    propose_issue_node,
    retrieve_context_node,
)
from commit_agent.agent.schemas import CommitAgentState
from commit_agent.core.project_config import ProjectConfig


def build_graph() -> CompiledStateGraph:
    """노드와 간선을 연결해 실행 가능한 그래프를 만든다."""
    builder = StateGraph(CommitAgentState)

    builder.add_node("analyze_diff", analyze_diff_node)
    builder.add_node("retrieve_context", retrieve_context_node)
    builder.add_node("generate_message", generate_message_node)
    builder.add_node("map_issue", map_issue_node)
    builder.add_node("propose_issue", propose_issue_node)

    builder.add_edge(START, "analyze_diff")
    builder.add_edge("analyze_diff", "retrieve_context")
    builder.add_edge("retrieve_context", "generate_message")
    builder.add_edge("generate_message", "map_issue")
    builder.add_conditional_edges(
        "map_issue",
        _needs_new_issue,
        {"propose_issue": "propose_issue", "done": END},
    )
    builder.add_edge("propose_issue", END)

    return builder.compile()


def _needs_new_issue(state: CommitAgentState) -> Literal["propose_issue", "done"]:
    """매핑된 이슈가 없으면 신규 이슈 초안을 만들러 간다."""
    return "done" if state.matched_issue else "propose_issue"


@lru_cache
def get_graph() -> CompiledStateGraph:
    """그래프를 한 번만 만들어 재사용한다."""
    return build_graph()


def run(
    diff_text: str,
    *,
    repo_slug: str | None = None,
    project: ProjectConfig | None = None,
) -> CommitAgentState:
    """diff 원문을 넣어 그래프를 끝까지 실행하고 최종 상태를 반환한다."""
    initial = CommitAgentState(
        diff_text=diff_text,
        repo_slug=repo_slug,
        project=project or ProjectConfig(),
    )
    result = get_graph().invoke(initial)
    return CommitAgentState.model_validate(result)
