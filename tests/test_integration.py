"""CLI 전체 파이프라인 통합 테스트.

계획서 12주차의 "실제 저장소에 CLI 설치해 전체 파이프라인(분석-생성-매핑) 동작
확인"에 해당한다. 노드 단위 테스트는 각 노드가 받은 입력을 어떻게 다루는지만
보므로, 명령들이 실제 저장소에서 맞물려 돌아가는지는 드러나지 않는다.

임시 git 저장소를 만들어 실제 `git` 을 쓰고, 벡터 스토어도 실제 로컬
인스턴스를 쓴다. LLM과 임베딩만 가짜로 바꾼다 — 그 둘만 돈이 들고 결과가
매번 달라진다.

검색 노드는 모든 예외를 삼키고 빈 결과로 넘어간다(인덱싱 전에도 동작해야
하므로). 그래서 검색 경로가 조용히 망가져도 단위 테스트로는 드러나지 않고,
"인덱싱한 커밋이 예시로 들어왔는지"를 여기서 확인해야 한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeModel, exploding
from git import Repo
from qdrant_client import QdrantClient
from typer.testing import CliRunner

from commit_agent.agent.nodes import (
    generate_message,
    map_issue,
    propose_issue,
    retrieve_context,
)
from commit_agent.agent.schemas import (
    BranchNameSuggestion,
    CommitMessageDraft,
    CommitType,
    IssueMatch,
    IssueProposal,
)
from commit_agent.cli import branch, issue_draft
from commit_agent.cli.main import app
from commit_agent.core import get_settings
from commit_agent.core.project_config import CONFIG_FILENAME
from commit_agent.git_integration.schemas import IssueInfo
from commit_agent.rag.services import issue_indexer

HOOK_PATH = Path(".git") / "hooks" / "prepare-commit-msg"

# `cli.commands` 가 같은 이름의 함수(`index`)를 내보내 모듈을 가려 버린다.
# 노드처럼 자기 이름공간에 끌어다 쓴 이름을 바꿔야 하므로 모듈 자체가 필요하다.
INDEX_MODULE = sys.modules["commit_agent.cli.commands.index"]

# 저장소에 심어 둘 과거 커밋. 규약을 지킨 메시지여야 검색 예시로 쓸 수 있다.
HISTORY = [
    ("src/app.py", "def run():\n    return 1\n", "feat(app): 실행 진입점 추가"),
    ("src/app.py", "def run():\n    return 2\n", "fix(app): 반환값 보정"),
    ("README.md", "# app\n", "docs: 사용법 추가"),
]

STAGED = "def run(retries: int = 3):\n    for _ in range(retries):\n        return 2\n"

SLUG = "owner/name"

# GitHub 경계에서 돌려줄 열린 이슈. 인덱싱·검색은 실제로 돈다.
ISSUES = [
    IssueInfo(
        number=12,
        title="실행 실패 시 재시도가 없다",
        body="run() 이 한 번 실패하면 그대로 끝난다. 몇 번 더 시도해야 한다.",
        state="open",
        url=f"https://github.com/{SLUG}/issues/12",
        updated_at=None,
    ),
    IssueInfo(
        number=30,
        title="사용법 문서가 부족하다",
        body="README에 설치 방법만 있고 실행 예시가 없다.",
        state="open",
        url=f"https://github.com/{SLUG}/issues/30",
        updated_at=None,
    ),
]


class FakeEmbeddings:
    """실제 모델을 부르지 않는 임베딩.

    차원이 일정해야 벡터 스토어가 받아 준다. 글자 수와 줄 수를 축에 넣어
    비슷한 문서끼리 가깝게 나오도록 둔다.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [len(text) % 97 / 97, text.count("\n") % 13 / 13, 0.5]


@pytest.fixture
def repo_dir(tmp_path, monkeypatch):
    """커밋이 몇 개 든 임시 저장소. 스테이징된 변경도 하나 남긴다."""
    target = tmp_path / "project"
    target.mkdir()

    repo = Repo.init(target, initial_branch="main")
    with repo.config_writer() as config:
        config.set_value("user", "name", "Tester")
        config.set_value("user", "email", "tester@example.com")

    for name, content, message in HISTORY:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        repo.index.add([name])
        repo.index.commit(message)

    # 생성 대상이 될 스테이징된 변경
    (target / "src" / "app.py").write_text(STAGED, encoding="utf-8")
    repo.index.add(["src/app.py"])

    monkeypatch.chdir(target)
    return target


@pytest.fixture
def fakes(tmp_path, monkeypatch, draft):
    """LLM·임베딩만 가짜로 바꾸고 벡터 스토어는 실제 로컬 인스턴스를 쓴다.

    `no_network` 가 막아 둔 `QdrantClient` 를 여기서만 되돌린다. 로컬 모드는
    파이썬 프로세스 안에서 돌고 네트워크를 타지 않는다.
    """
    model = FakeModel(draft)
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: model)

    embeddings = FakeEmbeddings()
    monkeypatch.setattr(retrieve_context, "get_embedding_model", lambda: embeddings)
    monkeypatch.setattr(INDEX_MODULE, "get_embedding_model", lambda _s=None: embeddings)

    # 이슈 매핑·초안 제안은 원격이 없으면 건너뛴다. 임시 저장소에는 원격이
    # 없으므로 가짜를 꽂지 않고, 불리면 `no_network` 가드가 테스트를 세운다
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)

    monkeypatch.setattr("commit_agent.core.vector_store.QdrantClient", QdrantClient)
    monkeypatch.setenv("COMMIT_AGENT_VECTOR_STORE_PATH", str(tmp_path / "store"))
    get_settings.cache_clear()

    yield model

    get_settings.cache_clear()


@pytest.fixture
def remote(repo_dir):
    """GitHub 원격을 붙인다.

    `get_remote_slug` 가 slug를 읽어야 매핑·초안 제안이 돌아간다. 원격이
    없으면 둘 다 건너뛴다.
    """
    Repo(repo_dir).create_remote("origin", f"https://github.com/{SLUG}.git")
    return SLUG


@pytest.fixture
def github(monkeypatch, fakes):
    """GitHub 경계만 가짜로 바꾼다.

    이슈 인덱싱과 유사도 검색은 실제로 돈다 — 그 둘이 매핑의 본체이고,
    조용히 망가져도 `map_issue_node` 가 예외를 삼켜 드러나지 않는다.
    """
    monkeypatch.setattr(map_issue, "open_github", lambda _token: object())
    monkeypatch.setattr(map_issue, "get_repository", lambda *_: object())
    monkeypatch.setattr(
        map_issue, "get_embedding_model", lambda _s=None: FakeEmbeddings()
    )
    monkeypatch.setattr(issue_indexer, "list_issues", lambda *_a, **_k: list(ISSUES))
    monkeypatch.setattr(
        map_issue,
        "get_issue",
        lambda _repo, number: next(i for i in ISSUES if i.number == number),
    )

    judge = FakeModel(IssueMatch(issue_number=12, reason="재시도를 추가한 변경"))
    monkeypatch.setattr(map_issue, "get_chat_model", lambda: judge)
    return judge


class FakeStdin:
    """터미널에서 실행한 것처럼 보이게 하는 stdin 대역.

    브랜치 제안과 이슈 등록은 `sys.stdin.isatty()` 가 False면 아예 건너뛴다.
    훅이 IDE나 CI에서도 돌기 때문인데, 그래서 CliRunner로는 밟히지 않는다.
    """

    @staticmethod
    def isatty() -> bool:
        return True


@pytest.fixture
def interactive(monkeypatch):
    """물어볼 수 있는 환경으로 바꾼다. 입력은 CliRunner가 넣는다."""
    for module in (branch, issue_draft):
        monkeypatch.setattr(module, "sys", type("S", (), {"stdin": FakeStdin})())


@pytest.fixture
def branch_namer(monkeypatch):
    """브랜치 이름을 지어 주는 가짜 LLM."""
    model = FakeModel(BranchNameSuggestion(name="feat/#12/add-retry"))
    monkeypatch.setattr(branch, "get_chat_model", lambda: model)
    return model


@pytest.fixture
def cli():
    return CliRunner()


def write_config(path: Path, **overrides: Any) -> None:
    """저장소 설정을 쓴다.

    이슈 매핑·초안 제안·브랜치 제안은 끈다. 셋 다 GitHub을 부르므로 여기서
    확인할 범위가 아니다.
    """
    values: dict[str, Any] = {
        "language": "ko",
        "issue_mapping": False,
        "propose_issue": False,
        "branch_suggest": False,
        **overrides,
    }
    (path / CONFIG_FILENAME).write_text(
        "\n".join(f"{k} = {_toml(v)}" for k, v in values.items()) + "\n",
        encoding="utf-8",
    )


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(f'"{v}"' for v in value) + "]"
    return f'"{value}"'


HEADER = re.compile(r"^[a-z]+(\([^)]+\))?!?: ")


def emitted(result) -> str:
    """stdout에서 커밋 메시지만 가려낸다.

    CliRunner는 넣어 준 입력을 stdout에 되울린다. 실제 터미널에서는 프로그램이
    사용자의 입력을 stdout에 쓰지 않으므로 테스트 환경만의 잡음이다.
    규약 형식으로 시작하는 줄부터를 메시지로 본다.
    """
    lines = result.stdout.splitlines()
    for i, line in enumerate(lines):
        if HEADER.match(line):
            return "\n".join(lines[i:]).strip()
    return ""


def run_ok(cli: CliRunner, *args: str):
    """CLI를 실행한다. 실패하면 출력을 그대로 보여 준다."""
    result = cli.invoke(app, list(args))
    assert result.exit_code == 0, f"{args} 실패 (exit {result.exit_code})\n{result.output}"
    return result


def test_init은_설정_파일을_만든다(repo_dir, cli, fakes):
    run_ok(cli, "init", "--yes")

    written = (repo_dir / CONFIG_FILENAME).read_text(encoding="utf-8")
    assert "language" in written
    assert "max_header_length" in written


def test_install이_훅을_깔고_uninstall이_지운다(repo_dir, cli, fakes):
    write_config(repo_dir)

    run_ok(cli, "install")
    hook = repo_dir / HOOK_PATH
    assert hook.exists()
    assert "commit-agent" in hook.read_text(encoding="utf-8")

    run_ok(cli, "uninstall")
    assert not hook.exists()


def test_index가_과거_커밋을_인덱싱한다(repo_dir, cli, fakes):
    write_config(repo_dir)

    output = run_ok(cli, "index").output

    assert f"새로 인덱싱: {len(HISTORY)}" in output


def test_index를_다시_돌리면_건너뛴다(repo_dir, cli, fakes):
    write_config(repo_dir)
    run_ok(cli, "index")

    output = run_ok(cli, "index").output

    assert "새로 인덱싱: 0" in output
    assert f"건너뜀: {len(HISTORY)}" in output


def test_generate가_규약_형식_메시지를_표준출력으로_낸다(repo_dir, cli, fakes):
    write_config(repo_dir)

    result = run_ok(cli, "generate")

    # 훅이 `generate > "$1"` 로 받아 쓰므로 stdout에는 메시지만 있어야 한다
    assert result.stdout.strip() == "feat(core): 추론 모델의 생각 분량을 설정으로 노출"


def test_인덱싱한_커밋이_예시로_프롬프트에_들어간다(repo_dir, cli, fakes):
    """검색 노드가 예외를 삼키므로 경로가 망가져도 생성은 성공한다.

    예시가 실제로 들어왔는지까지 봐야 검색이 돌아가는지 알 수 있다.
    """
    write_config(repo_dir)
    run_ok(cli, "index")

    run_ok(cli, "generate")

    user_message = fakes.calls[0][1]["content"]
    assert "과거 커밋 예시" in user_message
    assert "feat(app): 실행 진입점 추가" in user_message


def test_인덱스가_없어도_생성된다(repo_dir, cli, fakes):
    """처음 쓰는 저장소에서 index 없이 바로 커밋할 수 있어야 한다."""
    write_config(repo_dir)

    result = run_ok(cli, "generate")

    assert result.stdout.strip().startswith("feat(core): ")
    assert "과거 커밋 예시" not in fakes.calls[0][1]["content"]


def test_스테이징된_변경이_없으면_메시지를_내지_않는다(repo_dir, cli, fakes):
    write_config(repo_dir)
    Repo(repo_dir).index.reset()

    result = cli.invoke(app, ["generate"])

    assert result.exit_code != 0
    assert not result.stdout.strip()


def test_설정이_허용하지_않는_타입이면_메시지를_내지_않는다(repo_dir, cli, fakes):
    """빈 메시지를 내보내는 것보다 실패하는 쪽이 낫다."""
    write_config(repo_dir, types=["fix", "docs"])

    result = cli.invoke(app, ["generate"])

    assert result.exit_code != 0
    assert not result.stdout.strip()


def test_설정의_첫_줄_상한을_지킨다(repo_dir, cli, fakes, monkeypatch):
    long = CommitMessageDraft(
        type=CommitType.FEAT,
        scope="core",
        subject="추론 모델이 생각에 쓰는 분량을 설정 파일로 노출하고 기본값을 정한다",
    )
    monkeypatch.setattr(generate_message, "get_chat_model", lambda: FakeModel(long))
    write_config(repo_dir, max_header_length=40)

    result = run_ok(cli, "generate")

    assert len(result.stdout.strip().splitlines()[0]) <= 40


def test_설정_파일이_없어도_기본값으로_동작한다(repo_dir, cli, fakes):
    """init 을 거치지 않고 바로 generate 한 경우.

    설정 파일은 관례를 좁히는 수단이고 없으면 기본값을 쓴다. 처음 써 보는
    사람이 설치만 하고 커밋해도 메시지가 나와야 한다.
    """
    result = run_ok(cli, "generate")

    assert result.stdout.strip().startswith("feat(core): ")


def test_관련_이슈를_찾아_참조를_붙인다(repo_dir, remote, cli, github):
    """계획서의 "분석-생성-매핑" 중 매핑 경로.

    이슈를 인덱싱하고 생성된 메시지로 검색한 뒤 판단까지 거친다.
    `propose_issue` 에는 불리면 실패하는 가짜를 꽂아 두었으므로, 이 테스트가
    통과하면 매핑된 쪽으로 분기했다는 뜻이기도 하다.
    """
    write_config(repo_dir, issue_mapping=True)

    result = run_ok(cli, "generate")

    message = result.stdout.strip()
    assert message.startswith("feat(core): ")
    assert message.endswith("related to: #12")


def test_이슈_검색_쿼리로_생성된_메시지를_쓴다(repo_dir, remote, cli, github):
    """변경 요약이 아니라 커밋 메시지로 검색해야 한다.

    이슈 본문은 자연어인데 코드 변경 요약으로 찾으면 성격이 달라 변별력이
    떨어진다. 5주차에 측정으로 정한 설계다.
    """
    write_config(repo_dir, issue_mapping=True)

    run_ok(cli, "generate")

    judged = github.calls[0][1]["content"]
    assert "추론 모델의 생각 분량을 설정으로 노출" in judged


def test_관련_이슈가_없으면_초안을_제안한다(repo_dir, remote, cli, github, monkeypatch):
    """매핑 실패 쪽 분기. 참조는 붙지 않고 초안만 보여 준다."""
    monkeypatch.setattr(
        map_issue,
        "get_chat_model",
        lambda: FakeModel(IssueMatch(issue_number=None, reason="관련 이슈 없음")),
    )
    monkeypatch.setattr(
        propose_issue,
        "get_chat_model",
        lambda: FakeModel(
            IssueProposal(
                worth_tracking=True,
                title="실행 재시도 횟수를 설정으로 노출",
                body="- 재시도 횟수를 고정값으로 두고 있음",
            )
        ),
    )
    write_config(repo_dir, issue_mapping=True, propose_issue=True)

    result = run_ok(cli, "generate")

    assert "related to:" not in result.stdout
    # 초안은 안내이므로 stderr로 나가야 한다. 훅이 stdout을 그대로 받아 쓴다
    assert "실행 재시도 횟수를 설정으로 노출" in result.stderr
    assert "실행 재시도 횟수를 설정으로 노출" not in result.stdout


def test_이슈_매핑을_끄면_GitHub을_부르지_않는다(repo_dir, remote, cli, fakes, monkeypatch):
    monkeypatch.setattr(map_issue, "open_github", exploding)
    monkeypatch.setattr(propose_issue, "get_chat_model", exploding)
    write_config(repo_dir)

    result = run_ok(cli, "generate")

    assert "related to:" not in result.stdout


def with_branch_example(repo_dir: Path, name: str = "feat/#1/initial-setup") -> None:
    """브랜치 이름 예시를 남긴다. 예시가 없으면 제안 자체를 건너뛴다."""
    Repo(repo_dir).git.branch(name)


def test_브랜치_이름을_제안하고_Enter_두_번으로_전환한다(
    repo_dir, cli, fakes, interactive, branch_namer
):
    """제안한 이름을 고칠 기회를 주고 나서 확인을 받는다."""
    with_branch_example(repo_dir)
    write_config(repo_dir, branch_suggest=True)

    result = cli.invoke(app, ["generate"], input="\n\n")

    assert result.exit_code == 0
    assert Repo(repo_dir).active_branch.name == "feat/#12/add-retry"


def test_제안한_이름을_고쳐_쓸_수_있다(repo_dir, cli, fakes, interactive, branch_namer):
    with_branch_example(repo_dir)
    write_config(repo_dir, branch_suggest=True)

    result = cli.invoke(app, ["generate"], input="feat/#99/my-own-name\n\n")

    assert result.exit_code == 0
    assert Repo(repo_dir).active_branch.name == "feat/#99/my-own-name"


def test_확인에서_거절하면_브랜치를_만들지_않는다(
    repo_dir, cli, fakes, interactive, branch_namer
):
    with_branch_example(repo_dir)
    write_config(repo_dir, branch_suggest=True)

    result = cli.invoke(app, ["generate"], input="\nn\n")

    assert result.exit_code == 0
    assert Repo(repo_dir).active_branch.name == "main"
    # 거절해도 커밋 메시지는 나와야 한다
    assert emitted(result).startswith("feat(core): ")


def test_쓸_수_없는_이름을_넣으면_만들지_않는다(
    repo_dir, cli, fakes, interactive, branch_namer
):
    with_branch_example(repo_dir)
    write_config(repo_dir, branch_suggest=True)

    result = cli.invoke(app, ["generate"], input="has space\n")

    assert result.exit_code == 0
    assert Repo(repo_dir).active_branch.name == "main"


def test_작업_브랜치에_있으면_제안하지_않는다(repo_dir, cli, fakes, interactive, monkeypatch):
    """작업 중에 또 분기하면 곤란하다."""
    monkeypatch.setattr(branch, "get_chat_model", exploding)
    with_branch_example(repo_dir)
    Repo(repo_dir).git.switch("-c", "feat/#5/working")
    write_config(repo_dir, branch_suggest=True)

    result = run_ok(cli, "generate")

    assert Repo(repo_dir).active_branch.name == "feat/#5/working"
    assert result.stdout.strip().startswith("feat(core): ")


def test_이름_예시가_없으면_제안하지_않는다(repo_dir, cli, fakes, interactive, branch_namer):
    """규칙을 배울 예시가 없으면 이름을 지어내지 않는다."""
    write_config(repo_dir, branch_suggest=True)

    run_ok(cli, "generate")

    assert Repo(repo_dir).active_branch.name == "main"
    assert not branch_namer.calls


def test_물어볼_수_없는_환경이면_제안하지_않는다(repo_dir, cli, fakes, monkeypatch):
    """훅은 IDE의 git 패널이나 CI에서도 실행되므로 입력이 없을 수 있다."""
    monkeypatch.setattr(branch, "get_chat_model", exploding)
    with_branch_example(repo_dir)
    write_config(repo_dir, branch_suggest=True)

    run_ok(cli, "generate")

    assert Repo(repo_dir).active_branch.name == "main"


@pytest.fixture
def issue_creator(monkeypatch):
    """이슈 등록 경계만 가짜로 바꾼다."""
    created: list[Any] = []

    def create_issue(_repo, draft):
        created.append(draft)
        return IssueInfo(
            number=77,
            title=draft.title,
            state="open",
            url=f"https://github.com/{SLUG}/issues/77",
        )

    monkeypatch.setattr(issue_draft, "open_github", lambda _token: object())
    monkeypatch.setattr(issue_draft, "get_repository", lambda *_: object())
    monkeypatch.setattr(issue_draft, "create_issue", create_issue)
    return created


def _no_match(monkeypatch):
    """매핑되는 이슈가 없는 상태로 둔다."""
    monkeypatch.setattr(
        map_issue,
        "get_chat_model",
        lambda: FakeModel(IssueMatch(issue_number=None, reason="관련 이슈 없음")),
    )
    monkeypatch.setattr(
        propose_issue,
        "get_chat_model",
        lambda: FakeModel(
            IssueProposal(worth_tracking=True, title="실행 재시도 횟수를 설정으로 노출")
        ),
    )


def test_이슈를_만들겠다고_하면_등록하고_참조를_붙인다(
    repo_dir, remote, cli, github, interactive, issue_creator, monkeypatch
):
    _no_match(monkeypatch)
    write_config(repo_dir, issue_mapping=True, propose_issue=True)

    result = cli.invoke(app, ["generate"], input="y\n")

    assert result.exit_code == 0
    assert [d.title for d in issue_creator] == ["실행 재시도 횟수를 설정으로 노출"]
    assert emitted(result).endswith("related to: #77")


def test_이슈를_만들지_않겠다고_하면_참조가_붙지_않는다(
    repo_dir, remote, cli, github, interactive, issue_creator, monkeypatch
):
    _no_match(monkeypatch)
    write_config(repo_dir, issue_mapping=True, propose_issue=True)

    result = cli.invoke(app, ["generate"], input="n\n")

    assert result.exit_code == 0
    assert not issue_creator
    assert "related to:" not in result.stdout


def test_이슈_등록이_실패해도_커밋_메시지는_나온다(
    repo_dir, remote, cli, github, interactive, issue_creator, monkeypatch
):
    """훅에서 예외가 올라가면 메시지 없이 커밋된다."""
    _no_match(monkeypatch)

    def explode(_repo, _draft):
        raise RuntimeError("등록 실패")

    monkeypatch.setattr(issue_draft, "create_issue", explode)
    write_config(repo_dir, issue_mapping=True, propose_issue=True)

    result = cli.invoke(app, ["generate"], input="y\n")

    assert result.exit_code == 0
    assert emitted(result).startswith("feat(core): ")
    assert "related to:" not in emitted(result)


def test_init부터_generate까지_한_번에_돈다(repo_dir, cli, fakes):
    """설치부터 생성까지 사용자가 실제로 밟는 순서."""
    run_ok(cli, "init", "--yes")
    run_ok(cli, "install")
    run_ok(cli, "index")

    result = run_ok(cli, "generate")

    assert (repo_dir / HOOK_PATH).exists()
    assert result.stdout.strip().startswith("feat")
    assert "과거 커밋 예시" in fakes.calls[0][1]["content"]
