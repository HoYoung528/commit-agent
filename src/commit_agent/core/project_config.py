"""저장소 단위 설정(`.commit-agent.toml`).

개인 비밀값을 담는 `.env`와 달리 이 파일은 커밋되어 팀원 간에 공유된다.
커밋 메시지 언어처럼 저장소마다 정해지는 컨벤션을 담는다.

파일이 없으면 기본값을 쓰므로 `init` 없이도 도구는 동작한다.
파일이 있으면 엄격하게 읽는다. 오타 난 항목을 조용히 무시하면 팀이 정한
규칙이 적용되지 않는데도 아무도 모른다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import ErrorDetails

CONFIG_FILENAME = ".commit-agent.toml"
DEFAULT_LANGUAGE = "ko"
LANGUAGES = ("ko", "en")
DEFAULT_MAX_HEADER_LENGTH = 72
DEFAULT_REFERENCE_FORMAT = "related to: {ref}"

# `agent.schemas.CommitType`과 같은 목록이다. core가 agent를 불러오면 순환
# import가 생기므로 따로 두고, 둘이 어긋나지 않는지는 테스트로 확인한다.
COMMIT_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)


class ProjectConfigError(Exception):
    """설정 파일을 읽을 수 없거나 값이 잘못됐을 때."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"{path.name} 설정이 잘못됐습니다.\n" + "\n".join(problems))
        self.path = path
        self.problems = problems


class ProjectConfig(BaseModel):
    """저장소의 커밋 컨벤션."""

    # TOML은 값의 타입을 그대로 주므로 변환하지 않는다.
    # 느슨하게 두면 `issue_mapping = "no"` 가 문자열이라 참으로 읽힌다
    model_config = ConfigDict(extra="forbid", strict=True)

    # --- 메시지 형식 ---
    language: str = Field(
        default=DEFAULT_LANGUAGE,
        description="커밋 메시지를 쓸 언어. ko 또는 en",
    )
    types: list[str] = Field(
        default_factory=list,
        description="허용하는 Conventional Commits 타입. 비어 있으면 전체 허용",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="허용하는 scope. 비어 있으면 자유롭게 쓴다",
    )
    max_header_length: int = Field(
        default=DEFAULT_MAX_HEADER_LENGTH,
        ge=20,
        le=200,
        description="첫 줄(타입·scope 포함)의 최대 글자 수",
    )
    reference_format: str = Field(
        default=DEFAULT_REFERENCE_FORMAT,
        description="이슈 참조 줄의 형식. `{ref}` 자리에 `#번호`가 들어간다",
    )

    # --- 기능 스위치 ---
    issue_mapping: bool = Field(default=True, description="관련 이슈를 찾아 참조를 붙일지")
    propose_issue: bool = Field(default=True, description="관련 이슈가 없을 때 새 이슈를 제안할지")
    branch_suggest: bool = Field(
        default=True, description="기본 브랜치에서 커밋할 때 새 브랜치를 제안할지"
    )

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError(f"{', '.join(LANGUAGES)} 중 하나여야 합니다")
        return value

    @field_validator("types")
    @classmethod
    def _known_types(cls, value: list[str]) -> list[str]:
        if unknown := [t for t in value if t not in COMMIT_TYPES]:
            raise ValueError(
                f"알 수 없는 타입입니다: {', '.join(unknown)} "
                f"(쓸 수 있는 타입: {', '.join(COMMIT_TYPES)})"
            )
        return value

    @field_validator("reference_format")
    @classmethod
    def _has_reference(cls, value: str) -> str:
        if "{ref}" not in value:
            raise ValueError("`{ref}` 자리가 있어야 합니다 (예: \"Closes {ref}\")")
        try:
            value.format(ref="#1")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError("`{ref}` 말고 다른 중괄호는 쓸 수 없습니다") from exc
        return value

    def allows(self, commit_type: str) -> bool:
        """해당 타입이 이 저장소에서 허용되는지."""
        return not self.types or commit_type in self.types

    def allowed_types(self) -> list[str]:
        """허용 타입 목록. 설정이 비어 있으면 전체."""
        return self.types or list(COMMIT_TYPES)

    def allows_scope(self, scope: str) -> bool:
        """해당 scope를 쓸 수 있는지."""
        return not self.scopes or scope in self.scopes


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

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ProjectConfigError(path, [f"  TOML 문법 오류: {exc}"]) from exc

    try:
        return ProjectConfig.model_validate(data)
    except ValidationError as exc:
        raise ProjectConfigError(path, [_describe(e) for e in exc.errors()]) from exc


def _describe(error: ErrorDetails) -> str:
    """pydantic 오류 하나를 `  항목: 이유` 한 줄로 만든다."""
    field = ".".join(str(part) for part in error["loc"]) or "(전체)"

    if error["type"] == "extra_forbidden":
        reason = "알 수 없는 항목입니다. 오타가 아닌지 확인하세요"
    elif error["type"] == "value_error" and "ctx" in error:
        # 직접 쓴 검증 메시지. pydantic이 붙이는 "Value error, " 접두사를 뗀다
        reason = str(error["ctx"]["error"])
    else:
        reason = error["msg"]

    return f"  {field}: {reason}"
