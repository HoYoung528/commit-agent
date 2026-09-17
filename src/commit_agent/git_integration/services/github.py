"""PyGithub으로 GitHub 이슈를 조회하고 생성한다.

토큰은 인자로 받는다. 설정에서 읽어오는 일은 호출하는 쪽(CLI 또는 서버)의 몫이며,
이렇게 해두면 서버로 옮길 때도 그대로 쓸 수 있다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from github import Auth, Github
from github.GithubException import BadCredentialsException, UnknownObjectException

from commit_agent.git_integration.exceptions import (
    GitHubAuthError,
    GitHubRepositoryNotFoundError,
)
from commit_agent.git_integration.schemas import IssueDraft, IssueInfo

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.Repository import Repository


def open_github(token: str) -> Github:
    """personal access token으로 GitHub 클라이언트를 만든다."""
    if not token.strip():
        raise GitHubAuthError("GitHub 토큰이 비어 있습니다.")
    return Github(auth=Auth.Token(token))


def get_repository(client: Github, slug: str) -> Repository:
    """`owner/name` 형식의 저장소를 가져온다."""
    try:
        return client.get_repo(slug)
    except UnknownObjectException as exc:
        raise GitHubRepositoryNotFoundError(slug) from exc
    except BadCredentialsException as exc:
        raise GitHubAuthError("GitHub 토큰이 유효하지 않습니다.") from exc


def list_issues(
    repo: Repository,
    *,
    state: str = "open",
    limit: int = 100,
    include_pull_requests: bool = False,
) -> list[IssueInfo]:
    """이슈 목록을 읽어온다.

    GitHub API는 pull request도 이슈로 돌려주므로 기본적으로 걸러낸다.
    """
    issues: list[IssueInfo] = []

    for issue in repo.get_issues(state=state):
        if not include_pull_requests and issue.pull_request is not None:
            continue
        issues.append(_to_issue_info(issue))
        if len(issues) >= limit:
            break

    return issues


def get_issue(repo: Repository, number: int) -> IssueInfo:
    """이슈 하나를 번호로 읽어온다."""
    try:
        return _to_issue_info(repo.get_issue(number))
    except UnknownObjectException as exc:
        raise GitHubRepositoryNotFoundError(f"{repo.full_name}#{number}") from exc


def list_labels(repo: Repository) -> list[str]:
    """저장소에 정의된 라벨 이름 목록."""
    return [label.name for label in repo.get_labels()]


def create_issue(repo: Repository, draft: IssueDraft) -> IssueInfo:
    """초안대로 새 이슈를 만든다."""
    issue = repo.create_issue(
        title=draft.title,
        body=draft.body,
        labels=draft.labels or [],
    )
    return _to_issue_info(issue)


def _to_issue_info(issue: Issue) -> IssueInfo:
    """PyGithub의 Issue 객체를 직렬화 가능한 스키마로 옮긴다."""
    return IssueInfo(
        number=issue.number,
        title=issue.title,
        body=issue.body or "",
        state=issue.state,
        labels=[label.name for label in issue.labels],
        url=issue.html_url,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )
