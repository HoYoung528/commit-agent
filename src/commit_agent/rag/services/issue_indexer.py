"""GitHub 이슈를 벡터 스토어에 인덱싱한다.

커밋과 달리 **매번 통째로 다시 만든다.** 이슈는 제목이 수정되거나 라벨이
붙거나 닫히므로 "이미 있으면 건너뛰기"를 쓰면 오래된 내용이 남는다.
열린 이슈만 대상으로 하므로 보통 수십~수백 건이고, 다시 임베딩하는 비용도 작다.

닫힌 이슈는 넣지 않는다. 매핑 대상은 "지금 진행 중인 일"이며, 이미 해결된
이슈가 검색 결과에 섞이면 판단을 흐린다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from github.Repository import Repository
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from commit_agent.git_integration import list_issues
from commit_agent.git_integration.schemas import IssueInfo
from commit_agent.rag.schemas import Collection, Document
from commit_agent.rag.services.store import drop, ensure_collection, upsert

# 한 번에 임베딩·저장하는 이슈 수
DEFAULT_BATCH_SIZE = 50

# 본문이 길면 잘라낸다. 이슈 본문에는 로그나 스택트레이스가 통째로 붙기도 한다.
MAX_BODY_LENGTH = 4_000


@dataclass
class IssueIndexResult:
    """인덱싱 결과 요약."""

    indexed: int


def index_issues(
    repo: Repository,
    client: QdrantClient,
    embeddings: Embeddings,
    *,
    limit: int = 500,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> IssueIndexResult:
    """열린 이슈를 모두 다시 인덱싱한다.

    `on_progress` 는 배치를 저장할 때마다 (처리한 수, 전체 수)로 불린다.
    """
    issues = list_issues(repo, state="open", limit=limit)

    # 닫힌 이슈를 지우고 수정된 내용을 반영하기 위해 통째로 다시 만든다
    drop(client, Collection.ISSUES)
    if not issues:
        return IssueIndexResult(indexed=0)

    ensure_collection(client, Collection.ISSUES, _vector_size(embeddings))

    done = 0
    for start in range(0, len(issues), batch_size):
        batch = issues[start : start + batch_size]
        documents = [_to_document(issue) for issue in batch]
        vectors = embeddings.embed_documents([doc.text for doc in documents])

        upsert(client, Collection.ISSUES, documents, vectors)

        done += len(batch)
        if on_progress:
            on_progress(done, len(issues))

    return IssueIndexResult(indexed=len(issues))


def _to_document(issue: IssueInfo) -> Document:
    """이슈 하나를 인덱싱 단위로 바꾼다."""
    body = issue.body.strip()
    if len(body) > MAX_BODY_LENGTH:
        body = body[:MAX_BODY_LENGTH].rstrip() + "\n... (이하 생략)"

    text = f"{issue.title}\n\n{body}" if body else issue.title

    return Document(
        id=str(issue.number),
        text=text,
        metadata={
            "number": issue.number,
            "title": issue.title,
            "labels": issue.labels,
            "url": issue.url,
        },
    )


def _vector_size(embeddings: Embeddings) -> int:
    """모델이 만드는 벡터 차원. 컬렉션을 만들 때 필요하다."""
    return len(embeddings.embed_query("commit-agent"))
