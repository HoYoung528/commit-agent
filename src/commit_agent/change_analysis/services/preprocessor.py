"""LLM에 넘기기 전 diff 전처리.

의미 없는 파일(lock, 빌드 산출물 등)을 걸러내고, 패치 본문이 너무 길면 잘라낸다.
파일 목록과 추가·삭제 라인 수는 잘라내도 그대로 유지된다.
"""

from __future__ import annotations

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
) -> DiffAnalysis:
    """노이즈 파일을 제외하고 패치 본문 길이를 제한한 새 결과를 돌려준다."""
    kept: list[FileChange] = []
    excluded: list[str] = []

    for file in analysis.files:
        if is_noise(file):
            excluded.append(file.path)
        else:
            kept.append(file)

    limited = _limit_patch_size(kept, max_lines_per_file, max_total_lines)
    return DiffAnalysis(files=limited, excluded=[*analysis.excluded, *excluded])


def _limit_patch_size(
    files: list[FileChange], max_lines_per_file: int, max_total_lines: int
) -> list[FileChange]:
    """파일별·전체 라인 수 예산에 맞춰 hunk 본문을 잘라낸다."""
    limited: list[FileChange] = []
    remaining = max_total_lines

    for file in files:
        budget = min(max_lines_per_file, remaining)
        hunks, used, truncated = _take_lines(file, budget)
        remaining -= used

        if truncated or len(hunks) != len(file.hunks):
            file = file.model_copy(update={"hunks": hunks, "truncated": True})
        limited.append(file)

    return limited


def _take_lines(file: FileChange, budget: int) -> tuple[list[Hunk], int, bool]:
    """예산 안에 들어가는 hunk만 잘라서 (hunk 목록, 사용한 라인 수, 잘렸는지)."""
    if budget <= 0:
        return [], 0, bool(file.hunks)

    taken: list[Hunk] = []
    used = 0
    truncated = False

    for hunk in file.hunks:
        if used >= budget:
            truncated = True
            break
        room = budget - used
        if len(hunk.lines) <= room:
            taken.append(hunk)
            used += len(hunk.lines)
        else:
            taken.append(hunk.model_copy(update={"lines": hunk.lines[:room]}))
            used = budget
            truncated = True

    return taken, used, truncated
