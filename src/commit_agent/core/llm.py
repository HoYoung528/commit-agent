"""LLM 모델 객체 생성.

`init_chat_model`을 쓰므로 제공자 교체가 설정 문자열 변경으로 끝난다.
(`anthropic:claude-sonnet-5` → `openai:gpt-5`)
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from commit_agent.core.config import Settings, get_settings

# 커밋 메시지는 짧다. 넉넉하되 폭주하지 않을 정도로 잡는다.
MAX_TOKENS = 2048


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """설정에 지정된 모델 객체를 만든다."""
    settings = settings or get_settings()

    extra: dict[str, str] = {}
    if settings.has_anthropic_key():
        # 키가 `.env`에만 있고 환경변수로는 없을 수 있으므로 직접 넘긴다
        extra["api_key"] = settings.anthropic_api_key

    # temperature·top_p 같은 샘플링 파라미터는 현재 세대 모델에서 제거됐다.
    # 넣으면 400이 난다.
    return init_chat_model(settings.model, max_tokens=MAX_TOKENS, **extra)
