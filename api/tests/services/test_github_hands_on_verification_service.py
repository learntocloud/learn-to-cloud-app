"""Unit tests for github_hands_on_verification_service.

Tests cover:
- parse_github_url URL parsing and normalization
- _parse_retry_after header parsing
- get_github_headers with and without token
- validate_github_profile ownership and existence checks
- validate_profile_readme URL, ownership, and repo name checks
- validate_repo_fork URL, ownership, and fork verification
"""

from unittest.mock import MagicMock, patch

import pytest

from services.github_hands_on_verification_service import (
    _parse_retry_after,
    get_github_headers,
    parse_github_url,
    validate_github_profile,
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
        mock_settings.github_token = "ghp_test123"
        with patch(
            "services.github_hands_on_verification_service.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            headers = get_github_headers()
        assert headers["Authorization"] == "Bearer ghp_test123"
        assert headers["Accept"] == "application/vnd.github.v3+json"

    def test_no_auth_when_token_missing(self):
        mock_settings = MagicMock()
        mock_settings.github_token = ""
        with patch(
            "services.github_hands_on_verification_service.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            headers = get_github_headers()
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# parse_github_url
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseGitHubUrl:
    def test_standard_repo_url(self):
        result = parse_github_url("https://github.com/user/repo")
        assert result.is_valid is True
        assert result.username == "user"
        assert result.repo_name == "repo"

    def test_trailing_slash(self):
        result = parse_github_url("https://github.com/user/repo/")
        assert result.is_valid is True
        assert result.repo_name == "repo"

    def test_profile_url_no_repo(self):
        result = parse_github_url("https://github.com/user")
        assert result.is_valid is True
        assert result.username == "user"
        assert result.repo_name is None

    def test_http_prefix_normalized(self):
        result = parse_github_url("http://github.com/user/repo")
        assert result.is_valid is True
        assert result.username == "user"

    def test_www_prefix_normalized(self):
        result = parse_github_url("https://www.github.com/user/repo")
        assert result.is_valid is True
        assert result.username == "user"

    def test_http_www_prefix_normalized(self):
        result = parse_github_url("http://www.github.com/user/repo")
        assert result.is_valid is True

    def test_bare_github_prefix(self):
        result = parse_github_url("github.com/user/repo")
        assert result.is_valid is True
        assert result.username == "user"

    def test_www_without_scheme(self):
        result = parse_github_url("www.github.com/user/repo")
        assert result.is_valid is True

    def test_blob_path_extracts_file(self):
        result = parse_github_url("https://github.com/user/repo/blob/main/src/app.py")
        assert result.is_valid is True
        assert result.username == "user"
        assert result.repo_name == "repo"
        assert result.file_path == "src/app.py"

    def test_tree_path_without_file(self):
        result = parse_github_url("https://github.com/user/repo/tree/main")
        assert result.is_valid is True
        assert result.file_path is None

    def test_non_github_url_invalid(self):
        result = parse_github_url("https://gitlab.com/user/repo")
        assert result.is_valid is False

    def test_empty_string_invalid(self):
        result = parse_github_url("")
        assert result.is_valid is False

    def test_whitespace_stripped(self):
        result = parse_github_url("  https://github.com/user/repo  ")
        assert result.is_valid is True
        assert result.username == "user"

    def test_username_too_long_invalid(self):
        long_name = "a" * 40
        result = parse_github_url(f"https://github.com/{long_name}/repo")
        assert result.is_valid is False
        assert "Invalid GitHub username" in (result.error or "")

    def test_username_starts_with_hyphen_invalid(self):
        result = parse_github_url("https://github.com/-invalid/repo")
        assert result.is_valid is False

    def test_username_ends_with_hyphen_invalid(self):
        result = parse_github_url("https://github.com/invalid-/repo")
        assert result.is_valid is False

    def test_single_char_username_valid(self):
        result = parse_github_url("https://github.com/a/repo")
        assert result.is_valid is True

    def test_hyphenated_username_valid(self):
        result = parse_github_url("https://github.com/my-user/repo")
        assert result.is_valid is True

    def test_github_com_only_invalid(self):
        result = parse_github_url("https://github.com/")
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# validate_github_profile
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateGitHubProfile:
    @pytest.mark.asyncio
    async def test_non_github_url_fails(self):
        result = await validate_github_profile("https://linkedin.com/user", "testuser")
        assert result.is_valid is False
        assert result.username_match is False

    @pytest.mark.asyncio
    async def test_username_mismatch_fails(self):
        result = await validate_github_profile(
            "https://github.com/otheruser", "testuser"
        )
        assert result.is_valid is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_profile_exists_succeeds(self):
        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists",
            autospec=True,
            return_value=(True, "URL exists", False),
        ):
            result = await validate_github_profile(
                "https://github.com/testuser", "testuser"
            )
        assert result.is_valid is True
        assert result.username_match is True

    @pytest.mark.asyncio
    async def test_profile_not_found_fails(self):
        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists",
            autospec=True,
            return_value=(False, "URL not found (404)", False),
        ):
            result = await validate_github_profile(
                "https://github.com/testuser", "testuser"
            )
        assert result.is_valid is False
        assert result.username_match is True

    @pytest.mark.asyncio
    async def test_server_error_propagated(self):
        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists",
            autospec=True,
            return_value=(False, "GitHub service temporarily unavailable", True),
        ):
            result = await validate_github_profile(
                "https://github.com/testuser", "testuser"
            )
        assert result.is_valid is False
        assert result.server_error is True

    @pytest.mark.asyncio
    async def test_empty_username_in_url_fails(self):
        result = await validate_github_profile("https://github.com/", "testuser")
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# validate_profile_readme
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateProfileReadme:
    @pytest.mark.asyncio
    async def test_invalid_url_fails(self):
        result = await validate_profile_readme("not-a-url", "testuser")
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_username_mismatch_fails(self):
        result = await validate_profile_readme(
            "https://github.com/otheruser/otheruser/blob/main/README.md", "testuser"
        )
        assert result.is_valid is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_wrong_repo_name_fails(self):
        result = await validate_profile_readme(
            "https://github.com/testuser/wrong-repo/blob/main/README.md", "testuser"
        )
        assert result.is_valid is False
        assert "must be in a repo named" in result.message

    @pytest.mark.asyncio
    async def test_readme_exists_succeeds(self):
        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists",
            autospec=True,
            return_value=(True, "URL exists", False),
        ):
            result = await validate_profile_readme(
                "https://github.com/testuser/testuser/blob/main/README.md",
                "testuser",
            )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_readme_not_found_fails(self):
        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists",
            autospec=True,
            return_value=(False, "URL not found (404)", False),
        ):
            result = await validate_profile_readme(
                "https://github.com/testuser/testuser/blob/main/README.md",
                "testuser",
            )
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# validate_repo_fork
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateRepoFork:
    @pytest.mark.asyncio
    async def test_invalid_url_fails(self):
        result = await validate_repo_fork("not-a-url", "testuser", "learntocloud/repo")
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_username_mismatch_fails(self):
        result = await validate_repo_fork(
            "https://github.com/otheruser/repo",
            "testuser",
            "learntocloud/repo",
        )
        assert result.is_valid is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_no_repo_name_fails(self):
        result = await validate_repo_fork(
            "https://github.com/testuser",
            "testuser",
            "learntocloud/repo",
        )
        assert result.is_valid is False
        assert "repository name" in result.message.lower()

    @pytest.mark.asyncio
    async def test_valid_fork_succeeds(self):
        with patch(
            "services.github_hands_on_verification_service.check_repo_is_fork_of",
            autospec=True,
            return_value=(True, "Verified fork of learntocloud/repo", False),
        ):
            result = await validate_repo_fork(
                "https://github.com/testuser/repo",
                "testuser",
                "learntocloud/repo",
            )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_not_a_fork_fails(self):
        with patch(
            "services.github_hands_on_verification_service.check_repo_is_fork_of",
            autospec=True,
            return_value=(False, "Repository is not a fork", False),
        ):
            result = await validate_repo_fork(
                "https://github.com/testuser/repo",
                "testuser",
                "learntocloud/repo",
            )
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_server_error_propagated(self):
        with patch(
            "services.github_hands_on_verification_service.check_repo_is_fork_of",
            autospec=True,
            return_value=(False, "GitHub unavailable", True),
        ):
            result = await validate_repo_fork(
                "https://github.com/testuser/repo",
                "testuser",
                "learntocloud/repo",
            )
        assert result.is_valid is False
        assert result.server_error is True
