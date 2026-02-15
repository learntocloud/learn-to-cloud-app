"""Unit tests for health check routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routes.health_routes import health, ready


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_health_returns_200_healthy(self):
        """Health endpoint returns status=healthy."""
        result = await health()
        assert result.status == "healthy"
        assert result.service == "learn-to-cloud-api"


@pytest.mark.unit
class TestReadyEndpoint:
    """Tests for GET /ready."""

    async def test_ready_returns_200_when_healthy(self):
        """Ready returns 200 when init_done=True and DB is reachable."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True

        with patch(
            "routes.health_routes.check_db_connection",
            autospec=True,
        ) as mock_check:
            result = await ready(request)

        assert result.status == "ready"
        assert result.service == "learn-to-cloud-api"
        mock_check.assert_awaited_once_with(request.app.state.engine)

    async def test_ready_returns_503_when_init_error(self):
        """Ready returns 503 when init_error is set."""
        request = MagicMock()
        request.app.state.init_error = "content load failed"
        request.app.state.init_done = False

        with pytest.raises(HTTPException) as exc_info:
            await ready(request)

        assert exc_info.value.status_code == 503
        assert "Initialization failed" in exc_info.value.detail

    async def test_ready_returns_503_when_init_not_done(self):
        """Ready returns 503 when background init hasn't finished."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = False

        with pytest.raises(HTTPException) as exc_info:
            await ready(request)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Starting"

    async def test_ready_returns_503_when_db_check_fails(self):
        """Ready returns 503 when database connection check fails."""
        request = MagicMock()
        request.app.state.init_error = None
        request.app.state.init_done = True

        with patch(
            "routes.health_routes.check_db_connection",
            autospec=True,
            side_effect=ConnectionError("connection refused"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await ready(request)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Database unavailable"
