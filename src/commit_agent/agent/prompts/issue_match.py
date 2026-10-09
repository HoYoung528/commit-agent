"""커밋과 이슈를 연결할지 판단하는 프롬프트."""

from __future__ import annotations

from commit_agent.rag.schemas import SearchHit

# 후보 이슈 본문을 얼마나 보여줄지. 길면 판단이 흐려지고 토큰만 든다.
MAX_BODY_PREVIEW = 500

SYSTEM_PROMPT = """\
당신은 커밋이 어떤 이슈를 해결하는지 판단하는 도구입니다.

판단 기준:
- 이 커밋이 그 이슈가 요구한 일을 실제로 하는지 보세요.
- 주제가 겹친다고 관련 있는 것은 아닙니다. 같은 모듈을 건드렸더라도
  이슈가 요구한 것과 다른 일을 했다면 관련 없습니다.
- 확실하지 않으면 관련 없다고 답하세요. 틀린 연결은 연결하지 않느니만 못합니다.
- 후보 중에 맞는 것이 없으면 번호를 비워 두세요."""

USER_TEMPLATE = """\
## 커밋 메시지
{message}

## 후보 이슈
{candidates}

이 커밋이 해결하는 이슈가 후보 중에 있으면 그 번호를, 없으면 비워서 답하세요."""


def build_user_prompt(message: str, candidates: list[SearchHit]) -> str:
    """커밋 메시지와 후보 이슈를 판단용 메시지로 합친다."""
    blocks = []
    for hit in candidates:
        number = hit.metadata.get("number")
        title = hit.metadata.get("title") or ""
        # 인덱싱할 때 "제목\n\n본문" 형태로 넣었으므로 본문만 떼어낸다
        body = hit.text.split("\n\n", 1)[1] if "\n\n" in hit.text else ""
        blocks.append(f"### #{number} {title}\n{body.strip()[:MAX_BODY_PREVIEW]}")

    return USER_TEMPLATE.format(
        message=message,
        candidates="\n\n".join(blocks) if blocks else "(후보 없음)",
    )
