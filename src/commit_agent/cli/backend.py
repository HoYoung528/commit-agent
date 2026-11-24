"""생성을 로컬에서 할지 서버에 맡길지 고른다.

두 경로가 같은 결과 형태(`GenerateResponse`)를 돌려주므로 호출하는 쪽은
어느 쪽인지 몰라도 된다. 설정에 `server_url` 이 있으면 서버로 보낸다.

서버 모드에서도 git 접근과 설정 파일 읽기, 사용자 확인은 클라이언트에 남는다.
저장소를 건드리는 일이라 옮길 수 없다.
"""

from __future__ import annotations

import httpx

from commit_agent.agent.branch_name import suggest_branch_name
from commit_agent.agent.graph import run
from commit_agent.core.config import Settings
from commit_agent.core.llm import LLMError
from commit_agent.core.project_config import ProjectConfig
from commit_agent.server.schemas import GenerateRequest, GenerateResponse

# 훅 안에서 돌기 때문에 커밋이 오래 멈춰선 안 된다. 서버도 같은 모델을 부르므로
# 로컬 실행과 비슷한 시간이 걸린다고 보고 여유를 둔다.
TIMEOUT_SECONDS = 180


def generate(
    diff_text: str,
    *,
    repo_slug: str | None,
    project: ProjectConfig,
    branch_names: list[str],
    settings: Settings,
) -> GenerateResponse:
    """커밋 메시지와 이슈·브랜치 판단 재료를 받아 온다."""
    request = GenerateRequest(
        diff_text=diff_text,
        repo_slug=repo_slug,
        project=project,
        github_token=settings.github_token,
        branch_names=branch_names,
    )

    if settings.uses_server():
        return _remote(request, settings.server_url)
    return _local(request)


def _local(request: GenerateRequest) -> GenerateResponse:
    """지금까지와 같은 경로. 그래프를 이 프로세스에서 실행한다."""
    state = run(
        request.diff_text, repo_slug=request.repo_slug, project=request.project
    )

    branch_name = None
    if state.draft and request.branch_names:
        try:
            branch_name = suggest_branch_name(
                request.branch_names,
                state.draft.type.value,
                state.draft.subject,
                state.matched_issue.number if state.matched_issue else None,
            )
        except Exception:
            # 브랜치 이름은 부가 기능이다. 이것 때문에 커밋을 막지 않는다
            branch_name = None

    return GenerateResponse(
        commit_message=state.commit_message or "",
        draft=state.draft,
        matched_issue=state.matched_issue,
        issue_draft=state.issue_draft,
        branch_name=branch_name,
        secret_files=state.analysis.secret_files if state.analysis else [],
        masked=state.analysis.masked if state.analysis else {},
    )


def _remote(request: GenerateRequest, server_url: str) -> GenerateResponse:
    """서버에 맡긴다. 실패는 `LLMError` 로 바꿔 CLI의 기존 처리에 맡긴다."""
    url = f"{server_url.rstrip('/')}/generate"

    try:
        response = httpx.post(
            url, json=request.model_dump(mode="json"), timeout=TIMEOUT_SECONDS
        )
    except httpx.TimeoutException as exc:
        raise LLMError(
            f"서버 응답이 {TIMEOUT_SECONDS}초 안에 오지 않았습니다.",
            hint="잠시 후 다시 시도하세요.",
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMError(
            f"에이전트 서버에 연결할 수 없습니다: {server_url}",
            hint=(
                "서버가 떠 있는지 확인하세요. 서버 없이 쓰려면 "
                "`COMMIT_AGENT_SERVER_URL` 을 비우면 로컬에서 실행합니다."
            ),
        ) from exc

    if response.status_code != httpx.codes.OK:
        raise LLMError(
            f"서버가 요청을 처리하지 못했습니다: {_detail(response)}",
            hint="서버 로그를 확인하세요.",
        )

    return GenerateResponse.model_validate(response.json())


def _detail(response: httpx.Response) -> str:
    """서버가 보낸 안내 문구를 꺼낸다. 형식이 다르면 상태 코드만 쓴다."""
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"

    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return f"HTTP {response.status_code}"
