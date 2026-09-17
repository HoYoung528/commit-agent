"""git·GitHub 연동 서비스."""

from commit_agent.git_integration.services.github import (
    create_issue,
    get_issue,
    get_repository,
    list_issues,
    list_labels,
    open_github,
)
from commit_agent.git_integration.services.repo import (
    get_commit_diff,
    get_commit_history,
    get_remote_slug,
    get_staged_diff,
    has_staged_changes,
    open_repo,
)

__all__ = [
    "create_issue",
    "get_commit_diff",
    "get_commit_history",
    "get_issue",
    "get_remote_slug",
    "get_repository",
    "get_staged_diff",
    "has_staged_changes",
    "list_issues",
    "list_labels",
    "open_github",
    "open_repo",
]
