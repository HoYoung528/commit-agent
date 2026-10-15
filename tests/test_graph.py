"""그래프 전체 실행 흐름.

노드 단위 테스트는 상태를 손으로 만들어 넣었다. 여기서는 앞 노드가 채운 값이
뒤 노드로 실제로 전달되는지, 조건 분기가 의도대로 갈라지는지를 본다.

노드 자체의 동작은 각 노드 테스트가 보므로, 여기서는 노드를 기록용 가짜로
바꿔 **순서와 분기**만 확인하는 테스트와, 실제 노드를 그대로 두고 **값 전달**을
확인하는 테스트를 나눈다.
"""

from __future__ import annotations

import pytest

from commit_agent.agent import graph as graph_module
from commit_agent.agent.graph import build_graph, run
from commit_agent.agent.nodes import generate_message, map_issue, propose_issue
from commit_agent.agent.nodes import retrieve_context as retrieve_module
from commit_agent.agent.schemas import CommitAgentState, IssueMatch, IssueProposal
from commit_agent.core.project_config import ProjectConfig
from conftest import DIFF, FakeModel

NODE_NAMES = (
    "analyze_diff",
    "retrieve_context",
    "generate_message",
    "map_issue",
    "propose_issue",
)


@pytest.fixture
def visited(monkeypatch):
    """노드를 기록용 가짜로 바꿔 방문 순서만 남긴다."""
    order: list[str] = []

    def recorder(name: str, result: dict):
        def node(_state: CommitAgentState) -> dict:
            order.append(name)
            return result
        return node

    monkeypatch.setattr(graph_module, "analyze_diff_node", recorder("analyze_diff", {}))
    monkeypatch.setattr(
        graph_module, "retrieve_context_node", recorder("retrieve_context", {})
    )
    monkeypatch.setattr(
        graph_module,
        "generate_message_node",
        recorder("generate_message", {"commit_message": "feat: 무언가"}),
    )
    monkeypatch.setattr(
        graph_module, "propose_issue_node", recorder("propose_issue", {})
    )
    return order


def _run(builder_state: CommitAgentState) -> CommitAgentState:
    """lru_cache를 피해 매번 새로 조립한 그래프로 실행한다."""
    result = build_graph().invoke(builder_state)
    return CommitAgentState.model_validate(result)


def test_매핑되면_제안_노드로_가지_않는다(visited, monkeypatch, issue):
    monkeypatch.setattr(
        graph_module,
        "map_issue_node",
        lambda _s: {"matched_issue": issue, "commit_message": "feat: 무언가"},
    )

    _run(CommitAgentState(diff_text=DIFF))

    assert visited == ["analyze_diff", "retrieve_context", "generate_message"]
    assert "propose_issue" not in visited


def test_매핑되지_않으면_제안_노드로_간다(visited, monkeypatch):
    monkeypatch.setattr(graph_module, "map_issue_node", lambda _s: {"matched_issue": None})

    _run(CommitAgentState(diff_text=DIFF))

    assert visited == [
        "analyze_diff",
        "retrieve_context",
        "generate_message",
        "propose_issue",
    ]


def test_노드가_빠짐없이_등록되어_있다():
    assert set(build_graph().get_graph().nodes) >= {"__start__", *NODE_NAMES}


def test_앞_노드가_채운_값이_뒤로_전달된다(monkeypatch, draft, issue, hits):
    """실제 노드를 그대로 두고 외부 호출만 가짜로 바꾼다.

    `generate_message`가 만든 메시지를 `map_issue`가 검색 쿼리로 받아야 한다.
    """
    monkeypatch.setattr(retrieve_module, "get_store", lambda: _ClosableStore())
    monkeypatch.setattr(retrieve_module, "get_embedding_model", lambda: object())
    monkeypatch.setattr(retrieve_module, "retrieve_commits", lambda *a, **k: hits)
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))

    queries: list[str] = []
    _wire_map_issue(monkeypatch, issue, hits, queries)

    state = _run(CommitAgentState(diff_text=DIFF, repo_slug="owner/name"))

    # map_issue는 diff 요약이 아니라 생성된 메시지로 이슈를 찾아야 한다
    assert queries == [draft.render()]
    assert state.commit_message == f"{draft.render()}\n\nrelated to: #22"
    assert state.retrieved_commits == hits


def test_매핑이_없으면_초안까지_만들어진다(monkeypatch, draft, hits):
    monkeypatch.setattr(retrieve_module, "get_store", lambda: _ClosableStore())
    monkeypatch.setattr(retrieve_module, "get_embedding_model", lambda: object())
    monkeypatch.setattr(retrieve_module, "retrieve_commits", lambda *a, **k: [])
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))
    _wire_map_issue(monkeypatch, None, hits, [])
    _wire_propose_issue(monkeypatch)

    state = _run(CommitAgentState(diff_text=DIFF, repo_slug="owner/name"))

    assert state.matched_issue is None
    assert state.issue_draft is not None
    assert state.issue_draft.title == "새 작업"
    # 초안만 만들고 메시지에는 참조를 붙이지 않는다
    assert "related to" not in state.commit_message


def test_변경이_없으면_끝까지_빈_결과로_지나간다(monkeypatch):
    """인덱싱 전이거나 노이즈만 바뀐 경우. 외부를 전혀 부르지 않아야 한다."""
    for module in (retrieve_module, generate_message, map_issue, propose_issue):
        monkeypatch.setattr(module, "get_chat_model", _explode, raising=False)
        monkeypatch.setattr(module, "get_store", _explode, raising=False)

    state = _run(CommitAgentState(diff_text=""))

    assert state.analysis.is_empty()
    assert state.commit_message == ""
    assert state.matched_issue is None
    assert state.issue_draft is None


def test_run은_초기_상태를_만들어_실행한다(monkeypatch, draft):
    """`run()`이 입력을 상태로 옮기고 최종 상태를 돌려주는지."""
    monkeypatch.setattr(retrieve_module, "get_store", _explode)
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(draft))
    # repo_slug가 없어 map_issue는 건너뛰지만 propose_issue까지는 흘러간다
    _wire_propose_issue(monkeypatch)
    graph_module.get_graph.cache_clear()

    state = run(DIFF, repo_slug=None, project=ProjectConfig(language="en"))

    assert state.diff_text == DIFF
    assert state.project.language == "en"
    assert state.commit_message == draft.render()
    graph_module.get_graph.cache_clear()


class _ClosableStore:
    def close(self) -> None:
        pass


class _Settings:
    github_token = "ghp_x"

    def has_github_token(self) -> bool:
        return True


def _explode(*_args, **_kwargs):
    raise AssertionError("호출되지 않아야 합니다.")


def _wire_map_issue(monkeypatch, issue, hits, queries: list[str]):
    """map_issue의 외부 호출을 가짜로 바꾸고 검색 쿼리를 기록한다."""
    monkeypatch.setattr(map_issue, "get_settings", lambda: _Settings())
    monkeypatch.setattr(map_issue, "open_github", lambda _t: object())
    monkeypatch.setattr(map_issue, "get_repository", lambda *_: object())
    monkeypatch.setattr(map_issue, "get_store", lambda _s: _ClosableStore())
    monkeypatch.setattr(map_issue, "get_embedding_model", lambda _s: object())
    monkeypatch.setattr(map_issue, "index_issues", lambda *a, **k: None)

    def retrieve(_client, _embeddings, message, **_kwargs):
        queries.append(message)
        return hits

    monkeypatch.setattr(map_issue, "retrieve_issues", retrieve)
    monkeypatch.setattr(map_issue, "get_issue", lambda *_: issue)

    number = issue.number if issue else None
    monkeypatch.setattr(
        map_issue,
        "get_chat_model",
        lambda: FakeModel(IssueMatch(issue_number=number, reason="판단")),
    )


def _wire_propose_issue(monkeypatch):
    monkeypatch.setattr(propose_issue, "get_settings", lambda: _Settings())
    monkeypatch.setattr(propose_issue, "open_github", lambda _t: object())
    monkeypatch.setattr(propose_issue, "get_repository", lambda *_: object())
    monkeypatch.setattr(propose_issue, "list_labels", lambda _r: ["enhancement"])
    monkeypatch.setattr(
        propose_issue,
        "get_chat_model",
        lambda: FakeModel(
            IssueProposal(
                worth_tracking=True,
                title="새 작업",
                body="본문",
                labels=["enhancement"],
            )
        ),
    )
