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

from unittest.mock import MagicMock, patch

import httpx
import pytest

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.verification.errors import GitHubServerError
from learn_to_cloud_shared.verification.github_http import (
    _parse_retry_after,
    get_github_headers,
)
from learn_to_cloud_shared.verification.github_metadata import InMemoryGitHubMetadata
from learn_to_cloud_shared.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)

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
        target = GitHubTarget(owner="testuser", repo="testuser")
        metadata = InMemoryGitHubMetadata(existing_urls={target.url})
        result = await validate_profile_readme(target, metadata)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_readme_not_found_fails(self):
        target = GitHubTarget(owner="testuser", repo="testuser")
        metadata = InMemoryGitHubMetadata(existing_urls=set())
        result = await validate_profile_readme(target, metadata)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# validate_repo_fork
# ---------------------------------------------------------------------------


def _fork_target() -> GitHubTarget:
    return GitHubTarget(owner="testuser", repo="repo", forked_from="learntocloud/repo")


@pytest.mark.unit
class TestValidateRepoFork:
    @pytest.mark.asyncio
    async def test_missing_forked_from_fails(self):
        result = await validate_repo_fork(GitHubTarget(owner="testuser", repo="repo"))
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
        assert "Unexpected error" not in result.message

    @pytest.mark.asyncio
    async def test_server_error_propagated(self):
        metadata = InMemoryGitHubMetadata(
            repo_error=GitHubServerError("GitHub unavailable")
        )
        result = await validate_repo_fork(_fork_target(), metadata)
        assert result.is_valid is False
        assert result.verification_completed is False
