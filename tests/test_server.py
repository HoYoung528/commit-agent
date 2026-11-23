"""서버 실행 경로.

CLI와 같은 그래프를 엔드포인트로 감싼 것이므로, 여기서 볼 것은 그래프 내부가
아니라 경계다 — 요청에 실려 온 사용자 설정이 노드까지 닿는지, 사용자 확인이
필요한 것들이 응답에 담겨 나오는지, 실패가 HTTP 상태로 번역되는지.

사용자 GitHub 토큰이 노드까지 가는지가 특히 중요하다. 서버 자기 토큰으로는
사용자 저장소의 이슈를 읽을 수 없고, 조용히 서버 토큰을 쓰면 매핑이 그냥
건너뛰어져 아무 오류 없이 기능만 사라진다.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import DIFF, FakeModel, exploding
from fastapi.testclient import TestClient

from commit_agent.agent import branch_name as branch_namer
from commit_agent.agent.nodes import generate_message, map_issue, propose_issue
from commit_agent.agent.schemas import BranchNameSuggestion, IssueMatch
from commit_agent.core.llm import LLMError
from commit_agent.git_integration.schemas import IssueInfo
from commit_agent.rag.schemas import SearchHit
from commit_agent.server.app import app

SLUG = "owner/name"

ISSUE = IssueInfo(
    number=12,
    title="재시도가 없다",
    state="open",
    url=f"https://github.com/{SLUG}/issues/12",
)


class _Store:
    def close(self) -> None:
        pass


def _hit() -> SearchHit:
    """검색된 이슈 후보 하나."""
    return SearchHit(
        id=str(ISSUE.number),
        text=ISSUE.searchable_text(),
        metadata={"number": ISSUE.number, "title": ISSUE.title, "state": "open"},
        score=0.9,
    )


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def generating(monkeypatch, draft):
    """메시지 생성만 가짜로 바꾼다. 이슈 매핑은 원격이 없으면 건너뛴다."""
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))
    return draft


@pytest.fixture
def mapping(monkeypatch):
    """이슈 매핑 경계를 가짜로 바꾸고, 노드가 받은 설정을 기록한다."""
    seen: dict[str, Any] = {}

    def settings_from(config):
        from commit_agent.core.config import settings_from as real

        settings = real(config)
        seen["github_token"] = settings.github_token
        return settings

    monkeypatch.setattr(map_issue, "settings_from", settings_from)
    monkeypatch.setattr(map_issue, "open_github", lambda _t: object())
    monkeypatch.setattr(map_issue, "get_repository", lambda *_: object())
    monkeypatch.setattr(map_issue, "get_store", lambda _s: _Store())
    monkeypatch.setattr(map_issue, "get_embedding_model", lambda _s: object())
    monkeypatch.setattr(map_issue, "index_issues", lambda *a, **k: None)
    monkeypatch.setattr(map_issue, "retrieve_issues", lambda *a, **k: [_hit()])
    monkeypatch.setattr(map_issue, "get_issue", lambda *_: ISSUE)
    monkeypatch.setattr(
        map_issue,
        "get_chat_model",
        lambda: FakeModel(IssueMatch(issue_number=ISSUE.number, reason="같은 작업")),
    )
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)
    return seen


def body(**overrides: Any) -> dict[str, Any]:
    return {"diff_text": DIFF, **overrides}


def test_떠_있는지_확인할_수_있다(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_diff를_보내면_커밋_메시지가_돌아온다(client, generating):
    response = client.post("/generate", json=body())

    assert response.status_code == 200
    assert response.json()["commit_message"] == "feat(core): 추론 모델의 생각 분량을 설정으로 노출"


def test_조각도_함께_돌려준다(client, generating):
    """클라이언트가 타입·제목을 따로 써야 브랜치 이름을 정할 수 있다."""
    draft = client.post("/generate", json=body()).json()["draft"]

    assert draft["type"] == "feat"
    assert draft["scope"] == "core"


def test_요청에_실린_GitHub_토큰이_노드까지_간다(client, generating, mapping):
    """서버 토큰으로는 사용자 저장소를 읽을 수 없다."""
    response = client.post(
        "/generate", json=body(repo_slug=SLUG, github_token="ghp_from_client")
    )

    assert mapping["github_token"] == "ghp_from_client"
    assert response.json()["matched_issue"]["number"] == 12


def test_매핑된_이슈의_참조가_메시지에_붙는다(client, generating, mapping):
    message = client.post(
        "/generate", json=body(repo_slug=SLUG, github_token="ghp_x")
    ).json()["commit_message"]

    assert message.endswith("related to: #12")


def test_브랜치_이름_예시를_보내면_이름을_지어_준다(client, generating, monkeypatch):
    """이름을 짓는 데 모델이 필요하고 키는 서버에만 있다."""
    monkeypatch.setattr(
        branch_namer,
        "get_chat_model",
        lambda _s=None: FakeModel(BranchNameSuggestion(name="feat/#12/add-retry")),
    )

    response = client.post("/generate", json=body(branch_names=["feat/#1/setup"]))

    assert response.json()["branch_name"] == "feat/#12/add-retry"


def test_이름_예시가_없으면_브랜치_이름을_비운다(client, generating, monkeypatch):
    monkeypatch.setattr(branch_namer, "get_chat_model", exploding)

    assert client.post("/generate", json=body()).json()["branch_name"] is None


def test_브랜치_이름_생성이_실패해도_메시지는_나간다(client, generating, monkeypatch):
    """부가 기능이다. 이것 때문에 커밋을 막지 않는다."""

    def failing(_s=None):
        raise LLMError("실패", hint="나중에")

    monkeypatch.setattr(branch_namer, "get_chat_model", failing)

    response = client.post("/generate", json=body(branch_names=["feat/#1/setup"]))

    assert response.status_code == 200
    assert response.json()["branch_name"] is None
    assert response.json()["commit_message"]


def test_가린_파일을_응답에_알린다(client, generating):
    """커밋에는 그대로 들어가므로 사용자가 알아야 한다."""
    diff = (
        "diff --git a/.env b/.env\n"
        "index 1..2 100644\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1 +1,2 @@\n"
        " X=1\n"
        "+OPENAI_API_KEY=sk-secret\n"
    )
    response = client.post("/generate", json={"diff_text": diff + DIFF})

    assert ".env" in response.json()["secret_files"]


def test_생성이_실패하면_안내를_담아_502로_답한다(client, monkeypatch):
    def failing():
        raise LLMError("모델 API 요청 한도를 넘었습니다.", hint="잠시 후 다시 시도하세요.")

    monkeypatch.setattr(generate_message, "get_chat_model", failing)

    response = client.post("/generate", json=body())

    assert response.status_code == 502
    assert "요청 한도" in response.json()["detail"]
    assert "잠시 후" in response.json()["detail"]


def test_변경이_없으면_502로_답한다(client, monkeypatch):
    monkeypatch.setattr(generate_message, "get_chat_model", exploding)

    response = client.post("/generate", json={"diff_text": ""})

    assert response.status_code == 502


def test_diff가_없으면_422로_거른다(client):
    """스키마가 막아 그래프까지 가지 않는다."""
    assert client.post("/generate", json={}).status_code == 422
