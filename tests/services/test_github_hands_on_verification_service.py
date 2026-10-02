"""Unit tests for github_hands_on_verification_service.

Tests cover:
- _parse_retry_after header parsing
- get_github_headers with and without token
- validate_profile_readme and validate_repo_fork results built from the
  repository metadata the ownership preflight already fetched
"""

from unittest.mock import MagicMock, patch

import pytest

from learn_to_cloud.verification.github_http import (
    _parse_retry_after,
    get_github_headers,
)
from learn_to_cloud.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)
from learn_to_cloud.verification.repository_ownership import OwnedRepository
from learn_to_cloud.verification.repository_target import GitHubRepositoryTarget

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
            "learn_to_cloud.verification.github_http.get_worker_settings",
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
            "learn_to_cloud.verification.github_http.get_worker_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            headers = get_github_headers()
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# validate_profile_readme / validate_repo_fork
# ---------------------------------------------------------------------------


def test_profile_readme_passes_once_ownership_confirms_the_repository():
    result = validate_profile_readme()
    assert result.is_valid
    assert result.username_match
    assert result.repo_exists


def _owned(parent: str | None, forked_from: str | None = "learntocloud/repo"):
    return OwnedRepository(
        target=GitHubRepositoryTarget(
            owner="testuser", repo="repo", forked_from=forked_from
        ),
        parent=parent,
    )


@pytest.mark.parametrize("parent", ["learntocloud/repo", "LearnToCloud/Repo"])
def test_fork_of_required_upstream_passes(parent):
    result = validate_repo_fork(_owned(parent))
    assert result.is_valid
    assert result.message == (
        "Repository fork validated successfully! Verified fork of learntocloud/repo"
    )
    assert result.repo_exists


@pytest.mark.parametrize(
    ("parent", "message"),
    [
        (None, "Repository is not a fork"),
        ("someone-else/repo", "Forked from someone-else/repo, not learntocloud/repo"),
    ],
)
def test_fork_with_wrong_lineage_fails_as_completed(parent, message):
    result = validate_repo_fork(_owned(parent))
    assert not result.is_valid
    assert result.verification_completed
    assert result.message == message
    assert result.username_match
    assert result.repo_exists


def test_fork_without_required_upstream_is_a_programming_error():
    with pytest.raises(ValueError, match="requires an upstream"):
        validate_repo_fork(_owned("learntocloud/repo", forked_from=None))
