"""매핑되는 이슈가 없을 때 새 이슈를 제안하는 노드.

아직 구현되지 않았다. 그래프 분기를 확인하기 위한 자리표시자이며,
이슈 #20에서 초안 생성 로직으로 교체된다.

여기서는 초안만 만들고 실제 생성은 하지 않는다. 사용자 확인 없이
저장소에 이슈를 만들면 되돌리기 어렵다.
"""

from __future__ import annotations

from typing import Any

from commit_agent.agent.schemas import CommitAgentState


def propose_issue_node(state: CommitAgentState) -> dict[str, Any]:
    """새로 만들 이슈의 초안을 작성한다."""
    return {"issue_draft": None}
