"""Tests for users_routes.

Tests user profile endpoints with authenticated and public access.
"""

import uuid

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    UserFactory,
    create_async,
)


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestGetCurrentUser:
    """Tests for GET /api/user/me."""

    async def test_returns_current_user(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ):
        """Should return current authenticated user."""
        response = await authenticated_client.get("/api/user/me")

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert "first_name" in data

    async def test_requires_authentication(self, unauthenticated_client: AsyncClient):
        """Should return 401 without authentication."""
        response = await unauthenticated_client.get("/api/user/me")

        assert response.status_code == 401


class TestGetPublicProfile:
    """Tests for GET /api/user/profile/{username}."""

    async def test_returns_public_profile(self, client: AsyncClient, app: FastAPI):
        """Should return public profile by GitHub username."""
        username = unique_username("profile")
        # Create user within app's session to ensure it's visible to the endpoint
        async with app.state.session_maker() as session:
            await create_async(
                UserFactory,
                session,
                github_username=username,
                first_name="Test",
                avatar_url="https://example.com/avatar.png",
            )
            await session.commit()

        response = await client.get(f"/api/user/profile/{username}")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == username
        assert data["first_name"] == "Test"
        assert data["avatar_url"] == "https://example.com/avatar.png"

    async def test_returns_404_for_nonexistent_user(self, client: AsyncClient):
        """Should return 404 when user not found."""
        response = await client.get("/api/user/profile/nonexistent_user_xyz")

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    async def test_profile_includes_streak_data(
        self, client: AsyncClient, app: FastAPI
    ):
        """Should include streak information in profile."""
        username = unique_username("streak")
        async with app.state.session_maker() as session:
            await create_async(
                UserFactory,
                session,
                github_username=username,
            )
            await session.commit()

        response = await client.get(f"/api/user/profile/{username}")

        assert response.status_code == 200
        data = response.json()
        assert "streak" in data
        assert "current_streak" in data["streak"]
        assert "longest_streak" in data["streak"]
        assert "streak_alive" in data["streak"]

    async def test_profile_includes_heatmap_data(
        self, client: AsyncClient, app: FastAPI
    ):
        """Should include activity heatmap in profile."""
        username = unique_username("heatmap")
        async with app.state.session_maker() as session:
            await create_async(
                UserFactory,
                session,
                github_username=username,
            )
            await session.commit()

        response = await client.get(f"/api/user/profile/{username}")

        assert response.status_code == 200
        data = response.json()
        assert "activity_heatmap" in data
        assert "days" in data["activity_heatmap"]
        assert "total_activities" in data["activity_heatmap"]

    async def test_profile_includes_badges(self, client: AsyncClient, app: FastAPI):
        """Should include badges in profile."""
        username = unique_username("badge")
        async with app.state.session_maker() as session:
            await create_async(
                UserFactory,
                session,
                github_username=username,
            )
            await session.commit()

        response = await client.get(f"/api/user/profile/{username}")

        assert response.status_code == 200
        data = response.json()
        assert "badges" in data
        assert isinstance(data["badges"], list)

    async def test_case_insensitive_username_lookup(
        self, client: AsyncClient, app: FastAPI
    ):
        """Should find user regardless of username case."""
        username = unique_username("mixed")
        async with app.state.session_maker() as session:
            await create_async(
                UserFactory,
                session,
                github_username=username,  # Stored lowercase
            )
            await session.commit()

        # Request with uppercase - should still find the user
        response = await client.get(f"/api/user/profile/{username.upper()}")

        # GitHub usernames are case-insensitive, so this should work
        assert response.status_code == 200
        assert response.json()["username"] == username
