"""Unit tests for github_hands_on_verification_service.

Tests cover:
- _parse_retry_after header parsing
- get_github_headers with and without token
- validate_profile_readme existence check against a constructed target
- validate_repo_fork lineage check against a constructed target

The validation tests inject an :class:`InMemoryGitHubMetadata` adapter
instead of patching internals, so they exercise the real validator logic
through the ``GitHubMetadata`` seam.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.verification import (
    github_errors,
    github_http,
    github_metadata,
)
from learn_to_cloud_shared.verification.github_errors import GitHubServerError
from learn_to_cloud_shared.verification.github_http import (
    _parse_retry_after,
    get_github_headers,
)
from learn_to_cloud_shared.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)
from tests.fakes.github_metadata import InMemoryGitHubMetadata

# ---------------------------------------------------------------------------
# _parse_retry_after
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseRetryAfter:
    def test_valid_integer(self):
        assert _parse_retry_after("120") == 120.0

    def test_valid_float(self):
        assert _parse_retry_after("1.5") == 1.5

    def test_none_returns_none(self):
        assert _parse_retry_after(None) is None

    def test_non_numeric_returns_none(self):
        assert _parse_retry_after("not-a-number") is None

    def test_empty_string_returns_none(self):
        assert _parse_retry_after("") is None


# ---------------------------------------------------------------------------
# get_github_headers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetGitHubHeaders:
    def test_includes_auth_when_token_present(self):
        mock_settings = MagicMock()
        mock_settings.github.token = "ghp_test123"
        with patch(
            "learn_to_cloud_shared.verification.github_http.get_worker_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            headers = get_github_headers()
        assert headers["Authorization"] == "Bearer ghp_test123"
        assert headers["Accept"] == "application/vnd.github.v3+json"

    def test_no_auth_when_token_missing(self):
        mock_settings = MagicMock()
        mock_settings.github.token = ""
        with patch(
            "learn_to_cloud_shared.verification.github_http.get_worker_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            headers = get_github_headers()
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# validate_profile_readme
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateProfileReadme:
    @pytest.mark.asyncio
    async def test_readme_exists_succeeds(self):
        target = GitHubRepositoryTarget(owner="testuser", repo="testuser")
        metadata = InMemoryGitHubMetadata(existing_urls={target.url})
        result = await validate_profile_readme(target, metadata)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_readme_not_found_fails(self):
        target = GitHubRepositoryTarget(owner="testuser", repo="testuser")
        metadata = InMemoryGitHubMetadata(existing_urls=set())
        result = await validate_profile_readme(target, metadata)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# validate_repo_fork
# ---------------------------------------------------------------------------


def _fork_target() -> GitHubRepositoryTarget:
    return GitHubRepositoryTarget(
        owner="testuser", repo="repo", forked_from="learntocloud/repo"
    )


@pytest.mark.unit
class TestValidateRepoFork:
    @pytest.mark.asyncio
    async def test_missing_forked_from_fails(self):
        result = await validate_repo_fork(
            GitHubRepositoryTarget(owner="testuser", repo="repo")
        )
        assert result.is_valid is False
        assert "required_repo" in result.message

    @pytest.mark.asyncio
    async def test_valid_fork_succeeds(self):
        metadata = InMemoryGitHubMetadata(
            repos={
                "testuser/repo": {
                    "fork": True,
                    "parent": {"full_name": "learntocloud/repo"},
                }
            }
        )
        result = await validate_repo_fork(_fork_target(), metadata)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_not_a_fork_fails(self):
        metadata = InMemoryGitHubMetadata(repos={"testuser/repo": {"fork": False}})
        result = await validate_repo_fork(_fork_target(), metadata)
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_wrong_parent_fails(self):
        metadata = InMemoryGitHubMetadata(
            repos={
                "testuser/repo": {
                    "fork": True,
                    "parent": {"full_name": "someone-else/repo"},
                }
            }
        )
        result = await validate_repo_fork(_fork_target(), metadata)
        assert result.is_valid is False
        assert "not learntocloud/repo" in result.message

    @pytest.mark.asyncio
    async def test_repo_not_found_fails(self):
        metadata = InMemoryGitHubMetadata(repos={})
        result = await validate_repo_fork(_fork_target(), metadata)
        assert result.is_valid is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_auth_error_does_not_penalise(self):
        response = httpx.Response(401, request=httpx.Request("GET", "https://test"))
        metadata = InMemoryGitHubMetadata(
            repo_error=httpx.HTTPStatusError(
                "Unauthorized", request=response.request, response=response
            )
        )
        result = await validate_repo_fork(_fork_target(), metadata)
        assert result.is_valid is False
        assert result.verification_completed is False


async def test_server_error_propagated():
    metadata = InMemoryGitHubMetadata(
        repo_error=GitHubServerError("GitHub unavailable", status_code=503)
    )
    result = await validate_repo_fork(_fork_target(), metadata)
    assert result.is_valid is False
    assert result.verification_completed is False


@pytest.mark.parametrize("kind", ["readme", "fork"])
@pytest.mark.parametrize(
    ("status", "headers", "category"),
    [
        (401, {}, "authentication"),
        (403, {}, "authorization"),
        (403, {"Retry-After": "30"}, "rate_limit"),
        (404, {}, None),
        (429, {"Retry-After": "30"}, "rate_limit"),
        (503, {}, "provider_unavailable"),
    ],
)
async def test_real_profile_requests_keep_missing_and_unavailable_distinct(
    kind, status, headers, category
):
    calls = []
    counter = MagicMock()
    span = MagicMock()

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers=headers, text="private upstream detail")

    get = github_http.github_api_get.retry_with(sleep=AsyncMock())
    head = github_http.github_head_status.retry_with(sleep=AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with (
            patch.object(
                github_http, "_get_github_client", AsyncMock(return_value=client)
            ),
            patch.object(github_http, "get_github_headers", return_value={}),
            patch.object(github_metadata, "github_api_get", get),
            patch.object(github_metadata, "github_head_status", head),
            patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER", counter),
            patch.object(github_errors.trace, "get_current_span", return_value=span),
        ):
            result = (
                await validate_profile_readme(
                    GitHubRepositoryTarget(owner="testuser", repo="testuser")
                )
                if kind == "readme"
                else await validate_repo_fork(_fork_target())
            )
    assert len(calls) == (3 if status in {429, 503} else 1)
    assert calls[0].method == ("HEAD" if kind == "readme" else "GET")
    assert not result.is_valid
    assert result.username_match
    assert "private" not in result.message
    if status == 404:
        assert result.verification_completed
        assert result.repo_exists is False
        assert "not found" in result.message
        counter.add.assert_not_called()
    else:
        assert not result.verification_completed
        assert result.repo_exists is None
        assert result.message == f"GitHub API error ({status}). Try again later."
        counter.add.assert_called_once_with(1, {"error.type": category})
        event = (
            "github.url_check.failed"
            if kind == "readme"
            else "github.fork_check.failed"
            if status in {429, 503}
            else "fork_check.api_error"
        )
        span.add_event.assert_called_once_with(
            event, {"error.type": category, "http.response.status_code": status}
        )


@pytest.mark.parametrize("kind", ["readme", "fork"])
@pytest.mark.parametrize(
    "error_type", [httpx.ConnectError, httpx.ReadTimeout, ValueError]
)
async def test_incomplete_profile_does_not_claim_repository_absence(kind, error_type):
    error = error_type("sensitive detail")
    metadata = InMemoryGitHubMetadata(url_error=error, repo_error=error)
    with patch.object(github_errors, "_GITHUB_API_ERROR_COUNTER") as counter:
        result = (
            await validate_profile_readme(
                GitHubRepositoryTarget(owner="testuser", repo="testuser"), metadata
            )
            if kind == "readme"
            else await validate_repo_fork(_fork_target(), metadata)
        )
    assert not result.verification_completed
    assert result.repo_exists is None
    assert result.username_match
    assert "find your profile" not in result.message
    assert "sensitive" not in result.message
    if error_type is ValueError:
        counter.add.assert_not_called()
        assert result.message == "GitHub verification could not be completed."
    else:
        counter.add.assert_called_once_with(1, {"error.type": "network"})
        assert "Unexpected error" not in result.message
