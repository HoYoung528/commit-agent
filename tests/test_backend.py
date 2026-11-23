"""로컬 실행과 서버 호출 중 무엇을 쓸지 고르는 부분.

호출하는 쪽(`generate` 명령)은 어느 경로인지 모르고 같은 결과 형태만 본다.
그래서 여기서 볼 것은 경로 선택과 **실패를 사용자에게 어떻게 전달하는지**다.
서버가 꺼져 있거나 느릴 때 훅 안에서 아무 안내 없이 멈추면 사용자는 원인을
알 수 없다.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import DIFF, FakeModel, exploding

from commit_agent.agent import branch_name as branch_namer
from commit_agent.agent.nodes import generate_message, propose_issue
from commit_agent.cli import backend
from commit_agent.core import get_settings
from commit_agent.core.llm import LLMError
from commit_agent.core.project_config import ProjectConfig
from commit_agent.server.schemas import GenerateResponse

SERVER = "http://127.0.0.1:9999"


@pytest.fixture
def local_settings():
    return get_settings().model_copy(update={"server_url": ""})


@pytest.fixture
def server_settings():
    return get_settings().model_copy(update={"server_url": SERVER})


def call(settings, **overrides):
    return backend.generate(
        overrides.pop("diff_text", DIFF),
        repo_slug=overrides.pop("repo_slug", None),
        project=overrides.pop("project", ProjectConfig()),
        branch_names=overrides.pop("branch_names", []),
        settings=settings,
    )


def respond(handler, monkeypatch):
    """httpx 요청을 가로채 정해 둔 응답을 돌려준다."""
    transport = httpx.MockTransport(handler)
    original = httpx.post

    def post(url, **kwargs):
        timeout = kwargs.pop("timeout", None)
        with httpx.Client(transport=transport, timeout=timeout) as client:
            return client.post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", post)
    return original


def test_서버_주소가_없으면_로컬에서_실행한다(local_settings, monkeypatch, draft):
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))
    monkeypatch.setattr(httpx, "post", exploding)

    result = call(local_settings)

    assert result.commit_message == "feat(core): 추론 모델의 생각 분량을 설정으로 노출"


def test_로컬_실행도_같은_결과_형태를_돌려준다(local_settings, monkeypatch, draft):
    """호출하는 쪽이 경로를 몰라도 되게 한다."""
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))

    result = call(local_settings)

    assert isinstance(result, GenerateResponse)
    assert result.draft is not None


def test_서버_주소가_있으면_보내고_받는다(server_settings, monkeypatch):
    sent: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["url"] = str(request.url)
        sent["body"] = request.read().decode()
        return httpx.Response(
            200, json={"commit_message": "feat: 서버가 만든 메시지"}
        )

    respond(handler, monkeypatch)
    monkeypatch.setattr(generate_message, "get_chat_model", exploding)

    result = call(server_settings)

    assert sent["url"] == f"{SERVER}/generate"
    assert "diff_text" in str(sent["body"])
    assert result.commit_message == "feat: 서버가 만든 메시지"


def test_주소_끝의_슬래시를_중복시키지_않는다(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"commit_message": "feat: x"})

    respond(handler, monkeypatch)
    settings = get_settings().model_copy(update={"server_url": f"{SERVER}/"})

    call(settings)

    assert seen == [f"{SERVER}/generate"]


def test_사용자_토큰과_브랜치_예시를_함께_보낸다(server_settings, monkeypatch):
    """서버 토큰으로는 사용자 저장소를 읽을 수 없고, 이름 예시는 로컬에만 있다."""
    sent: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent.update(json.loads(request.read()))
        return httpx.Response(200, json={"commit_message": "feat: x"})

    respond(handler, monkeypatch)
    settings = server_settings.model_copy(update={"github_token": "ghp_user"})

    call(settings, repo_slug="owner/name", branch_names=["feat/#1/setup"])

    assert sent["github_token"] == "ghp_user"
    assert sent["branch_names"] == ["feat/#1/setup"]
    assert sent["repo_slug"] == "owner/name"


def test_서버에_닿지_않으면_로컬_전환_방법을_알려준다(server_settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("연결 거부", request=request)

    respond(handler, monkeypatch)

    with pytest.raises(LLMError, match="연결할 수 없습니다") as caught:
        call(server_settings)

    assert "COMMIT_AGENT_SERVER_URL" in caught.value.hint


def test_응답이_늦으면_시간_상한을_알려준다(server_settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("느림", request=request)

    respond(handler, monkeypatch)

    with pytest.raises(LLMError, match="초 안에 오지 않았습니다"):
        call(server_settings)


def test_서버가_보낸_안내를_그대로_보여준다(server_settings, monkeypatch):
    """서버가 모델 오류의 안내 문구까지 넘겨 준다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "모델 API 요청 한도를 넘었습니다."})

    respond(handler, monkeypatch)

    with pytest.raises(LLMError, match="요청 한도"):
        call(server_settings)


def test_안내가_없는_실패도_상태_코드를_남긴다(server_settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="서버 오류")

    respond(handler, monkeypatch)

    with pytest.raises(LLMError, match="HTTP 500"):
        call(server_settings)


def test_로컬_실행에서_브랜치_이름을_짓는다(local_settings, monkeypatch, draft):
    from commit_agent.agent.schemas import BranchNameSuggestion

    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))
    monkeypatch.setattr(
        branch_namer,
        "get_chat_model",
        lambda _s=None: FakeModel(BranchNameSuggestion(name="feat/#1/add-retry")),
    )

    result = call(local_settings, branch_names=["feat/#1/setup"])

    assert result.branch_name == "feat/#1/add-retry"


def test_로컬_실행에서_이름_생성이_실패해도_메시지는_나온다(
    local_settings, monkeypatch, draft
):
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)

    def failing(_s=None):
        raise LLMError("실패", hint="나중에")

    monkeypatch.setattr(branch_namer, "get_chat_model", failing)

    result = call(local_settings, branch_names=["feat/#1/setup"])

    assert result.branch_name is None
    assert result.commit_message
