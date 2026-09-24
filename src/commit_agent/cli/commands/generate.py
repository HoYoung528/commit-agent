"""`commit-agent generate` — 스테이징된 변경으로 커밋 메시지를 생성한다.

생성된 메시지만 stdout으로 내보내고 안내·에러는 stderr로 보낸다.
그래야 훅에서 `commit-agent generate > "$1"` 로 바로 쓸 수 있다.
"""

from __future__ import annotations

import typer

from commit_agent.agent import run
from commit_agent.cli.errors import fail, handle_errors
from commit_agent.core import get_settings
from commit_agent.core.project_config import load_project_config
from commit_agent.git_integration import get_remote_slug, get_staged_diff, open_repo
from commit_agent.git_integration.exceptions import NoStagedChangesError


@handle_errors
def generate() -> None:
    """스테이징된 변경으로 커밋 메시지를 생성합니다."""
    settings = get_settings()
    if not settings.has_anthropic_key():
        fail(
            "ANTHROPIC_API_KEY 가 설정되지 않았습니다.",
            hint="`.env` 파일에 키를 넣거나 환경변수로 설정하세요.",
        )

    repo = open_repo()
    diff_text = get_staged_diff(repo)
    if not diff_text.strip():
        raise NoStagedChangesError

    typer.secho("변경을 분석하는 중...", err=True, dim=True)
    state = run(
        diff_text,
        repo_slug=get_remote_slug(repo),
        project=load_project_config(),
    )

    if not state.commit_message:
        fail("커밋 메시지를 생성하지 못했습니다.")

    typer.echo(state.commit_message)
