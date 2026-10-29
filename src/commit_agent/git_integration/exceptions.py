"""git·GitHub 연동 과정에서 발생하는 예외."""

from __future__ import annotations


class GitIntegrationError(Exception):
    """git·GitHub 연동 관련 예외의 최상위 타입."""


class NotAGitRepositoryError(GitIntegrationError):
    """대상 경로가 git 저장소가 아닐 때."""

    def __init__(self, path: str) -> None:
        super().__init__(f"git 저장소가 아닙니다: {path}")
        self.path = path


class NoStagedChangesError(GitIntegrationError):
    """staged 변경이 하나도 없을 때."""

    def __init__(self) -> None:
        super().__init__("스테이징된 변경이 없습니다.")


class GitHubAuthError(GitIntegrationError):
    """GitHub 토큰이 없거나 유효하지 않을 때."""


class GitHubRateLimitError(GitIntegrationError):
    """GitHub API 요청 한도를 넘었을 때."""

    def __init__(self) -> None:
        super().__init__("GitHub API 요청 한도를 넘었습니다.")


class GitHubAPIError(GitIntegrationError):
    """재시도 끝에도 GitHub API 호출이 실패했을 때. 연결 실패면 status는 None."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubRepositoryNotFoundError(GitIntegrationError):
    """저장소나 이슈를 찾을 수 없을 때."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"GitHub에서 찾을 수 없습니다: {slug}")
        self.slug = slug
