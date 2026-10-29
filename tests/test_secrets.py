"""diff 안의 비밀값 처리."""

from __future__ import annotations

import pytest

from commit_agent.change_analysis.schemas import ChangeType, DiffAnalysis, FileChange, Hunk
from commit_agent.change_analysis.services.preprocessor import preprocess
from commit_agent.change_analysis.services.secrets import MASK, is_secret_file, mask_line

GITHUB_PAT = "ghp_" + "a1B2" * 9
AWS_KEY = "AKIA" + "ABCDEFGH12345678"


def _file(path: str, lines: list[str], old_path: str | None = None) -> FileChange:
    hunk = Hunk(old_start=1, old_lines=0, new_start=1, new_lines=len(lines), lines=lines)
    return FileChange(
        path=path, change_type=ChangeType.MODIFIED, old_path=old_path, hunks=[hunk]
    )


@pytest.mark.parametrize(
    "path",
    [".env", "app/.env.local", "certs/server.pem", "deploy/tls.key", "credentials.json", "id_rsa"],
)
def test_키_파일로_판단한다(path):
    assert is_secret_file(path)


@pytest.mark.parametrize(
    "path", [".env.example", "src/credentials_form.py", "docs/keys.md", "src/token.py"]
)
def test_키_파일이_아니다(path):
    assert not is_secret_file(path)


@pytest.mark.parametrize(
    "line",
    [
        f"+GITHUB_TOKEN={GITHUB_PAT}",
        f'+    "token": "{GITHUB_PAT}",',
        f"+aws_access_key_id = {AWS_KEY}",
        "+ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
        "+DB_PASSWORD=hunter2hunter2",
        '+SECRET_KEY = "x9f8e7d6c5b4a3"',
        "-api_key: 3f9a1c77be20d4e1",
        '+DB_PASSWORD = "P@ssw0rd!2024"',
        "+password: 'abc$123xyz'",
        '+JWT_SECRET = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc123"',
    ],
)
def test_흔한_키_형태를_가린다(line):
    masked, count = mask_line(line)

    assert count >= 1
    assert MASK in masked
    for secret in (
        GITHUB_PAT,
        AWS_KEY,
        "hunter2hunter2",
        "x9f8e7d6c5b4a3",
        "3f9a1c77be20d4e1",
        "P@ssw0rd",
        "abc$123",
        "eyJhbGci",
    ):
        assert secret not in masked


@pytest.mark.parametrize(
    "line",
    [
        "+    api_key = settings.api_key",
        "+    token = make_token(user)",
        '+API_KEY_ENV = "ANTHROPIC_API_KEY"',
        "+DEFAULT_MAX_TOKENS = 100_000",
        '+OPENAI_API_KEY="your-api-key-here"',
        '+    headers = {"Authorization": f"Bearer {token}"}',
    ],
)
def test_코드와_자리표시자는_건드리지_않는다(line):
    assert mask_line(line) == (line, 0)


def test_키_이름은_남기고_값만_가린다():
    masked, _ = mask_line("+DB_PASSWORD=hunter2hunter2  # 운영")

    assert masked == f"+DB_PASSWORD={MASK}  # 운영"


def test_키_파일은_본문을_빼고_목록에_남긴다():
    result = preprocess(DiffAnalysis(files=[_file(".env", [f"+GITHUB_TOKEN={GITHUB_PAT}"])]))

    assert result.files == []
    assert result.excluded == [".env"]
    assert result.secret_files == [".env"]
    assert result.is_redacted()


def test_키_파일에서_이름을_바꿔도_본문을_뺀다():
    file = _file("config/settings.txt", ["+password=abc123def456"], old_path=".env")

    result = preprocess(DiffAnalysis(files=[file]))

    assert result.secret_files == ["config/settings.txt"]


def test_일반_파일은_값을_가리고_개수를_남긴다():
    file = _file("src/config.py", [f'+TOKEN = "{GITHUB_PAT}"', "+DEBUG = True"])

    result = preprocess(DiffAnalysis(files=[file]))

    [kept] = result.files
    assert kept.hunks[0].lines == [f'+TOKEN = "{MASK}"', "+DEBUG = True"]
    assert result.masked == {"src/config.py": 1}


def test_길이를_자르기_전에_가린다():
    # 문자 상한이 키 중간에 걸리면 앞부분만 남아 패턴에 걸리지 않는다
    file = _file("src/config.py", [f"+GITHUB_TOKEN={GITHUB_PAT}"])

    result = preprocess(DiffAnalysis(files=[file]), max_chars_per_file=30)

    assert "a1B2" not in result.files[0].patch()


def test_비밀값이_없으면_알릴_것도_없다():
    result = preprocess(DiffAnalysis(files=[_file("src/app.py", ["+print('hi')"])]))

    assert not result.is_redacted()
