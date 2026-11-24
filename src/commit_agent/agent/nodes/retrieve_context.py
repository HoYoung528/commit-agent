"""생성에 참고할 과거 커밋을 찾아 상태에 담는 노드.

인덱싱하지 않은 저장소에서도 동작해야 하므로, 검색에 실패하면 빈 결과로
넘어가고 생성은 그대로 진행한다.
"""

from __future__ import annotations

from typing import Any

from commit_agent.agent.schemas import CommitAgentState
from commit_agent.core.embeddings import get_embedding_model
from commit_agent.core.vector_store import get_store
from commit_agent.rag.services import retrieve_commits

# 예시가 3개를 넘으면 이득이 평탄해지고 서로 간섭한다는 보고가 여럿이다.
# 늘려도 정답 타입이 다수를 차지하지 못해 판단이 바뀌지 않는 것도 측정으로 확인했다.
DEFAULT_LIMIT = 3


def retrieve_context_node(state: CommitAgentState) -> dict[str, Any]:
    """현재 변경과 비슷한 과거 커밋을 찾는다."""
    analysis = state.analysis
    if analysis is None or analysis.is_empty():
        return {"retrieved_commits": []}

    try:
        client = get_store()
        hits = retrieve_commits(
            client,
            get_embedding_model(),
            analysis,
            limit=DEFAULT_LIMIT,
            # 한 스토어를 여러 저장소가 함께 쓸 때 섞이지 않게 한다
            scope=state.repo_slug,
        )
        client.close()
    except Exception:
        # 인덱싱 전이거나 스토어에 접근할 수 없는 경우. 예시 없이 생성한다
        return {"retrieved_commits": []}

    return {"retrieved_commits": hits}
