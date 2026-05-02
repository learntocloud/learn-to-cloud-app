"""Tests for security_verification_service (Phase 6).

Covers:
- 404 / not-public repo handling
- Dependabot and CodeQL detection

URL validation and ownership checks are tested in the dispatcher tests.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from learn_to_cloud.services.verification.security_scanning import (
    validate_security_scanning,
)

_TEST_OWNER = "testuser"
_TEST_REPO = "my-repo"


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
            "learn_to_cloud.services.verification.security_scanning.fetch_repo_tree",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=mock_response.request, response=mock_response
            ),
        ):
            result = await validate_security_scanning(_TEST_OWNER, _TEST_REPO)
            assert result.is_valid is False
            assert "not found" in result.message.lower()
            assert result.username_match is True
