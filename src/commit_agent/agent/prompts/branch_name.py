"""브랜치 이름 생성 프롬프트.

규칙을 파싱해 일반화하지 않고, 이 저장소가 써온 이름을 예시로 보여준다.
저장소마다 규칙이 달라 패턴을 추론하려 들면 맞추기 어렵다.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 저장소의 기존 브랜치 이름을 보고 같은 규칙으로 새 이름을 짓는 도구입니다.

- 기존 이름에서 규칙을 읽어내고 그대로 따르세요. 구분자, 이슈 번호 표기 방식,
  접두사 사용 여부를 모두 맞추세요.
- 요약 부분은 항상 영어 소문자로 쓰고 단어는 하이픈으로 잇습니다.
- 요약은 2~4단어로 짧게. 이슈 제목을 그대로 번역하지 말고 핵심만 남기세요.
- 이름만 답하세요. 설명이나 따옴표를 붙이지 마세요."""

USER_TEMPLATE = """\
## 이 저장소의 기존 브랜치 이름
{names}

## 새로 만들 브랜치
커밋 유형: {commit_type}
이슈 번호: {issue}
작업 내용: {subject}

같은 규칙으로 브랜치 이름을 지으세요."""


def build_user_prompt(
    names: list[str], commit_type: str, subject: str, issue_number: int | None
) -> str:
    """기존 이름과 이번 작업 정보를 합친다."""
    return USER_TEMPLATE.format(
        names="\n".join(f"- {name}" for name in names),
        commit_type=commit_type,
        issue=f"#{issue_number}" if issue_number else "(없음)",
        subject=subject,
    )
