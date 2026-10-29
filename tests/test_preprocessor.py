"""diff 전처리의 길이 제한."""

from __future__ import annotations

from commit_agent.change_analysis.schemas import ChangeType, DiffAnalysis, FileChange, Hunk
from commit_agent.change_analysis.services.preprocessor import preprocess


def _file(path: str, *hunk_lines: list[str]) -> FileChange:
    hunks = [
        Hunk(old_start=1, old_lines=0, new_start=1, new_lines=len(lines), lines=lines)
        for lines in hunk_lines
    ]
    return FileChange(path=path, change_type=ChangeType.MODIFIED, hunks=hunks)


def _run(*files: FileChange, **limits: int) -> DiffAnalysis:
    return preprocess(DiffAnalysis(files=list(files)), **limits)


def test_예산_안이면_그대로_둔다():
    file = _file("a.py", ["+a", "+b"], ["+c"])

    result = _run(file)

    assert result.files == [file]
    assert not result.is_truncated()


def test_라인_상한을_넘으면_잘린다():
    result = _run(_file("a.py", ["+a", "+b"], ["+c", "+d"]), max_lines_per_file=3)

    [file] = result.files
    assert [h.lines for h in file.hunks] == [["+a", "+b"], ["+c"]]
    assert file.truncated


def test_한_줄이_긴_파일은_문자_상한에서_줄_안쪽까지_잘린다():
    result = _run(_file("bundle.js", ["+" + "x" * 1000]), max_chars_per_file=100)

    [file] = result.files
    assert len(file.hunks[0].lines[0]) == 100
    assert file.truncated


def test_문자_상한이_줄_경계에_걸리면_다음_hunk는_빠진다():
    result = _run(_file("a.json", ["+" + "x" * 9], ["+y"]), max_chars_per_file=10)

    [file] = result.files
    assert [h.lines for h in file.hunks] == [["+" + "x" * 9]]
    assert file.truncated


def test_전체_문자_예산은_파일끼리_나눠_쓴다():
    first = _file("a.svg", ["+" + "x" * 79])
    second = _file("b.svg", ["+" + "y" * 79])

    result = _run(first, second, max_total_chars=100)

    a, b = result.files
    assert a == first
    assert len(b.hunks[0].lines[0]) == 20
    assert b.truncated


def test_예산이_바닥나면_뒤_파일은_목록만_남는다():
    first = _file("a.py", ["+" + "x" * 99])
    second = _file("b.py", ["+b"])

    result = _run(first, second, max_total_chars=100)

    assert result.paths() == ["a.py", "b.py"]
    assert result.files[1].hunks == []
    assert result.files[1].truncated
