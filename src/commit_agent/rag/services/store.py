"""벡터 스토어에 문서를 넣고 검색한다.

클라이언트를 인자로 받으므로 로컬·서버 어느 쪽이든 동일하게 동작한다.
클라이언트를 만드는 일은 `core.vector_store` 가 맡는다.

임베딩은 여기서 하지 않는다. 벡터를 만드는 일은 인덱서의 몫이며,
그래야 임베딩 모델 선택과 저장 로직이 서로 묶이지 않는다.
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient, models

from commit_agent.rag.schemas import Collection, Document, SearchHit

# 문자열 id를 Qdrant가 받는 UUID로 바꿀 때 쓰는 이름공간
_ID_NAMESPACE = uuid.UUID("6f1b5d6e-0c5a-4f8e-9a1b-2c3d4e5f6a7b")


def ensure_collection(client: QdrantClient, collection: Collection, vector_size: int) -> None:
    """컬렉션이 없으면 만든다. 이미 있으면 아무것도 하지 않는다."""
    if client.collection_exists(collection.value):
        return

    client.create_collection(
        collection_name=collection.value,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )


def upsert(
    client: QdrantClient,
    collection: Collection,
    documents: list[Document],
    vectors: list[list[float]],
) -> None:
    """문서를 넣거나 덮어쓴다. `documents` 와 `vectors` 는 같은 순서로 대응된다."""
    if len(documents) != len(vectors):
        raise ValueError(f"문서 수({len(documents)})와 벡터 수({len(vectors)})가 다릅니다.")
    if not documents:
        return

    client.upsert(
        collection_name=collection.value,
        points=[
            models.PointStruct(
                id=_point_id(doc.id),
                vector=vector,
                # 원래 id와 본문을 payload에 함께 둔다. 검색 결과에서 그대로 꺼내 쓴다
                payload={"doc_id": doc.id, "text": doc.text, **doc.metadata},
            )
            for doc, vector in zip(documents, vectors, strict=True)
        ],
    )


def search(
    client: QdrantClient,
    collection: Collection,
    vector: list[float],
    *,
    limit: int = 5,
    where: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """쿼리 벡터와 가까운 문서를 찾는다.

    `where` 의 키와 값이 모두 일치하는 문서만 대상으로 한다.
    """
    if not client.collection_exists(collection.value):
        return []

    response = client.query_points(
        collection_name=collection.value,
        query=vector,
        limit=limit,
        query_filter=_build_filter(where),
        with_payload=True,
    )

    return [_to_hit(point) for point in response.points]


def count(client: QdrantClient, collection: Collection) -> int:
    """컬렉션에 든 문서 수. 인덱싱이 끝났는지 확인할 때 쓴다."""
    if not client.collection_exists(collection.value):
        return 0
    return client.count(collection_name=collection.value).count


def drop(client: QdrantClient, collection: Collection) -> None:
    """컬렉션을 통째로 지운다. 처음부터 다시 인덱싱할 때 쓴다."""
    if client.collection_exists(collection.value):
        client.delete_collection(collection_name=collection.value)


def _point_id(doc_id: str) -> str:
    """Qdrant는 정수나 UUID만 id로 받으므로 문자열을 UUID로 바꾼다.

    같은 문자열은 항상 같은 UUID가 되므로, 다시 인덱싱하면 덮어쓰게 된다.
    """
    return str(uuid.uuid5(_ID_NAMESPACE, doc_id))


def _build_filter(where: dict[str, Any] | None) -> models.Filter | None:
    """메타데이터 조건을 Qdrant 필터로 바꾼다."""
    if not where:
        return None

    return models.Filter(
        must=[
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in where.items()
        ]
    )


def _to_hit(point: models.ScoredPoint) -> SearchHit:
    """검색 결과를 스키마로 옮긴다."""
    payload = dict(point.payload or {})
    doc_id = payload.pop("doc_id", str(point.id))
    text = payload.pop("text", "")

    return SearchHit(id=doc_id, text=text, metadata=payload, score=point.score)
