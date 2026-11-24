"""생성된 커밋 메시지와 관련된 이슈를 찾는 노드.

검색 쿼리로 변경 요약이 아니라 **생성된 커밋 메시지**를 쓴다. 이슈 본문은
자연어인데 코드 변경 요약으로 찾으면 성격이 달라 변별력이 떨어진다.

검색은 후보만 추리고 관련 여부는 LLM이 판단한다. 유사도가 높아도 실제로
그 이슈를 해결하는 변경이 아닐 수 있다.
"""

# `from __future__ import annotations` 를 쓰지 않는다. LangGraph가 `config`
# 애노테이션을 실제 타입으로 검사하는데, 미래 import가 있으면 문자열로 남아
# 검사가 어긋나며 경고가 난다. requires-python 이 3.11 이상이라 `X | None` 은
# 런타임에서도 그대로 동작한다.
from typing import Any

from langchain_core.runnables import RunnableConfig

from commit_agent.agent.prompts import issue_match as prompts
from commit_agent.agent.schemas import CommitAgentState, IssueMatch, with_reference
from commit_agent.core.config import settings_from
from commit_agent.core.embeddings import get_embedding_model
from commit_agent.core.llm import LLMError, get_chat_model, translate_errors
from commit_agent.core.vector_store import get_store
from commit_agent.git_integration import get_issue, get_repository, open_github
from commit_agent.rag.schemas import SearchHit
from commit_agent.rag.services import index_issues, retrieve_issues

DEFAULT_LIMIT = 5

_SKIPPED: dict[str, Any] = {"retrieved_issues": [], "matched_issue": None}


def map_issue_node(state: CommitAgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """관련 이슈를 찾아 상태에 담는다.

    `config` 는 서버로 실행할 때만 실려 온다. 사용자 GitHub 토큰이 거기
    담겨 있다 — 서버 자기 토큰으로는 사용자 저장소를 읽을 수 없다.
    """
    message = state.commit_message
    if not message or not state.repo_slug or not state.project.issue_mapping:
        return _SKIPPED

    settings = settings_from(config)
    if not settings.has_github_token():
        return _SKIPPED

    try:
        gh_repo = get_repository(open_github(settings.github_token), state.repo_slug)
        client = get_store(settings)
        embeddings = get_embedding_model(settings)

        # 이슈는 수시로 바뀌므로 매핑 직전에 갱신한다.
        # 바뀐 것만 다시 임베딩하므로 평소에는 조회만 하고 끝난다.
        index_issues(gh_repo, client, embeddings, scope=state.repo_slug)
        hits = retrieve_issues(
            client, embeddings, message, limit=DEFAULT_LIMIT, scope=state.repo_slug
        )
        client.close()
    except Exception:
        # 토큰 만료, 네트워크 오류 등. 매핑 없이 넘어간다
        return _SKIPPED

    if not hits:
        return _SKIPPED

    try:
        match = _judge(message, hits)
    except LLMError:
        # 메시지는 이미 만들어졌다. 매핑 하나 때문에 커밋을 막지 않는다
        return {"retrieved_issues": hits, "matched_issue": None}

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
        "commit_message": with_reference(
            message, matched.reference(), state.project.reference_format
        ),
    }


def _judge(message: str, hits: list[SearchHit]) -> IssueMatch:
    """후보 중 실제로 관련 있는 이슈가 있는지 LLM에게 묻는다."""
    model = get_chat_model().with_structured_output(IssueMatch)
    with translate_errors():
        result = model.invoke(
            [
                {"role": "system", "content": prompts.SYSTEM_PROMPT},
                {"role": "user", "content": prompts.build_user_prompt(message, hits)},
            ]
        )

    if isinstance(result, IssueMatch):
        return result
    return IssueMatch.model_validate(result)
