"""`commit-agent install` — prepare-commit-msg 훅을 설치한다.

`.git/hooks/` 는 저장소마다 로컬에만 있고 커밋되지 않으므로,
clone 한 사람은 각자 설치해야 한다.
"""

from __future__ import annotations

import typer

from commit_agent.cli.errors import handle_errors
from commit_agent.cli.hook import (
    HOOK_FILENAME,
    build_hook_script,
    hook_path,
    is_managed_hook,
)


@handle_errors
def install(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="다른 훅이 이미 있어도 덮어씁니다.",
    ),
) -> None:
    """prepare-commit-msg 훅을 설치합니다."""
    path = hook_path()

    if path.exists() and not is_managed_hook(path) and not force:
        typer.secho(f"이미 다른 {HOOK_FILENAME} 훅이 있습니다.", err=True)
        typer.secho(f"  → {path}", err=True, dim=True)
        typer.secho("  덮어쓰려면 --force 를 붙이세요.", err=True, dim=True)
        raise typer.Exit(1)

    replaced = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_hook_script(), encoding="utf-8", newline="\n")
    path.chmod(0o755)

    action = "교체했습니다" if replaced else "설치했습니다"
    typer.secho(f"훅을 {action}.", fg=typer.colors.GREEN)
    typer.secho(f"  → {path}", dim=True)
    typer.secho("  이제 `git commit` 시 커밋 메시지 초안이 자동으로 채워집니다.")
