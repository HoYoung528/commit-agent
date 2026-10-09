"""생성된 커밋 메시지와 관련된 이슈를 찾는 노드.

검색 쿼리로 변경 요약이 아니라 **생성된 커밋 메시지**를 쓴다. 이슈 본문은
자연어인데 코드 변경 요약으로 찾으면 성격이 달라 변별력이 떨어진다.

검색은 후보만 추리고 관련 여부는 LLM이 판단한다. 유사도가 높아도 실제로
그 이슈를 해결하는 변경이 아닐 수 있다.
"""

from __future__ import annotations

from typing import Any

from commit_agent.agent.prompts import issue_match as prompts
from commit_agent.agent.schemas import CommitAgentState, IssueMatch
from commit_agent.core import get_settings
from commit_agent.core.embeddings import get_embedding_model
from commit_agent.core.llm import get_chat_model
from commit_agent.core.vector_store import get_store
from commit_agent.git_integration import get_issue, get_repository, open_github
from commit_agent.rag.schemas import SearchHit
from commit_agent.rag.services import index_issues, retrieve_issues

DEFAULT_LIMIT = 5

_SKIPPED: dict[str, Any] = {"retrieved_issues": [], "matched_issue": None}


def map_issue_node(state: CommitAgentState) -> dict[str, Any]:
    """관련 이슈를 찾아 상태에 담는다."""
    message = state.commit_message
    settings = get_settings()

    if not message or not state.repo_slug or not settings.has_github_token():
        return _SKIPPED

    try:
        gh_repo = get_repository(open_github(settings.github_token), state.repo_slug)
        client = get_store(settings)
        embeddings = get_embedding_model(settings)

        # 이슈는 수시로 바뀌므로 매핑 직전에 갱신한다.
        # 바뀐 것만 다시 임베딩하므로 평소에는 조회만 하고 끝난다.
        index_issues(gh_repo, client, embeddings)
        hits = retrieve_issues(client, embeddings, message, limit=DEFAULT_LIMIT)
        client.close()
    except Exception:
        # 토큰 만료, 네트워크 오류 등. 매핑 없이 넘어간다
        return _SKIPPED

    if not hits:
        return _SKIPPED

    match = _judge(message, hits)
    if match.issue_number is None:
        return {"retrieved_issues": hits, "matched_issue": None}

    try:
        matched = get_issue(gh_repo, match.issue_number)
    except Exception:
        # LLM이 후보에 없는 번호를 답한 경우
        return {"retrieved_issues": hits, "matched_issue": None}

    return {
        "retrieved_issues": hits,
        "matched_issue": matched,
        "commit_message": _with_reference(message, matched.reference()),
    }


def _with_reference(message: str, reference: str) -> str:
    """메시지 끝에 이슈 참조를 붙인다. 이미 있으면 그대로 둔다."""
    if reference in message:
        return message
    return f"{message.rstrip()}\n\nrelated to: {reference}"


def _judge(message: str, hits: list[SearchHit]) -> IssueMatch:
    """후보 중 실제로 관련 있는 이슈가 있는지 LLM에게 묻는다."""
    model = get_chat_model().with_structured_output(IssueMatch)
    result = model.invoke(
        [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompts.build_user_prompt(message, hits)},
        ]
    )

    if isinstance(result, IssueMatch):
        return result
    return IssueMatch.model_validate(result)
