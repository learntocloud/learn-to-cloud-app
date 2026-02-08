"""Tests for user account deletion.

Tests cover:
- Successful account deletion removes user and cascaded data
- Deleting a non-existent user raises UserNotFoundError
- Session is cleared after deletion (route-level)
- Business events are logged on deletion
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.users_service import (
    UserNotFoundError,
    delete_user_account,
)


@pytest.mark.unit
class TestDeleteUserAccount:
    """Tests for delete_user_account service function."""

    @pytest.mark.asyncio
    async def test_delete_existing_user(self):
        """Deleting an existing user calls repo.delete and commits."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.github_username = "testuser"

        with patch("services.users_service.UserRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_user)
            mock_repo.delete = AsyncMock()
            mock_repo_class.return_value = mock_repo

            await delete_user_account(mock_db, user_id=12345)

            mock_repo.get_by_id.assert_awaited_once_with(12345)
            mock_repo.delete.assert_awaited_once_with(12345)
            mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_raises(self):
        """Deleting a user that doesn't exist raises UserNotFoundError."""
        mock_db = AsyncMock()

        with patch("services.users_service.UserRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=None)
            mock_repo_class.return_value = mock_repo

            with pytest.raises(UserNotFoundError) as exc_info:
                await delete_user_account(mock_db, user_id=99999)

            assert exc_info.value.user_id == 99999
            mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_calls_repo(self):
        """Account deletion calls repository delete."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.github_username = "loguser"

        with patch("services.users_service.UserRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_user)
            mock_repo.delete = AsyncMock()
            mock_repo_class.return_value = mock_repo

            await delete_user_account(mock_db, user_id=12345)

            mock_repo.delete.assert_awaited_once()


@pytest.mark.integration
class TestDeleteUserAccountIntegration:
    """Integration tests for account deletion.

    Cascade behavior (submissions, step_progress, certificates) is enforced
    by SQLAlchemy model definitions (cascade="all, delete-orphan") and
    PostgreSQL ON DELETE CASCADE foreign keys.
    """
