"""생성된 커밋 메시지 스키마.

LLM이 완성된 문자열 대신 조각을 반환하게 하고 조립은 우리가 한다.
그래야 Conventional Commits 형식이 깨질 수 없고, 타입을 따로 뽑아
분류 일치율 같은 지표를 계산할 수 있다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CommitType(StrEnum):
    """Conventional Commits 타입."""

    FEAT = "feat"
    FIX = "fix"
    DOCS = "docs"
    STYLE = "style"
    REFACTOR = "refactor"
    PERF = "perf"
    TEST = "test"
    BUILD = "build"
    CI = "ci"
    CHORE = "chore"
    REVERT = "revert"


class CommitMessageDraft(BaseModel):
    """LLM이 만들어낸 커밋 메시지 조각.

    각 필드의 description이 그대로 LLM에게 전달되므로 작성 규칙도 여기 적는다.
    """

    type: CommitType = Field(description="변경 유형")
    scope: str | None = Field(
        default=None,
        description="변경이 집중된 범위. 모듈이나 디렉터리 이름. 애매하면 비워 둔다",
    )
    subject: str = Field(description="무엇을 왜 바꿨는지 한 줄. 마침표 없이")
    body: str | None = Field(
        default=None,
        description="한 줄로 부족할 때만 채우는 본문. 항목마다 `- `로 시작",
    )

    def render(self) -> str:
        """Conventional Commits 형식 문자열로 조립한다."""
        scope = f"({self.scope})" if self.scope else ""
        header = f"{self.type.value}{scope}: {self.subject}"

        if not self.body or not self.body.strip():
            return header
        return f"{header}\n\n{self.body.strip()}"


def with_reference(message: str, reference: str) -> str:
    """메시지 끝에 이슈 참조를 붙인다. 이미 있으면 그대로 둔다.

    기존 이슈를 매핑했을 때와 새 이슈를 만들었을 때 모두 같은 형식으로 붙는다.
    """
    if reference in message:
        return message
    return f"{message.rstrip()}\n\nrelated to: {reference}"
