"""브랜치 이름 제안 스키마.

자유 텍스트로 받으면 빈 응답이나 설명이 섞여 오는 경우가 있어 필드로 받는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BranchNameSuggestion(BaseModel):
    """저장소 규칙에 맞춘 브랜치 이름."""

    name: str = Field(
        description="브랜치 이름만. 설명이나 따옴표를 붙이지 않는다",
    )
