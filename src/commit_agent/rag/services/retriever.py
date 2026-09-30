"""인덱싱된 커밋과 이슈에서 유사한 것을 찾는다.

커밋은 변경 요약으로, 이슈는 생성된 커밋 메시지로 검색한다.
관련 여부 판단은 에이전트 노드가 하므로 점수 하한은 두지 않는다.
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from commit_agent.change_analysis import build_index_text
from commit_agent.change_analysis.schemas import DiffAnalysis
from commit_agent.rag.schemas import Collection, SearchHit
from commit_agent.rag.services.store import search

DEFAULT_LIMIT = 5


def retrieve_commits(
    client: QdrantClient,
    embeddings: Embeddings,
    analysis: DiffAnalysis,
    *,
    limit: int = DEFAULT_LIMIT,
    exclude_ids: set[str] | None = None,
) -> list[SearchHit]:
    """현재 변경과 비슷한 과거 커밋을 찾는다.

    `exclude_ids` 는 평가할 때 정답 커밋을 결과에서 빼는 용도다.
    """
    if analysis.is_empty():
        return []

    return _search(
        client,
        embeddings,
        Collection.COMMITS,
        build_index_text(analysis),
        limit=limit,
        exclude_ids=exclude_ids,
    )


def retrieve_issues(
    client: QdrantClient,
    embeddings: Embeddings,
    commit_message: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchHit]:
    """생성된 커밋 메시지와 관련된 이슈를 찾는다."""
    if not commit_message.strip():
        return []

    return _search(client, embeddings, Collection.ISSUES, commit_message, limit=limit)


def _search(
    client: QdrantClient,
    embeddings: Embeddings,
    collection: Collection,
    query: str,
    *,
    limit: int,
    exclude_ids: set[str] | None = None,
) -> list[SearchHit]:
    """쿼리 텍스트를 벡터로 바꿔 검색하고, 제외 대상을 걸러낸다."""
    # 제외할 것이 있으면 그만큼 더 받아 와야 개수를 채운다
    fetch = limit + len(exclude_ids) if exclude_ids else limit
    hits = search(client, collection, embeddings.embed_query(query), limit=fetch)

    if exclude_ids:
        hits = [hit for hit in hits if hit.id not in exclude_ids]

    return hits[:limit]
