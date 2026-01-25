"""Tests for the GitHub hands-on verification service module.

Tests GitHub-specific validation functions including profile verification,
profile README, and repository fork verification for Phase 0 and Phase 1.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from circuitbreaker import CircuitBreakerError


class TestParseGitHubUrl:
    """Tests for parse_github_url function."""

    def test_valid_profile_url(self):
        """Valid profile URL should parse correctly."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("https://github.com/testuser")
        assert result.is_valid is True
        assert result.username == "testuser"
        assert result.repo_name is None

    def test_valid_repo_url(self):
        """Valid repository URL should parse correctly."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("https://github.com/testuser/my-repo")
        assert result.is_valid is True
        assert result.username == "testuser"
        assert result.repo_name == "my-repo"

    def test_profile_readme_url(self):
        """Profile README URL should parse correctly."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url(
            "https://github.com/testuser/testuser/blob/main/README.md"
        )
        assert result.is_valid is True
        assert result.username == "testuser"
        assert result.repo_name == "testuser"
        assert result.file_path == "README.md"

    def test_url_normalization_http(self):
        """HTTP URL should be normalized to HTTPS."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("http://github.com/testuser")
        assert result.is_valid is True
        assert result.username == "testuser"

    def test_url_normalization_www(self):
        """www.github.com should be normalized."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("https://www.github.com/testuser")
        assert result.is_valid is True
        assert result.username == "testuser"

    def test_url_without_protocol(self):
        """URL without protocol should have https:// added."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("github.com/testuser")
        assert result.is_valid is True
        assert result.username == "testuser"

    def test_non_github_url(self):
        """Non-GitHub URL should be invalid."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("https://gitlab.com/testuser")
        assert result.is_valid is False
        assert result.error is not None and "GitHub URL" in result.error

    def test_invalid_username_format(self):
        """Invalid username format should be invalid."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("https://github.com/-invalid")
        assert result.is_valid is False
        assert result.error is not None and "Invalid GitHub username" in result.error

    def test_username_too_long(self):
        """Username > 39 chars should be invalid."""
        from services.github_hands_on_verification_service import parse_github_url

        long_username = "a" * 40
        result = parse_github_url(f"https://github.com/{long_username}")
        assert result.is_valid is False
        assert result.error is not None and "Invalid GitHub username" in result.error

    def test_empty_path(self):
        """URL with empty path should be invalid."""
        from services.github_hands_on_verification_service import parse_github_url

        result = parse_github_url("https://github.com/")
        assert result.is_valid is False
        assert result.error is not None


class TestGitHubClientManagement:
    """Tests for HTTP client management."""

    @pytest.mark.asyncio
    async def test_get_github_client_creates_client(self):
        """Should create client on first call."""
        from services.github_hands_on_verification_service import (
            _get_github_client,
            close_github_client,
        )

        await close_github_client()

        with patch(
            "services.github_hands_on_verification_service.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(http_timeout=10.0)

            client = await _get_github_client()
            assert client is not None

            await close_github_client()

    @pytest.mark.asyncio
    async def test_close_github_client(self):
        """close_github_client should close and clear client."""
        import services.github_hands_on_verification_service as module
        from services.github_hands_on_verification_service import (
            close_github_client,
        )

        mock_client = AsyncMock()
        mock_client.is_closed = False
        module._github_http_client = mock_client

        await close_github_client()
        mock_client.aclose.assert_called_once()
        assert module._github_http_client is None


class TestGitHubHeaders:
    """Tests for GitHub API headers."""

    def test_get_github_headers_without_token(self):
        """Headers without token should have Accept header only."""
        from services.github_hands_on_verification_service import _get_github_headers

        with patch(
            "services.github_hands_on_verification_service.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(github_token=None)
            headers = _get_github_headers()
            assert "Accept" in headers
            assert "Authorization" not in headers

    def test_get_github_headers_with_token(self):
        """Headers with token should include Authorization."""
        from services.github_hands_on_verification_service import _get_github_headers

        with patch(
            "services.github_hands_on_verification_service.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(github_token="ghp_test123")
            headers = _get_github_headers()
            assert headers["Authorization"] == "Bearer ghp_test123"


class TestRetryAfterParsing:
    """Tests for Retry-After header parsing."""

    def test_parse_retry_after_numeric(self):
        """Numeric Retry-After should parse."""
        from services.github_hands_on_verification_service import _parse_retry_after

        assert _parse_retry_after("30") == 30.0

    def test_parse_retry_after_none(self):
        """None should return None."""
        from services.github_hands_on_verification_service import _parse_retry_after

        assert _parse_retry_after(None) is None

    def test_parse_retry_after_invalid(self):
        """Invalid value should return None."""
        from services.github_hands_on_verification_service import _parse_retry_after

        assert _parse_retry_after("not-a-number") is None


class TestGitHubServerError:
    """Tests for GitHubServerError exception."""

    def test_github_server_error_basic(self):
        """Basic error should have message."""
        from services.github_hands_on_verification_service import GitHubServerError

        error = GitHubServerError("Server error")
        assert str(error) == "Server error"
        assert error.retry_after is None

    def test_github_server_error_with_retry(self):
        """Error with retry_after should store it."""
        from services.github_hands_on_verification_service import GitHubServerError

        error = GitHubServerError("Rate limited", retry_after=60.0)
        assert error.retry_after == 60.0


class TestCheckGitHubUrlExists:
    """Tests for check_github_url_exists function."""

    @pytest.mark.asyncio
    async def test_url_exists(self):
        """Existing URL should return True."""
        from services.github_hands_on_verification_service import (
            check_github_url_exists,
        )

        with patch(
            "services.github_hands_on_verification_service._check_github_url_exists_with_retry"
        ) as mock:
            mock.return_value = (True, "URL exists")

            exists, msg = await check_github_url_exists("https://github.com/testuser")
            assert exists is True

    @pytest.mark.asyncio
    async def test_url_not_found(self):
        """Non-existing URL should return False."""
        from services.github_hands_on_verification_service import (
            check_github_url_exists,
        )

        with patch(
            "services.github_hands_on_verification_service._check_github_url_exists_with_retry"
        ) as mock:
            mock.return_value = (False, "URL not found (404)")

            exists, msg = await check_github_url_exists(
                "https://github.com/nonexistent"
            )
            assert exists is False
            assert "404" in msg

    @pytest.mark.asyncio
    async def test_url_check_circuit_breaker(self):
        """Circuit breaker should return appropriate message."""
        from services.github_hands_on_verification_service import (
            check_github_url_exists,
        )

        with patch(
            "services.github_hands_on_verification_service._check_github_url_exists_with_retry"
        ) as mock:
            mock.side_effect = CircuitBreakerError(MagicMock())

            exists, msg = await check_github_url_exists("https://github.com/testuser")
            assert exists is False
            assert "temporarily unavailable" in msg


class TestCheckRepoIsForkOf:
    """Tests for check_repo_is_fork_of function."""

    @pytest.mark.asyncio
    async def test_repo_is_fork(self):
        """Repo that is a fork should return True."""
        from services.github_hands_on_verification_service import check_repo_is_fork_of

        with patch(
            "services.github_hands_on_verification_service._check_repo_is_fork_of_with_retry"
        ) as mock:
            mock.return_value = (True, "Verified fork of original/repo")

            is_fork, msg = await check_repo_is_fork_of(
                "testuser", "repo", "original/repo"
            )
            assert is_fork is True

    @pytest.mark.asyncio
    async def test_repo_not_a_fork(self):
        """Repo that is not a fork should return False."""
        from services.github_hands_on_verification_service import check_repo_is_fork_of

        with patch(
            "services.github_hands_on_verification_service._check_repo_is_fork_of_with_retry"
        ) as mock:
            mock.return_value = (False, "Repository is not a fork")

            is_fork, msg = await check_repo_is_fork_of(
                "testuser", "repo", "original/repo"
            )
            assert is_fork is False

    @pytest.mark.asyncio
    async def test_fork_check_circuit_breaker(self):
        """Circuit breaker should return appropriate message."""
        from services.github_hands_on_verification_service import check_repo_is_fork_of

        with patch(
            "services.github_hands_on_verification_service._check_repo_is_fork_of_with_retry"
        ) as mock:
            mock.side_effect = CircuitBreakerError(MagicMock())

            is_fork, msg = await check_repo_is_fork_of(
                "testuser", "repo", "original/repo"
            )
            assert is_fork is False
            assert "temporarily unavailable" in msg


class TestValidateGitHubProfile:
    """Tests for validate_github_profile function."""

    @pytest.mark.asyncio
    async def test_valid_profile(self):
        """Valid profile should pass."""
        from services.github_hands_on_verification_service import (
            validate_github_profile,
        )

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock:
            mock.return_value = (True, "URL exists")

            result = await validate_github_profile(
                "https://github.com/testuser", "testuser"
            )
            assert result.is_valid is True
            assert result.username_match is True

    @pytest.mark.asyncio
    async def test_profile_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import (
            validate_github_profile,
        )

        result = await validate_github_profile(
            "https://github.com/otheruser", "testuser"
        )
        assert result.is_valid is False
        assert result.username_match is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_profile_not_found(self):
        """Non-existent profile should fail."""
        from services.github_hands_on_verification_service import (
            validate_github_profile,
        )

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock:
            mock.return_value = (False, "Not found")

            result = await validate_github_profile(
                "https://github.com/testuser", "testuser"
            )
            assert result.is_valid is False
            assert result.username_match is True

    @pytest.mark.asyncio
    async def test_profile_invalid_url(self):
        """Invalid URL should fail."""
        from services.github_hands_on_verification_service import (
            validate_github_profile,
        )

        result = await validate_github_profile("not-a-url", "testuser")
        assert result.is_valid is False


class TestValidateProfileReadme:
    """Tests for validate_profile_readme function."""

    @pytest.mark.asyncio
    async def test_valid_profile_readme(self):
        """Valid profile README should pass."""
        from services.github_hands_on_verification_service import (
            validate_profile_readme,
        )

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock:
            mock.return_value = (True, "URL exists")

            result = await validate_profile_readme(
                "https://github.com/testuser/testuser/blob/main/README.md",
                "testuser",
            )
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_profile_readme_wrong_repo(self):
        """README in wrong repo should fail."""
        from services.github_hands_on_verification_service import (
            validate_profile_readme,
        )

        result = await validate_profile_readme(
            "https://github.com/testuser/other-repo/blob/main/README.md",
            "testuser",
        )
        assert result.is_valid is False
        assert "must be in a repo named" in result.message

    @pytest.mark.asyncio
    async def test_profile_readme_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import (
            validate_profile_readme,
        )

        result = await validate_profile_readme(
            "https://github.com/otheruser/otheruser/blob/main/README.md",
            "testuser",
        )
        assert result.is_valid is False
        assert result.username_match is False


class TestValidateRepoFork:
    """Tests for validate_repo_fork function."""

    @pytest.mark.asyncio
    async def test_valid_fork(self):
        """Valid fork should pass."""
        from services.github_hands_on_verification_service import validate_repo_fork

        with patch(
            "services.github_hands_on_verification_service.check_repo_is_fork_of"
        ) as mock:
            mock.return_value = (True, "Verified fork")

            result = await validate_repo_fork(
                "https://github.com/testuser/repo",
                "testuser",
                "original/repo",
            )
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_fork_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import validate_repo_fork

        result = await validate_repo_fork(
            "https://github.com/otheruser/repo",
            "testuser",
            "original/repo",
        )
        assert result.is_valid is False
        assert result.username_match is False

    @pytest.mark.asyncio
    async def test_fork_not_a_fork(self):
        """Non-fork repo should fail."""
        from services.github_hands_on_verification_service import validate_repo_fork

        with patch(
            "services.github_hands_on_verification_service.check_repo_is_fork_of"
        ) as mock:
            mock.return_value = (False, "Not a fork")

            result = await validate_repo_fork(
                "https://github.com/testuser/repo",
                "testuser",
                "original/repo",
            )
            assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_fork_missing_repo_name(self):
        """URL without repo name should fail."""
        from services.github_hands_on_verification_service import validate_repo_fork

        result = await validate_repo_fork(
            "https://github.com/testuser",
            "testuser",
            "original/repo",
        )
        assert result.is_valid is False
        assert "Could not extract repository name" in result.message
