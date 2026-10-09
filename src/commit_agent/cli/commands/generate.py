"""`commit-agent generate` — 스테이징된 변경으로 커밋 메시지를 생성한다.

생성된 메시지만 stdout으로 내보내고 안내·에러는 stderr로 보낸다.
그래야 훅에서 `commit-agent generate > "$1"` 로 바로 쓸 수 있다.
"""

from __future__ import annotations

import typer

from commit_agent.agent import run
from commit_agent.agent.schemas import CommitAgentState
from commit_agent.cli.errors import fail, handle_errors
from commit_agent.core import api_key_for, get_settings
from commit_agent.core.project_config import load_project_config
from commit_agent.git_integration import get_remote_slug, get_staged_diff, open_repo
from commit_agent.git_integration.exceptions import NoStagedChangesError


@handle_errors
def generate() -> None:
    """스테이징된 변경으로 커밋 메시지를 생성합니다."""
    settings = get_settings()
    if not api_key_for(settings):
        provider = settings.model.split(":", 1)[0]
        fail(
            f"{provider} 제공자의 API 키가 설정되지 않았습니다.",
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
    _report_issue(state)


def _report_issue(state: CommitAgentState) -> None:
    """매핑 결과나 이슈 초안을 stderr로 안내한다.

    stdout은 커밋 메시지 전용이므로 여기 섞지 않는다.
    """
    if state.matched_issue:
        typer.secho(
            f"\n관련 이슈를 찾았습니다: {state.matched_issue.reference()} "
            f"{state.matched_issue.title}",
            fg=typer.colors.GREEN,
            err=True,
        )
        return

    draft = state.issue_draft
    if draft is None:
        return

    typer.secho("\n관련된 이슈가 없습니다. 아래 내용으로 이슈를 만들 만합니다.", err=True)
    typer.secho(f"  제목: {draft.title}", err=True)
    if draft.labels:
        typer.secho(f"  라벨: {', '.join(draft.labels)}", err=True)
