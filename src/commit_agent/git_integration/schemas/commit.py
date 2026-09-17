"""커밋 정보 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CommitInfo(BaseModel):
    """로컬 저장소에서 읽어온 커밋 하나의 정보.

    RAG 인덱싱에서 과거 커밋 메시지의 원본으로 쓰인다.
    """

    sha: str
    message: str
    author_name: str
    author_email: str
    committed_at: datetime
    parents: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list, description="변경된 파일 경로")
    insertions: int = 0
    deletions: int = 0

    def short_sha(self) -> str:
        return self.sha[:7]

    def summary(self) -> str:
        """커밋 메시지 첫 줄."""
        return self.message.split("\n", 1)[0].strip()

    def body(self) -> str:
        """커밋 메시지 본문. 첫 줄과 뒤따르는 빈 줄을 제외한 나머지."""
        parts = self.message.split("\n", 1)
        return parts[1].strip() if len(parts) > 1 else ""

    def is_merge(self) -> bool:
        return len(self.parents) > 1

    def changed_lines(self) -> int:
        return self.insertions + self.deletions
