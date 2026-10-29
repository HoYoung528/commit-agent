"""`map_issue` 노드.

검색은 후보만 추리고 관련 여부는 LLM이 판단한다. 유사도가 높아도 실제로
그 이슈를 해결하는 변경이 아닐 수 있으므로, 두 단계가 따로 동작해야 한다.
"""

from __future__ import annotations

import pytest

from commit_agent.agent.nodes import map_issue
from commit_agent.agent.nodes.map_issue import map_issue_node
from commit_agent.agent.schemas import IssueMatch
from commit_agent.core.project_config import ProjectConfig
from conftest import FailingModel, FakeModel, api_error, exploding

MESSAGE = "feat(core): 추론 모델의 생각 분량을 설정으로 노출"


@pytest.fixture
def wired(monkeypatch, issue, hits):
    """GitHub·스토어·검색을 전부 가짜로 바꾼다. LLM은 각 테스트가 정한다."""
    monkeypatch.setattr(map_issue, "open_github", lambda _token: object())
    monkeypatch.setattr(map_issue, "get_repository", lambda *_: object())
    monkeypatch.setattr(map_issue, "get_store", lambda _s: _FakeStore())
    monkeypatch.setattr(map_issue, "get_embedding_model", lambda _s: object())
    monkeypatch.setattr(map_issue, "index_issues", lambda *a, **k: None)
    monkeypatch.setattr(map_issue, "retrieve_issues", lambda *a, **k: hits)
    monkeypatch.setattr(map_issue, "get_issue", lambda *_: issue)
    monkeypatch.setattr(map_issue, "get_settings", _settings_with_token)


class _FakeStore:
    def close(self) -> None:
        pass


class _Settings:
    github_token = "ghp_x"

    def has_github_token(self) -> bool:
        return True


class _NoToken(_Settings):
    def has_github_token(self) -> bool:
        return False


def _settings_with_token():
    return _Settings()


def _match(number):
    return FakeModel(IssueMatch(issue_number=number, reason="같은 작업"))


def test_관련_이슈를_찾으면_메시지에_참조를_붙인다(state, wired, monkeypatch, issue):
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: _match(22))

    result = map_issue_node(state)

    assert result["matched_issue"] == issue
    assert result["commit_message"] == f"{MESSAGE}\n\nrelated to: #22"


def test_관련_이슈가_없다고_판단하면_참조를_붙이지_않는다(state, wired, monkeypatch, hits):
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: _match(None))

    result = map_issue_node(state)

    assert result["matched_issue"] is None
    assert result["retrieved_issues"] == hits
    assert "commit_message" not in result


def test_후보가_있어도_판단은_따로_한다(state, wired, monkeypatch, hits):
    """검색이 5건을 줘도 LLM이 전부 무관하다고 하면 매핑하지 않는다."""
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: _match(None))

    result = map_issue_node(state)

    assert len(result["retrieved_issues"]) == len(hits)
    assert result["matched_issue"] is None


def test_메시지가_없으면_아무것도_하지_않는다(state, monkeypatch):
    monkeypatch.setattr(map_issue, "get_settings", _settings_with_token)
    monkeypatch.setattr(map_issue, "open_github", exploding)

    assert map_issue_node(state) == {"retrieved_issues": [], "matched_issue": None}


def test_토큰이_없으면_건너뛴다(state, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "get_settings", lambda: _NoToken())
    monkeypatch.setattr(map_issue, "open_github", exploding)

    assert map_issue_node(state) == {"retrieved_issues": [], "matched_issue": None}


def test_원격_저장소가_없으면_건너뛴다(state, monkeypatch):
    state.commit_message = MESSAGE
    state.repo_slug = None
    monkeypatch.setattr(map_issue, "get_settings", _settings_with_token)
    monkeypatch.setattr(map_issue, "open_github", exploding)

    assert map_issue_node(state) == {"retrieved_issues": [], "matched_issue": None}


def test_검색이_실패하면_건너뛴다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "retrieve_issues", exploding)

    assert map_issue_node(state) == {"retrieved_issues": [], "matched_issue": None}


def test_후보가_비면_판단하지_않는다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "retrieve_issues", lambda *a, **k: [])
    monkeypatch.setattr(map_issue, "get_chat_model", exploding)

    assert map_issue_node(state) == {"retrieved_issues": [], "matched_issue": None}


def test_후보에_없는_번호를_답하면_매핑하지_않는다(state, wired, monkeypatch, hits):
    """LLM이 존재하지 않는 이슈 번호를 지어낼 수 있다."""
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: _match(999))
    monkeypatch.setattr(map_issue, "get_issue", exploding)

    result = map_issue_node(state)

    assert result["matched_issue"] is None
    assert result["retrieved_issues"] == hits


def test_설정에서_끄면_건너뛴다(state, monkeypatch):
    state.commit_message = MESSAGE
    state.project = ProjectConfig(issue_mapping=False)
    monkeypatch.setattr(map_issue, "get_settings", _settings_with_token)
    monkeypatch.setattr(map_issue, "open_github", exploding)

    assert map_issue_node(state) == {"retrieved_issues": [], "matched_issue": None}


def test_참조_형식을_설정대로_붙인다(state, wired, monkeypatch):
    state.commit_message = MESSAGE
    state.project = ProjectConfig(reference_format="Closes {ref}")
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: _match(22))

    result = map_issue_node(state)

    assert result["commit_message"] == f"{MESSAGE}\n\nCloses #22"


def test_판단_호출이_실패하면_매핑_없이_넘어간다(state, wired, monkeypatch, hits):
    """메시지는 이미 만들어졌으므로 커밋을 막지 않는다."""
    state.commit_message = MESSAGE
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: FailingModel(api_error(500)))

    result = map_issue_node(state)

    assert result["matched_issue"] is None
    assert result["retrieved_issues"] == hits
    assert "commit_message" not in result


def test_참조가_이미_있으면_중복으로_붙이지_않는다(state, wired, monkeypatch):
    state.commit_message = f"{MESSAGE}\n\nrelated to: #22"
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: _match(22))

    result = map_issue_node(state)

    assert result["commit_message"].count("related to") == 1
