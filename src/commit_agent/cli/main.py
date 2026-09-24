"""typer 애플리케이션 정의.

명령 등록만 담당하고 본문은 `commands/` 에 둔다.
아직 구현되지 않은 명령은 여기 뼈대로 남아 있으며, 해당 이슈에서
`commands/` 로 옮기면서 본문을 채운다.
"""

from __future__ import annotations

import sys

import typer

from commit_agent import __version__
from commit_agent.cli.commands import generate as generate_command
from commit_agent.cli.commands import init as init_command

def _force_utf8_output() -> None:
    """출력을 UTF-8·LF로 고정한다.

    git 훅은 로케일 설정 없이 실행되므로, Windows에서는 기본값이 cp949가 되어
    한글이 깨지고 줄바꿈이 CRLF로 바뀐다. 커밋 메시지 파일에 그대로 들어가므로
    진입 시점에 맞춰 둔다.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")


_force_utf8_output()

app = typer.Typer(
    name="commit-agent",
    help="코드 변경을 분석해 커밋 메시지를 생성하고 관련 이슈를 연결합니다.",
    no_args_is_help=True,
    add_completion=False,
)

app.command()(generate_command)
app.command()(init_command)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"commit-agent {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="버전을 출력하고 종료합니다.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """commit-agent 명령 모음."""


@app.command()
def index() -> None:
    """과거 커밋과 이슈를 벡터 스토어에 인덱싱합니다."""
    raise NotImplementedError


@app.command()
def install() -> None:
    """prepare-commit-msg 훅을 설치합니다."""
    raise NotImplementedError


@app.command()
def uninstall() -> None:
    """설치된 훅을 제거합니다."""
    raise NotImplementedError


if __name__ == "__main__":
    app()
