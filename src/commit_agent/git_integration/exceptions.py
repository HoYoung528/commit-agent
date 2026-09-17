"""git 연동 과정에서 발생하는 예외."""

from __future__ import annotations


class GitIntegrationError(Exception):
    """git 연동 관련 예외의 최상위 타입."""


class NotAGitRepositoryError(GitIntegrationError):
    """대상 경로가 git 저장소가 아닐 때."""

    def __init__(self, path: str) -> None:
        super().__init__(f"git 저장소가 아닙니다: {path}")
        self.path = path


class NoStagedChangesError(GitIntegrationError):
    """staged 변경이 하나도 없을 때."""

    def __init__(self) -> None:
        super().__init__("staged 변경이 없습니다. `git add` 로 변경을 스테이징하세요.")
