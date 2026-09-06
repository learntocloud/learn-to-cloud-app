"""Ownership preflight tests using synthetic GitHub metadata and HTTP responses."""

from json import JSONDecodeError
from unittest.mock import AsyncMock

import httpx
import pytest

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.schemas import ValidationResult
from learn_to_cloud_shared.verification.errors import GitHubServerError
from learn_to_cloud_shared.verification.github_metadata import (
    GitHubApiMetadata,
    InMemoryGitHubMetadata,
)
from learn_to_cloud_shared.verification.repository_ownership import (
    check_repository_ownership,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TARGET = GitHubTarget("learner", "project", "upstream/project")


def _repo(**changes):
    return {
        "owner": {"id": 42, "login": "learner"},
        "name": "project",
        "private": False,
        **changes,
    }


async def test_matching_owner_preserves_target_and_fork_expectation():
    metadata = InMemoryGitHubMetadata(repos={"learner/project": _repo()})
    assert await check_repository_ownership(TARGET, 42, metadata) == TARGET


@pytest.mark.parametrize("login", ["reclaimed-name", "another-user", "organization"])
async def test_wrong_owner_cannot_pass_based_on_name_or_fork(login):
    data = _repo(
        owner={"id": 99, "login": login},
        fork=True,
        parent={"full_name": "upstream/project"},
    )
    result = await check_repository_ownership(
        TARGET, 42, InMemoryGitHubMetadata(repos={"learner/project": data})
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert result.verification_completed
    assert result.username_match is False
    assert "must belong" in result.message
    assert "If you changed" in result.message


async def test_missing_repository_has_actionable_conditional_login_guidance():
    result = await check_repository_ownership(TARGET, 42, InMemoryGitHubMetadata())
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert result.verification_completed
    assert result.repo_exists is False
    assert "public" in result.message
    assert "If you changed your GitHub username" in result.message


async def test_private_repository_fails_even_when_metadata_is_accessible():
    result = await check_repository_ownership(
        TARGET,
        42,
        InMemoryGitHubMetadata(repos={"learner/project": _repo(private=True)}),
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert result.verification_completed
    assert "public" in result.message


@pytest.mark.parametrize("owner_id", [None, True, False, "42", 42.0, 0, -1, 2**63])
async def test_owner_id_is_not_coerced(owner_id):
    result = await check_repository_ownership(
        TARGET,
        42,
        InMemoryGitHubMetadata(
            repos={"learner/project": _repo(owner={"id": owner_id, "login": "learner"})}
        ),
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed


@pytest.mark.parametrize(
    "data",
    [
        [],
        {},
        _repo(owner=None),
        _repo(owner={"id": 42}),
        _repo(owner={"id": 42, "login": "../other"}),
        _repo(owner={"id": 42, "login": ""}),
        _repo(name=None),
        _repo(name=""),
        _repo(name=".."),
        _repo(name="repo/path"),
        _repo(name="repo?token=secret"),
        _repo(name="x" * 256),
        _repo(private=None),
        _repo(private="false"),
    ],
)
async def test_malformed_metadata_is_incomplete(data, caplog):
    result = await check_repository_ownership(
        TARGET, 42, InMemoryGitHubMetadata(repos={"learner/project": data})
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed
    record = caplog.records[-1]
    assert record.message == "github.ownership.invalid_metadata"
    assert record.__dict__["error.type"] == "response_validation"
    assert "secret" not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
async def test_provider_errors_do_not_fail_the_assignment(status, caplog):
    response = httpx.Response(
        status,
        request=httpx.Request("GET", "https://api.github.com/repos/private-user/repo"),
        headers={"retry-after": "120"} if status in {403, 429} else {},
        json={"message": "private-provider-response"},
    )
    error = httpx.HTTPStatusError(
        "private-exception-content", request=response.request, response=response
    )
    result = await check_repository_ownership(
        TARGET, 42, InMemoryGitHubMetadata(repo_error=error)
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed
    assert "private-" not in caplog.text
    assert "private-" not in result.message


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("private-network-details"),
        httpx.ReadTimeout("private-timeout-details"),
        GitHubServerError("private-server-details"),
        JSONDecodeError("private-json-details", "", 0),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "private-decode-details"),
    ],
)
async def test_transport_and_decode_failures_are_incomplete(error, caplog):
    result = await check_repository_ownership(
        TARGET, 42, InMemoryGitHubMetadata(repo_error=error)
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed
    assert "private-" not in caplog.text


@pytest.mark.parametrize("owner_id", [42, 99])
async def test_real_metadata_adapter_checks_redirect_destination(monkeypatch, owner_id):
    paths = []

    def respond(request):
        paths.append(request.url.path)
        if request.url.path == "/repos/learner/project":
            return httpx.Response(
                301, headers={"location": "https://api.github.com/repos/new-name/moved"}
            )
        return httpx.Response(
            200, json=_repo(owner={"id": owner_id, "login": "new-name"}, name="moved")
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), follow_redirects=True
    ) as client:
        monkeypatch.setattr(
            "learn_to_cloud_shared.verification.github_http._get_github_client",
            AsyncMock(return_value=client),
        )
        result = await check_repository_ownership(TARGET, 42, GitHubApiMetadata())

    assert paths == ["/repos/learner/project", "/repos/new-name/moved"]
    if owner_id == 42:
        assert result == GitHubTarget("new-name", "moved", "upstream/project")
    else:
        assert isinstance(result, ValidationResult)
        assert not result.is_valid
        assert result.username_match is False


async def test_unexpected_errors_propagate():
    with pytest.raises(RuntimeError, match="internal failure"):
        await check_repository_ownership(
            TARGET,
            42,
            InMemoryGitHubMetadata(repo_error=RuntimeError("internal failure")),
        )


async def test_profile_only_target_is_not_silently_accepted():
    with pytest.raises(ValueError, match="requires a repository"):
        await check_repository_ownership(GitHubTarget("learner"), 42)
