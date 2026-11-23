"""환경변수와 `.env`에서 개인 설정을 읽어온다.

여기 담기는 값은 개인 비밀값과 개인 취향뿐이다. 커밋 메시지 언어처럼
저장소마다 정해지는 컨벤션은 프로젝트 설정 파일(`init` 명령)에서 다룬다.

CLI는 사용자의 저장소 안에서 실행되므로 `.env`는 현재 디렉터리에서 찾는다.
실제 환경변수가 있으면 그쪽이 우선한다.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.runnables import RunnableConfig
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# `제공자:모델` 형식. 제공자를 바꾸려면 이 값만 바꾸면 된다 (예: "openai:gpt-5").
DEFAULT_MODEL = "anthropic:claude-sonnet-5"

# 저장소 안에 두는 로컬 벡터 스토어 위치. .gitignore 대상이다.
DEFAULT_VECTOR_STORE_PATH = ".commit-agent/qdrant"

# 임베딩도 `제공자:모델` 형식. Anthropic은 임베딩 API가 없어 다른 제공자를 쓴다.
DEFAULT_EMBEDDING_MODEL = "openai:text-embedding-3-large"

# 추론 모델은 짧은 답에도 생각을 길게 한다. 커밋 메시지나 브랜치 이름처럼
# 판단이 단순한 작업에서는 줄여야 커밋이 느려지지 않는다.
# 제공자마다 지원 여부가 다르므로 비워 두면 넘기지 않는다.
DEFAULT_REASONING_EFFORT = "minimal"


class Settings(BaseSettings):
    """환경변수 또는 현재 디렉터리의 `.env`에서 읽어오는 설정."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(
        default="",
        description="LLM 호출용 API 키. env: ANTHROPIC_API_KEY",
    )
    github_token: str = Field(
        default="",
        description="이슈 조회·생성용 personal access token. env: GITHUB_TOKEN",
    )
    model: str = Field(
        default=DEFAULT_MODEL,
        alias="COMMIT_AGENT_MODEL",
        description="커밋 메시지 생성에 쓸 모델. `제공자:모델` 형식",
    )
    openai_api_key: str = Field(
        default="",
        description="임베딩 호출용 API 키. env: OPENAI_API_KEY",
    )
    embedding_model: str = Field(
        default=DEFAULT_EMBEDDING_MODEL,
        alias="COMMIT_AGENT_EMBEDDING_MODEL",
        description="임베딩에 쓸 모델. `제공자:모델` 형식",
    )
    embedding_dimensions: int = Field(
        default=0,
        alias="COMMIT_AGENT_EMBEDDING_DIMENSIONS",
        description="임베딩 차원. 0이면 모델 기본값을 쓴다",
    )
    reasoning_effort: str = Field(
        default=DEFAULT_REASONING_EFFORT,
        alias="COMMIT_AGENT_REASONING_EFFORT",
        description="추론 모델이 생각에 쓸 분량. 비워 두면 모델 기본값을 쓴다",
    )
    vector_store_path: str = Field(
        default=DEFAULT_VECTOR_STORE_PATH,
        alias="COMMIT_AGENT_VECTOR_STORE_PATH",
        description="로컬 벡터 스토어 위치",
    )
    vector_store_url: str = Field(
        default="",
        alias="COMMIT_AGENT_VECTOR_STORE_URL",
        description="공유 벡터 스토어 주소. 지정하면 로컬 대신 여기에 붙는다",
    )
    server_url: str = Field(
        default="",
        alias="COMMIT_AGENT_SERVER_URL",
        description=(
            "에이전트 서버 주소. 지정하면 생성을 서버에 맡기고 모델 API 키가 "
            "필요하지 않다. 비우면 지금처럼 로컬에서 실행한다"
        ),
    )

    def uses_server(self) -> bool:
        """생성을 서버에 맡기는지. 그렇다면 모델 API 키가 필요하지 않다."""
        return bool(self.server_url.strip())

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def has_github_token(self) -> bool:
        return bool(self.github_token.strip())

    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽어 재사용한다."""
    return Settings()


def settings_from(config: RunnableConfig | None) -> Settings:
    """그래프 실행에 실려 온 설정을 꺼낸다. 없으면 프로세스 설정을 쓴다.

    서버는 요청을 받을 때마다 그 사용자의 GitHub 토큰을 담은 `Settings` 를
    만들어 그래프 config에 싣는다. 서버 자기 토큰으로는 사용자 저장소의
    이슈를 읽을 수 없기 때문이다.

    CLI로 실행하면 config가 없으므로 지금처럼 프로세스 설정을 그대로 쓴다.
    `get_settings()` 는 `lru_cache` 라 프로세스 전역이고, 서버에서는 요청마다
    달라야 하므로 그 경로를 쓰지 않는다.
    """
    scoped = (config or {}).get("configurable", {}).get("settings")
    return scoped if isinstance(scoped, Settings) else get_settings()
