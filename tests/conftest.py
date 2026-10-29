"""테스트 전체가 공유하는 가짜 객체.

노드들은 LLM·GitHub·벡터 스토어를 직접 호출한다. 실제로 부르면 느리고,
키가 필요하고, 결과가 매번 달라져서 단정할 수 없다. 그래서 미리 정한 답을
돌려주는 가짜로 갈아끼운다.

노드는 `from ... import get_issue` 로 자기 이름공간에 끌어다 쓰므로,
monkeypatch 대상은 원본 모듈이 아니라 **노드 모듈의 속성**이어야 한다.
"""

from __future__ import annotations

from typing import Any

import anthropic
import httpx
import pytest

from commit_agent.agent.schemas import CommitAgentState, CommitMessageDraft, CommitType
from commit_agent.change_analysis import analyze
from commit_agent.core import get_settings
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


class FailingModel(FakeModel):
    """`invoke`가 정해 둔 예외를 던지는 가짜 LLM. 재시도 끝에 실패한 상황이다."""

    def __init__(self, error: Exception) -> None:
        super().__init__(None)
        self.error = error

    def invoke(self, messages: list[dict[str, str]]) -> Any:
        self.calls.append(messages)
        raise self.error


_STATUS_ERRORS = {
    401: "AuthenticationError",
    403: "PermissionDeniedError",
    404: "NotFoundError",
    429: "RateLimitError",
    500: "InternalServerError",
}


def api_error(status: int, sdk: Any = anthropic) -> Exception:
    """제공자 SDK가 HTTP 상태 코드에 맞춰 던지는 예외를 만든다.

    Anthropic과 OpenAI SDK는 예외 이름과 생성자가 같다.
    """
    request = httpx.Request("POST", "https://api.example.com")
    response = httpx.Response(status, request=request)
    error_class = getattr(sdk, _STATUS_ERRORS[status])
    return error_class("실패", response=response, body=None)


def exploding(*_args: Any, **_kwargs: Any) -> Any:
    """불리면 안 되는 자리에 꽂아 둔다."""
    raise AssertionError("호출되지 않아야 합니다.")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """가짜로 바꾸는 것을 깜빡한 경로가 실제 API를 부르지 못하게 막는다.

    노드를 하나라도 빠뜨리면 조용히 네트워크를 타서 느려지고 키가 필요해진다.
    여기서 막아 두면 그런 테스트가 통과하지 않고 바로 실패한다.

    키도 가짜로 덮는다. 실패 출력에 지역 변수가 찍히므로 실제 키를 쓰면
    로그에 그대로 남는다.
    """
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "test-key")
    get_settings.cache_clear()

    monkeypatch.setattr(
        "commit_agent.core.llm.init_chat_model",
        _refuse("LLM"),
    )
    monkeypatch.setattr(
        "commit_agent.core.embeddings.init_embeddings",
        _refuse("임베딩"),
    )
    monkeypatch.setattr(
        "commit_agent.core.vector_store.QdrantClient",
        _refuse("벡터 스토어"),
    )

    yield

    # 가짜 키가 담긴 설정이 다음 테스트로 넘어가지 않게 한다
    get_settings.cache_clear()


def _refuse(what: str):
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            f"테스트에서 실제 {what}를 불렀습니다. 해당 노드를 가짜로 바꾸세요."
        )

    return refuse


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
