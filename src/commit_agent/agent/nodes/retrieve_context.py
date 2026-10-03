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

DEFAULT_LIMIT = 5


def retrieve_context_node(state: CommitAgentState) -> dict[str, Any]:
    """현재 변경과 비슷한 과거 커밋을 찾는다."""
    analysis = state.analysis
    if analysis is None or analysis.is_empty():
        return {"retrieved_commits": []}

    try:
        client = get_store()
        hits = retrieve_commits(client, get_embedding_model(), analysis, limit=DEFAULT_LIMIT)
        client.close()
    except Exception:
        # 인덱싱 전이거나 스토어에 접근할 수 없는 경우. 예시 없이 생성한다
        return {"retrieved_commits": []}

    return {"retrieved_commits": hits}
