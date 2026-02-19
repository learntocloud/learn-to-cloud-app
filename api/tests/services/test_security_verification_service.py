"""Tests for security_verification_service (Phase 6).

Covers:
- URL validation variants (www, http, query strings, fragments)
- Username mismatch detection
- 404 / not-public repo handling
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.security_verification_service import validate_security_scanning

# ---------------------------------------------------------------------------
# URL validation and ownership
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSecurityScanningURLValidation:
    """URL parsing and ownership checks for validate_security_scanning."""

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self):
        result = await validate_security_scanning("not-a-url", "testuser")
        assert result.is_valid is False
        assert "Invalid GitHub repository URL" in result.message

    @pytest.mark.asyncio
    async def test_username_mismatch_returns_error(self):
        result = await validate_security_scanning(
            "https://github.com/otheruser/repo", "testuser"
        )
        assert result.is_valid is False
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_www_github_url_accepted(self):
        """www.github.com URLs should be parsed correctly."""
        with patch(
            "services.security_verification_service.fetch_repo_tree",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate_security_scanning(
                "https://www.github.com/testuser/my-repo", "testuser"
            )
            # Should reach the scanning step (not fail URL validation)
            assert "Invalid GitHub repository URL" not in result.message

    @pytest.mark.asyncio
    async def test_http_url_accepted(self):
        """http:// URLs should be parsed correctly."""
        with patch(
            "services.security_verification_service.fetch_repo_tree",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate_security_scanning(
                "http://github.com/testuser/my-repo", "testuser"
            )
            assert "Invalid GitHub repository URL" not in result.message

    @pytest.mark.asyncio
    async def test_url_with_query_string_accepted(self):
        """Query strings should be stripped, not included in repo name."""
        with patch(
            "services.security_verification_service.fetch_repo_tree",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate_security_scanning(
                "https://github.com/testuser/my-repo?tab=readme", "testuser"
            )
            assert "Invalid GitHub repository URL" not in result.message

    @pytest.mark.asyncio
    async def test_url_with_fragment_accepted(self):
        """Fragment identifiers should be stripped."""
        with patch(
            "services.security_verification_service.fetch_repo_tree",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate_security_scanning(
                "https://github.com/testuser/my-repo#readme", "testuser"
            )
            assert "Invalid GitHub repository URL" not in result.message


# ---------------------------------------------------------------------------
# 404 / not-public repo
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSecurityScanning404:
    """Repo-not-found handling."""

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self):
        mock_response = httpx.Response(
            status_code=404, request=httpx.Request("GET", "https://api.github.com")
        )
        with patch(
            "services.security_verification_service.fetch_repo_tree",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=mock_response.request, response=mock_response
            ),
        ):
            result = await validate_security_scanning(
                "https://github.com/testuser/nonexistent-repo", "testuser"
            )
            assert result.is_valid is False
            assert "not found" in result.message.lower()
            assert result.username_match is True
