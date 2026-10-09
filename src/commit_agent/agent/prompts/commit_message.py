"""커밋 메시지 생성 프롬프트."""

from __future__ import annotations

from commit_agent.rag.schemas import SearchHit

_LANGUAGE_NAMES = {"ko": "한국어", "en": "영어"}

SYSTEM_TEMPLATE = """\
당신은 코드 변경을 읽고 Conventional Commits 규약에 맞는 커밋 메시지를 쓰는 도구입니다.

판단 기준:
- 무엇이 바뀌었는지가 아니라 왜 바꿨는지를 쓰세요. diff를 그대로 옮겨 적지 마세요.
- 변경 유형은 파일 경로가 아니라 변경의 의도로 판단하세요.
  다만 테스트 파일만 바뀌었으면 test, 문서만 바뀌었으면 docs가 보통 맞습니다.
- scope는 변경이 한 모듈에 모여 있을 때만 쓰고, 여러 곳에 흩어져 있으면 비워 두세요.
- 한 줄로 충분하면 본문은 비워 두세요. 억지로 채우지 마세요.
- 변경이 여러 갈래면 가장 중요한 것을 제목에 쓰고 나머지를 본문에 나열하세요.

이 저장소가 허용하는 타입은 다음뿐입니다. 이 중에서만 고르세요.
{types}

제목과 본문은 {language}로 쓰고, 타입 접두사는 영어 그대로 둡니다."""

USER_TEMPLATE = """\
다음 변경에 대한 커밋 메시지를 작성하세요.
{examples}
## 변경 요약
{summary}

## 변경 내용
{patches}"""

EXAMPLES_TEMPLATE = """
## 이 저장소의 과거 커밋 예시

아래는 지금 변경과 비슷한 작업에 이 저장소가 실제로 쓴 메시지입니다.
문장 길이, 본문을 쓰는 방식, scope 사용 여부 같은 관행을 따르되
내용을 그대로 베끼지는 마세요.

{examples}
"""


def build_system_prompt(language: str, types: list[str]) -> str:
    """저장소 설정을 반영한 시스템 프롬프트를 만든다."""
    return SYSTEM_TEMPLATE.format(
        types=", ".join(types),
        language=_LANGUAGE_NAMES.get(language, language),
    )


def build_user_prompt(summary: str, patches: str, examples: str = "") -> str:
    """분석 요약과 패치 본문을 사용자 메시지로 합친다."""
    return USER_TEMPLATE.format(
        examples=f"\n{examples}" if examples else "",
        summary=summary,
        patches=patches or "(내용 없음)",
    )


def build_examples(hits: list[SearchHit]) -> str:
    """검색된 과거 커밋을 프롬프트에 넣을 예시 블록으로 만든다.

    메시지만 보여주면 문장 투만 배우므로, 어떤 변경에 어떤 메시지를 썼는지
    짝으로 제시해 판단 기준까지 참고하게 한다.
    """
    blocks = []
    for hit in hits:
        message = str(hit.metadata.get("message") or "").strip()
        if not message:
            continue
        change = hit.text.splitlines()[0] if hit.text else ""
        blocks.append(f"### 변경: {change}\n{message}")

    if not blocks:
        return ""
    return EXAMPLES_TEMPLATE.format(examples="\n\n".join(blocks))
