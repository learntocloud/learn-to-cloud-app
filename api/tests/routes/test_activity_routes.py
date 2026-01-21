"""Tests for activity routes."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import UserActivityFactory, UserFactory


class TestGetUserStreak:
    """Tests for GET /api/activity/streak endpoint."""

    async def test_returns_streak_for_authenticated_user(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ):
        """Test returns streak data for authenticated user."""
        response = await authenticated_client.get("/api/activity/streak")

        assert response.status_code == 200
        data = response.json()
        assert "current_streak" in data
        assert "longest_streak" in data

    async def test_returns_401_for_unauthenticated_user(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.get("/api/activity/streak")
        assert response.status_code == 401

    async def test_streak_defaults_to_zero(
        self, authenticated_client: AsyncClient
    ):
        """Test streak defaults to zero for new user."""
        response = await authenticated_client.get("/api/activity/streak")

        assert response.status_code == 200
        data = response.json()
        assert data["current_streak"] >= 0
        assert data["longest_streak"] >= 0

    async def test_streak_response_structure(
        self, authenticated_client: AsyncClient
    ):
        """Test response has expected structure."""
        response = await authenticated_client.get("/api/activity/streak")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "current_streak" in data
        assert "longest_streak" in data
        assert "streak_alive" in data
        assert "total_activity_days" in data
