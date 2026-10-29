"""저장소 설정 파일 읽기와 검증."""

from __future__ import annotations

import importlib
import tomllib

import pytest

from commit_agent.agent.schemas import CommitType
from commit_agent.core.project_config import (
    COMMIT_TYPES,
    CONFIG_FILENAME,
    DEFAULT_ISSUE_TEMPLATES,
    DEFAULT_MAX_HEADER_LENGTH,
    DEFAULT_REFERENCE_FORMAT,
    ProjectConfig,
    ProjectConfigError,
    load_project_config,
)


@pytest.fixture
def repo(tmp_path):
    """설정 파일을 찾다가 멈출 저장소 루트."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def _write(repo, text: str):
    (repo / CONFIG_FILENAME).write_text(text, encoding="utf-8")


def _problems(repo) -> str:
    with pytest.raises(ProjectConfigError) as info:
        load_project_config(repo)
    return str(info.value)


def test_타입_목록이_스키마의_enum과_같다():
    """core는 순환 import 때문에 목록을 따로 둔다. 둘이 어긋나면 검증이 틀린다."""
    assert list(COMMIT_TYPES) == [t.value for t in CommitType]


def test_파일이_없으면_기본값을_쓴다(repo):
    config = load_project_config(repo)

    assert config == ProjectConfig()
    assert config.reference_format == DEFAULT_REFERENCE_FORMAT
    assert config.issue_mapping and config.propose_issue and config.branch_suggest


def test_모든_항목을_읽는다(repo):
    _write(
        repo,
        """
language = "en"
types = ["feat", "fix"]
scopes = ["core", "cli"]
max_header_length = 50
reference_format = "Closes {ref}"
issue_mapping = false
propose_issue = false
branch_suggest = false
""",
    )

    config = load_project_config(repo)

    assert config.language == "en"
    assert config.allowed_types() == ["feat", "fix"]
    assert config.allows_scope("core") and not config.allows_scope("docs")
    assert config.max_header_length == 50
    assert config.reference_format == "Closes {ref}"
    assert not (config.issue_mapping or config.propose_issue or config.branch_suggest)


@pytest.mark.parametrize("language", ["ko", "en"])
def test_init이_만든_파일을_그대로_읽을_수_있다(language):
    """검증이 엄격하므로 템플릿에 오타가 있으면 init 직후부터 도구가 멈춘다."""
    # 패키지가 같은 이름의 명령 함수를 내보내므로 모듈은 이렇게 가져온다
    init_module = importlib.import_module("commit_agent.cli.commands.init")
    text = init_module._TEMPLATE.format(
        language=language,
        types=",\n".join(f'    "{t}"' for t in ["feat", "fix"]),
        max_header_length=DEFAULT_MAX_HEADER_LENGTH,
        reference_format=DEFAULT_REFERENCE_FORMAT,
        issue_template=DEFAULT_ISSUE_TEMPLATES[language],
    )

    config = ProjectConfig.model_validate(tomllib.loads(text))

    assert config.allowed_types() == ["feat", "fix"]
    assert config.reference_format == DEFAULT_REFERENCE_FORMAT
    assert config.issue_body_template() == DEFAULT_ISSUE_TEMPLATES[language]


def test_이슈_템플릿이_비어_있으면_언어별_기본값을_쓴다():
    ko, en = DEFAULT_ISSUE_TEMPLATES["ko"], DEFAULT_ISSUE_TEMPLATES["en"]

    assert ProjectConfig().issue_body_template() == ko
    assert ProjectConfig(language="en").issue_body_template() == en
    assert ProjectConfig(issue_template="  \n").issue_body_template() == ko


def test_이슈_템플릿을_여러_줄로_읽는다(repo):
    _write(repo, "issue_template = '''\n## 문제\n\n## 해결\n'''\n")

    assert load_project_config(repo).issue_body_template() == "## 문제\n\n## 해결"


def test_오타_난_항목을_알려준다(repo):
    _write(repo, 'langauge = "en"\n')

    problems = _problems(repo)

    assert "langauge" in problems
    assert "알 수 없는 항목" in problems


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('language = "jp"\n', "ko, en 중 하나"),
        ('types = ["feature", "fix"]\n', "알 수 없는 타입입니다: feature"),
        ('reference_format = "related to"\n', "{ref}"),
        ('reference_format = "{ref} {other}"\n', "다른 중괄호"),
        ("max_header_length = 5\n", "max_header_length"),
        # 문자열을 참·거짓으로 바꿔 읽으면 "no"도 참이 된다
        ('issue_mapping = "no"\n', "issue_mapping"),
        ("max_header_length = 72.5\n", "max_header_length"),
    ],
)
def test_잘못된_값을_항목별로_알려준다(repo, text, expected):
    _write(repo, text)

    assert expected in _problems(repo)


def test_여러_항목이_틀리면_모두_알려준다(repo):
    _write(repo, 'language = "jp"\ntypes = ["feature"]\n')

    problems = _problems(repo)

    assert "language" in problems
    assert "types" in problems


def test_TOML_문법_오류도_traceback_대신_알려준다(repo):
    _write(repo, 'language = "ko\n')

    assert "TOML 문법 오류" in _problems(repo)
