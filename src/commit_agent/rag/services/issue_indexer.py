"""GitHub 이슈를 벡터 스토어에 인덱싱한다.

매핑 직전에 호출되므로 빠르게 끝나야 한다. 그래서 `updated_at` 을 비교해
**바뀐 이슈만** 다시 임베딩한다. 평소에는 바뀐 것이 없어 임베딩 호출이
한 번도 일어나지 않는다.

닫힌 이슈는 넣지 않고, 이미 저장돼 있으면 지운다. 매핑 대상은 진행 중인
일이며 해결된 이슈가 검색 결과에 섞이면 판단을 흐린다.
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
from commit_agent.rag.services.store import (
    delete,
    ensure_collection,
    stored_fields,
    upsert,
)

# 한 번에 임베딩·저장하는 이슈 수
DEFAULT_BATCH_SIZE = 50

# 본문이 길면 잘라낸다. 이슈 본문에는 로그나 스택트레이스가 통째로 붙기도 한다.
MAX_BODY_LENGTH = 4_000


@dataclass
class IssueIndexResult:
    """인덱싱 결과 요약."""

    total: int
    indexed: int
    removed: int


def index_issues(
    repo: Repository,
    client: QdrantClient,
    embeddings: Embeddings,
    *,
    limit: int = 500,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> IssueIndexResult:
    """열린 이슈를 인덱싱한다. 내용이 바뀐 것만 다시 임베딩한다."""
    issues = list_issues(repo, state="open", limit=limit)
    stored = stored_fields(client, Collection.ISSUES, ["updated_at"])

    # 닫혔거나 사라진 이슈를 치운다
    open_ids = {str(issue.number) for issue in issues}
    removed = [doc_id for doc_id in stored if doc_id not in open_ids]
    delete(client, Collection.ISSUES, removed)

    todo = [issue for issue in issues if _changed(issue, stored)]
    if not todo:
        return IssueIndexResult(total=len(issues), indexed=0, removed=len(removed))

    ensure_collection(client, Collection.ISSUES, _vector_size(embeddings))

    done = 0
    for start in range(0, len(todo), batch_size):
        batch = todo[start : start + batch_size]
        documents = [_to_document(issue) for issue in batch]
        vectors = embeddings.embed_documents([doc.text for doc in documents])

        upsert(client, Collection.ISSUES, documents, vectors)

        done += len(batch)
        if on_progress:
            on_progress(done, len(todo))

    return IssueIndexResult(total=len(issues), indexed=len(todo), removed=len(removed))


def _changed(issue: IssueInfo, stored: dict[str, dict[str, object]]) -> bool:
    """저장된 시각과 달라졌는지. 저장된 적이 없으면 새 이슈다."""
    previous = stored.get(str(issue.number))
    if previous is None:
        return True
    return previous.get("updated_at") != _updated_at(issue)


def _updated_at(issue: IssueInfo) -> str:
    """비교에 쓸 수정 시각 문자열. 값이 없으면 빈 문자열."""
    return issue.updated_at.isoformat() if issue.updated_at else ""


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
            "updated_at": _updated_at(issue),
        },
    )


def _vector_size(embeddings: Embeddings) -> int:
    """모델이 만드는 벡터 차원. 컬렉션을 만들 때 필요하다."""
    return len(embeddings.embed_query("commit-agent"))
