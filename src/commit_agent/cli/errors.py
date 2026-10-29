"""CLI 에러 처리.

도메인 예외를 사람이 읽을 수 있는 메시지로 바꿔 stderr에 출력하고 종료한다.
traceback을 그대로 노출하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, NoReturn

import typer

from commit_agent.core.llm import LLMError
from commit_agent.core.project_config import ProjectConfigError
from commit_agent.git_integration.exceptions import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubRateLimitError,
    GitIntegrationError,
    NoStagedChangesError,
    NotAGitRepositoryError,
)

# 예외별 안내 문구. 원인만으로는 다음에 뭘 해야 할지 모르므로 행동을 함께 적는다.
_HINTS: dict[type[Exception], str] = {
    NotAGitRepositoryError: "git 저장소 안에서 실행하세요.",
    NoStagedChangesError: "`git add` 로 변경을 스테이징한 뒤 다시 실행하세요.",
    GitHubAuthError: "`.env` 의 GITHUB_TOKEN 과 그 권한을 확인하세요.",
    GitHubRateLimitError: "잠시 후 다시 시도하세요.",
    GitHubAPIError: "네트워크 연결을 확인하고 잠시 후 다시 시도하세요.",
    ProjectConfigError: "위 항목을 고친 뒤 다시 실행하세요.",
}


def hint_for(exc: Exception) -> str | None:
    """예외에 맞는 안내 문구. 없으면 None."""
    if isinstance(exc, LLMError):
        return exc.hint
    return _HINTS.get(type(exc))


def fail(message: str, *, hint: str | None = None, code: int = 1) -> NoReturn:
    """에러 메시지를 stderr에 출력하고 종료한다."""
    typer.secho(f"오류: {message}", fg=typer.colors.RED, err=True)
    if hint:
        typer.secho(f"  → {hint}", err=True)
    raise typer.Exit(code)


def handle_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """명령에서 발생한 도메인 예외를 안내 메시지로 바꾼다."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (GitIntegrationError, LLMError, ProjectConfigError) as exc:
            fail(str(exc), hint=hint_for(exc))
        except KeyboardInterrupt:
            fail("중단되었습니다.", code=130)

    return wrapper
