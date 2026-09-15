"""`git diff` 텍스트를 구조화된 분석 결과로 변환.

저장소에 접근하지 않고 diff 텍스트만 입력으로 받는다. diff를 꺼내오는 일은
`git_integration`이 담당한다.
"""

from __future__ import annotations

import re

from commit_agent.change_analysis.schemas import ChangeType, DiffAnalysis, FileChange, Hunk

_FILE_HEADER = re.compile(r"^diff --git (?P<paths>.+)$")
_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@(?P<section>.*)$"
)
_RENAME_FROM = re.compile(r"^rename from (?P<path>.+)$")
_RENAME_TO = re.compile(r"^rename to (?P<path>.+)$")

_NO_NEWLINE = "\\ No newline at end of file"


def parse_diff(text: str) -> DiffAnalysis:
    """`git diff` 출력 텍스트를 `DiffAnalysis`로 변환."""
    parsed = (_parse_file(block) for block in _split_files(text))
    return DiffAnalysis(files=[f for f in parsed if f is not None])


def _split_files(text: str) -> list[list[str]]:
    """`diff --git` 줄을 기준으로 파일별 블록으로 나눈다."""
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in text.splitlines():
        if _FILE_HEADER.match(line):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)

    if current is not None:
        blocks.append(current)
    return blocks


def _parse_file(block: list[str]) -> FileChange | None:
    """파일 블록 하나를 `FileChange`로 변환. 경로를 못 찾으면 None."""
    old_from_header, new_from_header = _paths_from_header(block[0])
    new_path: str | None = None
    old_path: str | None = None
    rename_from: str | None = None
    rename_to: str | None = None
    change_type = ChangeType.MODIFIED
    is_binary = False
    body_start = len(block)

    for i, line in enumerate(block[1:], start=1):
        if line.startswith("@@"):
            body_start = i
            break
        if line.startswith("new file mode"):
            change_type = ChangeType.ADDED
        elif line.startswith("deleted file mode"):
            change_type = ChangeType.DELETED
        elif m := _RENAME_FROM.match(line):
            rename_from = _strip_prefix(m.group("path"))
        elif m := _RENAME_TO.match(line):
            rename_to = _strip_prefix(m.group("path"))
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            is_binary = True
        elif line.startswith("--- "):
            old_path = _strip_prefix(line[4:])
        elif line.startswith("+++ "):
            new_path = _strip_prefix(line[4:])

    if rename_from and rename_to:
        change_type = ChangeType.RENAMED
        old_path, new_path = rename_from, rename_to

    path = new_path or old_path or new_from_header or old_from_header
    if not path:
        return None

    hunks = _parse_hunks(block[body_start:])

    return FileChange(
        path=path,
        change_type=change_type,
        additions=sum(1 for h in hunks for ln in h.lines if ln.startswith("+")),
        deletions=sum(1 for h in hunks for ln in h.lines if ln.startswith("-")),
        old_path=old_path if change_type is ChangeType.RENAMED else None,
        is_binary=is_binary,
        hunks=hunks,
    )


def _parse_hunks(lines: list[str]) -> list[Hunk]:
    """`@@` 로 시작하는 hunk들을 파싱."""
    hunks: list[Hunk] = []
    current: Hunk | None = None

    for line in lines:
        if m := _HUNK_HEADER.match(line):
            current = Hunk(
                old_start=int(m.group("old_start")),
                old_lines=int(m.group("old_lines") or 1),
                new_start=int(m.group("new_start")),
                new_lines=int(m.group("new_lines") or 1),
                section=m.group("section").strip(),
            )
            hunks.append(current)
        elif current is not None and line != _NO_NEWLINE:
            current.lines.append(line)

    return hunks


def _paths_from_header(line: str) -> tuple[str, str]:
    """`diff --git a/x b/y` 줄에서 (이전 경로, 이후 경로)를 뽑는다.

    경로에 공백이 들어갈 수 있어 마지막 ` b/` 를 기준으로 자른다.
    """
    m = _FILE_HEADER.match(line)
    if m is None:
        return "", ""

    paths = m.group("paths")
    idx = paths.rfind(" b/")
    if idx == -1:
        idx = paths.rfind(' "b/')
    if idx == -1:
        return "", ""

    return _strip_prefix(paths[:idx]), _strip_prefix(paths[idx + 1 :])


def _strip_prefix(path: str) -> str:
    """따옴표를 풀고 `a/`, `b/` 접두사를 제거. `/dev/null` 은 빈 문자열."""
    path = _unquote(path.strip())
    if path == "/dev/null":
        return ""
    return path[2:] if path.startswith(("a/", "b/")) else path


def _unquote(path: str) -> str:
    """git이 특수문자 경로에 씌우는 따옴표와 이스케이프를 푼다."""
    if len(path) < 2 or not path.startswith('"') or not path.endswith('"'):
        return path

    body = path[1:-1]
    try:
        escaped = body.encode("latin-1", "backslashreplace")
        return escaped.decode("unicode_escape").encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return body
