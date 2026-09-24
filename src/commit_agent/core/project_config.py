"""저장소 단위 설정(`.commit-agent.toml`).

개인 비밀값을 담는 `.env`와 달리 이 파일은 커밋되어 팀원 간에 공유된다.
커밋 메시지 언어처럼 저장소마다 정해지는 컨벤션을 담는다.

파일이 없으면 기본값을 쓰므로 `init` 없이도 도구는 동작한다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_FILENAME = ".commit-agent.toml"
DEFAULT_LANGUAGE = "ko"


class ProjectConfig(BaseModel):
    """저장소의 커밋 컨벤션."""

    language: str = Field(
        default=DEFAULT_LANGUAGE,
        description="커밋 메시지를 쓸 언어. ko 또는 en",
    )
    types: list[str] = Field(
        default_factory=list,
        description="허용하는 Conventional Commits 타입. 비어 있으면 전체 허용",
    )

    def allows(self, commit_type: str) -> bool:
        """해당 타입이 이 저장소에서 허용되는지."""
        return not self.types or commit_type in self.types


def find_config_file(start: Path | None = None) -> Path | None:
    """현재 디렉터리에서 위로 올라가며 설정 파일을 찾는다.

    하위 디렉터리에서 실행해도 저장소 루트의 설정을 읽게 한다.
    저장소 루트를 만나면 더 올라가지 않는다.
    """
    current = (start or Path.cwd()).resolve()

    for directory in [current, *current.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            break

    return None


def load_project_config(start: Path | None = None) -> ProjectConfig:
    """설정 파일을 읽는다. 없으면 기본값을 돌려준다."""
    path = find_config_file(start)
    if path is None:
        return ProjectConfig()

    with path.open("rb") as f:
        data = tomllib.load(f)

    return ProjectConfig.model_validate(data)
