"""FastAPI 애플리케이션.

그래프를 엔드포인트로 감싼다. 노드는 고치지 않는다 — 2주차에 LangGraph를
고른 이유가 실행 환경과 그래프 정의를 분리하는 것이었고, 그 판단이 맞는지는
여기서 드러난다.

엔드포인트는 하나다. 훅 안에서 돌기 때문에 왕복이 한 번이어야 한다. 사용자
확인이 필요한 두 단계(이슈 등록, 브랜치 전환)는 서버가 하지 않고, 판단에
필요한 재료만 응답에 담아 보낸다.

    uvicorn commit_agent.server.app:app --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from commit_agent.agent.branch_name import suggest_branch_name
from commit_agent.agent.graph import run
from commit_agent.agent.schemas import CommitAgentState
from commit_agent.core import get_settings
from commit_agent.core.config import Settings
from commit_agent.core.llm import LLMError
from commit_agent.server.schemas import GenerateRequest, GenerateResponse

app = FastAPI(
    title="commit-agent",
    description="코드 변경을 분석해 커밋 메시지를 생성하고 관련 이슈를 연결합니다.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """떠 있는지 확인한다. 클라이언트가 서버 모드로 붙기 전에 쓴다."""
    return {"status": "ok"}


@app.post("/generate")
def generate(request: GenerateRequest) -> GenerateResponse:
    """변경을 분석해 커밋 메시지를 만들고 관련 이슈를 찾는다."""
    try:
        state = run(
            request.diff_text,
            repo_slug=request.repo_slug,
            project=request.project,
            config={"configurable": {"settings": _settings_for(request)}},
        )
    except LLMError as exc:
        # 모델 호출이 재시도 끝에도 실패한 경우. 안내 문구까지 넘겨 클라이언트가
        # 사용자에게 다음에 할 일을 보여줄 수 있게 한다
        raise HTTPException(status_code=502, detail=f"{exc} {exc.hint}") from exc

    if not state.commit_message:
        raise HTTPException(status_code=502, detail="커밋 메시지를 생성하지 못했습니다.")

    return GenerateResponse(
        commit_message=state.commit_message,
        draft=state.draft,
        matched_issue=state.matched_issue,
        issue_draft=state.issue_draft,
        branch_name=_branch_name(request, state),
        secret_files=state.analysis.secret_files if state.analysis else [],
        masked=state.analysis.masked if state.analysis else {},
    )


def _settings_for(request: GenerateRequest) -> Settings:
    """요청별 설정. 모델 API 키는 서버 것을 쓰고 GitHub 토큰만 갈아끼운다.

    계획서대로 모델 키는 서버가 관리한다. 반면 GitHub 토큰은 서버 것으로는
    사용자 저장소를 읽을 수 없어 요청으로 받는다. 저장하지 않는다.
    """
    return get_settings().model_copy(update={"github_token": request.github_token})


def _branch_name(request: GenerateRequest, state: CommitAgentState) -> str | None:
    """브랜치 이름을 지어 응답에 담는다.

    이름을 쓸지는 사용자가 정하고 브랜치를 만드는 것도 클라이언트가 하지만,
    이름을 짓는 데 모델이 필요해 서버에서 한다. 키가 서버에만 있기 때문이다.

    이 단계가 실패해도 커밋 메시지는 나가야 하므로 예외를 삼킨다.
    """
    if not state.draft or not request.branch_names:
        return None

    try:
        return suggest_branch_name(
            request.branch_names,
            state.draft.type.value,
            state.draft.subject,
            state.matched_issue.number if state.matched_issue else None,
        )
    except Exception:
        return None
