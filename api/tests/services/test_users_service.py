"""Tests for users_service module.

Tests cover:
- normalize_github_username lowercasing and edge cases
- parse_display_name splitting logic
- get_user_by_id cache hit/miss and not found
- get_or_create_user_from_github upsert and username conflict
- delete_user_account success and not found
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_or_create_user_from_github,
    get_user_by_id,
    normalize_github_username,
    parse_display_name,
)


@pytest.fixture(autouse=True)
def _clear_user_cache():
    from core.cache import _user_cache

    _user_cache.clear()
    yield
    _user_cache.clear()


@pytest.mark.unit
class TestDeleteUserAccount:
    """Tests for delete_user_account service function."""

    @pytest.mark.asyncio
    async def test_delete_existing_user(self):
        """Deleting an existing user calls repo.delete (caller commits)."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.github_username = "testuser"

        with patch(
            "services.users_service.UserRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_user)
            mock_repo.delete = AsyncMock()

            await delete_user_account(mock_db, user_id=12345)

            mock_repo.get_by_id.assert_awaited_once_with(12345)
            mock_repo.delete.assert_awaited_once_with(12345)
            # Service does NOT commit — caller (route) owns the transaction
            mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_raises(self):
        """Deleting a user that doesn't exist raises UserNotFoundError."""
        mock_db = AsyncMock()

        with patch(
            "services.users_service.UserRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_by_id = AsyncMock(return_value=None)

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

        with patch(
            "services.users_service.UserRepository", autospec=True
        ) as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.get_by_id = AsyncMock(return_value=mock_user)
            mock_repo.delete = AsyncMock()

            await delete_user_account(mock_db, user_id=12345)

            mock_repo.delete.assert_awaited_once()


@pytest.mark.integration
class TestDeleteUserAccountIntegration:
    """Integration tests for account deletion.

    Cascade behavior (submissions, step_progress) is enforced
    by SQLAlchemy model definitions (cascade="all, delete-orphan") and
    PostgreSQL ON DELETE CASCADE foreign keys.
    """


# ---------------------------------------------------------------------------
# normalize_github_username
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeGithubUsername:
    def test_lowercases(self):
        assert normalize_github_username("TestUser") == "testuser"

    def test_none_returns_none(self):
        assert normalize_github_username(None) is None

    def test_empty_returns_none(self):
        assert normalize_github_username("") is None

    def test_already_lowercase(self):
        assert normalize_github_username("testuser") == "testuser"


# ---------------------------------------------------------------------------
# parse_display_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseDisplayName:
    def test_full_name(self):
        assert parse_display_name("John Doe") == ("John", "Doe")

    def test_single_name(self):
        assert parse_display_name("John") == ("John", "")

    def test_multi_part_last_name(self):
        assert parse_display_name("John Van Doe") == ("John", "Van Doe")

    def test_none(self):
        assert parse_display_name(None) == ("", "")

    def test_empty_string(self):
        assert parse_display_name("") == ("", "")


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetUserById:
    @pytest.mark.asyncio
    async def test_returns_cached_user(self):
        from core.cache import set_cached_user

        mock_user = MagicMock()
        set_cached_user(1, mock_user)
        result = await get_user_by_id(AsyncMock(), user_id=1)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self):
        mock_user = MagicMock()
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_user)
            result = await get_user_by_id(AsyncMock(), user_id=1)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)
            result = await get_user_by_id(AsyncMock(), user_id=999)
        assert result is None


# ---------------------------------------------------------------------------
# get_or_create_user_from_github
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetOrCreateUserFromGithub:
    @pytest.mark.asyncio
    async def test_new_user(self):
        mock_user = MagicMock()
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_github_username = AsyncMock(return_value=None)
            repo.upsert = AsyncMock(return_value=mock_user)
            result = await get_or_create_user_from_github(
                AsyncMock(),
                github_id=123,
                first_name="Test",
                last_name="User",
                avatar_url="https://example.com/avatar.png",
                github_username="TestUser",
            )
        assert result is mock_user
        repo.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_username_conflict_clears_old_owner(self):
        old_owner = MagicMock()
        old_owner.id = 456
        new_user = MagicMock()
        with patch("services.users_service.UserRepository", autospec=True) as MockRepo:
            repo = MockRepo.return_value
            repo.get_by_github_username = AsyncMock(return_value=old_owner)
            repo.clear_github_username = AsyncMock()
            repo.upsert = AsyncMock(return_value=new_user)
            await get_or_create_user_from_github(
                AsyncMock(),
                github_id=123,
                first_name="New",
                last_name="User",
                avatar_url=None,
                github_username="sharedname",
            )
        repo.clear_github_username.assert_awaited_once_with(456)
