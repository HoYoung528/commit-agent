"""커밋 메시지를 생성하는 노드."""

from __future__ import annotations

from typing import Any

from commit_agent.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from commit_agent.agent.schemas import CommitAgentState, CommitMessageDraft
from commit_agent.change_analysis import render_patches, summarize
from commit_agent.core.llm import get_chat_model


def generate_message_node(state: CommitAgentState) -> dict[str, Any]:
    """분석 결과를 근거로 LLM에게 커밋 메시지 조각을 받아 조립한다."""
    analysis = state.analysis
    if analysis is None or analysis.is_empty():
        return {"commit_message": ""}

    model = get_chat_model().with_structured_output(CommitMessageDraft)
    draft = model.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
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
