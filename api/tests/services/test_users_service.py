"""Tests for users_service module.

Tests cover:
- normalize_github_username lowercasing and edge cases
- normalize_display_name preservation and malformed provider data
- get_or_create_user_from_github upsert and username conflict
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from learn_to_cloud_shared.schemas import UserResponse
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.services.users_service import (
    get_or_create_user_from_github,
    normalize_display_name,
    normalize_github_username,
)

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
