"""Tests for the GitHub hands-on verification service module.

Tests GitHub-specific validation functions including profile verification,
repository checks, workflow runs, file searches, and container image validation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from circuitbreaker import CircuitBreakerError

from schemas import ValidationResult


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
        # The error message may vary, just check it's not valid
        assert result.error is not None


class TestPatternMatching:
    """Tests for file pattern matching functions."""

    def test_parse_pattern_specs_simple_file(self):
        """Simple filename pattern should parse correctly."""
        from services.github_hands_on_verification_service import _parse_pattern_specs

        specs = _parse_pattern_specs(["Dockerfile"])
        assert len(specs) == 1
        assert specs[0]["raw"] == "Dockerfile"
        assert specs[0]["name"] == "Dockerfile"
        assert specs[0]["path"] is None
        assert specs[0]["is_dir"] is False

    def test_parse_pattern_specs_with_path(self):
        """Pattern with path should parse correctly."""
        from services.github_hands_on_verification_service import _parse_pattern_specs

        specs = _parse_pattern_specs([".github/workflows/ci.yml"])
        assert len(specs) == 1
        assert specs[0]["path"] == ".github/workflows"
        assert specs[0]["name"] == "ci.yml"

    def test_parse_pattern_specs_directory(self):
        """Directory pattern (ending with /) should parse correctly."""
        from services.github_hands_on_verification_service import _parse_pattern_specs

        specs = _parse_pattern_specs(["infra/"])
        assert len(specs) == 1
        assert specs[0]["is_dir"] is True
        assert specs[0]["path"] == "infra"

    def test_parse_pattern_specs_extension(self):
        """Extension pattern should parse correctly."""
        from services.github_hands_on_verification_service import _parse_pattern_specs

        specs = _parse_pattern_specs([".tf"])
        assert len(specs) == 1
        assert specs[0]["name"] == ".tf"

    def test_pattern_matches_item_exact_name(self):
        """Exact filename match should work."""
        from services.github_hands_on_verification_service import (
            _parse_pattern_specs,
            _pattern_matches_item,
        )

        specs = _parse_pattern_specs(["Dockerfile"])
        assert _pattern_matches_item("Dockerfile", "Dockerfile", "file", specs[0])

    def test_pattern_matches_item_with_path(self):
        """Match with path prefix should work."""
        from services.github_hands_on_verification_service import (
            _parse_pattern_specs,
            _pattern_matches_item,
        )

        specs = _parse_pattern_specs([".github/workflows/ci.yml"])
        assert _pattern_matches_item(
            ".github/workflows/ci.yml", "ci.yml", "file", specs[0]
        )

    def test_pattern_matches_item_directory(self):
        """Directory match should work."""
        from services.github_hands_on_verification_service import (
            _parse_pattern_specs,
            _pattern_matches_item,
        )

        specs = _parse_pattern_specs(["infra/"])
        assert _pattern_matches_item("infra", "infra", "dir", specs[0])
        assert _pattern_matches_item("infra/main.tf", "main.tf", "file", specs[0])


class TestGitHubClientManagement:
    """Tests for HTTP client management."""

    @pytest.mark.asyncio
    async def test_get_github_client_creates_client(self):
        """Should create client on first call."""
        from services.github_hands_on_verification_service import (
            _get_github_client,
            close_github_client,
        )

        # Close any existing client first
        await close_github_client()

        with patch(
            "services.github_hands_on_verification_service.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(http_timeout=10.0)

            client = await _get_github_client()
            assert client is not None

            # Clean up
            await close_github_client()

    @pytest.mark.asyncio
    async def test_close_github_client(self):
        """close_github_client should close and clear client."""
        from services.github_hands_on_verification_service import (
            close_github_client,
            _github_http_client,
        )
        import services.github_hands_on_verification_service as module

        # Create a mock client
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

            exists, msg = await check_github_url_exists("https://github.com/nonexistent")
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
        from services.github_hands_on_verification_service import validate_github_profile

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
        from services.github_hands_on_verification_service import validate_github_profile

        result = await validate_github_profile(
            "https://github.com/otheruser", "testuser"
        )
        assert result.is_valid is False
        assert result.username_match is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_profile_not_found(self):
        """Non-existent profile should fail."""
        from services.github_hands_on_verification_service import validate_github_profile

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
        from services.github_hands_on_verification_service import validate_github_profile

        result = await validate_github_profile("not-a-url", "testuser")
        assert result.is_valid is False


class TestValidateRepoUrl:
    """Tests for validate_repo_url function."""

    @pytest.mark.asyncio
    async def test_valid_repo(self):
        """Valid repo should pass."""
        from services.github_hands_on_verification_service import validate_repo_url

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock:
            mock.return_value = (True, "URL exists")

            result = await validate_repo_url(
                "https://github.com/testuser/my-repo", "testuser"
            )
            assert result.is_valid is True
            assert result.username_match is True
            assert result.repo_exists is True

    @pytest.mark.asyncio
    async def test_repo_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import validate_repo_url

        result = await validate_repo_url(
            "https://github.com/otheruser/repo", "testuser"
        )
        assert result.is_valid is False
        assert result.username_match is False

    @pytest.mark.asyncio
    async def test_repo_not_found(self):
        """Non-existent repo should fail."""
        from services.github_hands_on_verification_service import validate_repo_url

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock:
            mock.return_value = (False, "Not found")

            result = await validate_repo_url(
                "https://github.com/testuser/repo", "testuser"
            )
            assert result.is_valid is False
            assert result.repo_exists is False


class TestValidateProfileReadme:
    """Tests for validate_profile_readme function."""

    @pytest.mark.asyncio
    async def test_valid_profile_readme(self):
        """Valid profile README should pass."""
        from services.github_hands_on_verification_service import validate_profile_readme

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
        from services.github_hands_on_verification_service import validate_profile_readme

        result = await validate_profile_readme(
            "https://github.com/testuser/other-repo/blob/main/README.md",
            "testuser",
        )
        assert result.is_valid is False
        assert "must be in a repo named" in result.message

    @pytest.mark.asyncio
    async def test_profile_readme_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import validate_profile_readme

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


class TestValidateWorkflowRun:
    """Tests for validate_workflow_run function."""

    @pytest.mark.asyncio
    async def test_valid_workflow_runs(self):
        """Repo with successful workflow runs should pass."""
        from services.github_hands_on_verification_service import validate_workflow_run
        from datetime import datetime, UTC

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification_service._fetch_workflow_runs_with_retry"
            ) as mock_runs:
                mock_runs.return_value = {
                    "total_count": 1,
                    "workflow_runs": [
                        {
                            "name": "CI",
                            "created_at": datetime.now(UTC).isoformat(),
                        }
                    ],
                }

                result = await validate_workflow_run(
                    "https://github.com/testuser/repo", "testuser"
                )
                assert result.is_valid is True
                assert "CI" in result.message

    @pytest.mark.asyncio
    async def test_no_workflow_runs(self):
        """Repo with no workflow runs should fail."""
        from services.github_hands_on_verification_service import validate_workflow_run

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification_service._fetch_workflow_runs_with_retry"
            ) as mock_runs:
                mock_runs.return_value = {"total_count": 0, "workflow_runs": []}

                result = await validate_workflow_run(
                    "https://github.com/testuser/repo", "testuser"
                )
                assert result.is_valid is False
                assert "No successful workflow runs" in result.message

    @pytest.mark.asyncio
    async def test_workflow_actions_not_enabled(self):
        """Repo without Actions should fail."""
        from services.github_hands_on_verification_service import validate_workflow_run

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification_service._fetch_workflow_runs_with_retry"
            ) as mock_runs:
                mock_runs.return_value = None  # 404 = Actions not found

                result = await validate_workflow_run(
                    "https://github.com/testuser/repo", "testuser"
                )
                assert result.is_valid is False
                assert "GitHub Actions not found" in result.message

    @pytest.mark.asyncio
    async def test_workflow_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import validate_workflow_run

        result = await validate_workflow_run(
            "https://github.com/otheruser/repo", "testuser"
        )
        assert result.is_valid is False
        assert result.username_match is False


class TestValidateRepoHasFiles:
    """Tests for validate_repo_has_files function."""

    @pytest.mark.asyncio
    async def test_files_found(self):
        """Files matching patterns should pass."""
        from services.github_hands_on_verification_service import validate_repo_has_files

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification_service._search_code_with_retry"
            ) as mock_search:
                mock_search.return_value = {
                    "total_count": 1,
                    "items": [{"path": "Dockerfile", "name": "Dockerfile", "type": "file"}],
                }

                result = await validate_repo_has_files(
                    "https://github.com/testuser/repo",
                    "testuser",
                    ["Dockerfile"],
                    "Docker configuration",
                )
                assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_files_not_found(self):
        """Missing files should fail."""
        from services.github_hands_on_verification_service import validate_repo_has_files

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification_service._search_code_with_retry"
            ) as mock_search:
                mock_search.return_value = {"total_count": 0, "items": []}

                result = await validate_repo_has_files(
                    "https://github.com/testuser/repo",
                    "testuser",
                    ["Dockerfile"],
                    "Docker configuration",
                )
                assert result.is_valid is False
                assert "Could not find" in result.message

    @pytest.mark.asyncio
    async def test_files_search_rate_limited_falls_back(self):
        """Rate-limited search should fall back to contents API."""
        from services.github_hands_on_verification_service import validate_repo_has_files

        with patch(
            "services.github_hands_on_verification_service.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification_service._search_code_with_retry"
            ) as mock_search:
                mock_search.return_value = None  # 403 = rate limited

                with patch(
                    "services.github_hands_on_verification_service._validate_repo_files_via_contents"
                ) as mock_contents:
                    mock_contents.return_value = ValidationResult(
                        is_valid=True,
                        message="Found files",
                        username_match=True,
                        repo_exists=True,
                    )

                    result = await validate_repo_has_files(
                        "https://github.com/testuser/repo",
                        "testuser",
                        ["Dockerfile"],
                        "Docker configuration",
                    )
                    mock_contents.assert_called_once()


class TestValidateContainerImage:
    """Tests for validate_container_image function."""

    @pytest.mark.asyncio
    async def test_docker_hub_image_found(self):
        """Existing Docker Hub image should pass."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        with patch(
            "services.github_hands_on_verification_service._check_container_image_with_retry"
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True,
                message="Found public Docker Hub image",
                username_match=True,
                repo_exists=True,
            )

            result = await validate_container_image("testuser/myapp:latest", "testuser")
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_ghcr_image_found(self):
        """Existing GHCR image should pass."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        with patch(
            "services.github_hands_on_verification_service._check_container_image_with_retry"
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True,
                message="Found public GHCR image",
                username_match=True,
                repo_exists=True,
            )

            result = await validate_container_image(
                "ghcr.io/testuser/myapp:latest", "testuser"
            )
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_container_username_mismatch(self):
        """Username mismatch should fail."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        result = await validate_container_image("otheruser/myapp:latest", "testuser")
        assert result.is_valid is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_container_circuit_breaker(self):
        """Circuit breaker should return appropriate message."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        with patch(
            "services.github_hands_on_verification_service._check_container_image_with_retry"
        ) as mock:
            mock.side_effect = CircuitBreakerError(MagicMock())

            result = await validate_container_image("testuser/myapp", "testuser")
            assert result.is_valid is False
            assert "temporarily unavailable" in result.message

    @pytest.mark.asyncio
    async def test_ghcr_image_missing_username(self):
        """GHCR image without username should fail."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        result = await validate_container_image("ghcr.io/myapp", "testuser")
        assert result.is_valid is False
        assert "username/image" in result.message

    @pytest.mark.asyncio
    async def test_acr_image_accepted(self):
        """ACR image should be accepted without verification."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        with patch(
            "services.github_hands_on_verification_service._check_container_image_with_retry"
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True,
                message="ACR image reference accepted",
                username_match=True,
                repo_exists=True,
            )

            result = await validate_container_image(
                "myregistry.azurecr.io/myapp:v1", "testuser"
            )
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_url_prefix_stripped(self):
        """https:// prefix should be stripped."""
        from services.github_hands_on_verification_service import (
            validate_container_image,
        )

        with patch(
            "services.github_hands_on_verification_service._check_container_image_with_retry"
        ) as mock:
            mock.return_value = ValidationResult(
                is_valid=True,
                message="Found image",
                username_match=True,
                repo_exists=True,
            )

            result = await validate_container_image(
                "https://docker.io/testuser/myapp", "testuser"
            )
            assert result.is_valid is True


class TestValidateRepoFilesViaContents:
    """Tests for _validate_repo_files_via_contents fallback function."""

    @pytest.mark.asyncio
    async def test_files_found_in_root(self):
        """Files in root directory should be found."""
        from services.github_hands_on_verification_service import (
            _validate_repo_files_via_contents,
        )

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"path": "Dockerfile", "name": "Dockerfile", "type": "file"}
        ]
        mock_client.get.return_value = mock_response

        result = await _validate_repo_files_via_contents(
            mock_client,
            "testuser",
            "repo",
            ["Dockerfile"],
            "Docker configuration",
        )
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_files_not_found(self):
        """Missing files should fail."""
        from services.github_hands_on_verification_service import (
            _validate_repo_files_via_contents,
        )

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response

        result = await _validate_repo_files_via_contents(
            mock_client,
            "testuser",
            "repo",
            ["Dockerfile"],
            "Docker configuration",
        )
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_api_error_handled(self):
        """API errors should be handled gracefully."""
        from services.github_hands_on_verification_service import (
            _validate_repo_files_via_contents,
        )

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response

        result = await _validate_repo_files_via_contents(
            mock_client,
            "testuser",
            "repo",
            ["Dockerfile"],
            "Docker configuration",
        )
        assert result.is_valid is False


class TestCheckContainerImageWithRetry:
    """Tests for _check_container_image_with_retry internal function."""

    @pytest.mark.asyncio
    async def test_docker_hub_token_failure(self):
        """Docker Hub token failure should fail."""
        from services.github_hands_on_verification_service import (
            _check_container_image_with_retry,
        )

        with patch(
            "services.github_hands_on_verification_service._get_github_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            token_response = MagicMock()
            token_response.status_code = 401
            mock_client.get.return_value = token_response

            result = await _check_container_image_with_retry(
                "docker.io", "testuser/myapp", "latest"
            )
            assert result.is_valid is False
            assert "Could not authenticate" in result.message

    @pytest.mark.asyncio
    async def test_unsupported_registry(self):
        """Unsupported registry should fail."""
        from services.github_hands_on_verification_service import (
            _check_container_image_with_retry,
        )

        with patch(
            "services.github_hands_on_verification_service._get_github_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await _check_container_image_with_retry(
                "quay.io", "testuser/myapp", "latest"
            )
            assert result.is_valid is False
            assert "Unsupported container registry" in result.message
