"""`retrieve_context` 노드.

인덱싱하지 않은 저장소에서도 커밋이 되어야 하므로, 검색이 실패하면
빈 결과로 넘어가고 생성은 그대로 진행되어야 한다.
"""

from __future__ import annotations

import pytest

from commit_agent.agent.nodes import retrieve_context
from commit_agent.agent.nodes.retrieve_context import retrieve_context_node


class FakeStore:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(retrieve_context, "get_store", lambda: fake)
    monkeypatch.setattr(retrieve_context, "get_embedding_model", lambda: object())
    return fake


def test_검색_결과를_상태에_담는다(state, store, monkeypatch, hits):
    monkeypatch.setattr(retrieve_context, "retrieve_commits", lambda *a, **k: hits)

    assert retrieve_context_node(state)["retrieved_commits"] == hits


def test_변경이_없으면_검색하지_않는다(empty_state, monkeypatch):
    monkeypatch.setattr(retrieve_context, "get_store", _exploding_store)

    assert retrieve_context_node(empty_state) == {"retrieved_commits": []}


def test_스토어에_접근할_수_없으면_빈_결과로_넘어간다(state, monkeypatch):
    monkeypatch.setattr(retrieve_context, "get_store", _exploding_store)

    assert retrieve_context_node(state) == {"retrieved_commits": []}


def test_검색이_실패해도_빈_결과로_넘어간다(state, store, monkeypatch):
    monkeypatch.setattr(retrieve_context, "retrieve_commits", _exploding_store)

    assert retrieve_context_node(state) == {"retrieved_commits": []}


def test_검색을_마치면_스토어를_닫는다(state, store, monkeypatch, hits):
    monkeypatch.setattr(retrieve_context, "retrieve_commits", lambda *a, **k: hits)
    retrieve_context_node(state)

    assert store.closed


def _exploding_store(*_args, **_kwargs):
    raise RuntimeError("스토어 없음")
