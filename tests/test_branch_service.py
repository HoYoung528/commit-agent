"""브랜치 조회·생성 서비스.

저장소 상태를 바꾸는 코드라 가짜로 대신할 수 없다. 임시 저장소에 실제 git을
돌려 확인한다.

브랜치 이름 예시를 모으는 쪽이 특히 중요하다. 예시가 비면 이름을 지어내지
않고 제안 자체를 건너뛰므로, 수집이 조용히 망가지면 기능이 사라진 것처럼
된다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from commit_agent.git_integration.services.branch import (
    branch_exists,
    collect_branch_names,
    create_and_switch,
    current_branch,
    is_valid_name,
    on_default_branch,
)


@pytest.fixture
def repo(tmp_path):
    """커밋 하나가 든 임시 저장소. 기본 브랜치는 main."""
    target = tmp_path / "repo"
    target.mkdir()

    repo = Repo.init(target, initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("user", "name", "Tester")
        config.set_value("user", "email", "tester@example.com")

    (target / "a.txt").write_text("a\n", encoding="utf-8")
    repo.index.add(["a.txt"])
    repo.index.commit("feat: 첫 커밋")
    return repo


def merge_pr(repo: Repo, number: int, branch: str, filename: str) -> None:
    """GitHub이 남기는 형식의 머지 커밋을 만든다."""
    repo.git.switch("-c", branch)
    (Path(repo.working_tree_dir or ".") / filename).write_text("x\n", encoding="utf-8")
    repo.index.add([filename])
    repo.index.commit(f"feat: {branch} 작업")

    repo.git.switch("main")
    repo.git.merge(
        "--no-ff", branch, "-m", f"Merge pull request #{number} from Owner/{branch}"
    )
    repo.git.branch("-D", branch)


def test_현재_브랜치를_읽는다(repo):
    assert current_branch(repo) == "main"
    assert on_default_branch(repo)


def test_detached_HEAD면_브랜치가_없다(repo):
    repo.git.checkout("--detach", "HEAD")

    assert current_branch(repo) is None
    assert not on_default_branch(repo)


def test_작업_브랜치에서는_기본_브랜치가_아니다(repo):
    repo.git.switch("-c", "feat/#1/something")

    assert not on_default_branch(repo)


def test_머지_커밋_메시지에서_브랜치_이름을_뽑는다(repo):
    """새로 클론한 저장소에는 작업 브랜치가 없어 머지 커밋이 유일한 기록이다."""
    merge_pr(repo, 59, "feat/#30/issue-create", "b.txt")

    assert collect_branch_names(repo) == ["feat/#30/issue-create"]


def test_로컬_브랜치도_예시로_모으되_기본_브랜치는_뺀다(repo):
    repo.git.branch("feat/#2/add-retry")

    names = collect_branch_names(repo)

    assert "feat/#2/add-retry" in names
    assert "main" not in names


def test_머지_커밋과_로컬_브랜치를_합치고_중복을_없앤다(repo):
    merge_pr(repo, 59, "feat/#30/issue-create", "b.txt")
    repo.git.branch("feat/#30/issue-create")

    assert collect_branch_names(repo) == ["feat/#30/issue-create"]


def test_예시가_없으면_빈_목록(repo):
    """main 하나뿐인 저장소. 제안을 건너뛰어야 한다."""
    assert collect_branch_names(repo) == []


def test_모으는_개수에_상한이_있다(repo):
    for i in range(5):
        repo.git.branch(f"feat/#{i}/work")

    assert len(collect_branch_names(repo, limit=3)) == 3


def test_git에게_이름이_쓸_수_있는지_묻는다(repo):
    assert is_valid_name(repo, "feat/#12/add-retry")
    assert not is_valid_name(repo, "")
    assert not is_valid_name(repo, "feat//double")
    assert not is_valid_name(repo, "has space")
    assert not is_valid_name(repo, "-leading-dash")


def test_브랜치를_만들고_전환한다(repo):
    create_and_switch(repo, "feat/#12/add-retry")

    assert current_branch(repo) == "feat/#12/add-retry"
    assert branch_exists(repo, "feat/#12/add-retry")


def test_같은_이름이_있으면_그_브랜치로_간다(repo):
    """같은 이슈 작업을 이어서 하는 경우다."""
    repo.git.branch("feat/#12/add-retry")

    create_and_switch(repo, "feat/#12/add-retry")

    assert current_branch(repo) == "feat/#12/add-retry"


def test_없는_브랜치는_없다고_답한다(repo):
    assert not branch_exists(repo, "feat/#99/nope")
