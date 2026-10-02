"""Ownership preflight tests using synthetic GitHub metadata and HTTP responses."""

from json import JSONDecodeError
from unittest.mock import AsyncMock

import httpx2
import pytest

from learn_to_cloud.schemas.verification import ValidationResult
from learn_to_cloud.verification.github_api import GitHubClient
from learn_to_cloud.verification.github_errors import GitHubServerError
from learn_to_cloud.verification.repository_ownership import (
    OwnedRepository,
    check_repository_ownership,
)
from learn_to_cloud.verification.repository_target import GitHubRepositoryTarget
from tests.support.fakes.github import FakeGitHub

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

TARGET = GitHubRepositoryTarget("learner", "project", "upstream/project")


def _repo(**changes):
    return {
        "owner": {"id": 42, "login": "learner"},
        "name": "project",
        "private": False,
        **changes,
    }


@pytest.mark.parametrize(
    ("fork_fields", "parent"),
    [
        ({}, None),
        ({"fork": False}, None),
        (
            {"fork": True, "parent": {"full_name": "upstream/project"}},
            "upstream/project",
        ),
    ],
)
async def test_matching_owner_preserves_target_and_reports_fork_parent(
    fork_fields, parent
):
    metadata = FakeGitHub(repos={"learner/project": _repo(**fork_fields)})
    assert await check_repository_ownership(TARGET, 42, metadata) == OwnedRepository(
        target=TARGET, parent=parent
    )


@pytest.mark.parametrize(
    "fork_fields",
    [
        {"fork": "yes"},
        {"fork": True},
        {"fork": True, "parent": "upstream/project"},
        {"fork": True, "parent": {"full_name": None}},
    ],
)
async def test_malformed_fork_metadata_is_incomplete(fork_fields):
    metadata = FakeGitHub(repos={"learner/project": _repo(**fork_fields)})
    result = await check_repository_ownership(TARGET, 42, metadata)
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed


@pytest.mark.parametrize("login", ["reclaimed-name", "another-user", "organization"])
async def test_wrong_owner_cannot_pass_based_on_name_or_fork(login):
    data = _repo(
        owner={"id": 99, "login": login},
        fork=True,
        parent={"full_name": "upstream/project"},
    )
    result = await check_repository_ownership(
        TARGET, 42, FakeGitHub(repos={"learner/project": data})
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert result.verification_completed
    assert result.username_match is False
    assert result.message == (
        "Use the required repository under the GitHub account you signed "
        "in with. If you changed your GitHub username, sign out and back "
        "in, then resubmit."
    )


async def test_missing_repository_has_actionable_conditional_login_guidance():
    result = await check_repository_ownership(TARGET, 42, FakeGitHub())
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert result.verification_completed
    assert result.repo_exists is False
    assert result.message == (
        "Can't access the required repository. "
        "Make sure it's public and under your GitHub account. "
        "If you changed your GitHub username, sign out and back in, "
        "then resubmit."
    )


async def test_private_repository_fails_even_when_metadata_is_accessible():
    result = await check_repository_ownership(
        TARGET,
        42,
        FakeGitHub(repos={"learner/project": _repo(private=True)}),
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert result.verification_completed
    assert result.message == "Make the required repository public, then resubmit."


@pytest.mark.parametrize("owner_id", [None, True, False, "42", 42.0, 0, -1, 2**63])
async def test_owner_id_is_not_coerced(owner_id):
    result = await check_repository_ownership(
        TARGET,
        42,
        FakeGitHub(
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
        _repo(name=None),
        _repo(private=None),
        _repo(private="false"),
    ],
)
async def test_malformed_metadata_is_incomplete(data, caplog):
    result = await check_repository_ownership(
        TARGET, 42, FakeGitHub(repos={"learner/project": data})
    )
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed
    assert result.message == "Couldn't read GitHub's response. Try again later."
    record = caplog.records[-1]
    assert record.message == "github.ownership.invalid_metadata"
    assert record.__dict__["error.type"] == "response_validation"
    assert "secret" not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
async def test_provider_errors_do_not_fail_the_assignment(status, caplog):
    response = httpx2.Response(
        status,
        request=httpx2.Request("GET", "https://api.github.com/repos/private-user/repo"),
        headers={"retry-after": "120"} if status in {403, 429} else {},
        json={"message": "private-provider-response"},
    )
    error = httpx2.HTTPStatusError(
        "private-exception-content", request=response.request, response=response
    )
    result = await check_repository_ownership(TARGET, 42, FakeGitHub(repo_error=error))
    assert isinstance(result, ValidationResult)
    assert not result.is_valid
    assert not result.verification_completed
    assert "private-" not in caplog.text
    assert "private-" not in result.message


@pytest.mark.parametrize(
    "error",
    [
        httpx2.ConnectError("private-network-details"),
        httpx2.ReadTimeout("private-timeout-details"),
        GitHubServerError("private-server-details", status_code=503),
        JSONDecodeError("private-json-details", "", 0),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "private-decode-details"),
    ],
)
async def test_transport_and_decode_failures_are_incomplete(error, caplog):
    result = await check_repository_ownership(TARGET, 42, FakeGitHub(repo_error=error))
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
            return httpx2.Response(
                301, headers={"location": "https://api.github.com/repos/new-name/moved"}
            )
        return httpx2.Response(
            200, json=_repo(owner={"id": owner_id, "login": "new-name"}, name="moved")
        )

    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(respond), follow_redirects=True
    ) as client:
        monkeypatch.setattr(
            "learn_to_cloud.verification.github_http._get_github_client",
            AsyncMock(return_value=client),
        )
        result = await check_repository_ownership(TARGET, 42, GitHubClient())

    assert paths == ["/repos/learner/project", "/repos/new-name/moved"]
    if owner_id == 42:
        assert result == OwnedRepository(
            target=GitHubRepositoryTarget("new-name", "moved", "upstream/project"),
            parent=None,
        )
    else:
        assert isinstance(result, ValidationResult)
        assert not result.is_valid
        assert result.username_match is False


async def test_unexpected_errors_propagate():
    with pytest.raises(RuntimeError, match="internal failure"):
        await check_repository_ownership(
            TARGET,
            42,
            FakeGitHub(repo_error=RuntimeError("internal failure")),
        )
