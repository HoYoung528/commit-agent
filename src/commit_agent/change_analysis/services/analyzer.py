"""변경 분석 모듈의 진입점."""

from __future__ import annotations

from commit_agent.change_analysis.services.parser import parse_diff
from commit_agent.change_analysis.services.preprocessor import (
    DEFAULT_MAX_LINES_PER_FILE,
    DEFAULT_MAX_TOTAL_LINES,
    preprocess,
)
from commit_agent.change_analysis.schemas import DiffAnalysis


def analyze(
    diff_text: str,
    *,
    max_lines_per_file: int = DEFAULT_MAX_LINES_PER_FILE,
    max_total_lines: int = DEFAULT_MAX_TOTAL_LINES,
) -> DiffAnalysis:
    """diff 텍스트를 파싱하고 전처리해 분석 결과를 돌려준다."""
    return preprocess(
        parse_diff(diff_text),
        max_lines_per_file=max_lines_per_file,
        max_total_lines=max_total_lines,
    )
