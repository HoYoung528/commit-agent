"""이슈 초안을 사람에게 보여주고 GitHub에 등록한다."""

from __future__ import annotations

import sys

from commit_agent.core import get_settings
from commit_agent.git_integration import create_issue, get_repository, open_github
from commit_agent.git_integration.exceptions import GitHubAuthError
from commit_agent.git_integration.schemas import IssueDraft, IssueInfo


def render(draft: IssueDraft, *, indent: str = "  ") -> str:
    """사람이 확인할 수 있게 초안을 펼친다."""
    lines = [f"{indent}제목: {draft.title}"]
    if draft.labels:
        lines.append(f"{indent}라벨: {', '.join(draft.labels)}")

    body = draft.body.strip()
    if body:
        lines.append(f"{indent}본문:")
        lines.extend(f"{indent}  {line}" for line in body.splitlines())

    return "\n".join(lines)


def can_prompt() -> bool:
    """사용자에게 물어볼 수 있는 환경인지.

    훅은 IDE의 git 패널이나 CI에서도 실행되므로 입력이 없을 수 있다.
    """
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def create(draft: IssueDraft, repo_slug: str) -> IssueInfo:
    """초안으로 GitHub 이슈를 만든다."""
    settings = get_settings()
    if not settings.has_github_token():
        raise GitHubAuthError("GITHUB_TOKEN 이 설정되지 않았습니다.")

    gh_repo = get_repository(open_github(settings.github_token), repo_slug)
    return create_issue(gh_repo, draft)
