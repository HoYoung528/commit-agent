"""분석 결과를 사람이 읽는 텍스트로 렌더링한다.

LLM 프롬프트에 넣는 용도이자, 이후 RAG에서 유사 커밋·이슈를 찾을 때
검색 쿼리로 쓰이는 형식이다. 같은 변경이면 항상 같은 텍스트가 나오도록
LLM을 쓰지 않고 규칙만으로 만든다.
"""

from __future__ import annotations

from commit_agent.change_analysis.schemas import DiffAnalysis, FileChange


def summarize(analysis: DiffAnalysis) -> str:
    """변경의 윤곽을 짧은 텍스트로 만든다. 패치 본문은 넣지 않는다."""
    if analysis.is_empty():
        return "변경 없음"

    lines = [
        f"파일 {len(analysis.files)}개, "
        f"+{analysis.total_additions()} -{analysis.total_deletions()}",
    ]

    if dirs := analysis.top_level_dirs():
        lines.append("경로: " + ", ".join(f"{d} ({n})" for d, n in dirs.items()))
    if extensions := analysis.extensions():
        lines.append("확장자: " + ", ".join(f"{e} ({n})" for e, n in extensions.items()))

    lines.append("변경 파일:")
    lines.extend(f"  {_file_line(f)}" for f in analysis.files)

    if sections := _touched_sections(analysis):
        lines.append("건드린 함수·클래스: " + ", ".join(sections))
    if analysis.excluded:
        lines.append("제외됨: " + ", ".join(analysis.excluded))

    return "\n".join(lines)


def render_patches(analysis: DiffAnalysis) -> str:
    """패치 본문을 파일별로 이어 붙인다. 프롬프트의 근거 자료로 쓴다."""
    blocks: list[str] = []

    for file in analysis.files:
        if file.is_binary:
            blocks.append(f"--- {file.path} (바이너리)")
            continue
        if not file.hunks:
            continue
        suffix = "  [일부 생략됨]" if file.truncated else ""
        blocks.append(f"--- {file.path}{suffix}\n{file.patch()}")

    return "\n\n".join(blocks)


def _file_line(file: FileChange) -> str:
    """파일 한 줄 요약."""
    parts = [f"[{file.change_type.value}]", file.path]
    if file.old_path:
        parts.append(f"(이전: {file.old_path})")
    if file.is_binary:
        parts.append("(바이너리)")
    else:
        parts.append(f"+{file.additions} -{file.deletions}")
    return " ".join(parts)


def _touched_sections(analysis: DiffAnalysis) -> list[str]:
    """hunk 헤더에 담긴 함수·클래스 이름을 중복 없이 모은다."""
    seen: list[str] = []
    for file in analysis.files:
        for hunk in file.hunks:
            section = hunk.section.strip()
            if section and section not in seen:
                seen.append(section)
    return seen
