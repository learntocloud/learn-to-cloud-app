"""Tests for health_routes.

Tests health check endpoints for liveness and readiness probes.
"""

import pytest
from httpx import AsyncClient

from schemas import DetailedHealthResponse, HealthResponse


class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_returns_healthy_status(self, client: AsyncClient):
        """Should return healthy status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "learn-to-cloud-api"


class TestReadyEndpoint:
    """Tests for GET /ready."""

    async def test_returns_ready_when_initialized(self, client: AsyncClient, app):
        """Should return ready when app is initialized and DB is reachable."""
        # Ensure app state is set for readiness
        app.state.init_done = True
        app.state.init_error = None

        response = await client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["service"] == "learn-to-cloud-api"

    async def test_returns_503_when_not_initialized(self, client: AsyncClient, app):
        """Should return 503 when app is not initialized."""
        app.state.init_done = False

        response = await client.get("/ready")

        assert response.status_code == 503
        assert "Starting" in response.json()["detail"]

    async def test_returns_503_when_init_error(self, client: AsyncClient, app):
        """Should return 503 when initialization failed."""
        app.state.init_done = True
        app.state.init_error = "Database connection failed"

        response = await client.get("/ready")

        assert response.status_code == 503
        assert "Initialization failed" in response.json()["detail"]


class TestHealthDetailedEndpoint:
    """Tests for GET /health/detailed."""

    async def test_returns_detailed_health(self, client: AsyncClient, app):
        """Should return detailed health with component status."""
        # Make sure init state is clean
        app.state.init_done = True
        app.state.init_error = None

        response = await client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "service" in data
        assert data["service"] == "learn-to-cloud-api"

    async def test_database_status_is_boolean(self, client: AsyncClient, app):
        """Should return boolean database status."""
        app.state.init_done = True
        app.state.init_error = None

        response = await client.get("/health/detailed")

        data = response.json()
        assert isinstance(data["database"], bool)
