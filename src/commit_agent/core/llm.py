"""LLM 모델 객체 생성과 호출 실패 처리.

`init_chat_model`을 쓰므로 제공자 교체가 설정 문자열 변경으로 끝난다.
(`anthropic:claude-sonnet-5` → `openai:gpt-5`)

재시도는 제공자 SDK가 한다. 429·5xx·연결 오류를 지수 백오프로 다시 보내고
`Retry-After`도 지킨다. 여기서는 횟수와 시간 상한만 정하고, 재시도 끝에도
실패하면 원인별 안내를 담은 `LLMError`로 바꾼다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import anthropic
import openai
from langchain.chat_models import init_chat_model
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError

from commit_agent.core.config import Settings, get_settings

# 추론 모델은 이 한도를 추론과 출력이 함께 쓴다. 짧은 답을 요구하는 호출에서
# 추론이 한도를 다 쓰면 출력이 비어 버리므로, 출력 길이가 아니라 추론 여유를
# 기준으로 잡는다. 폭주를 막는 안전장치일 뿐 목표치가 아니다.
MAX_TOKENS = 8192

# 훅 안에서 돌기 때문에 커밋이 오래 멈추면 안 된다. SDK 기본 타임아웃은
# 600초라 너무 길다. 추론 모델이 MAX_TOKENS를 다 써도 끝날 만큼만 잡는다.
TIMEOUT_SECONDS = 120
MAX_RETRIES = 3


class LLMError(Exception):
    """LLM 호출이 재시도 끝에도 실패했을 때. 다음에 할 일을 함께 담는다."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.hint = hint


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """설정에 지정된 모델 객체를 만든다."""
    settings = settings or get_settings()

    extra: dict[str, str] = {}
    # 키가 `.env`에만 있고 환경변수로는 없을 수 있으므로 직접 넘긴다.
    # 제공자마다 쓰는 키가 다르므로 모델 문자열의 접두사로 고른다.
    if api_key := api_key_for(settings):
        extra["api_key"] = api_key

    # 추론 모델 전용 파라미터다. 지원하지 않는 제공자에 넘기면 터지므로
    # 설정이 비어 있으면 아예 넘기지 않는다.
    if effort := settings.reasoning_effort.strip():
        extra["reasoning_effort"] = effort

    # temperature·top_p 같은 샘플링 파라미터는 현재 세대 모델에서 제거됐다.
    # 넣으면 400이 난다.
    return init_chat_model(
        settings.model,
        max_tokens=MAX_TOKENS,
        timeout=TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
        **extra,
    )


@contextmanager
def translate_errors() -> Iterator[None]:
    """제공자 SDK의 예외를 `LLMError`로 바꾼다.

    모르는 예외는 그대로 내보낸다. 코드 버그까지 API 오류로 보이면 안 된다.
    임베딩 호출도 같은 SDK를 쓰므로 여기로 감싼다.
    """
    try:
        yield
    except (anthropic.APIError, openai.APIError) as exc:
        raise _explain(exc) from exc
    except (OutputParserException, ValidationError) as exc:
        raise LLMError(
            "모델 응답을 해석하지 못했습니다.",
            hint="다시 실행하세요. 반복되면 다른 모델을 써 보세요.",
        ) from exc


def _explain(exc: anthropic.APIError | openai.APIError) -> LLMError:
    """예외 종류로 원인과 안내 문구를 고른다."""
    if isinstance(
        exc,
        (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            openai.AuthenticationError,
            openai.PermissionDeniedError,
        ),
    ):
        return LLMError("모델 API 키가 유효하지 않습니다.", hint="`.env` 의 API 키를 확인하세요.")
    if isinstance(exc, (anthropic.RateLimitError, openai.RateLimitError)):
        return LLMError("모델 API 요청 한도를 넘었습니다.", hint="잠시 후 다시 시도하세요.")
    # 타임아웃은 연결 오류의 하위 타입이라 먼저 본다
    if isinstance(exc, (anthropic.APITimeoutError, openai.APITimeoutError)):
        return LLMError(
            f"모델 응답이 {TIMEOUT_SECONDS}초 안에 오지 않았습니다.",
            hint="잠시 후 다시 시도하세요.",
        )
    if isinstance(exc, (anthropic.APIConnectionError, openai.APIConnectionError)):
        return LLMError("모델 API에 연결할 수 없습니다.", hint="네트워크 연결을 확인하세요.")
    if isinstance(exc, (anthropic.NotFoundError, openai.NotFoundError)):
        return LLMError(
            "설정한 모델을 찾을 수 없습니다.", hint="`.env` 의 모델 이름을 확인하세요."
        )
    if isinstance(exc, (anthropic.APIStatusError, openai.APIStatusError)) and (
        exc.status_code >= 500
    ):
        return LLMError(
            f"모델 API 서버 오류입니다 ({exc.status_code}).",
            hint="제공자 쪽 문제입니다. 잠시 후 다시 시도하세요.",
        )
    return LLMError(f"모델 API 호출에 실패했습니다: {exc}", hint="요청 내용과 설정을 확인하세요.")


def api_key_for(settings: Settings) -> str:
    """`제공자:모델` 형식에서 제공자를 읽어 해당 키를 고른다.

    키가 없으면 빈 문자열. 호출 전에 키가 있는지 확인할 때도 쓴다.
    """
    provider = settings.model.split(":", 1)[0] if ":" in settings.model else ""

    keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
    }
    return keys.get(provider, "").strip()
