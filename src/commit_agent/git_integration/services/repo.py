"""GitPython으로 로컬 저장소를 조회한다.

staged diff와 커밋 히스토리를 읽기만 하며 저장소 상태를 바꾸지 않는다.
읽어온 diff 텍스트의 해석은 `change_analysis`가 담당한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from commit_agent.git_integration.exceptions import NotAGitRepositoryError
from commit_agent.git_integration.schemas import CommitInfo

if TYPE_CHECKING:
    from git.objects import Commit

# 최초 커밋의 diff를 뽑을 때 비교 대상으로 쓰는 git의 빈 트리 해시
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# 색상 코드나 외부 diff 도구가 섞이면 파싱이 깨지므로 항상 끈다
_DIFF_OPTIONS = ("--no-color", "--no-ext-diff", "--find-renames")


def open_repo(path: str | Path = ".") -> Repo:
    """주어진 경로가 속한 git 저장소를 연다.

    하위 디렉터리에서 실행해도 상위의 저장소 루트를 찾아 올라간다.
    """
    try:
        return Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise NotAGitRepositoryError(str(path)) from exc


def get_staged_diff(repo: Repo) -> str:
    """스테이징된 변경의 diff 텍스트(`git diff --cached`)를 반환한다.

    스테이징된 변경이 없으면 빈 문자열이다.
    """
    return repo.git.diff("--cached", *_DIFF_OPTIONS)


def has_staged_changes(repo: Repo) -> bool:
    """스테이징된 변경이 있는지 여부."""
    return bool(get_staged_diff(repo).strip())


def get_remote_slug(repo: Repo, remote: str = "origin") -> str | None:
    """원격 URL에서 GitHub 저장소 이름(`owner/name`)을 뽑는다.

    GitHub이 아니거나 원격이 없으면 None이다.
    https/ssh 두 형식을 모두 처리한다.
    """
    try:
        url = repo.remote(remote).url
    except ValueError:
        return None

    if "github.com" not in url:
        return None

    # git@github.com:owner/name.git  또는  https://github.com/owner/name.git
    path = url.split("github.com", 1)[1].lstrip(":/")
    path = path.removesuffix(".git").strip("/")

    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else None


def get_commit_history(
    repo: Repo,
    *,
    limit: int = 200,
    skip_merges: bool = True,
    include_stats: bool = False,
) -> list[CommitInfo]:
    """최신 커밋부터 순서대로 히스토리를 읽어 반환한다.

    `include_stats`를 켜면 커밋마다 변경 파일과 라인 수를 함께 채우는데,
    커밋당 diff를 한 번씩 계산하므로 저장소가 크면 느려진다.
    """
    if not repo.head.is_valid():  # 최초 커밋 전에는 HEAD가 없다
        return []

    return [
        _to_commit_info(commit, include_stats=include_stats)
        for commit in repo.iter_commits(max_count=limit, no_merges=skip_merges)
    ]


def get_commit_diff(repo: Repo, sha: str) -> str:
    """커밋 하나가 만들어낸 diff 텍스트를 반환한다.

    부모가 없는 최초 커밋은 빈 트리와 비교한다.
    """
    commit = repo.commit(sha)
    base = commit.parents[0].hexsha if commit.parents else _EMPTY_TREE
    return repo.git.diff(base, commit.hexsha, *_DIFF_OPTIONS)


def _to_commit_info(commit: Commit, *, include_stats: bool) -> CommitInfo:
    """GitPython의 Commit 객체를 직렬화 가능한 스키마로 옮긴다."""
    files: list[str] = []
    insertions = 0
    deletions = 0

    if include_stats:
        stats = commit.stats
        files = sorted(stats.files)
        insertions = stats.total["insertions"]
        deletions = stats.total["deletions"]

    message = commit.message
    if isinstance(message, bytes):
        message = message.decode("utf-8", "replace")

    return CommitInfo(
        sha=commit.hexsha,
        message=message,
        author_name=commit.author.name or "",
        author_email=commit.author.email or "",
        committed_at=commit.committed_datetime,
        parents=[p.hexsha for p in commit.parents],
        files=files,
        insertions=insertions,
        deletions=deletions,
    )
