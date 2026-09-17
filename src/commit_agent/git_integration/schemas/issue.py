"""GitHub 이슈 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IssueInfo(BaseModel):
    """GitHub에서 읽어온 이슈 하나의 정보.

    RAG 인덱싱과 이슈 매핑 판단의 원본으로 쓰인다.
    """

    number: int
    title: str
    body: str = ""
    state: str = Field(description="open 또는 closed")
    labels: list[str] = Field(default_factory=list)
    url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_open(self) -> bool:
        return self.state == "open"

    def reference(self) -> str:
        """커밋 메시지에 넣는 참조 형식(`#12`)."""
        return f"#{self.number}"

    def searchable_text(self) -> str:
        """임베딩·유사도 검색에 넣을 텍스트."""
        return f"{self.title}\n\n{self.body}".strip()


class IssueDraft(BaseModel):
    """새로 만들 이슈의 초안.

    에이전트가 매핑되는 이슈를 찾지 못했을 때 생성해 GitHub으로 보낸다.
    """

    title: str
    body: str = ""
    labels: list[str] = Field(default_factory=list)
