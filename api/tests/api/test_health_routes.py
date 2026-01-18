"""API tests for health check endpoints.

Tests the /health, /health/detailed, and /ready endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def test_app():
    """Provide the FastAPI app for testing."""
    return app


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Test health check API endpoints."""

    async def test_health_returns_200(self, test_app):
        """GET /health returns 200 with healthy status."""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "learn-to-cloud-api"

    async def test_health_detailed_returns_component_status(self, test_app):
        """GET /health/detailed returns component statuses."""
        mock_result = {
            "database": True,
            "azure_auth": None,  # Not using Azure auth
            "pool": None,  # Using NullPool
        }

        with patch(
            "routes.health_routes.comprehensive_health_check", return_value=mock_result
        ):
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] is True

    async def test_health_detailed_unhealthy_database(self, test_app):
        """GET /health/detailed returns unhealthy when database is down."""
        mock_result = {
            "database": False,
            "azure_auth": None,
            "pool": None,
        }

        with patch(
            "routes.health_routes.comprehensive_health_check", return_value=mock_result
        ):
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] is False

    async def test_ready_returns_503_during_startup(self, test_app):
        """GET /ready returns 503 when initialization not complete."""
        # Simulate app not yet initialized
        test_app.state.init_done = False
        test_app.state.init_error = None

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/ready")

        assert response.status_code == 503
        assert "Starting" in response.json()["detail"]

    async def test_ready_returns_503_on_init_error(self, test_app):
        """GET /ready returns 503 when initialization failed."""
        test_app.state.init_done = False
        test_app.state.init_error = "Database migration failed"

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/ready")

        assert response.status_code == 503
        assert "Initialization failed" in response.json()["detail"]

    async def test_ready_returns_200_when_healthy(self, test_app):
        """GET /ready returns 200 when fully initialized."""
        test_app.state.init_done = True
        test_app.state.init_error = None

        with patch("routes.health_routes.check_db_connection", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"

    async def test_ready_returns_503_on_db_error(self, test_app):
        """GET /ready returns 503 when database is unavailable."""
        test_app.state.init_done = True
        test_app.state.init_error = None

        with patch(
            "routes.health_routes.check_db_connection",
            side_effect=Exception("Connection refused"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/ready")

        assert response.status_code == 503
        assert "Database unavailable" in response.json()["detail"]
