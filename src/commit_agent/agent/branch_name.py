"""브랜치 이름을 짓는다.

그래프 노드가 아니다. 이름을 지으려면 저장소가 써온 이름 예시가 필요하고 그건
로컬 git에서만 모을 수 있으며, 결과를 쓸지는 사용자가 확인한 뒤 정한다.
그래서 그래프 바깥에 두고 CLI와 서버가 함께 쓴다.

이름이 git에서 쓸 수 있는지 검사하는 일은 여기서 하지 않는다. `git
check-ref-format` 을 쓰므로 저장소가 필요하고, 저장소는 클라이언트에만 있다.
"""

from __future__ import annotations

from commit_agent.agent.prompts import branch_name as prompts
from commit_agent.agent.schemas import BranchNameSuggestion
from commit_agent.core.config import Settings
from commit_agent.core.llm import get_chat_model


def suggest_branch_name(
    names: list[str],
    commit_type: str,
    subject: str,
    issue_number: int | None,
    *,
    settings: Settings | None = None,
) -> str | None:
    """저장소가 써온 이름을 예시로 주고 새 이름을 받는다.

    예시가 없으면 이름을 지어내지 않는다 — 규칙을 배울 근거가 없는데 지으면
    저장소 관례와 어긋난 이름이 나온다.
    """
    if not names:
        return None

    model = get_chat_model(settings).with_structured_output(BranchNameSuggestion)
    result = model.invoke(
        [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": prompts.build_user_prompt(
                    names, commit_type, subject, issue_number
                ),
            },
        ]
    )

    if not isinstance(result, BranchNameSuggestion):
        result = BranchNameSuggestion.model_validate(result)

    return result.name.strip() or None
