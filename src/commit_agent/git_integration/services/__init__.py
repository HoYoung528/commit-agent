"""git·GitHub 연동 서비스."""

from commit_agent.git_integration.services.branch import (
    branch_exists,
    collect_branch_names,
    create_and_switch,
    current_branch,
    is_valid_name,
    on_default_branch,
)
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
    "branch_exists",
    "collect_branch_names",
    "create_and_switch",
    "create_issue",
    "current_branch",
    "get_commit_diff",
    "get_commit_history",
    "get_issue",
    "get_remote_slug",
    "get_repository",
    "get_staged_diff",
    "has_staged_changes",
    "is_valid_name",
    "list_issues",
    "list_labels",
    "on_default_branch",
    "open_github",
    "open_repo",
]
