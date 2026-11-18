"""평가 표본을 준비하는 코드.

저장소 히스토리에서 타입·scope 목록을 뽑는 함수는 평가 조건을 정한다.
목록에서 빠진 타입은 생성 스키마에서 제외되어 그 타입의 커밋을 전부 틀리므로,
수집 규칙이 어긋나면 측정값이 통째로 흔들린다.
"""

from __future__ import annotations

from dataclasses import dataclass

from evaluation.corpus import scopes_in_history, types_in_history


@dataclass
class FakeCommit:
    message: str


class FakeRepo:
    """`iter_commits` 만 흉내 내는 가짜 저장소.

    두 함수는 커밋 메시지 첫 줄만 보므로 실제 저장소를 만들 필요가 없다.
    """

    def __init__(self, *messages: str) -> None:
        self.commits = [FakeCommit(m) for m in messages]
        self.limits: list[int] = []

    def iter_commits(self, max_count: int, no_merges: bool = False):
        self.limits.append(max_count)
        return iter(self.commits[:max_count])


def test_타입을_빈도순으로_모은다():
    repo = FakeRepo(
        "fix: a", "fix: b", "fix: c", "feat: d", "feat: e", "chore: f"
    )

    assert types_in_history(repo, limit=100) == ["fix", "feat", "chore"]


def test_규약을_벗어난_커밋은_세지_않는다():
    repo = FakeRepo("fix: a", "WIP", "Merge branch 'main'", "update stuff")

    assert types_in_history(repo, limit=100) == ["fix"]


def test_scope가_붙은_타입도_타입으로_센다():
    repo = FakeRepo("fix(core): a", "fix: b", "feat(cli)!: c")

    assert types_in_history(repo, limit=100) == ["fix", "feat"]


def test_수집_범위를_그대로_넘긴다():
    """좁게 잡으면 드물게 쓰는 타입이 빠져 그 타입의 커밋을 전부 틀린다."""
    repo = FakeRepo("fix: a")

    types_in_history(repo, limit=3000)

    assert repo.limits == [3000]


def test_범위_밖의_커밋은_보지_않는다():
    repo = FakeRepo("fix: a", "feat: b", "perf: c")

    assert types_in_history(repo, limit=2) == ["fix", "feat"]


def test_scope를_빈도순으로_모은다():
    repo = FakeRepo("fix(core): a", "fix(core): b", "feat(cli): c", "feat(cli): d")

    assert scopes_in_history(repo, limit=100) == ["core", "cli"]


def test_한_번만_쓰인_scope는_제외한다():
    """일회성 값일 수 있어 기본값은 2회 이상만 센다."""
    repo = FakeRepo("fix(core): a", "fix(core): b", "feat(once): c")

    assert scopes_in_history(repo, limit=100) == ["core"]


def test_최소_횟수를_1로_주면_전부_포함한다():
    repo = FakeRepo("fix(core): a", "feat(once): b")

    assert sorted(scopes_in_history(repo, limit=100, min_count=1)) == ["core", "once"]


def test_scope가_없는_커밋은_세지_않는다():
    repo = FakeRepo("fix: a", "fix: b", "chore(ci): c", "chore(ci): d")

    assert scopes_in_history(repo, limit=100) == ["ci"]
