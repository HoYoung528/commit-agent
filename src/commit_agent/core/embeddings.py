"""임베딩 모델 객체 생성.

`init_embeddings` 를 쓰므로 제공자 교체가 설정 문자열 변경으로 끝난다.
Anthropic은 임베딩 API를 제공하지 않아 생성 모델과 제공자가 다를 수 있다.
"""

from __future__ import annotations

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings

from commit_agent.core.config import Settings, get_settings


def get_embedding_model(settings: Settings | None = None) -> Embeddings:
    """설정에 지정된 임베딩 모델 객체를 만든다."""
    settings = settings or get_settings()

    extra: dict[str, object] = {}
    if settings.has_openai_key():
        # 키가 `.env`에만 있고 환경변수로는 없을 수 있으므로 직접 넘긴다
        extra["api_key"] = settings.openai_api_key
    if settings.embedding_dimensions:
        extra["dimensions"] = settings.embedding_dimensions

    return init_embeddings(settings.embedding_model, **extra)
