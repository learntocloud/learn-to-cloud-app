"""API tests for activity endpoints.

Tests the /api/activity/* endpoints including streak data.
"""

from dataclasses import dataclass
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


@pytest.fixture
def test_app():
    """Provide the FastAPI app for testing."""
    return app


@dataclass
class MockUser:
    """Mock user data."""

    id: str = "user_123"
    email: str = "test@example.com"


@dataclass
class MockStreakData:
    """Mock streak data returned by get_streak_data."""

    current_streak: int = 5
    longest_streak: int = 10
    total_activity_days: int = 50
    last_activity_date: date | None = None
    streak_alive: bool = True

    def __post_init__(self):
        if self.last_activity_date is None:
            self.last_activity_date = date.today()


@pytest.mark.asyncio
class TestActivityStreakEndpoint:
    """Test GET /api/activity/streak endpoint."""

    async def test_get_streak_requires_auth(self, test_app):
        """GET /api/activity/streak returns 401 without auth."""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/activity/streak")

        # Without auth header, should get 401 or 403
        assert response.status_code in [401, 403]
