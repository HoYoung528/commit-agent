"""`propose_issue` 노드.

모든 변경이 이슈가 되어야 하는 것은 아니다. 초안을 만들기 전에 기록할
가치가 있는지부터 판단하고, 라벨은 저장소에 실제로 있는 것만 쓴다.
"""

from __future__ import annotations

import pytest

from commit_agent.agent.nodes import propose_issue
from commit_agent.agent.nodes.propose_issue import propose_issue_node
from commit_agent.agent.schemas import IssueProposal
from commit_agent.core.project_config import ProjectConfig
from conftest import FailingModel, FakeModel, api_error, exploding

MESSAGE = "feat(core): 추론 모델의 생각 분량을 설정으로 노출"
LABELS = ["bug", "enhancement", "documentation"]


class _Settings:
    github_token = "ghp_x"

    def has_github_token(self) -> bool:
        return True


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(propose_issue, "get_settings", lambda: _Settings())
    monkeypatch.setattr(propose_issue, "open_github", lambda _token: object())
    monkeypatch.setattr(propose_issue, "get_repository", lambda *_: object())
    monkeypatch.setattr(propose_issue, "list_labels", lambda _repo: LABELS)


def _proposal(**kwargs):
    base = {
        "worth_tracking": True,
        "title": "추론 분량을 설정으로 노출",
        "body": "- 커밋이 느려지는 원인",
        "labels": ["enhancement"],
    }
    return FakeModel(IssueProposal(**{**base, **kwargs}))


def test_초안을_만든다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(propose_issue, "get_chat_model", lambda: _proposal())

    draft = propose_issue_node(state)["issue_draft"]

    assert draft.title == "추론 분량을 설정으로 노출"
    assert draft.labels == ["enhancement"]


def test_기록할_가치가_없으면_초안을_만들지_않는다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(
        propose_issue, "get_chat_model", lambda: _proposal(worth_tracking=False)
    )

    assert propose_issue_node(state) == {"issue_draft": None}


def test_제목이_비면_초안을_만들지_않는다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(propose_issue, "get_chat_model", lambda: _proposal(title="  "))

    assert propose_issue_node(state) == {"issue_draft": None}


def test_없는_라벨은_걸러낸다(state, wired, monkeypatch):
    """LLM이 저장소에 없는 라벨을 지어낼 수 있다."""
    state.commit_message = MESSAGE
    monkeypatch.setattr(
        propose_issue,
        "get_chat_model",
        lambda: _proposal(labels=["enhancement", "performance", "refactor"]),
    )

    draft = propose_issue_node(state)["issue_draft"]

    assert draft.labels == ["enhancement"]


def test_라벨_조회에_실패하면_라벨_없이_진행한다(state, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(propose_issue, "get_settings", lambda: _Settings())
    monkeypatch.setattr(propose_issue, "open_github", exploding)
    monkeypatch.setattr(propose_issue, "get_chat_model", lambda: _proposal())

    draft = propose_issue_node(state)["issue_draft"]

    assert draft.labels == []
    assert draft.title


def test_기본_본문_템플릿을_프롬프트에_넣는다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    fake = _proposal()
    monkeypatch.setattr(propose_issue, "get_chat_model", lambda: fake)

    propose_issue_node(state)

    system_message = fake.calls[0][0]["content"]
    assert "## 배경" in system_message
    assert "## 할 일" in system_message


def test_설정한_본문_템플릿을_프롬프트에_넣는다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    state.project = ProjectConfig(issue_template="## 문제 {상황}\n\n## 해결")
    fake = _proposal()
    monkeypatch.setattr(propose_issue, "get_chat_model", lambda: fake)

    propose_issue_node(state)

    system_message = fake.calls[0][0]["content"]
    # 템플릿에 중괄호가 있어도 프롬프트 조립이 깨지지 않는다
    assert "## 문제 {상황}\n\n## 해결" in system_message
    assert "## 배경" not in system_message


def test_남은_안내_주석은_본문에서_지운다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    body = (
        "## 배경\n<!-- 왜 필요한 작업인지 -->\n커밋이 느리다\n\n\n"
        "## 할 일\n<!-- 안내 -->\n- 줄인다"
    )
    monkeypatch.setattr(propose_issue, "get_chat_model", lambda: _proposal(body=body))

    draft = propose_issue_node(state)["issue_draft"]

    assert draft.body == "## 배경\n\n커밋이 느리다\n\n## 할 일\n\n- 줄인다"


def test_설정에서_끄면_호출하지_않는다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    state.project = ProjectConfig(propose_issue=False)
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)

    assert propose_issue_node(state) == {"issue_draft": None}


def test_초안_호출이_실패하면_초안_없이_넘어간다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(
        propose_issue, "get_chat_model", lambda: FailingModel(api_error(429))
    )

    assert propose_issue_node(state) == {"issue_draft": None}


def test_메시지가_없으면_호출하지_않는다(state, monkeypatch):
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)

    assert propose_issue_node(state) == {"issue_draft": None}


def test_변경이_없으면_호출하지_않는다(empty_state, monkeypatch):
    empty_state.commit_message = MESSAGE
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)

    assert propose_issue_node(empty_state) == {"issue_draft": None}
