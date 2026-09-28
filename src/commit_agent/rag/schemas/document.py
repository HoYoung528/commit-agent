"""벡터 스토어에 넣고 꺼내는 단위."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Collection(StrEnum):
    """컬렉션 구분.

    계획서에 따라 과거 커밋과 이슈를 별도 컬렉션으로 나눈다.
    """

    COMMITS = "commits"
    ISSUES = "issues"


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
