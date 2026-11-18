"""커밋 메시지 프롬프트를 만드는 순수 함수들.

예시 블록과 다시 묻는 메시지는 생성 품질을 직접 좌우하는데, 둘 다 조건이
문자열 안에 숨어 있어 깨져도 조용히 품질만 나빠진다. 경계를 고정한다.
"""

from __future__ import annotations

from commit_agent.agent.prompts.commit_message import (
    build_retry_prompt,
    build_system_prompt,
    strip_trailers,
)


def test_서명과_공동작성자_꼬리말을_걷어낸다():
    message = (
        "fix: 재시도 상한을 지킨다\n"
        "\n"
        "본문 한 줄\n"
        "\n"
        "Signed-off-by: A <a@b.c>\n"
        "Co-authored-by: B <b@c.d>\n"
        "Reviewed-by: C <c@d.e>"
    )

    assert strip_trailers(message) == "fix: 재시도 상한을 지킨다\n\n본문 한 줄"


def test_이슈_참조는_남긴다():
    """저장소가 이슈를 어떻게 다는지는 작성 관례에 속한다."""
    message = "feat: 기능 추가\n\ncloses #12"

    assert strip_trailers(message) == message


def test_본문_문장은_꼬리말로_보지_않는다():
    """`Fixes: ` 로 시작하는 본문 문장과 구분이 어려워 제거 대상에서 뺐다."""
    message = "fix: 경쟁 상태 해결\n\nFixes: a race condition in the retry loop"

    assert strip_trailers(message) == message


def test_대소문자를_가리지_않는다():
    assert strip_trailers("fix: x\n\nSIGNED-OFF-BY: A <a@b.c>") == "fix: x"


def test_꼬리말만_있으면_빈_문자열이_된다():
    assert strip_trailers("Signed-off-by: A <a@b.c>") == ""


def test_허용_타입만_판별_기준과_함께_나열한다():
    prompt = build_system_prompt("ko", ["feat", "chore"])

    assert "- feat: 없던 동작을" in prompt
    assert "- chore: 의존성 갱신" in prompt
    assert "- fix:" not in prompt


def test_기준이_없는_타입은_이름만_적는다():
    """저장소가 규약 밖의 타입을 쓰더라도 목록에서 빠지지 않아야 한다."""
    prompt = build_system_prompt("ko", ["feat", "hotfix"])

    assert "- hotfix\n" in prompt or prompt.rstrip().endswith("- hotfix")


def test_scope_목록이_없으면_scope_규칙을_넣지_않는다():
    prompt = build_system_prompt("ko", ["feat"])

    assert "scope는 다음 중에서만" not in prompt


def test_다시_묻는_메시지가_제목_예산을_계산해_알려준다():
    prompt = build_retry_prompt("feat(core): ", "x" * 70, max_length=72)

    # 접두사 12자를 뺀 60자가 제목에 쓸 수 있는 양
    assert "60자 이내" in prompt
    assert "82자 (상한 72자)" in prompt
    assert "잘라내지 말고" in prompt
