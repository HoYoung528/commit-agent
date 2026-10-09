"""매핑되는 이슈가 없을 때 새 이슈를 제안하는 노드.

초안만 만들고 실제 생성은 하지 않는다. 커밋할 때마다 저장소에 이슈가
생기면 되돌리기 어려우므로, 생성 여부는 사용자가 확인한 뒤 결정한다.

모든 변경이 이슈가 되어야 하는 것은 아니다. 오타 수정이나 포맷팅처럼
추적할 필요가 없는 변경이면 초안을 만들지 않는다.
"""

from __future__ import annotations

from typing import Any

from commit_agent.agent.prompts import issue_draft as prompts
from commit_agent.agent.schemas import CommitAgentState, IssueProposal
from commit_agent.change_analysis import summarize
from commit_agent.core import get_settings
from commit_agent.core.llm import get_chat_model
from commit_agent.git_integration import get_repository, list_labels, open_github
from commit_agent.git_integration.schemas import IssueDraft

_SKIPPED: dict[str, Any] = {"issue_draft": None}


def propose_issue_node(state: CommitAgentState) -> dict[str, Any]:
    """새로 만들 이슈의 초안을 작성한다."""
    message = state.commit_message
    analysis = state.analysis
    if not message or analysis is None or analysis.is_empty():
        return _SKIPPED

    labels = _available_labels(state.repo_slug)
    proposal = _draft(message, summarize(analysis), labels, state.project.language)

    if not proposal.worth_tracking or not proposal.title.strip():
        return _SKIPPED

    return {
        "issue_draft": IssueDraft(
            title=proposal.title.strip(),
            body=proposal.body.strip(),
            # LLM이 없는 라벨을 지어낼 수 있으므로 실제 목록과 대조한다
            labels=[label for label in proposal.labels if label in labels],
        )
    }


def _available_labels(repo_slug: str | None) -> list[str]:
    """저장소에 정의된 라벨. 조회에 실패하면 라벨 없이 진행한다."""
    settings = get_settings()
    if not repo_slug or not settings.has_github_token():
        return []

    try:
        gh_repo = get_repository(open_github(settings.github_token), repo_slug)
        return list_labels(gh_repo)
    except Exception:
        return []


def _draft(
    message: str, summary: str, labels: list[str], language: str
) -> IssueProposal:
    """이슈로 남길 가치가 있는지 묻고, 있으면 초안을 받는다."""
    model = get_chat_model().with_structured_output(IssueProposal)
    result = model.invoke(
        [
            {"role": "system", "content": prompts.build_system_prompt(language)},
            {
                "role": "user",
                "content": prompts.build_user_prompt(message, summary, labels),
            },
        ]
    )

    if isinstance(result, IssueProposal):
        return result
    return IssueProposal.model_validate(result)
