"""diff를 분석해 상태에 담는 노드."""

from __future__ import annotations

from typing import Any

from commit_agent.agent.schemas import CommitAgentState
from commit_agent.change_analysis import analyze


def analyze_diff_node(state: CommitAgentState) -> dict[str, Any]:
    """staged diff 원문을 구조화된 분석 결과로 바꾼다."""
    return {"analysis": analyze(state.diff_text)}
