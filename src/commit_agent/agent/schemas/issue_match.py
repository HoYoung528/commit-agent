"""이슈 매핑 판단 결과 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IssueMatch(BaseModel):
    """검색된 후보 중 어느 이슈가 관련 있는지에 대한 판단."""

    issue_number: int | None = Field(
        default=None,
        description="관련 있는 이슈 번호. 확실하지 않으면 비워 둔다",
    )
    reason: str = Field(
        description="그렇게 판단한 이유. 관련 없다고 봤다면 그 이유",
    )
