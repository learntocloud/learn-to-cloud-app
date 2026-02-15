"""Unit tests for user routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routes.users_routes import (
    delete_current_user,
    get_badge_catalog_endpoint,
    get_current_user,
    get_public_profile_endpoint,
)
from schemas import (
    BadgeCatalogItem,
    BadgeCatalogResponse,
    PublicProfileData,
    UserResponse,
)
from services.users_service import UserNotFoundError


def _fake_user_response() -> UserResponse:
    """Build a minimal UserResponse for testing."""
    return UserResponse(
        id=1,
        first_name="Test",
        last_name="User",
        avatar_url="https://example.com/avatar.png",
        github_username="testuser",
        is_admin=False,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


@pytest.mark.unit
class TestGetCurrentUser:
    """Tests for GET /api/user/me."""

    async def test_returns_user_response(self):
        """Returns UserResponse from get_or_create_user."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        user = _fake_user_response()

        with patch(
            "routes.users_routes.get_or_create_user",
            autospec=True,
            return_value=user,
        ) as mock_service:
            result = await get_current_user(mock_request, user_id=1, db=mock_db)

        mock_service.assert_awaited_once_with(mock_db, 1)
        assert result.id == 1
        assert result.github_username == "testuser"


@pytest.mark.unit
class TestGetPublicProfile:
    """Tests for GET /api/user/profile/{username}."""

    async def test_returns_profile(self):
        """Returns PublicProfileData when user exists."""
        mock_db = AsyncMock()
        mock_request = MagicMock()
        profile = PublicProfileData(
            username="testuser",
            first_name="Test",
            avatar_url=None,
            current_phase=1,
            phases_completed=0,
            total_phases=7,
            submissions=[],
            badges=[],
        )

        with patch(
            "routes.users_routes.get_public_profile",
            autospec=True,
            return_value=profile,
        ) as mock_service:
            result = await get_public_profile_endpoint(
                mock_request, username="testuser", db=mock_db, user_id=None
            )

        mock_service.assert_awaited_once_with(mock_db, "testuser", None)
        assert result.username == "testuser"

    async def test_returns_404_when_not_found(self):
        """Returns 404 when profile is None."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.users_routes.get_public_profile",
            autospec=True,
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_public_profile_endpoint(
                    mock_request, username="nobody", db=mock_db, user_id=None
                )

        assert exc_info.value.status_code == 404


@pytest.mark.unit
class TestGetBadgeCatalog:
    """Tests for GET /api/user/badges/catalog."""

    async def test_returns_badge_catalog(self):
        """Returns BadgeCatalogResponse from get_badge_catalog."""
        mock_request = MagicMock()
        items = [
            BadgeCatalogItem(
                id="phase-1",
                name="Phase 1",
                description="Complete phase 1",
                icon="🏅",
                num="1",
                how_to="Complete all steps in phase 1",
            ),
        ]

        with patch(
            "routes.users_routes.get_badge_catalog",
            autospec=True,
            return_value=(items, 1),
        ) as mock_service:
            result = await get_badge_catalog_endpoint(mock_request)

        mock_service.assert_called_once()
        assert isinstance(result, BadgeCatalogResponse)
        assert result.total_badges == 1
        assert len(result.phase_badges) == 1


@pytest.mark.unit
class TestDeleteCurrentUser:
    """Tests for DELETE /api/user/me."""

    async def test_delete_returns_none(self):
        """Successful deletion returns None (204 via route decorator)."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.users_routes.delete_user_account",
            autospec=True,
        ) as mock_service:
            result = await delete_current_user(mock_request, user_id=42, db=mock_db)

        assert result is None
        mock_service.assert_awaited_once_with(mock_db, 42)
        mock_request.session.clear.assert_called_once()

    async def test_delete_user_not_found_raises_404(self):
        """UserNotFoundError from service becomes 404."""
        mock_db = AsyncMock()
        mock_request = MagicMock()

        with patch(
            "routes.users_routes.delete_user_account",
            autospec=True,
            side_effect=UserNotFoundError(42),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_current_user(mock_request, user_id=42, db=mock_db)

        assert exc_info.value.status_code == 404
