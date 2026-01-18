"""API tests for user endpoints.

Tests the /api/user/* endpoints including /me and /profile.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from models import ActivityType, SubmissionType


@pytest.fixture
def test_app():
    """Provide the FastAPI app for testing."""
    return app


@dataclass
class MockUser:
    """Mock user data."""

    id: str = "user_123"
    email: str = "test@example.com"
    first_name: str = "Test"
    last_name: str = "User"
    avatar_url: str | None = None
    github_username: str | None = "testuser"
    is_admin: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.updated_at is None:
            self.updated_at = datetime.now(UTC)


@dataclass
class MockStreak:
    """Mock streak data."""

    current_streak: int = 5
    longest_streak: int = 10
    total_activity_days: int = 50
    last_activity_date: date | None = None
    streak_alive: bool = True

    def __post_init__(self):
        if self.last_activity_date is None:
            self.last_activity_date = date.today()


@dataclass
class MockActivityHeatmapDay:
    """Mock heatmap day data."""

    date: date
    count: int
    activity_types: list = field(default_factory=list)


@dataclass
class MockActivityHeatmap:
    """Mock activity heatmap data."""

    days: list
    start_date: date
    end_date: date
    total_activities: int


@dataclass
class MockPublicProfile:
    """Mock public profile data."""

    id: str
    username: str
    github_username: str
    first_name: str | None
    avatar_url: str | None
    current_phase: int
    phases_completed: int
    member_since: datetime
    streak: MockStreak
    activity_heatmap: MockActivityHeatmap
    submissions: list
    badges: list


@pytest.mark.asyncio
class TestUserMeEndpoint:
    """Test GET /api/user/me endpoint."""

    async def test_get_me_requires_auth(self, test_app):
        """GET /api/user/me returns 401 without auth."""
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/api/user/me")

        # Without auth header, should get 401 or 403
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestPublicProfileEndpoint:
    """Test GET /api/user/profile/{username} endpoint."""

    async def test_get_profile_not_found(self, test_app):
        """GET /api/user/profile/{username} returns 404 for unknown user."""
        with patch(
            "routes.users_routes.get_public_profile", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/api/user/profile/nonexistent_user")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_profile_returns_data(self, test_app):
        """GET /api/user/profile/{username} returns profile data."""
        today = date.today()
        mock_profile = MockPublicProfile(
            id="user_123",
            username="testuser",
            github_username="testuser",
            first_name="Test",
            avatar_url="https://avatars.githubusercontent.com/u/123",
            current_phase=2,
            phases_completed=1,
            member_since=datetime.now(UTC),
            streak=MockStreak(
                current_streak=5, longest_streak=10, last_activity_date=today
            ),
            activity_heatmap=MockActivityHeatmap(
                days=[
                    MockActivityHeatmapDay(
                        date=today, count=3, activity_types=[ActivityType.STEP_COMPLETE]
                    )
                ],
                start_date=today,
                end_date=today,
                total_activities=3,
            ),
            submissions=[],
            badges=[],
        )

        with patch(
            "routes.users_routes.get_public_profile", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_profile

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/api/user/profile/testuser")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["streak"]["current_streak"] == 5
        assert data["streak"]["longest_streak"] == 10
        assert "activity_heatmap" in data
        assert "submissions" in data
        assert "badges" in data

    async def test_get_profile_with_badges_and_submissions(self, test_app):
        """GET /api/user/profile/{username} includes badges and submissions."""
        today = date.today()

        @dataclass
        class MockBadge:
            id: str = "badge-1"
            name: str = "First Steps"
            description: str = "Complete your first step"
            icon: str = "star"
            phase_id: int = 1
            earned_at: datetime | None = None

            def __post_init__(self):
                if self.earned_at is None:
                    self.earned_at = datetime.now(UTC)

        @dataclass
        class MockSubmission:
            requirement_id: str = "phase1-req1"
            submission_type: SubmissionType = SubmissionType.REPO_URL
            phase_id: int = 1
            submitted_value: str = "https://github.com/user/repo"
            name: str = "Deploy to Cloud"
            validated_at: datetime | None = None

            def __post_init__(self):
                if self.validated_at is None:
                    self.validated_at = datetime.now(UTC)

        mock_profile = MockPublicProfile(
            id="user_123",
            username="achiever",
            github_username="achiever",
            first_name="Achiever",
            avatar_url=None,
            current_phase=2,
            phases_completed=1,
            member_since=datetime.now(UTC),
            streak=MockStreak(),
            activity_heatmap=MockActivityHeatmap(
                days=[],
                start_date=today,
                end_date=today,
                total_activities=0,
            ),
            submissions=[MockSubmission()],
            badges=[MockBadge()],
        )

        with patch(
            "routes.users_routes.get_public_profile", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_profile

            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                response = await client.get("/api/user/profile/achiever")

        assert response.status_code == 200
        data = response.json()
        assert len(data["submissions"]) == 1
        assert data["submissions"][0]["phase_id"] == 1
        assert len(data["badges"]) == 1
        assert data["badges"][0]["name"] == "First Steps"
