"""Tests for users_service module.

Tests cover:
- normalize_github_username lowercasing and edge cases
- normalize_display_name preservation and malformed provider data
- get_user_by_id cache hit/miss and not found
- get_or_create_user_from_github upsert and username conflict
- delete_user_account success and not found
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from learn_to_cloud_shared.schemas import UserResponse
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.services.users_service import (
    UserNotFoundError,
    delete_user_account,
    get_or_create_user_from_github,
    get_user_by_id,
    normalize_display_name,
    normalize_github_username,
)


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
            "learn_to_cloud.services.users_service.UserRepository", autospec=True
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
            "learn_to_cloud.services.users_service.UserRepository", autospec=True
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
            "learn_to_cloud.services.users_service.UserRepository", autospec=True
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
# normalize_display_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeDisplayName:
    @pytest.mark.parametrize(
        "name",
        [
            "John",
            "John Van Doe",
            "李",
            "أمل",
            "é e\u0301",
            "🛰️",
            "  A  B\t ",
            "名" * 600,
        ],
    )
    def test_preserves_exact_string(self, name, caplog):
        assert normalize_display_name(name) is name
        assert not caplog.records

    @pytest.mark.parametrize("name", [None, "", " ", "\t\n", "\u2003\u00a0"])
    def test_absent_or_blank(self, name, caplog):
        assert normalize_display_name(name) is None
        assert not caplog.records

    @pytest.mark.parametrize(
        "name",
        [False, 42, [], {}, {"name": "sentinel"}, "sentinel\x00", "\ud800", "\udfff"],
    )
    def test_malformed_warns_without_values(self, name, caplog):
        assert normalize_display_name(name) is None
        (record,) = caplog.records
        assert record.getMessage() == "auth.callback.display_name_ignored"
        assert record.args == ()
        assert record.exc_info is None


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetUserById:
    @pytest.mark.asyncio
    async def test_returns_user_from_db(self):
        mock_user = MagicMock()
        with patch(
            "learn_to_cloud.services.users_service.UserRepository", autospec=True
        ) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_user)
            result = await get_user_by_id(AsyncMock(), user_id=1)
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        with patch(
            "learn_to_cloud.services.users_service.UserRepository", autospec=True
        ) as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=None)
            result = await get_user_by_id(AsyncMock(), user_id=999)
        assert result is None


# ---------------------------------------------------------------------------
# get_or_create_user_from_github
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetOrCreateUserFromGithub:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("  Test  User 李  ", "  Test  User 李  "),
            (None, None),
            (" \t", None),
            (42, None),
        ],
    )
    async def test_new_user(self, name, expected):
        mock_user = MagicMock()
        db = AsyncMock()
        with patch(
            "learn_to_cloud.services.users_service.UserRepository", autospec=True
        ) as MockRepo:
            repo = MockRepo.return_value
            repo.upsert = AsyncMock(return_value=mock_user)
            result = await get_or_create_user_from_github(
                db,
                github_id=123,
                display_name=name,
                avatar_url="https://example.com/avatar.png",
                github_username="TestUser",
            )
        assert result is mock_user
        repo.upsert.assert_awaited_once_with(
            123,
            display_name=expected,
            avatar_url="https://example.com/avatar.png",
            github_username="testuser",
        )
        db.commit.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, None),
        ("", None),
        (" \t\n\u2003\u00a0", None),
        ("Prince", "Prince"),
        ("A", "A"),
        ("John Van Doe", "John Van Doe"),
        ("李", "李"),
        ("أمل", "أمل"),
        ("é e\u0301", "é e\u0301"),
        ("🛰️", "🛰️"),
        ("  Outer  Inner\t ", "  Outer  Inner\t "),
        ("名" * 600, "名" * 600),
        ('<script>alert("x")</script>', '<script>alert("x")</script>'),
        ({"name": "Malformed sentinel"}, None),
        (False, None),
        ("Malformed sentinel\x00", None),
        ("Malformed sentinel\ud800", None),
        ("Malformed sentinel\udfff", None),
    ],
)
async def test_provider_name_round_trip_and_removal(
    db_session: AsyncSession, name, expected
):
    user = await get_or_create_user_from_github(
        db_session,
        github_id=73142,
        github_username="TestUser",
        display_name="Previously populated",
        avatar_url="previous-avatar",
    )
    created_at = user.created_at
    updated = await get_or_create_user_from_github(
        db_session,
        github_id=73142,
        github_username="TestUser",
        display_name=name,
        avatar_url=None,
    )
    assert updated is user
    await db_session.refresh(updated)
    assert updated.display_name == expected
    assert updated.created_at == created_at
    assert updated.github_username == "testuser"
    assert updated.avatar_url is None
    assert (
        UserResponse.model_validate(updated).model_dump(mode="json")["display_name"]
        == expected
    )
