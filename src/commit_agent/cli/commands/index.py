"""`commit-agent index` — 커밋 히스토리를 벡터 스토어에 인덱싱한다.

이미 인덱싱된 커밋은 건너뛰므로 여러 번 실행해도 새 커밋만 처리된다.
이슈 인덱싱은 여기서 하지 않는다. 이슈는 수시로 바뀌어 매핑 직전에
갱신해야 하므로, 갱신 시점은 매핑 노드를 만들 때 함께 정한다.
"""

from __future__ import annotations

import sys

import typer

from commit_agent.cli.errors import fail, handle_errors
from commit_agent.core import get_settings
from commit_agent.core.embeddings import get_embedding_model
from commit_agent.core.vector_store import get_store
from commit_agent.git_integration import open_repo
from commit_agent.rag import Collection
from commit_agent.rag.services import drop, index_commits


@handle_errors
def index(
    rebuild: bool = typer.Option(
        False,
        "--rebuild",
        help="기존 인덱스를 지우고 처음부터 다시 만듭니다.",
    ),
    limit: int = typer.Option(
        10_000,
        "--limit",
        help="인덱싱할 최대 커밋 수입니다.",
    ),
) -> None:
    """과거 커밋을 벡터 스토어에 인덱싱합니다."""
    settings = get_settings()
    if not settings.has_openai_key():
        fail(
            "OPENAI_API_KEY 가 설정되지 않았습니다.",
            hint="임베딩 생성에 필요합니다. `.env` 파일에 키를 넣으세요.",
        )

    repo = open_repo()
    client = get_store(settings)

    try:
        if rebuild:
            drop(client, Collection.COMMITS)
            typer.secho("기존 인덱스를 지웠습니다.", err=True, dim=True)

        result = index_commits(
            repo,
            client,
            get_embedding_model(settings),
            limit=limit,
            on_progress=_progress,
        )
    finally:
        client.close()

    typer.secho("인덱싱이 완료되었습니다.", fg=typer.colors.GREEN)
    typer.secho(f"  전체 커밋: {result.total}")
    typer.secho(f"  새로 인덱싱: {result.indexed}")
    if result.skipped:
        typer.secho(f"  건너뜀: {result.skipped} (이미 인덱싱됨)", dim=True)


def _progress(done: int, total: int) -> None:
    """임베딩 호출이 길어질 수 있으므로 진행 상황을 보여준다.

    같은 줄을 덮어쓰므로 터미널에서만 쓴다. 파일이나 파이프로 내보낼 때는
    제어 문자가 그대로 남아 읽기 어려워진다.
    """
    if not sys.stderr.isatty():
        return

    end = "\n" if done >= total else ""
    typer.secho(f"\r  인덱싱 중... {done}/{total}{end}", nl=False, err=True)
