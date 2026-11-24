"""컬렉션 범위 분리.

한 벡터 스토어를 여러 저장소가 함께 쓰면 인덱스가 섞인다. 섞여도 오류가 나지
않고 "엉뚱한 저장소의 커밋이 예시로 들어오는" 형태로만 드러나므로, 이름 규칙을
테스트로 못 박는다.

실제 로컬 스토어에 두 범위를 함께 넣어 서로 안 보이는지까지 확인한다.
"""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from commit_agent.rag.schemas import Collection, Document, collection_name
from commit_agent.rag.services.store import count, ensure_collection, search, upsert


def test_범위가_없으면_기존_이름을_쓴다():
    """로컬에서 이미 만들어 둔 인덱스를 다시 만들지 않아도 된다."""
    assert collection_name(Collection.COMMITS) == "commits"
    assert collection_name(Collection.ISSUES, None) == "issues"
    assert collection_name(Collection.COMMITS, "") == "commits"


def test_범위를_주면_이름에_붙는다():
    assert collection_name(Collection.COMMITS, "owner/name") == "commits__owner_name"
    assert collection_name(Collection.ISSUES, "owner/name") == "issues__owner_name"


def test_저장소가_다르면_이름이_다르다():
    a = collection_name(Collection.COMMITS, "vercel/ai")
    b = collection_name(Collection.COMMITS, "crewAIInc/crewAI")

    assert a != b


def test_같은_저장소면_같은_이름이_나온다():
    """같은 저장소를 보는 사람끼리는 인덱스를 공유한다."""
    assert collection_name(Collection.COMMITS, "owner/name") == collection_name(
        Collection.COMMITS, "owner/name"
    )


@pytest.mark.parametrize(
    "scope",
    ["owner/name", "owner name", "owner.name", "owner@name", "한글/저장소"],
)
def test_쓸_수_없는_문자를_치환한다(scope):
    """`/` 처럼 컬렉션 이름에 못 쓰는 문자가 들어온다."""
    name = collection_name(Collection.COMMITS, scope)

    assert name.startswith("commits__")
    assert "/" not in name and " " not in name and "." not in name


def test_커밋과_이슈는_같은_범위에서도_나뉜다():
    """계획서대로 과거 커밋과 이슈는 별도 컬렉션이다."""
    scope = "owner/name"

    assert collection_name(Collection.COMMITS, scope) != collection_name(
        Collection.ISSUES, scope
    )


def _doc(doc_id: str, text: str) -> Document:
    return Document(id=doc_id, text=text, metadata={"message": text})


def test_한_스토어에_두_저장소를_넣어도_서로_안_보인다(tmp_path, monkeypatch):
    """이름 규칙이 실제로 격리를 만드는지 확인한다."""
    monkeypatch.setattr(
        "commit_agent.core.vector_store.QdrantClient", QdrantClient, raising=False
    )
    client = QdrantClient(path=str(tmp_path / "store"))

    first = collection_name(Collection.COMMITS, "owner/first")
    second = collection_name(Collection.COMMITS, "owner/second")

    for name, text in ((first, "첫 저장소 커밋"), (second, "두 번째 저장소 커밋")):
        ensure_collection(client, name, 3)
        upsert(client, name, [_doc("a", text)], [[0.1, 0.2, 0.3]])

    assert count(client, first) == 1
    assert count(client, second) == 1

    [hit] = search(client, first, [0.1, 0.2, 0.3], limit=5)
    assert hit.metadata["message"] == "첫 저장소 커밋"

    client.close()
