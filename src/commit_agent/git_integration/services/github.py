"""PyGithub으로 GitHub 이슈를 조회하고 생성한다.

토큰은 인자로 받는다. 설정에서 읽어오는 일은 호출하는 쪽(CLI 또는 서버)의 몫이며,
이렇게 해두면 서버로 옮길 때도 그대로 쓸 수 있다.

PyGithub 예외는 밖으로 내보내지 않고 `GitIntegrationError` 하위 타입으로 바꾼다.
원본 메시지는 응답 JSON이 통째로 찍혀 사람이 읽기 어렵다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from github import Auth, Github, GithubRetry
from github.GithubException import (
    BadCredentialsException,
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)

from commit_agent.git_integration.exceptions import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubRateLimitError,
    GitHubRepositoryNotFoundError,
)
from commit_agent.git_integration.schemas import IssueDraft, IssueInfo

if TYPE_CHECKING:
    from github.Issue import Issue
    from github.Repository import Repository

TIMEOUT_SECONDS = 15

# PyGithub 기본값은 10번 재시도하고, 한도에 걸리면 리셋 시각까지 상한 없이
# 기다린다. 훅 안에서는 커밋이 길게는 한 시간까지 멈출 수 있다.
# 몇 번만 빠르게 다시 보내고, 오래 기다려야 하면 포기한다.
#
# 이슈 생성(POST)은 재시도하지 않는다. 서버가 만들고 응답만 잃었으면
# 다시 보낼 때 이슈가 두 개 생긴다.
_RETRY = GithubRetry(
    total=3,
    backoff_factor=0.5,
    max_rate_limit_wait=10,
    allowed_methods=frozenset({"GET"}),
)


def open_github(token: str) -> Github:
    """personal access token으로 GitHub 클라이언트를 만든다."""
    if not token.strip():
        raise GitHubAuthError("GitHub 토큰이 비어 있습니다.")
    return Github(auth=Auth.Token(token), timeout=TIMEOUT_SECONDS, retry=_RETRY)


@contextmanager
def _translate_errors() -> Iterator[None]:
    """PyGithub·네트워크 예외를 도메인 예외로 바꾼다."""
    try:
        yield
    except BadCredentialsException as exc:
        raise GitHubAuthError("GitHub 토큰이 유효하지 않습니다.") from exc
    except RateLimitExceededException as exc:
        raise GitHubRateLimitError from exc
    except GithubException as exc:
        detail = _api_message(exc)
        raise GitHubAPIError(f"GitHub API 오류 ({exc.status}): {detail}", exc.status) from exc
    except OSError as exc:
        # requests의 연결·타임아웃 예외는 모두 OSError 하위 타입이다
        raise GitHubAPIError("GitHub에 연결할 수 없습니다.") from exc


def _api_message(exc: GithubException) -> str:
    """GitHub가 응답 본문에 담아 보낸 설명.

    `exc.message`는 PyGithub이 따로 붙이는 값이라 대개 비어 있다.
    """
    if isinstance(exc.data, dict) and exc.data.get("message"):
        return str(exc.data["message"])
    return exc.message or "응답 없음"


def get_repository(client: Github, slug: str) -> Repository:
    """`owner/name` 형식의 저장소를 가져온다."""
    with _translate_errors():
        try:
            return client.get_repo(slug)
        except UnknownObjectException as exc:
            raise GitHubRepositoryNotFoundError(slug) from exc


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

    # 목록은 순회하면서 페이지를 받아오므로 순회 전체를 감싼다
    with _translate_errors():
        for issue in repo.get_issues(state=state):
            if not include_pull_requests and issue.pull_request is not None:
                continue
            issues.append(_to_issue_info(issue))
            if len(issues) >= limit:
                break

    return issues


def get_issue(repo: Repository, number: int) -> IssueInfo:
    """이슈 하나를 번호로 읽어온다."""
    with _translate_errors():
        try:
            return _to_issue_info(repo.get_issue(number))
        except UnknownObjectException as exc:
            raise GitHubRepositoryNotFoundError(f"{repo.full_name}#{number}") from exc


def list_labels(repo: Repository) -> list[str]:
    """저장소에 정의된 라벨 이름 목록."""
    with _translate_errors():
        return [label.name for label in repo.get_labels()]


def create_issue(repo: Repository, draft: IssueDraft) -> IssueInfo:
    """초안대로 새 이슈를 만든다. 중복 생성을 피하려고 재시도하지 않는다."""
    with _translate_errors():
        try:
            issue = repo.create_issue(
                title=draft.title,
                body=draft.body,
                labels=draft.labels or [],
            )
        except UnknownObjectException as exc:
            # 쓰기 권한이 없는 토큰에는 GitHub가 403 대신 404를 준다
            raise GitHubAuthError("이 저장소에 이슈를 만들 권한이 없습니다.") from exc
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
