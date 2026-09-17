"""에이전트 그래프의 상태 스키마.

노드들이 이 객체를 주고받으며 각자 맡은 필드를 채운다. 노드가 늘어나도
필드만 추가하면 되도록, 단계별 산출물을 서로 다른 필드로 분리해 둔다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from commit_agent.change_analysis.schemas import DiffAnalysis


class CommitAgentState(BaseModel):
    """커밋 메시지 생성 흐름 전체에서 공유되는 상태."""

    # --- 입력 ---
    diff_text: str = Field(description="git diff --cached 원문")
    repo_slug: str | None = Field(
        default=None,
        description="`owner/name`. 이슈 매핑에 필요하며 없으면 매핑을 건너뛴다",
    )

    # --- analyze 노드가 채움 ---
    analysis: DiffAnalysis | None = None

    # --- generate 노드가 채움 ---
    commit_message: str | None = None

    # --- 이후 단계에서 추가될 자리 ---
    # retrieved_commits: list[CommitInfo]   (RAG, 5~6주차)
    # retrieved_issues: list[IssueInfo]     (RAG, 5~6주차)
    # change_type: str | None               (분류 노드, 7~9주차)
    # matched_issue: IssueInfo | None       (이슈 매핑, 7~9주차)
    # issue_draft: IssueDraft | None        (신규 이슈 제안, 7~9주차)
