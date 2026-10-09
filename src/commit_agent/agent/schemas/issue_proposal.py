"""신규 이슈 제안 결과 스키마."""

from __future__ import annotations

from pydantic import BaseModel, Field


class IssueProposal(BaseModel):
    """이 변경을 이슈로 남길지에 대한 판단과 초안.

    모든 커밋이 이슈가 되어야 하는 것은 아니므로, 초안을 만들기 전에
    기록할 가치가 있는지부터 묻는다.
    """

    worth_tracking: bool = Field(
        description="이슈로 남길 가치가 있는 작업인지. 오타 수정이나 포맷팅이면 false",
    )
    title: str = Field(
        default="",
        description="이슈 제목. 해야 할 일 관점으로 한 줄",
    )
    body: str = Field(default="", description="왜 필요하고 무엇을 하는지")
    labels: list[str] = Field(
        default_factory=list,
        description="저장소에 실제로 있는 라벨 중에서만 고른다",
    )
