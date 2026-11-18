"""`generate_message` 노드."""

from __future__ import annotations

import pytest

from commit_agent.agent.nodes import generate_message
from commit_agent.agent.schemas import CommitMessageDraft, CommitType, draft_schema
from commit_agent.core.llm import LLMError
from commit_agent.core.project_config import ProjectConfig
from conftest import FailingModel, FakeModel, SequenceModel, api_error, exploding


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


def test_허용_타입을_판별_기준과_함께_전달한다(state, model):
    """타입 이름만 주면 경계가 헷갈리므로 기준을 함께 보낸다."""
    state.project = ProjectConfig(types=["feat", "fix"])
    generate_message.generate_message_node(state)

    system_message = model.calls[0][0]["content"]
    assert "- feat: 없던 동작을" in system_message
    assert "- fix: 의도대로" in system_message
    # 허용하지 않은 타입의 기준은 넣지 않는다
    assert "- refactor:" not in system_message


def test_dict로_와도_스키마로_되살린다(state, monkeypatch):
    raw = {"type": "fix", "scope": None, "subject": "오류 수정", "body": None}
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(raw))

    result = generate_message.generate_message_node(state)

    assert isinstance(result["draft"], CommitMessageDraft)
    assert result["commit_message"] == "fix: 오류 수정"


def _answer(monkeypatch, **fields):
    """LLM이 돌려줄 조각을 정한다."""
    base = {"type": "feat", "scope": None, "subject": "기능 추가", "body": None}
    fake = FakeModel({**base, **fields})
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: fake)
    return fake


def test_허용_타입만_고를_수_있는_스키마를_넘긴다():
    schema = draft_schema(["feat", "fix"]).model_json_schema()

    [enum] = [d["enum"] for d in schema["$defs"].values() if "enum" in d]
    assert enum == ["feat", "fix"]


def test_좁힌_스키마로_받은_결과도_원래_스키마로_옮긴다(state, monkeypatch):
    narrowed = draft_schema(["feat", "fix"])
    answer = narrowed(type="fix", subject="오류 수정")
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(answer))
    state.project = ProjectConfig(types=["feat", "fix"])

    result = generate_message.generate_message_node(state)

    assert result["draft"].type is CommitType.FIX
    assert result["commit_message"] == "fix: 오류 수정"


def test_허용하지_않은_타입을_고르면_실패한다(state, monkeypatch):
    _answer(monkeypatch, type="test")
    state.project = ProjectConfig(types=["feat", "fix"])

    with pytest.raises(LLMError, match="허용하지 않는 타입"):
        generate_message.generate_message_node(state)


def test_목록에_없는_scope는_비운다(state, monkeypatch):
    _answer(monkeypatch, scope="agent")
    state.project = ProjectConfig(scopes=["core", "cli"])

    assert generate_message.generate_message_node(state)["commit_message"] == "feat: 기능 추가"


def test_목록에_있는_scope는_그대로_둔다(state, monkeypatch):
    _answer(monkeypatch, scope="core")
    state.project = ProjectConfig(scopes=["core", "cli"])

    result = generate_message.generate_message_node(state)

    assert result["commit_message"] == "feat(core): 기능 추가"


def test_첫_줄이_길면_내용을_덜어_다시_쓰게_한다(state, monkeypatch):
    """자르면 문장이 중간에서 끊기므로 먼저 다시 묻는다."""
    long = {"type": "feat", "scope": None, "body": None,
            "subject": "설정 파일의 항목을 검증하고 잘못된 값을 알려준다"}
    short = {**long, "subject": "설정 항목을 검증한다"}
    fake = SequenceModel(long, short)
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: fake)
    state.project = ProjectConfig(max_header_length=30)

    result = generate_message.generate_message_node(state)

    assert len(fake.calls) == 2
    assert result["commit_message"] == "feat: 설정 항목을 검증한다"


def test_상한_안에_들어오면_다시_묻지_않는다(state, monkeypatch):
    fake = _answer(monkeypatch, subject="기능 추가")
    state.project = ProjectConfig(max_header_length=72)

    generate_message.generate_message_node(state)

    assert len(fake.calls) == 1


def test_다시_물을_때_제목에_쓸_수_있는_글자_수를_알려준다(state, monkeypatch):
    """첫 줄 상한만 주면 모델이 접두사 길이를 가늠해야 해서 또 넘긴다."""
    fake = _answer(monkeypatch, scope="core", subject="설정 파일의 항목을 검증하고 잘못된 값을 알려준다")
    state.project = ProjectConfig(max_header_length=30)

    generate_message.generate_message_node(state)

    retry = fake.calls[1][-1]["content"]
    assert "feat(core): 설정 파일의 항목을 검증하고 잘못된 값을 알려준다" in retry
    assert "30자" in retry
    # 접두사 `feat(core): ` 12자를 뺀 18자가 제목에 쓸 수 있는 양
    assert "18자 이내" in retry
    assert "잘라내지 말고" in retry


def test_다시_물어도_길면_최후_수단으로_자른다(state, monkeypatch):
    """훅 안에서 돌기 때문에 여기서 실패하면 커밋 메시지가 비어 버린다."""
    _answer(monkeypatch, subject="설정 파일의 항목을 검증하고 잘못된 값을 알려준다")
    state.project = ProjectConfig(max_header_length=30)

    header = generate_message.generate_message_node(state)["commit_message"]

    assert len(header) <= 30
    assert header == "feat: 설정 파일의 항목을 검증하고 잘못된 값을"


def test_다시_물어도_길면_scope를_먼저_버린다(state, monkeypatch):
    """scope는 빼도 문장이 남지만 제목을 자르면 문장이 끊긴다."""
    _answer(monkeypatch, scope="core", subject="설정 항목을 검증한다")
    state.project = ProjectConfig(max_header_length=26)

    header = generate_message.generate_message_node(state)["commit_message"]

    assert header == "feat: 설정 항목을 검증한다"


def test_scope가_길어_제목_자리가_없으면_scope를_버린다(state, monkeypatch):
    _answer(monkeypatch, scope="a-very-long-module-name", subject="기능을 추가한다 정말로 많이")
    state.project = ProjectConfig(max_header_length=36)

    header = generate_message.generate_message_node(state)["commit_message"]

    assert header.startswith("feat: ")
    assert len(header) <= 36


def test_scope_목록과_길이_상한을_프롬프트에_알린다(state, model):
    state.project = ProjectConfig(scopes=["core", "cli"], max_header_length=50)
    generate_message.generate_message_node(state)

    system_message = model.calls[0][0]["content"]
    assert "core, cli" in system_message
    assert "50자" in system_message


def test_호출이_실패하면_안내를_담아_올린다(state, monkeypatch):
    """만들 메시지가 없으니 삼키지 않고 CLI까지 올려 보낸다."""
    failing = FailingModel(api_error(429))
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: failing)

    with pytest.raises(LLMError, match="요청 한도"):
        generate_message.generate_message_node(state)
