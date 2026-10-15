"""브랜치를 조회하고 만든다.

읽기만 하는 `repo.py` 와 달리 저장소 상태를 바꾸므로 따로 둔다.
"""

from __future__ import annotations

import re

from git import Repo
from git.exc import GitCommandError

# "Merge pull request #59 from HoYoung528/feat/#30/issue-create"
_MERGE_BRANCH = re.compile(r"^Merge pull request #\d+ from [^/\s]+/(\S+)")

# 여기 있는 브랜치에서만 새 브랜치를 딴다. 작업 중에 또 분기하면 곤란하다.
DEFAULT_BRANCHES = ("main", "master")


def current_branch(repo: Repo) -> str | None:
    """현재 브랜치 이름. detached HEAD면 None."""
    try:
        return repo.active_branch.name
    except TypeError:
        return None


def on_default_branch(repo: Repo) -> bool:
    """기본 브랜치에 있는지. 여기서만 새 브랜치를 제안한다."""
    return current_branch(repo) in DEFAULT_BRANCHES


def branch_exists(repo: Repo, name: str) -> bool:
    """같은 이름의 로컬 브랜치가 이미 있는지."""
    return any(head.name == name for head in repo.heads)


def collect_branch_names(repo: Repo, *, limit: int = 20) -> list[str]:
    """이 저장소가 써온 브랜치 이름을 모은다.

    머지한 브랜치는 보통 삭제되므로 머지 커밋 메시지가 유일한 기록이다.
    남아 있는 로컬 브랜치도 함께 본다.
    """
    names: list[str] = []

    if repo.head.is_valid():
        for commit in repo.iter_commits(max_count=200, merges=True):
            matched = _MERGE_BRANCH.match(str(commit.message).strip())
            if matched:
                names.append(matched.group(1))

    names.extend(
        head.name for head in repo.heads if head.name not in DEFAULT_BRANCHES
    )

    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)

    return unique[:limit]


def is_valid_name(repo: Repo, name: str) -> bool:
    """git이 받아들이는 브랜치 이름인지 git에게 직접 묻는다."""
    if not name:
        return False
    try:
        repo.git.check_ref_format("--branch", name)
    except GitCommandError:
        return False
    return True


def create_and_switch(repo: Repo, name: str) -> None:
    """브랜치로 전환한다. 없으면 만들고 전환한다.

    같은 이름이 있으면 그 브랜치로 간다. 같은 이슈 작업을 이어서 하는 경우다.
    """
    if branch_exists(repo, name):
        repo.git.switch(name)
        return

    repo.git.switch("-c", name)
