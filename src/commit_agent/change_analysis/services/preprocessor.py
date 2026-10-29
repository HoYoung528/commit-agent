"""LLM에 넘기기 전 diff 전처리.

의미 없는 파일(lock, 빌드 산출물 등)을 걸러내고, 패치 본문이 너무 길면 잘라낸다.
파일 목록과 추가·삭제 라인 수는 잘라내도 그대로 유지된다.

길이는 라인 수와 문자 수 두 가지로 제한한다. 번들 출력이나 대용량 JSON처럼
한 줄이 매우 긴 파일은 라인 상한만으로는 막을 수 없다.
"""

from __future__ import annotations

from dataclasses import dataclass

from commit_agent.change_analysis.schemas import DiffAnalysis, FileChange, Hunk

# 내용을 읽어도 커밋 메시지에 도움이 안 되는 파일들
NOISE_FILENAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "composer.lock",
        "go.sum",
    }
)
NOISE_DIRS = frozenset(
    {"node_modules", "dist", "build", "vendor", "__pycache__", ".venv", "venv"}
)
NOISE_SUFFIXES = (".min.js", ".min.css", ".map", ".snap", ".lock")

DEFAULT_MAX_LINES_PER_FILE = 300
DEFAULT_MAX_TOTAL_LINES = 1500
# 평범한 코드라면 라인 상한에 먼저 걸리도록 한 줄 평균 60~70자를 잡았다
DEFAULT_MAX_CHARS_PER_FILE = 20_000
DEFAULT_MAX_TOTAL_CHARS = 100_000


def is_noise(file: FileChange) -> bool:
    """커밋 메시지 생성에 참고할 가치가 없는 파일인지."""
    name = file.path.rsplit("/", 1)[-1]
    if name in NOISE_FILENAMES or name.endswith(NOISE_SUFFIXES):
        return True
    return any(part in NOISE_DIRS for part in file.path.split("/")[:-1])


def preprocess(
    analysis: DiffAnalysis,
    *,
    max_lines_per_file: int = DEFAULT_MAX_LINES_PER_FILE,
    max_total_lines: int = DEFAULT_MAX_TOTAL_LINES,
    max_chars_per_file: int = DEFAULT_MAX_CHARS_PER_FILE,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> DiffAnalysis:
    """노이즈 파일을 제외하고 패치 본문 길이를 제한한 새 결과를 돌려준다."""
    kept: list[FileChange] = []
    excluded: list[str] = []

    for file in analysis.files:
        if is_noise(file):
            excluded.append(file.path)
        else:
            kept.append(file)

    limited = _limit_patch_size(
        kept,
        _Budget(max_lines_per_file, max_chars_per_file),
        _Budget(max_total_lines, max_total_chars),
    )
    return DiffAnalysis(files=limited, excluded=[*analysis.excluded, *excluded])


@dataclass
class _Budget:
    """남은 라인 수와 문자 수."""

    lines: int
    chars: int


def _limit_patch_size(
    files: list[FileChange], per_file: _Budget, total: _Budget
) -> list[FileChange]:
    """파일별·전체 예산에 맞춰 hunk 본문을 잘라낸다."""
    limited: list[FileChange] = []

    for file in files:
        budget = _Budget(
            min(per_file.lines, total.lines), min(per_file.chars, total.chars)
        )
        hunks, used, truncated = _take_lines(file, budget)
        total.lines -= used.lines
        total.chars -= used.chars

        if truncated:
            file = file.model_copy(update={"hunks": hunks, "truncated": True})
        limited.append(file)

    return limited


def _take_lines(file: FileChange, budget: _Budget) -> tuple[list[Hunk], _Budget, bool]:
    """예산 안에 들어가는 만큼만 잘라서 (hunk 목록, 사용량, 잘렸는지).

    남은 문자 수보다 긴 줄은 그 줄 안에서 자른다. 줄 단위로만 자르면
    한 줄짜리 번들 파일은 본문이 통째로 사라진다.
    """
    taken: list[Hunk] = []
    used = _Budget(0, 0)

    for hunk in file.hunks:
        kept: list[str] = []
        for line in hunk.lines:
            room = budget.chars - used.chars
            if used.lines >= budget.lines or room <= 0:
                break
            kept.append(line[:room])
            used.lines += 1
            used.chars += len(kept[-1])
            if len(line) > room:
                break

        if kept == hunk.lines:
            taken.append(hunk)
            continue

        if kept:
            taken.append(hunk.model_copy(update={"lines": kept}))
        return taken, used, True

    return taken, used, False
