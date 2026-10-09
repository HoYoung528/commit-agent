"""매핑되는 이슈가 없을 때 새 이슈 초안을 만드는 프롬프트."""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 커밋 내용을 보고 이 작업을 기록할 이슈 초안을 만드는 도구입니다.

먼저 이슈로 남길 가치가 있는지 판단하세요. 모든 변경이 이슈가 되어야 하는 것은
아닙니다. 오타 수정, 포맷팅, 사소한 리팩터링처럼 추적할 필요가 없는 변경이면
초안을 만들지 말고 `worth_tracking` 을 false로 두세요.

초안을 만들 때는:
- 제목은 무엇을 하는 작업인지 한 줄로. 커밋 메시지를 그대로 베끼지 말고
  "해야 할 일" 관점으로 쓰세요.
- 본문에는 왜 필요한지와 무엇을 하는지를 적으세요. 커밋 내용을 나열하지 마세요.
- 라벨은 아래 목록에 있는 것만 고르세요. 적절한 것이 없으면 비워 두세요.

제목과 본문은 {language}로 씁니다."""

USER_TEMPLATE = """\
## 커밋 메시지
{message}

## 변경 요약
{summary}

## 이 저장소에서 쓸 수 있는 라벨
{labels}

이 작업을 기록할 이슈 초안을 만드세요. 기록할 가치가 없으면 그렇다고 답하세요."""


def build_system_prompt(language: str) -> str:
    """저장소 설정을 반영한 시스템 프롬프트를 만든다."""
    names = {"ko": "한국어", "en": "영어"}
    return SYSTEM_PROMPT.format(language=names.get(language, language))


def build_user_prompt(message: str, summary: str, labels: list[str]) -> str:
    """커밋 내용과 사용 가능한 라벨을 초안 작성용 메시지로 합친다."""
    return USER_TEMPLATE.format(
        message=message,
        summary=summary,
        labels=", ".join(labels) if labels else "(없음)",
    )
