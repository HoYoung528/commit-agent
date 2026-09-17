"""변경 분석 결과 스키마."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeType(StrEnum):
    """파일 단위 변경 유형."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class Hunk(BaseModel):
    """unified diff의 hunk 하나. `@@ -a,b +c,d @@` 로 시작하는 변경 덩어리."""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    section: str = Field(default="", description="hunk 헤더 뒤에 붙는 함수·클래스 이름")
    lines: list[str] = Field(default_factory=list, description="`+`/`-`/` ` 로 시작하는 본문")

    def header(self) -> str:
        """`@@ -a,b +c,d @@` 형태의 hunk 헤더."""
        section = f" {self.section}" if self.section else ""
        return (
            f"@@ -{self.old_start},{self.old_lines} "
            f"+{self.new_start},{self.new_lines} @@{section}"
        )

    def text(self) -> str:
        """헤더를 포함한 hunk 전체 텍스트."""
        return "\n".join([self.header(), *self.lines])


class FileChange(BaseModel):
    """diff에서 추출한 파일 하나의 변경 정보."""

    path: str
    change_type: ChangeType
    additions: int = 0
    deletions: int = 0
    old_path: str | None = Field(default=None, description="rename 전 경로")
    is_binary: bool = False
    hunks: list[Hunk] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="전처리에서 패치 본문이 잘렸는지")

    def extension(self) -> str:
        """확장자(점 제외, 소문자). 없으면 빈 문자열."""
        name = self.path.rsplit("/", 1)[-1]
        stem = name.lstrip(".")
        return stem.rsplit(".", 1)[-1].lower() if "." in stem else ""

    def directory(self) -> str:
        """파일이 속한 디렉터리. 최상위 파일이면 빈 문자열."""
        return self.path.rsplit("/", 1)[0] if "/" in self.path else ""

    def top_level_dir(self) -> str:
        """최상위 디렉터리. 최상위 파일이면 빈 문자열."""
        return self.path.split("/", 1)[0] if "/" in self.path else ""

    def changed_lines(self) -> int:
        """추가 + 삭제 라인 수."""
        return self.additions + self.deletions

    def patch(self) -> str:
        """hunk들을 합친 패치 본문."""
        return "\n".join(h.text() for h in self.hunks)


class DiffAnalysis(BaseModel):
    """staged diff 전체에 대한 분석 결과."""

    files: list[FileChange] = Field(default_factory=list)
    excluded: list[str] = Field(
        default_factory=list,
        description="전처리에서 제외된 파일 경로 (lock 파일, 바이너리 등)",
    )

    def is_empty(self) -> bool:
        return not self.files

    def total_additions(self) -> int:
        return sum(f.additions for f in self.files)

    def total_deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    def changed_lines(self) -> int:
        """전체 추가 + 삭제 라인 수."""
        return self.total_additions() + self.total_deletions()

    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    def is_truncated(self) -> bool:
        """패치 본문이 잘린 파일이 하나라도 있는지."""
        return any(f.truncated for f in self.files)

    def extensions(self) -> dict[str, int]:
        """확장자별 파일 수. 개수 내림차순."""
        return _counted(f.extension() for f in self.files)

    def top_level_dirs(self) -> dict[str, int]:
        """최상위 디렉터리별 파일 수. 개수 내림차순."""
        return _counted(f.top_level_dir() for f in self.files)

    def by_change_type(self) -> dict[ChangeType, list[FileChange]]:
        """변경 유형별 파일 묶음."""
        grouped: dict[ChangeType, list[FileChange]] = {}
        for f in self.files:
            grouped.setdefault(f.change_type, []).append(f)
        return grouped


def _counted(values: Iterable[str]) -> dict[str, int]:
    """빈 문자열은 제외하고 값별 개수를 세어 개수 내림차순으로 정렬."""
    counts: dict[str, int] = {}
    for v in values:
        if not v:
            continue
        counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
