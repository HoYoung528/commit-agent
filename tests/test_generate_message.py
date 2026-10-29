"""`generate_message` 노드."""

from __future__ import annotations

import pytest

from commit_agent.agent.nodes import generate_message
from commit_agent.agent.schemas import CommitMessageDraft, CommitType
from commit_agent.core.llm import LLMError
from commit_agent.core.project_config import ProjectConfig
from conftest import FailingModel, FakeModel, api_error, exploding


@pytest.fixture
def model(monkeypatch, draft):
    """가짜 LLM을 꽂고 그 객체를 돌려준다."""
    fake = FakeModel(draft)
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: fake)
    return fake


def test_받은_조각을_조립해_메시지를_만든다(state, model):
    result = generate_message.generate_message_node(state)

    assert result["commit_message"] == "feat(core): 추론 모델의 생각 분량을 설정으로 노출"
    assert result["draft"].type is CommitType.FEAT


def test_변경이_없으면_호출하지_않는다(empty_state, monkeypatch):
    monkeypatch.setattr(generate_message, "get_chat_model", exploding)

    assert generate_message.generate_message_node(empty_state) == {"commit_message": ""}


def test_검색된_커밋을_예시로_넘긴다(state, model, hits):
    state.retrieved_commits = hits
    generate_message.generate_message_node(state)

    user_message = model.calls[0][1]["content"]
    assert "과거 커밋 예시" in user_message
    assert "feat(core): 모델 설정 분리" in user_message


def test_검색_결과가_없으면_예시_블록을_넣지_않는다(state, model):
    generate_message.generate_message_node(state)

    assert "과거 커밋 예시" not in model.calls[0][1]["content"]


def test_허용_타입을_프롬프트에_전달한다(state, model):
    state.project = ProjectConfig(types=["feat", "fix"])
    generate_message.generate_message_node(state)

    system_message = model.calls[0][0]["content"]
    assert "feat, fix" in system_message


def test_dict로_와도_스키마로_되살린다(state, monkeypatch):
    raw = {"type": "fix", "scope": None, "subject": "오류 수정", "body": None}
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(raw))

    result = generate_message.generate_message_node(state)

    assert isinstance(result["draft"], CommitMessageDraft)
    assert result["commit_message"] == "fix: 오류 수정"


def test_호출이_실패하면_안내를_담아_올린다(state, monkeypatch):
    """만들 메시지가 없으니 삼키지 않고 CLI까지 올려 보낸다."""
    failing = FailingModel(api_error(429))
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: failing)

    with pytest.raises(LLMError, match="요청 한도"):
        generate_message.generate_message_node(state)
