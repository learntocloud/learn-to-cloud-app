"""Unit tests for internal operational routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from learn_to_cloud.routes.internal_routes import smoke_verification


def _request_with_token(configured: str) -> MagicMock:
    """Build a mock request whose app carries the given configured token."""
    request = MagicMock()
    request.app.state.settings.smoke_test.token = configured
    request.app.state.session_maker = MagicMock()
    return request


@pytest.mark.unit
class TestSmokeVerificationEndpoint:
    """Tests for POST /internal/smoke/verification."""

    async def test_returns_404_when_token_not_configured(self):
        """The endpoint is disabled (404) when no token is configured."""
        request = _request_with_token("")

        with pytest.raises(HTTPException) as exc_info:
            await smoke_verification(request, x_smoke_test_token="anything")

        assert exc_info.value.status_code == 404

    async def test_returns_401_when_header_missing(self):
        """A missing token header is rejected with 401."""
        request = _request_with_token("expected-secret")

        with pytest.raises(HTTPException) as exc_info:
            await smoke_verification(request, x_smoke_test_token=None)

        assert exc_info.value.status_code == 401

    async def test_returns_401_when_header_mismatch(self):
        """A wrong token header is rejected with 401."""
        request = _request_with_token("expected-secret")

        with pytest.raises(HTTPException) as exc_info:
            await smoke_verification(request, x_smoke_test_token="wrong-secret")

        assert exc_info.value.status_code == 401

    async def test_returns_200_when_token_matches_and_check_passes(self):
        """A matching token runs the read-only check and returns ok."""
        request = _request_with_token("expected-secret")

        with patch(
            "learn_to_cloud.routes.internal_routes.run_submit_smoke_check",
            new_callable=AsyncMock,
            return_value={"requirement_slug": "phase0-req"},
        ) as mock_check:
            result = await smoke_verification(
                request, x_smoke_test_token="expected-secret"
            )

        assert result == {"status": "ok", "requirement_slug": "phase0-req"}
        mock_check.assert_awaited_once_with(request.app.state.session_maker)

    async def test_returns_503_when_check_raises(self):
        """A failing read path surfaces as 503 so CI fails the deploy."""
        request = _request_with_token("expected-secret")

        with patch(
            "learn_to_cloud.routes.internal_routes.run_submit_smoke_check",
            new_callable=AsyncMock,
            side_effect=RuntimeError("schema mismatch"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await smoke_verification(request, x_smoke_test_token="expected-secret")

        assert exc_info.value.status_code == 503
        assert "RuntimeError" in exc_info.value.detail
