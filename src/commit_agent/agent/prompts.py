"""LLM에 넣는 프롬프트.

RAG가 붙으면 유사 커밋·이슈 예시가 사용자 메시지에 추가된다.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
당신은 코드 변경을 읽고 Conventional Commits 규약에 맞는 커밋 메시지를 쓰는 도구입니다.

판단 기준:
- 무엇이 바뀌었는지가 아니라 왜 바꿨는지를 쓰세요. diff를 그대로 옮겨 적지 마세요.
- 변경 유형은 파일 경로가 아니라 변경의 의도로 판단하세요.
  다만 테스트 파일만 바뀌었으면 test, 문서만 바뀌었으면 docs가 보통 맞습니다.
- scope는 변경이 한 모듈에 모여 있을 때만 쓰고, 여러 곳에 흩어져 있으면 비워 두세요.
- 한 줄로 충분하면 본문은 비워 두세요. 억지로 채우지 마세요.
- 변경이 여러 갈래면 가장 중요한 것을 제목에 쓰고 나머지를 본문에 나열하세요.

제목과 본문은 한국어로 쓰고, 타입 접두사는 영어 그대로 둡니다."""

USER_TEMPLATE = """\
다음 변경에 대한 커밋 메시지를 작성하세요.

## 변경 요약
{summary}

## 변경 내용
{patches}"""


def build_user_prompt(summary: str, patches: str) -> str:
    """분석 요약과 패치 본문을 사용자 메시지로 합친다."""
    return USER_TEMPLATE.format(summary=summary, patches=patches or "(내용 없음)")
