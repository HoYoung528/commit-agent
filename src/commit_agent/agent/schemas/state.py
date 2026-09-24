"""에이전트 그래프의 상태 스키마.

노드들이 이 객체를 주고받으며 각자 맡은 필드를 채운다. 노드가 늘어나도
필드만 추가하면 되도록, 단계별 산출물을 서로 다른 필드로 분리해 둔다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from commit_agent.agent.schemas.commit_message import CommitMessageDraft
from commit_agent.change_analysis.schemas import DiffAnalysis
from commit_agent.core.project_config import ProjectConfig


class CommitAgentState(BaseModel):
    """커밋 메시지 생성 흐름 전체에서 공유되는 상태."""

    # --- 입력 ---
    diff_text: str = Field(description="git diff --cached 원문")
    repo_slug: str | None = Field(
        default=None,
        description="`owner/name`. 이슈 매핑에 필요하며 없으면 매핑을 건너뛴다",
    )
    project: ProjectConfig = Field(
        default_factory=ProjectConfig,
        description="저장소의 커밋 컨벤션. 파일을 읽는 일은 호출하는 쪽이 한다",
    )

    # --- analyze 노드가 채움 ---
    analysis: DiffAnalysis | None = None

    # --- generate 노드가 채움 ---
    draft: CommitMessageDraft | None = Field(
        default=None,
        description="LLM이 반환한 조각. 타입만 따로 필요할 때 쓴다",
    )
    commit_message: str | None = Field(default=None, description="조립된 최종 메시지")

    # --- 이후 단계에서 추가될 자리 ---
    # retrieved_commits: list[CommitInfo]   (RAG, 5~6주차)
    # retrieved_issues: list[IssueInfo]     (RAG, 5~6주차)
    # change_type: str | None               (분류 노드, 7~9주차)
    # matched_issue: IssueInfo | None       (이슈 매핑, 7~9주차)
    # issue_draft: IssueDraft | None        (신규 이슈 제안, 7~9주차)
