"""GitHub 호출 실패를 도메인 예외로 바꾸는 처리."""

from __future__ import annotations

import pytest
from github.GithubException import (
    BadCredentialsException,
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)

from commit_agent.git_integration.exceptions import (
    GitHubAPIError,
    GitHubAuthError,
    GitHubRateLimitError,
    GitHubRepositoryNotFoundError,
)
from commit_agent.git_integration.schemas import IssueDraft
from commit_agent.git_integration.services import github


class _Repo:
    """호출하면 정해 둔 예외를 던지는 가짜 저장소."""

    full_name = "owner/name"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def _fail(self, *_args, **_kwargs):
        raise self.error

    get_issue = get_labels = create_issue = get_issues = _fail


class _Client:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_repo(self, _slug):
        raise self.error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BadCredentialsException(401, {"message": "Bad credentials"}), GitHubAuthError),
        (RateLimitExceededException(403, {"message": "rate limit"}), GitHubRateLimitError),
        (GithubException(502, {"message": "Bad Gateway"}), GitHubAPIError),
        (ConnectionError("reset"), GitHubAPIError),
    ],
)
def test_PyGithub_예외를_도메인_예외로_바꾼다(error, expected):
    with pytest.raises(expected):
        github.list_labels(_Repo(error))


def test_API_오류는_상태_코드와_메시지를_남긴다():
    with pytest.raises(GitHubAPIError) as info:
        github.list_labels(_Repo(GithubException(502, {"message": "Bad Gateway"})))

    assert info.value.status == 502
    assert "Bad Gateway" in str(info.value)


def test_없는_저장소는_따로_구분한다():
    with pytest.raises(GitHubRepositoryNotFoundError):
        github.get_repository(_Client(UnknownObjectException(404)), "owner/name")


def test_목록은_순회_중에_난_오류도_바꾼다():
    with pytest.raises(GitHubRateLimitError):
        github.list_issues(_Repo(RateLimitExceededException(403)))


def test_이슈_생성의_404는_권한_문제로_알린다():
    """쓰기 권한이 없는 토큰에는 GitHub가 403 대신 404를 준다."""
    draft = IssueDraft(title="제목", body="본문")

    with pytest.raises(GitHubAuthError, match="권한"):
        github.create_issue(_Repo(UnknownObjectException(404)), draft)


def test_클라이언트는_오래_기다리지_않게_재시도를_제한한다(monkeypatch):
    # PyGithub은 재시도 설정을 비공개 속성에 두므로 생성 인자로 확인한다
    monkeypatch.setattr(github, "Github", lambda **kwargs: kwargs)

    retry = github.open_github("ghp_x")["retry"]

    assert retry.total == 3
    assert retry.max_rate_limit_wait == 10
    assert "POST" not in retry.allowed_methods
