"""CLI 에러 처리.

도메인 예외를 사람이 읽을 수 있는 메시지로 바꿔 stderr에 출력하고 종료한다.
traceback을 그대로 노출하지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import typer

from commit_agent.git_integration.exceptions import (
    GitHubAuthError,
    GitIntegrationError,
    NoStagedChangesError,
    NotAGitRepositoryError,
)

# 예외별 안내 문구. 원인만으로는 다음에 뭘 해야 할지 모르므로 행동을 함께 적는다.
_HINTS: dict[type[Exception], str] = {
    NotAGitRepositoryError: "git 저장소 안에서 실행하세요.",
    NoStagedChangesError: "`git add` 로 변경을 스테이징한 뒤 다시 실행하세요.",
    GitHubAuthError: "`.env` 의 GITHUB_TOKEN 을 확인하세요.",
}


def fail(message: str, *, hint: str | None = None, code: int = 1) -> None:
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
        except GitIntegrationError as exc:
            fail(str(exc), hint=_HINTS.get(type(exc)))
        except KeyboardInterrupt:
            fail("중단되었습니다.", code=130)

    return wrapper
