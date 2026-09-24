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


class GitHubRepositoryNotFoundError(GitIntegrationError):
    """저장소나 이슈를 찾을 수 없을 때."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"GitHub에서 찾을 수 없습니다: {slug}")
        self.slug = slug
