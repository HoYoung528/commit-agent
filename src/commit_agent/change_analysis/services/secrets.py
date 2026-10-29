"""diff에 섞인 비밀값 처리.

스테이징된 diff는 LLM·임베딩 API로 그대로 나간다. 키 파일은 본문을 통째로
빼고, 나머지 파일에서는 흔한 키 형태만 가린다. 모든 비밀값을 찾아내는 것은
목표가 아니다. 무엇을 뺐는지 사용자에게 알리는 데까지가 범위다.
"""

from __future__ import annotations

import re

from commit_agent.change_analysis.schemas import FileChange, Hunk

MASK = "[REDACTED]"

SECRET_FILENAMES = frozenset({"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc"})
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
# 키 이름만 적어 두는 예시 파일은 그대로 보낸다
ENV_EXAMPLE_SUFFIXES = (".example", ".sample", ".template")

# 형태만 보고 확신할 수 있는 토큰
TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),  # GitHub PAT·OAuth 등
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"),  # GitHub fine-grained PAT
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),  # AWS 액세스 키 ID
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),  # Anthropic·OpenAI
)

# `API_KEY=...`, `"token": "..."`, `password: ...` 같은 대입.
# 따옴표 안의 값은 기호가 섞여 있어도 가린다. 따옴표 없는 값은 뒤에
# `(`·`.`·`[` 가 오면 `token=make_token(x)` 같은 코드이므로 건너뛴다.
# 이름에 `key`만 들어가도 걸리므로 `monkey` 같은 오탐이 있지만,
# 조건을 좁히면 `apiKey` 같은 camelCase를 놓친다
ASSIGNMENT = re.compile(
    r"""(?ix)
    \b[\w.-]*(?:key|token|secret|passwd|password)\w*
    ["']?\s*[:=]\s*
    (?: "(?P<double>[^"\s]{8,})"
      | '(?P<single>[^'\s]{8,})'
      | (?P<bare>[a-z0-9_+/=-]{8,}+)(?![(.\[])
    )
    """
)
VALUE_GROUPS = ("double", "single", "bare")


def is_secret_file(path: str) -> bool:
    """본문 전체를 보내면 안 되는 파일인지."""
    name = path.rsplit("/", 1)[-1].lower()
    if name == ".env" or name.startswith(".env."):
        return not name.endswith(ENV_EXAMPLE_SUFFIXES)
    if name.split(".", 1)[0] == "credentials":
        return True
    return name in SECRET_FILENAMES or name.endswith(SECRET_SUFFIXES)


def mask_file(file: FileChange) -> tuple[FileChange, int]:
    """hunk 본문의 비밀값을 가린 파일과 가린 개수를 돌려준다."""
    count = 0
    hunks: list[Hunk] = []

    for hunk in file.hunks:
        lines: list[str] = []
        for line in hunk.lines:
            masked, n = mask_line(line)
            lines.append(masked)
            count += n
        hunks.append(hunk.model_copy(update={"lines": lines}))

    if not count:
        return file, 0
    return file.model_copy(update={"hunks": hunks}), count


def mask_line(line: str) -> tuple[str, int]:
    """한 줄에서 비밀값을 가린 결과와 가린 개수."""
    count = 0
    for pattern in TOKEN_PATTERNS:
        line, n = pattern.subn(MASK, line)
        count += n

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        # 실제 키는 거의 항상 영문과 숫자가 섞여 있다.
        # 이 조건으로 `your-api-key`, `20_000_000` 같은 값을 거른다
        group = next(g for g in VALUE_GROUPS if match[g] is not None)
        value = match[group]
        if not (any(c.isdigit() for c in value) and any(c.isalpha() for c in value)):
            return match[0]
        count += 1
        start, end = (i - match.start() for i in match.span(group))
        return match[0][:start] + MASK + match[0][end:]

    return ASSIGNMENT.sub(replace, line), count
