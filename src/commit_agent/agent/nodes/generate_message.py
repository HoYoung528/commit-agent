"""커밋 메시지를 생성하는 노드.

아직 구현되지 않았다. 그래프 배선을 확인하기 위한 자리표시자이며,
이슈 #6에서 프롬프트 구성과 LLM 호출로 교체된다.
"""

from __future__ import annotations

from typing import Any

from commit_agent.agent.schemas import CommitAgentState

PLACEHOLDER_MESSAGE = "(커밋 메시지 생성 미구현 — 이슈 #6)"


def generate_message_node(state: CommitAgentState) -> dict[str, Any]:
    """분석 결과를 받아 커밋 메시지를 만든다."""
    if state.analysis is None or state.analysis.is_empty():
        return {"commit_message": ""}

    return {"commit_message": PLACEHOLDER_MESSAGE}
