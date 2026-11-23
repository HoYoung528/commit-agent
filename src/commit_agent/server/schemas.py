"""서버 요청·응답 스키마.

클라이언트와 서버가 주고받는 것만 여기 둔다. 그래프 상태(`CommitAgentState`)를
그대로 돌려주지 않는다 — 상태에는 검색된 과거 커밋과 이슈가 들어 있어 응답이
커지고, 클라이언트가 쓰지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from commit_agent.agent.schemas import CommitMessageDraft
from commit_agent.core.project_config import ProjectConfig
from commit_agent.git_integration.schemas import IssueDraft, IssueInfo


class GenerateRequest(BaseModel):
    """커밋 메시지 생성 요청.

    계획서대로 클라이언트는 diff와 최소한의 컨텍스트만 보낸다. git 접근과
    설정 파일 읽기는 클라이언트에 남으므로 그 결과를 실어 보낸다.
    """

    diff_text: str = Field(description="스테이징된 변경의 diff 원문")
    repo_slug: str | None = Field(
        default=None,
        description="`owner/name`. 이슈 매핑에 필요하다. GitHub이 아니면 비운다",
    )
    project: ProjectConfig = Field(
        default_factory=ProjectConfig,
        description="저장소 설정(`.commit-agent.toml`). 클라이언트가 읽어 보낸다",
    )
    github_token: str = Field(
        default="",
        description=(
            "이슈 조회에 쓸 사용자 토큰. 서버 토큰으로는 사용자 저장소를 "
            "읽을 수 없으므로 요청으로 받는다. 저장하지 않는다"
        ),
    )
    branch_names: list[str] = Field(
        default_factory=list,
        description=(
            "저장소가 써온 브랜치 이름. 새 이름을 지을 때 규칙을 배울 예시로 "
            "쓴다. 로컬 git에서만 모을 수 있어 클라이언트가 보낸다"
        ),
    )


class GenerateResponse(BaseModel):
    """생성 결과.

    사용자 확인이 필요한 두 가지(이슈 등록, 브랜치 전환)는 서버가 하지 않는다.
    확인이 응답 이후에 일어나고, 저장소를 바꾸는 일은 클라이언트 몫이다.
    """

    commit_message: str = Field(description="조립된 커밋 메시지. 참조까지 붙어 있다")
    draft: CommitMessageDraft | None = Field(
        default=None, description="메시지 조각. 타입·scope를 따로 쓸 때 필요하다"
    )
    matched_issue: IssueInfo | None = Field(
        default=None, description="관련 있다고 판단한 기존 이슈"
    )
    issue_draft: IssueDraft | None = Field(
        default=None, description="관련 이슈가 없을 때의 신규 이슈 초안"
    )
    branch_name: str | None = Field(
        default=None, description="제안하는 브랜치 이름. 지을 수 없으면 비운다"
    )
    secret_files: list[str] = Field(
        default_factory=list, description="민감정보로 보여 본문을 뺀 파일"
    )
    masked: dict[str, int] = Field(
        default_factory=dict, description="값을 가린 파일과 건수"
    )
