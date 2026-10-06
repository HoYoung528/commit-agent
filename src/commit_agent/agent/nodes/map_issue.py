"""생성된 커밋 메시지와 관련된 이슈를 찾는 노드.

아직 구현되지 않았다. 그래프 분기를 확인하기 위한 자리표시자이며,
이슈 #19에서 검색과 판단 로직으로 교체된다.

검색 쿼리로는 변경 요약이 아니라 **생성된 커밋 메시지**를 쓴다. 이슈 본문은
자연어인데 코드 변경 요약으로 찾으면 성격이 달라 변별력이 떨어진다.
"""

from __future__ import annotations

from typing import Any

from commit_agent.agent.schemas import CommitAgentState


def map_issue_node(state: CommitAgentState) -> dict[str, Any]:
    """관련 이슈를 찾아 상태에 담는다."""
    return {"retrieved_issues": [], "matched_issue": None}
