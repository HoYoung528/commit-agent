"""테스트 전체가 공유하는 가짜 객체.

노드들은 LLM·GitHub·벡터 스토어를 직접 호출한다. 실제로 부르면 느리고,
키가 필요하고, 결과가 매번 달라져서 단정할 수 없다. 그래서 미리 정한 답을
돌려주는 가짜로 갈아끼운다.

노드는 `from ... import get_issue` 로 자기 이름공간에 끌어다 쓰므로,
monkeypatch 대상은 원본 모듈이 아니라 **노드 모듈의 속성**이어야 한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from commit_agent.agent.schemas import CommitAgentState, CommitMessageDraft, CommitType
from commit_agent.change_analysis import analyze
from commit_agent.git_integration.schemas import IssueInfo
from commit_agent.rag.schemas import SearchHit

DIFF = """\
diff --git a/src/commit_agent/core/llm.py b/src/commit_agent/core/llm.py
index 1111111..2222222 100644
--- a/src/commit_agent/core/llm.py
+++ b/src/commit_agent/core/llm.py
@@ -10,6 +10,9 @@ from commit_agent.core.config import Settings
 def get_chat_model() -> BaseChatModel:
     settings = get_settings()
+    if effort := settings.reasoning_effort.strip():
+        extra["reasoning_effort"] = effort
     return init_chat_model(settings.model, **extra)
"""


class FakeModel:
    """`invoke`가 미리 정한 답을 돌려주는 가짜 LLM.

    `with_structured_output`은 자기 자신을 돌려주므로 체이닝이 그대로 된다.
    호출 횟수를 세어 "불리지 않아야 하는데 불렸는지" 확인할 수 있다.
    """

    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.calls: list[list[dict[str, str]]] = []

    def with_structured_output(self, _schema: Any) -> FakeModel:
        return self

    def invoke(self, messages: list[dict[str, str]]) -> Any:
        self.calls.append(messages)
        return self.answer


def exploding(*_args: Any, **_kwargs: Any) -> Any:
    """불리면 안 되는 자리에 꽂아 둔다."""
    raise AssertionError("호출되지 않아야 합니다.")


@pytest.fixture
def analysis():
    """실제 diff를 파싱한 분석 결과. 전처리까지 거친 상태다."""
    return analyze(DIFF)


@pytest.fixture
def state(analysis):
    """diff 분석까지 끝난 상태."""
    return CommitAgentState(
        diff_text=DIFF,
        repo_slug="owner/name",
        analysis=analysis,
    )


@pytest.fixture
def empty_state():
    """변경이 없는 상태. 각 노드가 일을 건너뛰어야 한다."""
    return CommitAgentState(diff_text="", analysis=analyze(""))


@pytest.fixture
def draft():
    return CommitMessageDraft(
        type=CommitType.FEAT,
        scope="core",
        subject="추론 모델의 생각 분량을 설정으로 노출",
    )


@pytest.fixture
def issue():
    return IssueInfo(
        number=22,
        title="LLM·GitHub API 예외 처리 및 재시도 구현",
        body="재시도 로직이 없다",
        state="open",
        url="https://github.com/owner/name/issues/22",
    )


@pytest.fixture
def hits():
    """검색 결과 두 건. 점수는 내림차순이다."""
    return [
        SearchHit(
            id="aaa",
            text="core/llm.py 수정",
            metadata={"message": "feat(core): 모델 설정 분리", "number": 22},
            score=0.81,
        ),
        SearchHit(
            id="bbb",
            text="cli/errors.py 수정",
            metadata={"message": "fix(cli): 오류 안내 보강", "number": 23},
            score=0.42,
        ),
    ]
