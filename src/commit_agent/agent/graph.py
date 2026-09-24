"""에이전트 그래프 조립과 실행.

지금은 `analyze → generate` 두 단계뿐이다. 이후 검색(RAG), 변경 유형 분류,
이슈 매핑, 신규 이슈 생성 제안 노드가 이 사이에 추가된다.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from commit_agent.agent.nodes import analyze_diff_node, generate_message_node
from commit_agent.agent.schemas import CommitAgentState
from commit_agent.core.project_config import ProjectConfig


def build_graph() -> CompiledStateGraph:
    """노드와 간선을 연결해 실행 가능한 그래프를 만든다."""
    builder = StateGraph(CommitAgentState)

    builder.add_node("analyze_diff", analyze_diff_node)
    builder.add_node("generate_message", generate_message_node)

    builder.add_edge(START, "analyze_diff")
    builder.add_edge("analyze_diff", "generate_message")
    builder.add_edge("generate_message", END)

    return builder.compile()


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
