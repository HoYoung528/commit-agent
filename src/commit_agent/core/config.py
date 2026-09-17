"""환경변수와 `.env`에서 개인 설정을 읽어온다.

여기 담기는 값은 개인 비밀값과 개인 취향뿐이다. 커밋 메시지 언어처럼
저장소마다 정해지는 컨벤션은 프로젝트 설정 파일(`init` 명령)에서 다룬다.

CLI는 사용자의 저장소 안에서 실행되므로 `.env`는 현재 디렉터리에서 찾는다.
실제 환경변수가 있으면 그쪽이 우선한다.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "claude-sonnet-5"


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
        description="커밋 메시지 생성에 쓸 모델",
    )

    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key.strip())

    def has_github_token(self) -> bool:
        return bool(self.github_token.strip())


@lru_cache
def get_settings() -> Settings:
    """설정을 한 번만 읽어 재사용한다."""
    return Settings()
