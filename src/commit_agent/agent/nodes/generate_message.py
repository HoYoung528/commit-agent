"""커밋 메시지를 생성하는 노드."""

from __future__ import annotations

from typing import Any

from commit_agent.agent.prompts import commit_message as prompts
from commit_agent.agent.schemas import CommitAgentState, CommitMessageDraft, draft_schema
from commit_agent.change_analysis import change_metrics, render_patches, summarize
from commit_agent.core.llm import LLMError, get_chat_model, translate_errors
from commit_agent.core.project_config import ProjectConfig

# 첫 줄 상한을 지키느라 제목이 이보다 짧아지면 scope를 포기한다
MIN_SUBJECT_LENGTH = 15


def generate_message_node(state: CommitAgentState) -> dict[str, Any]:
    """분석 결과를 근거로 LLM에게 커밋 메시지 조각을 받아 조립한다.

    이 노드가 실패하면 만들 메시지가 없으므로 `LLMError`를 그대로 올린다.
    """
    analysis = state.analysis
    if analysis is None or analysis.is_empty():
        return {"commit_message": ""}

    project = state.project
    allowed = project.allowed_types()

    model = get_chat_model().with_structured_output(draft_schema(allowed))
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": prompts.build_system_prompt(
                project.language,
                allowed,
                scopes=project.scopes,
                max_length=project.max_header_length,
            ),
        },
        {
            "role": "user",
            "content": prompts.build_user_prompt(
                summary=summarize(analysis),
                patches=render_patches(analysis),
                examples=prompts.build_examples(state.retrieved_commits),
                metrics=change_metrics(analysis),
            ),
        },
    ]

    with translate_errors():
        draft = _normalize(_invoke(model, messages), project)

        # 상한을 넘겼을 때 바로 잘라내면 문장이 중간에서 끊겨 `...to`,
        # `...and` 로 끝나는 제목이 된다. 내용을 덜어 다시 쓰게 한 번 더 묻는다.
        # 호출이 한 번 늘지만 넘기는 경우에만 발생한다
        if _over(draft, project) > 0:
            messages.append({
                "role": "user",
                "content": prompts.build_retry_prompt(
                    draft.header_prefix(), draft.subject, project.max_header_length
                ),
            })
            retried = _normalize(_invoke(model, messages), project)
            if _over(retried, project) <= 0:
                draft = retried

    draft = _fit(draft, project)

    return {"draft": draft, "commit_message": draft.render()}


def _invoke(model: Any, messages: list[dict[str, str]]) -> CommitMessageDraft:
    """모델을 부르고 원래 스키마로 옮겨 담는다.

    좁힌 스키마로 받았으면 타입이 별도 enum이므로 그대로 쓸 수 없다.
    """
    result = model.invoke(messages)
    if isinstance(result, CommitMessageDraft):
        result = result.model_dump(mode="json")
    return CommitMessageDraft.model_validate(result)


def _header(draft: CommitMessageDraft) -> str:
    return f"{draft.header_prefix()}{draft.subject}"


def _over(draft: CommitMessageDraft, project: ProjectConfig) -> int:
    """첫 줄이 상한을 넘은 글자 수. 넘지 않으면 0 이하."""
    return len(_header(draft)) - project.max_header_length


def _normalize(draft: CommitMessageDraft, project: ProjectConfig) -> CommitMessageDraft:
    """프롬프트로 알린 저장소 규칙을 결과에 다시 적용한다.

    LLM은 지시를 어길 수 있다. 고칠 수 있는 것은 고치고, 고칠 수 없으면 실패한다.
    길이는 여기서 건드리지 않는다 — 다시 묻는 기회를 주기 전에 자르면 안 된다.
    """
    commit_type = draft.type.value
    if not project.allows(commit_type):
        raise LLMError(
            f"이 저장소가 허용하지 않는 타입({commit_type})을 골랐습니다.",
            hint=f"다시 실행하거나 `.commit-agent.toml` 의 types 에 {commit_type} 를 추가하세요.",
        )

    if draft.scope and not project.allows_scope(draft.scope):
        draft = draft.model_copy(update={"scope": None})

    room = project.max_header_length - len(draft.header_prefix())
    if draft.scope and room < MIN_SUBJECT_LENGTH:
        # scope가 길어 제목 자리가 거의 없으면 scope를 버린다
        draft = draft.model_copy(update={"scope": None})

    return draft


def _fit(draft: CommitMessageDraft, project: ProjectConfig) -> CommitMessageDraft:
    """다시 물어도 상한을 넘으면 최후 수단으로 줄인다.

    scope를 먼저 버려 제목 자리를 넓힌다. 제목을 자르면 문장이 끊기지만
    scope는 빼도 문장이 남는다. 그래도 넘으면 자른다 — 훅 안에서 돌기 때문에
    여기서 실패하면 커밋 메시지가 비어 버린다.
    """
    if _over(draft, project) > 0 and draft.scope:
        draft = draft.model_copy(update={"scope": None})

    over = _over(draft, project)
    if over > 0:
        room = project.max_header_length - len(draft.header_prefix())
        draft = draft.model_copy(update={"subject": _shorten(draft.subject, room)})

    return draft


def _shorten(text: str, limit: int) -> str:
    """단어 중간에서 끊기지 않게 공백 기준으로 자른다. 공백이 없으면 글자 수로 자른다."""
    cut = text[:limit]
    if text[limit] != " " and " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip()
