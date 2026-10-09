"""LLM에 넣는 프롬프트.

용도별로 파일을 나눈다. 같은 이름의 함수가 여러 개이므로
모듈째 가져다 쓰는 쪽이 읽기 쉽다.

    from commit_agent.agent.prompts import commit_message, issue_match

    commit_message.build_user_prompt(...)
    issue_match.build_user_prompt(...)
"""

from commit_agent.agent.prompts import commit_message, issue_match

__all__ = ["commit_message", "issue_match"]
