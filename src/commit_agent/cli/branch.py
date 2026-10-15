"""이슈를 근거로 브랜치 이름을 짓고 전환한다.

기본 브랜치에 있을 때만 제안한다. 작업 중인 브랜치에서 또 분기하면 곤란하다.
커밋 전에 전환하므로, 커밋을 중단하면 브랜치만 남는다.
"""

from __future__ import annotations

import sys

import typer
from git import Repo

from commit_agent.agent.prompts import branch_name as prompts
from commit_agent.agent.schemas import BranchNameSuggestion
from commit_agent.core.llm import get_chat_model
from commit_agent.git_integration import (
    branch_exists,
    collect_branch_names,
    create_and_switch,
    is_valid_name,
    on_default_branch,
)


def maybe_switch(
    repo: Repo, commit_type: str, subject: str, issue_number: int | None
) -> str | None:
    """새 브랜치를 제안하고 전환한다. 전환하지 않았으면 None.

    실패해도 커밋은 진행되어야 하므로 예외를 밖으로 내보내지 않는다.
    """
    if not on_default_branch(repo) or not _can_prompt():
        return None

    try:
        name = _suggest(repo, commit_type, subject, issue_number)
    except Exception:
        return None

    if not name:
        return None

    chosen = _decide(repo, name)
    if not chosen:
        return None

    existing = branch_exists(repo, chosen)
    try:
        create_and_switch(repo, chosen)
    except Exception as exc:
        typer.secho(f"브랜치 전환에 실패했습니다: {exc}", fg=typer.colors.RED, err=True)
        return None

    typer.secho(f"{chosen} 로 전환했습니다.", fg=typer.colors.GREEN, err=True)
    if not existing:
        typer.secho(f"  커밋을 취소하면 `git branch -d {chosen}` 로 지우세요.", err=True)

    return chosen


def _decide(repo: Repo, suggested: str) -> str | None:
    """쓸 브랜치 이름을 확정한다. 만들지 않기로 하면 None.

    제안한 이름을 고칠 기회를 주고 나서 확인을 받는다.
    그대로 쓸 거면 Enter 두 번이다.
    """
    typed = _ask("\n브랜치 이름", suggested)
    if typed is None:
        return None

    name = typed.strip()
    if not is_valid_name(repo, name):
        typer.secho(
            f"브랜치 이름으로 쓸 수 없습니다: {name}", fg=typer.colors.RED, err=True
        )
        return None

    action = "로 전환" if branch_exists(repo, name) else "를 만들고 전환"
    return name if _confirm(f"{name} {action}할까요?") else None


def _ask(text: str, default: str) -> str | None:
    """제안을 기본값으로 보여주고 입력을 받는다. 읽을 수 없으면 None."""
    try:
        return typer.prompt(text, default=default, err=True)
    except (typer.Abort, EOFError):
        return None


def _suggest(
    repo: Repo, commit_type: str, subject: str, issue_number: int | None
) -> str | None:
    """저장소가 써온 이름을 예시로 주고 새 이름을 받는다."""
    names = collect_branch_names(repo)
    if not names:
        # 규칙을 배울 예시가 없으면 이름을 지어내지 않는다
        return None

    model = get_chat_model().with_structured_output(BranchNameSuggestion)
    result = model.invoke(
        [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": prompts.build_user_prompt(
                    names, commit_type, subject, issue_number
                ),
            },
        ]
    )

    if not isinstance(result, BranchNameSuggestion):
        result = BranchNameSuggestion.model_validate(result)

    name = result.name.strip()
    return name if is_valid_name(repo, name) else None


def _can_prompt() -> bool:
    """사용자에게 물어볼 수 있는 환경인지."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _confirm(text: str) -> bool:
    """맘에 들면 Enter로 넘어가도록 기본값을 '예'로 둔다.

    입력을 읽을 수 없으면 브랜치를 만들지 않는다.
    """
    try:
        return typer.confirm(text, default=True, err=True)
    except (typer.Abort, EOFError):
        return False
