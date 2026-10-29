"""`commit-agent init` — 저장소에 설정 파일을 만든다."""

from __future__ import annotations

import sys
from pathlib import Path

import questionary
import typer

from commit_agent.agent.schemas import CommitType
from commit_agent.cli.errors import fail, handle_errors
from commit_agent.core.project_config import (
    CONFIG_FILENAME,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_HEADER_LENGTH,
    DEFAULT_REFERENCE_FORMAT,
)
from commit_agent.git_integration import open_repo

_LANGUAGES = {"ko": "한국어", "en": "English"}
_ALL_TYPES = [t.value for t in CommitType]

_TEMPLATE = """\
# commit-agent 저장소 설정
# 이 파일은 커밋해서 팀원과 공유합니다.
# API 키 같은 개인 값은 .env 에 두세요.

# 커밋 메시지를 쓸 언어 (ko 또는 en)
language = "{language}"

# 이 저장소에서 허용하는 Conventional Commits 타입
types = [
{types}
]

# 허용하는 scope. 비워 두면 자유롭게 씁니다 (예: ["core", "cli"])
scopes = []

# 첫 줄(타입·scope 포함)의 최대 글자 수
max_header_length = {max_header_length}

# 이슈 참조 줄의 형식. {{ref}} 자리에 #번호가 들어갑니다 (예: "Closes {{ref}}")
reference_format = "{reference_format}"

# 관련 이슈를 찾아 참조를 붙일지
issue_mapping = true

# 관련 이슈가 없을 때 새 이슈를 제안할지
propose_issue = true

# 기본 브랜치에서 커밋할 때 새 브랜치를 제안할지
branch_suggest = true
"""


@handle_errors
def init(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="묻지 않고 기본값으로 만듭니다.",
    ),
) -> None:
    """프로젝트에 필요한 설정 파일을 만듭니다."""
    repo = open_repo()
    target = Path(repo.working_tree_dir or ".") / CONFIG_FILENAME

    if target.exists():
        typer.secho("이미 설정이 되어 있습니다.", err=True)
        typer.secho(f"  → {target}", err=True, dim=True)
        typer.secho("  다시 설정하려면 이 파일을 지우고 실행하세요.", err=True, dim=True)
        raise typer.Exit

    if yes:
        language, types = DEFAULT_LANGUAGE, _ALL_TYPES
    else:
        _require_terminal()
        language = _ask_language()
        types = _ask_types()

    target.write_text(
        _TEMPLATE.format(
            language=language,
            types=",\n".join(f'    "{t}"' for t in types),
            max_header_length=DEFAULT_MAX_HEADER_LENGTH,
            reference_format=DEFAULT_REFERENCE_FORMAT,
        ),
        encoding="utf-8",
    )

    typer.secho("\n프로젝트 설정이 완료되었습니다.", fg=typer.colors.GREEN)
    typer.secho(f"  파일: {CONFIG_FILENAME}", dim=True)
    typer.secho(f"  언어: {language}")
    typer.secho(f"  타입: {', '.join(types)}")
    typer.secho("  나머지 항목은 기본값으로 넣었습니다. 파일을 열어 바꿀 수 있습니다.", dim=True)


def _require_terminal() -> None:
    """대화형 질문은 터미널에서만 가능하다."""
    if not sys.stdin.isatty():
        fail(
            "대화형 입력을 받을 수 없는 환경입니다.",
            hint="`commit-agent init --yes` 로 기본값을 사용하세요.",
        )


def _cancelled() -> None:
    """질문 도중 취소한 경우."""
    fail("취소되었습니다.", code=130)


def _ask_language() -> str:
    """커밋 메시지 언어를 고르게 한다."""
    answer = questionary.select(
        "커밋 메시지를 어떤 언어로 쓸까요?",
        choices=[
            questionary.Choice(title=f"{name} ({code})", value=code)
            for code, name in _LANGUAGES.items()
        ],
    ).ask()

    if answer is None:
        _cancelled()
    return str(answer)


def _ask_types() -> list[str]:
    """허용할 타입을 체크박스로 고르게 한다."""
    while True:
        answer = questionary.checkbox(
            "허용할 타입을 선택하세요 (스페이스로 토글, 엔터로 확정)",
            choices=[questionary.Choice(title=t, checked=True) for t in _ALL_TYPES],
        ).ask()

        if answer is None:
            _cancelled()
        if answer:
            return [str(t) for t in answer]

        typer.secho("  하나 이상 선택하세요.", fg=typer.colors.RED)
