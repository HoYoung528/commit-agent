"""prepare-commit-msg 훅 스크립트.

`git commit` 실행 시 에디터가 열리기 직전에 git이 이 스크립트를 부른다.
스크립트는 `commit-agent generate` 결과를 커밋 메시지 파일에 써넣는다.

git이 넘기는 인자:
    $1  커밋 메시지 파일 경로
    $2  메시지 출처 (message / template / merge / squash / commit)
    $3  커밋 SHA (amend 등)

훅은 가상환경이 활성화되지 않은 셸에서 실행되므로 `commit-agent` 가 PATH에
없을 수 있다(IDE의 git 패널, 다른 터미널 등). 그래서 설치 시점에 실행 파일의
절대 경로를 스크립트에 박는다.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from commit_agent.git_integration import open_repo

HOOK_FILENAME = "prepare-commit-msg"

# 우리가 설치한 훅인지 판별하는 표식. uninstall이 남의 훅을 지우지 않도록 한다.
HOOK_MARKER = "# commit-agent managed hook"

_TEMPLATE = """\
#!/bin/sh
{marker}
#
# `commit-agent uninstall` 로 제거할 수 있습니다.
# 이 표식 줄을 지우면 uninstall이 이 파일을 인식하지 못합니다.

msg_file="$1"
msg_source="$2"

# -m 으로 메시지를 직접 줬거나 머지·squash·amend 커밋이면 건드리지 않는다.
# 사용자가 이미 쓴 메시지를 덮어쓰면 안 된다.
case "$msg_source" in
  message|merge|squash|commit)
    exit 0
    ;;
esac

# 생성에 실패해도 커밋은 진행되어야 한다.
# API 오류나 네트워크 문제로 커밋 자체가 막히면 안 된다.
generated=$("{command}" generate 2>/dev/null) || exit 0
[ -n "$generated" ] || exit 0

# 기존 내용(주석으로 된 안내문 등)은 아래에 남겨 둔다.
printf '%s\\n\\n' "$generated" | cat - "$msg_file" > "$msg_file.commit-agent"
mv "$msg_file.commit-agent" "$msg_file"
"""


def find_executable() -> str:
    """훅에서 호출할 `commit-agent` 실행 파일의 절대 경로를 찾는다.

    지금 실행 중인 인터프리터 옆을 먼저 보고, 없으면 PATH에서 찾는다.
    """
    scripts_dir = Path(sys.executable).parent
    for name in ("commit-agent.exe", "commit-agent"):
        candidate = scripts_dir / name
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("commit-agent")
    if found:
        return found

    raise FileNotFoundError("commit-agent 실행 파일을 찾을 수 없습니다.")


def build_hook_script(command: str | None = None) -> str:
    """실행 파일 경로를 박은 훅 스크립트를 만든다."""
    path = command or find_executable()
    # 셸에서 Windows 경로의 역슬래시가 이스케이프로 해석되지 않도록 바꾼다
    return _TEMPLATE.format(marker=HOOK_MARKER, command=path.replace("\\", "/"))


def hook_path() -> Path:
    """현재 저장소의 훅 파일 경로."""
    repo = open_repo()
    return Path(repo.git_dir) / "hooks" / HOOK_FILENAME


def is_managed_hook(path: Path) -> bool:
    """commit-agent가 설치한 훅인지 표식으로 판별한다."""
    try:
        return HOOK_MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
