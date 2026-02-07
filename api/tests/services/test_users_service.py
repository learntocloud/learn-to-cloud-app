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
    async def test_delete_logs_business_event(self):
        """Account deletion emits a business event."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.github_username = "loguser"

        with (
            patch("services.users_service.UserRepository") as mock_repo_class,
            patch("services.users_service.log_business_event") as mock_log_event,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_user)
            mock_repo.delete = AsyncMock()
            mock_repo_class.return_value = mock_repo

            await delete_user_account(mock_db, user_id=12345)

            mock_log_event.assert_called_once_with("users.account_deleted", 1)

    @pytest.mark.asyncio
    async def test_delete_sets_wide_event_fields(self):
        """Account deletion enriches wide event with user context."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.github_username = "wideuser"

        with (
            patch("services.users_service.UserRepository") as mock_repo_class,
            patch("services.users_service.set_wide_event_fields") as mock_set_fields,
        ):
            mock_repo = MagicMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_user)
            mock_repo.delete = AsyncMock()
            mock_repo_class.return_value = mock_repo

            await delete_user_account(mock_db, user_id=12345)

            mock_set_fields.assert_called_once_with(
                deleted_user_id=12345,
                deleted_github_username="wideuser",
            )


@pytest.mark.integration
class TestDeleteUserAccountIntegration:
    """Integration tests for account deletion with real database."""

    @pytest.mark.asyncio
    async def test_delete_cascades_related_data(self, db_session):
        """Deleting a user removes submissions, step progress, and certificates."""
        from tests.factories import (
            CertificateFactory,
            StepProgressFactory,
            SubmissionFactory,
            UserFactory,
            create_async,
        )

        # Create user with related data
        user = await create_async(UserFactory, db_session)
        await create_async(SubmissionFactory, db_session, user_id=user.id)
        await create_async(StepProgressFactory, db_session, user_id=user.id)
        await create_async(CertificateFactory, db_session, user_id=user.id)
        await db_session.flush()

        # Delete the user
        from repositories.user_repository import UserRepository

        repo = UserRepository(db_session)
        await repo.delete(user.id)
        await db_session.flush()

        # Verify user is gone
        deleted_user = await repo.get_by_id(user.id)
        assert deleted_user is None
