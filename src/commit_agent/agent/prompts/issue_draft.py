"""매핑되는 이슈가 없을 때 새 이슈 초안을 만드는 프롬프트."""

from __future__ import annotations

import re

SYSTEM_PROMPT = """\
당신은 커밋 내용을 보고 이 작업을 기록할 이슈 초안을 만드는 도구입니다.

먼저 이슈로 남길 가치가 있는지 판단하세요. 모든 변경이 이슈가 되어야 하는 것은
아닙니다. 오타 수정, 포맷팅, 사소한 리팩터링처럼 추적할 필요가 없는 변경이면
초안을 만들지 말고 `worth_tracking` 을 false로 두세요.

초안을 만들 때는:
- 제목은 무엇을 하는 작업인지 한 줄로. 커밋 메시지를 그대로 베끼지 말고
  "해야 할 일" 관점으로 쓰세요.
- 본문은 아래 템플릿을 따르세요. 제목(`#` 줄)과 순서는 그대로 두고 각 칸을
  채웁니다. `<!-- -->` 주석은 무엇을 쓸지 알려주는 안내이니 지우고 내용으로
  바꾸세요. 커밋 내용을 그대로 나열하지 마세요.
- 라벨은 아래 목록에 있는 것만 고르세요. 적절한 것이 없으면 비워 두세요.

제목과 본문은 {language}로 씁니다.

## 본문 템플릿
{template}"""

USER_TEMPLATE = """\
## 커밋 메시지
{message}

## 변경 요약
{summary}

## 이 저장소에서 쓸 수 있는 라벨
{labels}

이 작업을 기록할 이슈 초안을 만드세요. 기록할 가치가 없으면 그렇다고 답하세요."""

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def build_system_prompt(language: str, template: str) -> str:
    """저장소 설정을 반영한 시스템 프롬프트를 만든다."""
    names = {"ko": "한국어", "en": "영어"}
    return SYSTEM_PROMPT.format(language=names.get(language, language), template=template)


def build_user_prompt(message: str, summary: str, labels: list[str]) -> str:
    """커밋 내용과 사용 가능한 라벨을 초안 작성용 메시지로 합친다."""
    return USER_TEMPLATE.format(
        message=message,
        summary=summary,
        labels=", ".join(labels) if labels else "(없음)",
    )


def strip_guides(body: str) -> str:
    """LLM이 지우지 않고 남긴 템플릿 안내 주석을 걷어낸다.

    주석은 GitHub 화면에는 안 보이지만 원문에 남아 이슈를 고칠 때 거슬린다.
    주석을 지우고 생긴 빈 줄 묶음은 한 줄로 줄인다.
    """
    cleaned = _COMMENT.sub("", body)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
