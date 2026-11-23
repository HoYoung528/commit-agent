"""`commit-agent generate` — 스테이징된 변경으로 커밋 메시지를 생성한다.

생성된 메시지만 stdout으로 내보내고 안내·에러는 stderr로 보낸다.
그래야 훅에서 `commit-agent generate > "$1"` 로 바로 쓸 수 있다.

관련 이슈가 없으면 이 자리에서 새 이슈를 만들 수 있다. 이슈를 먼저 만들어야
번호를 메시지에 넣을 수 있으므로, 메시지 출력은 이슈 처리가 끝난 뒤에 한다.

기본 브랜치에 있으면 이슈 번호로 브랜치를 만들고 전환한다. 훅은 커밋이
만들어지기 전에 실행되므로, 여기서 전환하면 커밋이 새 브랜치에 들어간다.
"""

from __future__ import annotations

import typer

from commit_agent.agent.schemas import with_reference
from commit_agent.cli import backend, branch, issue_draft
from commit_agent.cli.errors import fail, handle_errors, hint_for
from commit_agent.core import api_key_for, get_settings
from commit_agent.core.project_config import ProjectConfig, load_project_config
from commit_agent.git_integration import (
    collect_branch_names,
    get_remote_slug,
    get_staged_diff,
    open_repo,
)
from commit_agent.git_integration.exceptions import NoStagedChangesError
from commit_agent.server.schemas import GenerateResponse


@handle_errors
def generate() -> None:
    """스테이징된 변경으로 커밋 메시지를 생성합니다."""
    settings = get_settings()
    # 서버에 맡기면 모델 API 키가 서버에만 있으면 된다
    if not settings.uses_server() and not api_key_for(settings):
        provider = settings.model.split(":", 1)[0]
        fail(
            f"{provider} 제공자의 API 키가 설정되지 않았습니다.",
            hint="`.env` 파일에 키를 넣거나 환경변수로 설정하세요.",
        )

    repo = open_repo()
    diff_text = get_staged_diff(repo)
    if not diff_text.strip():
        raise NoStagedChangesError

    # 설정이 잘못됐으면 LLM을 부르기 전에 멈춘다
    project = load_project_config()

    typer.secho("변경을 분석하는 중...", err=True, dim=True)
    repo_slug = get_remote_slug(repo)
    result = backend.generate(
        diff_text,
        repo_slug=repo_slug,
        project=project,
        # 브랜치 이름을 지을 때 규칙을 배울 예시다. 로컬 git에서만 모을 수 있다
        branch_names=collect_branch_names(repo) if project.branch_suggest else [],
        settings=settings,
    )
    _report_redactions(result)

    if not result.commit_message:
        fail("커밋 메시지를 생성하지 못했습니다.")

    message, _ = _resolve_issue(result, result.commit_message, repo_slug, project)

    if result.draft and project.branch_suggest:
        # 이름은 생성 단계에서 이미 지어져 있다. 그 시점에 알 수 있는 이슈
        # 번호는 매핑된 기존 이슈까지이므로, 바로 위에서 새로 만든 이슈의
        # 번호는 이름에 들어가지 않는다. 사용자가 확인 단계에서 고칠 수 있다
        branch.maybe_switch(repo, result.branch_name)

    typer.echo(message)


def _report_redactions(result: GenerateResponse) -> None:
    """민감정보로 보여 LLM에 보내지 않은 항목을 알린다.

    가린 것은 LLM에 보낸 쪽뿐이다. 커밋에는 그대로 들어가므로 사용자가
    알아야 커밋 전에 스테이징을 고칠 수 있다.
    """
    if not result.secret_files and not result.masked:
        return

    typer.secho(
        "\n민감정보로 보이는 내용을 LLM에 보내지 않았습니다. 커밋에는 그대로 포함됩니다.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    if result.secret_files:
        typer.secho("  본문을 뺀 파일: " + ", ".join(result.secret_files), err=True)
    if result.masked:
        masked = ", ".join(f"{path} ({n}건)" for path, n in result.masked.items())
        typer.secho("  값을 가린 파일: " + masked, err=True)


def _resolve_issue(
    result: GenerateResponse,
    message: str,
    repo_slug: str | None,
    project: ProjectConfig,
) -> tuple[str, int | None]:
    """이슈 연결을 마치고 최종 커밋 메시지와 이슈 번호를 돌려준다.

    매핑된 이슈가 있으면 참조는 이미 붙어 있다. 없으면 새로 만들지 묻는다.
    """
    if result.matched_issue:
        typer.secho(
            f"\n관련 이슈: {result.matched_issue.reference()} {result.matched_issue.title}",
            fg=typer.colors.GREEN,
            err=True,
        )
        return message, result.matched_issue.number

    draft = result.issue_draft
    if draft is None:
        return message, None

    typer.secho("\n관련된 이슈가 없습니다. 아래 내용으로 만들 수 있습니다.", err=True)
    typer.secho(issue_draft.render(draft), err=True)

    if not (repo_slug and issue_draft.can_prompt()):
        return message, None

    if not _confirmed():
        return message, None

    try:
        issue = issue_draft.create(draft, repo_slug)
    except Exception as exc:
        # 등록에 실패해도 커밋은 진행되어야 한다
        typer.secho(f"이슈 생성에 실패했습니다: {exc}", fg=typer.colors.RED, err=True)
        if hint := hint_for(exc):
            typer.secho(f"  → {hint}", err=True)
        return message, None

    typer.secho(f"이슈를 만들었습니다: {issue.url}", fg=typer.colors.GREEN, err=True)
    linked = with_reference(message, issue.reference(), project.reference_format)
    return linked, issue.number


def _confirmed() -> bool:
    """이슈를 만들지 묻는다. 입력을 읽을 수 없으면 만들지 않는다.

    훅에서 예외가 올라가면 메시지 없이 커밋되므로 여기서 막는다.
    """
    try:
        return typer.confirm("\n이슈를 만들까요?", default=False, err=True)
    except (typer.Abort, EOFError):
        return False
