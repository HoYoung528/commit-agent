"""커밋 메시지를 생성하는 노드."""

from __future__ import annotations

from typing import Any

from commit_agent.agent.prompts import build_system_prompt, build_user_prompt
from commit_agent.agent.schemas import CommitAgentState, CommitMessageDraft, CommitType
from commit_agent.change_analysis import render_patches, summarize
from commit_agent.core.llm import get_chat_model

_ALL_TYPES = [t.value for t in CommitType]


def generate_message_node(state: CommitAgentState) -> dict[str, Any]:
    """분석 결과를 근거로 LLM에게 커밋 메시지 조각을 받아 조립한다."""
    analysis = state.analysis
    if analysis is None or analysis.is_empty():
        return {"commit_message": ""}

    # 설정이 비어 있으면 전체 타입을 허용한다
    allowed = state.project.types or _ALL_TYPES

    model = get_chat_model().with_structured_output(CommitMessageDraft)
    draft = model.invoke(
        [
            {
                "role": "system",
                "content": build_system_prompt(state.project.language, allowed),
            },
            {
                "role": "user",
                "content": build_user_prompt(
                    summary=summarize(analysis),
                    patches=render_patches(analysis),
                ),
            },
        ]
    )

    if not isinstance(draft, CommitMessageDraft):
        draft = CommitMessageDraft.model_validate(draft)

    return {"draft": draft, "commit_message": draft.render()}
