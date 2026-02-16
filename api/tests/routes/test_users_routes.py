"""Unit tests for user routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routes.users_routes import (
    delete_current_user,
    get_current_user,
)
from schemas import UserResponse
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
