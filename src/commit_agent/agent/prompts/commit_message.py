"""커밋 메시지 생성 프롬프트."""

from __future__ import annotations

import re

from commit_agent.core.project_config import DEFAULT_MAX_HEADER_LENGTH
from commit_agent.rag.schemas import SearchHit

_LANGUAGE_NAMES = {"ko": "한국어", "en": "영어"}

# 커밋 꼬리말. git·도구가 붙이는 줄이라 작성 관례와 무관하다.
# 이슈 참조(`closes:` 등)는 빼지 않는다. 저장소가 이슈를 어떻게 다는지는
# 관례에 속하고, `Fixes: a race condition` 같은 본문 문장과 구분하기 어렵다.
TRAILER = re.compile(
    r"^(signed-off-by|co-authored-by|reviewed-by|acked-by|tested-by|"
    r"reported-by|suggested-by)\s*:",
    re.IGNORECASE,
)

# 타입 이름만 나열하면 경계가 헷갈리는 쌍이 많다. feat/fix, refactor/perf/style,
# build/ci/chore 세 묶음에서 주로 섞인다. 지시문에 판별 기준을 적는 것이
# 프롬프트 수준에서 측정된 가장 큰 레버다(지시문 제거 시 F1 최대 27.9% 하락).
TYPE_CRITERIA = {
    "feat": "없던 동작을 추가하거나 기존 동작의 범위를 넓힘. 사용자가 새로 할 수 있는 일이 생긴다",
    "fix": "의도대로 동작하지 않던 것을 바로잡음. 고치기 전에도 그 동작은 있어야 했다",
    "docs": "문서만 바뀜. 코드 주석만 고친 경우도 포함",
    "style": "동작을 바꾸지 않는 서식 변경. 들여쓰기, 줄바꿈, 포맷터 적용",
    "refactor": "동작은 그대로 두고 구조를 바꿈. 고친 버그도 추가한 기능도 없다",
    "perf": "동작은 그대로 두고 더 빠르거나 가볍게 만듦",
    "test": "테스트 코드만 추가하거나 고침",
    "build": "빌드 방식이나 의존성을 바꿈. 패키지 매니페스트·락파일·빌드 설정",
    "ci": "CI 설정이나 워크플로를 바꿈",
    # 배제 조건("다른 타입이 맞으면 그쪽")을 주면 조금이라도 걸치는 쪽으로 도망가
    # 정답률이 떨어진다. 저장소들은 잡무성 변경을 폭넓게 chore로 묶으므로 예시로 제시한다.
    "chore": "의존성 갱신, 설정·스크립트 정리, 버전 올리기, 생성 파일 갱신처럼 제품 동작과 직접 관련 없는 잡무",
    "revert": "이전 커밋을 되돌림",
}

SYSTEM_TEMPLATE = """\
당신은 코드 변경을 읽고 Conventional Commits 규약에 맞는 커밋 메시지를 쓰는 도구입니다.

판단 기준:
- 무엇이 바뀌었는지가 아니라 왜 바꿨는지를 쓰세요. diff를 그대로 옮겨 적지 마세요.
- 변경 유형은 파일 경로가 아니라 변경의 의도로 판단하세요.
- scope는 변경이 한 모듈에 모여 있을 때만 쓰고, 여러 곳에 흩어져 있으면 비워 두세요.
- 한 줄로 충분하면 본문은 비워 두세요. 억지로 채우지 마세요.
- 변경이 여러 갈래면 가장 중요한 것을 제목에 쓰고 나머지를 본문에 나열하세요.
- 첫 줄은 타입과 scope를 포함해 {max_length}자를 넘기지 마세요.

이 저장소가 허용하는 타입은 다음뿐입니다. 이 중에서만 고르세요.
{type_criteria}
{scope_rule}
제목과 본문은 {language}로 쓰고, 타입 접두사는 영어 그대로 둡니다."""

SCOPE_RULE = """
scope는 다음 중에서만 고르세요. 맞는 것이 없으면 비워 두세요.
{scopes}
"""

USER_TEMPLATE = """\
다음 변경에 대한 커밋 메시지를 작성하세요.
{examples}
## 변경 요약
{summary}
{metrics}
## 변경 내용
{patches}"""

METRICS_TEMPLATE = """
## 변경 규모
{metrics}
"""

EXAMPLES_TEMPLATE = """
## 이 저장소의 과거 커밋 예시

아래는 지금 변경과 비슷한 작업에 이 저장소가 실제로 쓴 메시지입니다.
문장 길이, 본문을 쓰는 방식, scope 사용 여부 같은 관행을 따르되
내용을 그대로 베끼지는 마세요.

{examples}
"""


def build_system_prompt(
    language: str,
    types: list[str],
    scopes: list[str] | None = None,
    max_length: int = DEFAULT_MAX_HEADER_LENGTH,
) -> str:
    """저장소 설정을 반영한 시스템 프롬프트를 만든다."""
    return SYSTEM_TEMPLATE.format(
        type_criteria=_type_criteria(types),
        scope_rule=SCOPE_RULE.format(scopes=", ".join(scopes)) if scopes else "",
        max_length=max_length,
        language=_LANGUAGE_NAMES.get(language, language),
    )


def _type_criteria(types: list[str]) -> str:
    """허용 타입만 판별 기준과 함께 나열한다."""
    return "\n".join(
        f"- {t}: {TYPE_CRITERIA[t]}" if t in TYPE_CRITERIA else f"- {t}" for t in types
    )


def build_user_prompt(
    summary: str, patches: str, examples: str = "", metrics: str = ""
) -> str:
    """분석 요약과 패치 본문을 사용자 메시지로 합친다."""
    return USER_TEMPLATE.format(
        examples=f"\n{examples}" if examples else "",
        summary=summary,
        metrics=METRICS_TEMPLATE.format(metrics=metrics) if metrics else "",
        patches=patches or "(내용 없음)",
    )


def build_examples(hits: list[SearchHit]) -> str:
    """검색된 과거 커밋을 프롬프트에 넣을 예시 블록으로 만든다.

    메시지만 보여주면 문장 투만 배우므로, 어떤 변경에 어떤 메시지를 썼는지
    짝으로 제시해 판단 기준까지 참고하게 한다.
    """
    blocks = []
    for hit in hits:
        message = strip_trailers(str(hit.metadata.get("message") or ""))
        if not message:
            continue
        change = hit.text.splitlines()[0] if hit.text else ""
        blocks.append(f"### 변경: {change}\n{message}")

    if not blocks:
        return ""
    return EXAMPLES_TEMPLATE.format(examples="\n\n".join(blocks))


def strip_trailers(message: str) -> str:
    """서명·공동작성자 같은 꼬리말을 걷어낸다.

    도구나 템플릿이 붙이는 줄이라 저장소의 작성 관례가 아니다. 저장소에 따라
    예시 대부분에 붙어 있어, 그대로 두면 "본문을 이렇게 쓴다"는 신호를 흐린다.
    """
    kept = [line for line in message.splitlines() if not TRAILER.match(line.strip())]
    return "\n".join(kept).strip()
