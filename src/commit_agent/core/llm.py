"""LLM 모델 객체 생성.

`init_chat_model`을 쓰므로 제공자 교체가 설정 문자열 변경으로 끝난다.
(`anthropic:claude-sonnet-5` → `openai:gpt-5`)
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from commit_agent.core.config import Settings, get_settings

# 추론 모델은 이 한도를 추론과 출력이 함께 쓴다. 짧은 답을 요구하는 호출에서
# 추론이 한도를 다 쓰면 출력이 비어 버리므로, 출력 길이가 아니라 추론 여유를
# 기준으로 잡는다. 폭주를 막는 안전장치일 뿐 목표치가 아니다.
MAX_TOKENS = 8192


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
    return init_chat_model(settings.model, max_tokens=MAX_TOKENS, **extra)


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
