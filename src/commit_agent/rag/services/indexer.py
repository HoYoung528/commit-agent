"""과거 커밋을 벡터 스토어에 인덱싱한다.

임베딩 입력은 커밋 메시지가 아니라 **변경 요약**이다. 우리가 찾으려는 것이
"지금과 비슷한 변경을 했던 커밋"이고, 검색할 때도 같은 형식(현재 변경 요약)을
쿼리로 쓰기 때문이다. 커밋 메시지는 검색 결과로 꺼내 쓰도록 payload에 담는다.

이미 저장된 커밋은 건너뛴다. 비싼 것은 diff 계산과 임베딩 호출이므로,
sha 목록을 훑는 비용은 그에 비해 무시할 만하다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from git import Repo
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from commit_agent.change_analysis import analyze, summarize
from commit_agent.change_analysis.schemas import DiffAnalysis
from commit_agent.git_integration import get_commit_diff, get_commit_history
from commit_agent.git_integration.schemas import CommitInfo
from commit_agent.rag.schemas import Collection, Document
from commit_agent.rag.services.store import ensure_collection, existing_ids, upsert

# 한 번에 임베딩·저장하는 커밋 수. 중간에 끊겨도 여기까지는 남는다.
DEFAULT_BATCH_SIZE = 50


@dataclass
class IndexResult:
    """인덱싱 결과 요약."""

    total: int
    skipped: int
    indexed: int


def index_commits(
    repo: Repo,
    client: QdrantClient,
    embeddings: Embeddings,
    *,
    limit: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> IndexResult:
    """커밋 히스토리를 인덱싱한다.

    `on_progress` 는 배치를 저장할 때마다 (처리한 수, 전체 할 일 수)로 불린다.
    """
    commits = get_commit_history(repo, limit=limit or 10_000)
    if not commits:
        return IndexResult(total=0, skipped=0, indexed=0)

    already = existing_ids(client, Collection.COMMITS, [c.sha for c in commits])
    todo = [c for c in commits if c.sha not in already]

    if not todo:
        return IndexResult(total=len(commits), skipped=len(already), indexed=0)

    ensure_collection(client, Collection.COMMITS, _vector_size(embeddings))

    done = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        documents = [_to_document(repo, commit) for commit in batch]
        vectors = embeddings.embed_documents([doc.text for doc in documents])

        upsert(client, Collection.COMMITS, documents, vectors)

        done += len(batch)
        if on_progress:
            on_progress(done, len(todo))

    return IndexResult(total=len(commits), skipped=len(already), indexed=len(todo))


def _to_document(repo: Repo, commit: CommitInfo) -> Document:
    """커밋 하나를 인덱싱 단위로 바꾼다."""
    analysis = analyze(get_commit_diff(repo, commit.sha))

    return Document(
        id=commit.sha,
        text=summarize(analysis),  # 임베딩 입력: 변경 요약
        metadata={
            "message": commit.message.strip(),  # 검색 결과로 꺼내 쓸 값
            "summary_line": commit.summary(),
            "committed_at": commit.committed_at.isoformat(),
            **_change_facets(analysis),
        },
    )


def _change_facets(analysis: DiffAnalysis) -> dict[str, object]:
    """검색 필터로 쓸 변경 특징."""
    extensions = analysis.extensions()
    dirs = analysis.top_level_dirs()

    return {
        "file_count": len(analysis.files),
        "changed_lines": analysis.changed_lines(),
        "extensions": list(extensions),
        "top_level_dirs": list(dirs),
    }


def _vector_size(embeddings: Embeddings) -> int:
    """모델이 만드는 벡터 차원. 컬렉션을 만들 때 필요하다."""
    return len(embeddings.embed_query("commit-agent"))
