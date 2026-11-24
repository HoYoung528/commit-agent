"""벡터 스토어에 넣고 꺼내는 단위."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Collection(StrEnum):
    """컬렉션 구분.

    계획서에 따라 과거 커밋과 이슈를 별도 컬렉션으로 나눈다.
    """

    COMMITS = "commits"
    ISSUES = "issues"


def collection_name(kind: Collection, scope: str | None = None) -> str:
    """실제로 쓸 컬렉션 이름.

    한 서버를 여러 사람이 쓰면 저장소별로 나눠야 서로의 인덱스가 섞이지
    않는다. 같은 저장소를 보는 사람끼리는 같은 이름이 나와 인덱스를 공유한다 —
    과거 커밋 인덱스는 git 히스토리에서 만들어지므로 공유해도 내용이 같고,
    그게 "팀 단위로 공유"의 실질이다.

    범위를 비우면 지금까지 쓰던 이름을 그대로 돌려준다. 로컬 실행에서 이미
    만들어 둔 인덱스를 다시 만들지 않아도 되게 하기 위해서다.
    """
    if not scope:
        return kind.value

    return f"{kind.value}__{_sanitize(scope)}"


def _sanitize(scope: str) -> str:
    """컬렉션 이름에 쓸 수 있는 문자만 남긴다.

    저장소 이름(`owner/name`)의 `/` 처럼 쓸 수 없는 문자가 들어온다.
    """
    return re.sub(r"[^A-Za-z0-9_-]+", "_", scope).strip("_")


class Document(BaseModel):
    """인덱싱 대상 하나.

    `text`는 임베딩 입력이자 검색 대상이고, `metadata`는 필터 조건으로 쓴다.
    (예: 확장자가 md인 과거 커밋 중에서만 검색)
    """

    id: str = Field(description="같은 대상을 다시 넣으면 덮어쓰도록 하는 식별자")
    text: str = Field(description="임베딩에 넣을 텍스트")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel):
    """검색 결과 하나."""

    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(description="유사도. 클수록 가깝다")
