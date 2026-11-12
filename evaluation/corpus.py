"""평가용 커밋 표본을 준비한다.

계획서의 검증 방법을 따른다 — 특정 시점 이전 커밋만 인덱싱하고, 그 이후
커밋은 diff만 입력해 생성한 뒤 실제 메시지와 비교한다. 정답 이후의 커밋이
인덱스에 남으면 미래 정보가 새므로 시점으로 자른다.

평가 대상은 사람이 쓴 Conventional Commits 커밋만이다. 봇 커밋은 템플릿이라
저장소의 관례가 아니다. 인덱싱 쪽은 걸러내지 않는다 — 실사용에서도 히스토리를
그대로 넣기 때문이다.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from git import Repo

from commit_agent.git_integration import open_repo

HEADER = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[^)]+)\))?!?: (?P<subject>.+)"
)

BOT = re.compile(r"dependabot|renovate|github-actions|\[bot\]|semantic-release", re.I)


@dataclass(frozen=True)
class CommitRef:
    """평가 대상 커밋 하나."""

    sha: str
    type: str
    scope: str | None
    subject: str

    @property
    def header(self) -> str:
        scope = f"({self.scope})" if self.scope else ""
        return f"{self.type}{scope}: {self.subject}"


def parse_header(message: str) -> tuple[str, str | None, str] | None:
    """커밋 메시지 첫 줄에서 타입·scope·제목을 뽑는다. 규약 밖이면 None."""
    matched = HEADER.match(message.strip().splitlines()[0] if message.strip() else "")
    if not matched:
        return None
    return matched["type"], matched["scope"], matched["subject"]


def clone(slug: str, into: Path, *, depth: int) -> Repo:
    """저장소를 받아 둔다. 이미 있으면 그대로 쓴다.

    `split_at` 이 HEAD를 분할 지점으로 떼어 놓으므로, 다시 돌릴 때는 원래
    끝으로 되돌린다. 그러지 않으면 수집 구간이 조용히 줄어든다.
    """
    target = into / slug.replace("/", "__")
    if not target.exists():
        subprocess.run(
            ["git", "clone", "--quiet", f"--depth={depth}",
             f"https://github.com/{slug}.git", str(target)],
            check=True,
        )

    repo = open_repo(target)
    if repo.head.is_detached:
        repo.git.checkout("--quiet", repo.remotes.origin.refs[0].remote_head)

    return repo


def collect(repo: Repo, *, limit: int) -> list[CommitRef]:
    """사람이 쓴 규약 준수 커밋을 최신순으로 모은다."""
    refs: list[CommitRef] = []

    for commit in repo.iter_commits(max_count=limit, no_merges=True):
        author = f"{commit.author.name} {commit.author.email}"
        if BOT.search(author):
            continue

        parsed = parse_header(str(commit.message))
        if parsed is None:
            continue

        commit_type, scope, subject = parsed
        refs.append(CommitRef(commit.hexsha, commit_type, scope, subject))

    return refs


def split_at(repo: Repo, refs: list[CommitRef], *, eval_ratio: float) -> list[CommitRef]:
    """최신 쪽을 평가 대상으로 떼어내고, 나머지 시점으로 HEAD를 옮긴다.

    HEAD를 분할 지점으로 옮기면 이후 인덱싱이 그 이전 커밋만 훑는다.
    평가 대상 커밋의 diff는 HEAD보다 앞서 있어도 객체가 있으므로 읽을 수 있다.
    """
    cut = max(1, int(len(refs) * eval_ratio))
    evaluation, rest = refs[:cut], refs[cut:]
    if not rest:
        raise ValueError("인덱싱할 커밋이 남지 않습니다. limit을 늘리세요.")

    repo.git.checkout("--quiet", "--detach", rest[0].sha)
    return evaluation


def stratified_sample(
    refs: list[CommitRef], *, per_type: int, seed: int = 20261105
) -> list[CommitRef]:
    """타입별로 고르게 뽑는다.

    무작위로 뽑으면 fix에 몰려 "fix를 잘 맞추는지"만 재게 된다.
    """
    buckets: dict[str, list[CommitRef]] = defaultdict(list)
    for ref in refs:
        buckets[ref.type].append(ref)

    rng = random.Random(seed)
    picked: list[CommitRef] = []
    for commit_type in sorted(buckets):
        group = buckets[commit_type]
        picked.extend(rng.sample(group, min(per_type, len(group))))

    return picked


def load_or_pick(
    path: Path,
    slug: str,
    repo: Repo,
    *,
    limit: int,
    eval_ratio: float,
    per_type: int,
    resample: bool = False,
) -> tuple[list[CommitRef], str]:
    """표본을 파일에서 읽는다. 없으면 뽑아서 저장한다.

    매번 다시 뽑으면 저장소에 새 커밋이 쌓일 때마다 분할 지점과 표본이
    바뀌어, 두 실행의 결과를 비교할 수 없다. 한 번 정한 표본을 파일로
    못 박아야 프롬프트나 검색을 바꿨을 때 그 효과를 읽을 수 있다.
    """
    saved = _read_sample(path)

    if not resample and slug in saved:
        entry = saved[slug]
        picked = [CommitRef(**r) for r in entry["sample"]]
        return picked, entry["split_at"]

    refs = collect(repo, limit=limit)
    cut = max(1, int(len(refs) * eval_ratio))
    evaluation, rest = refs[:cut], refs[cut:]
    if not rest:
        raise ValueError("인덱싱할 커밋이 남지 않습니다. limit을 늘리세요.")

    picked = stratified_sample(evaluation, per_type=per_type)
    saved[slug] = {
        "split_at": rest[0].sha,
        "pool_size": len(evaluation),
        "sample": [vars(r) for r in picked],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    return picked, rest[0].sha


def _read_sample(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def types_in_history(repo: Repo, *, limit: int) -> list[str]:
    """저장소가 써온 타입을 빈도순으로 모은다.

    실사용에서는 `.commit-agent.toml` 의 `types` 에 저장소가 쓰는 타입을
    적어 두고, 그 목록으로 생성 스키마가 좁혀진다. 평가에서도 같은 조건을
    주려면 목록이 필요하다.

    인덱싱 구간이 아니라 수집한 히스토리 전체를 본다. 좁은 구간만 보면
    드물게 쓰는 타입이 빠지고, 빠진 타입은 생성에서 아예 고를 수 없어
    그 타입의 커밋을 전부 틀린다. 사용자도 설정을 쓸 때 특정 구간이 아니라
    저장소 전체를 보고 적는다.
    """
    counts: Counter[str] = Counter()
    for commit in repo.iter_commits(max_count=limit, no_merges=True):
        parsed = parse_header(str(commit.message))
        if parsed:
            counts[parsed[0]] += 1

    return [commit_type for commit_type, _ in counts.most_common()]


def scopes_in_history(repo: Repo, *, limit: int, min_count: int = 2) -> list[str]:
    """저장소가 써온 scope를 빈도순으로 모은다.

    타입과 마찬가지로 실사용에서는 `.commit-agent.toml` 의 `scopes` 에 적어 둔다.
    한 번만 쓰인 값은 일회성일 수 있어 제외한다.
    """
    counts: Counter[str] = Counter()
    for commit in repo.iter_commits(max_count=limit, no_merges=True):
        parsed = parse_header(str(commit.message))
        if parsed and parsed[1]:
            counts[parsed[1]] += 1

    return [scope for scope, n in counts.most_common() if n >= min_count]
