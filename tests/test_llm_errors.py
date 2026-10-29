"""LLM 호출 실패를 원인별 안내로 바꾸는 처리."""

from __future__ import annotations

import anthropic
import httpx
import openai
import pytest
import typer
from conftest import api_error

from commit_agent.cli.errors import handle_errors
from commit_agent.core import llm
from commit_agent.core.llm import LLMError, translate_errors

REQUEST = httpx.Request("POST", "https://api.example.com")


def _raise(error: Exception) -> LLMError:
    with pytest.raises(LLMError) as info, translate_errors():
        raise error
    return info.value


@pytest.mark.parametrize("sdk", [anthropic, openai])
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "API 키"),
        (403, "API 키"),
        (404, "모델을 찾을 수 없습니다"),
        (429, "요청 한도"),
        (500, "서버 오류"),
    ],
)
def test_상태_코드별로_원인을_알려준다(sdk, status, expected):
    error = _raise(api_error(status, sdk))

    assert expected in str(error)
    assert error.hint


@pytest.mark.parametrize("sdk", [anthropic, openai])
def test_타임아웃과_연결_실패를_구분한다(sdk):
    assert "초 안에" in str(_raise(sdk.APITimeoutError(request=REQUEST)))
    assert "연결할 수 없습니다" in str(_raise(sdk.APIConnectionError(request=REQUEST)))


def test_원인을_모르는_API_오류도_LLMError가_된다():
    request = httpx.Request("POST", "https://api.example.com")
    error = anthropic.BadRequestError(
        "too long", response=httpx.Response(400, request=request), body=None
    )

    assert "호출에 실패했습니다" in str(_raise(error))


def test_API와_무관한_예외는_그대로_내보낸다():
    """코드 버그까지 API 오류로 보이면 원인을 찾기 어렵다."""
    with pytest.raises(KeyError), translate_errors():
        raise KeyError("x")


def test_모델에_재시도와_타임아웃_상한을_넘긴다(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm, "init_chat_model", lambda *_a, **kw: captured.update(kw))

    llm.get_chat_model()

    assert captured["max_retries"] == llm.MAX_RETRIES
    assert captured["timeout"] == llm.TIMEOUT_SECONDS


def test_CLI는_traceback_대신_안내를_출력한다(capsys):
    @handle_errors
    def command():
        with translate_errors():
            raise api_error(429)

    with pytest.raises(typer.Exit) as info:
        command()

    stderr = capsys.readouterr().err
    assert info.value.exit_code == 1
    assert "요청 한도" in stderr
    assert "잠시 후 다시 시도하세요" in stderr
