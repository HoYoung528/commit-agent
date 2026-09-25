"""`commit-agent uninstall` — 설치된 훅을 제거한다."""

from __future__ import annotations

import typer

from commit_agent.cli.errors import handle_errors
from commit_agent.cli.hook import HOOK_FILENAME, hook_path, is_managed_hook


@handle_errors
def uninstall() -> None:
    """설치된 훅을 제거합니다."""
    path = hook_path()

    if not path.exists():
        typer.secho("설치된 훅이 없습니다.", err=True)
        raise typer.Exit

    if not is_managed_hook(path):
        typer.secho(f"{HOOK_FILENAME} 훅이 commit-agent 것이 아닙니다.", err=True)
        typer.secho(f"  → {path}", err=True, dim=True)
        typer.secho("  직접 확인한 뒤 지우세요.", err=True, dim=True)
        raise typer.Exit(1)

    path.unlink()
    typer.secho("훅을 제거했습니다.", fg=typer.colors.GREEN)
    typer.secho(f"  → {path}", dim=True)
