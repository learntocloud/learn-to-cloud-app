"""User routes reuse resolved accounts and committed lifecycle operations."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from learn_to_cloud_shared.models import User
from starlette.datastructures import State

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    AuthenticationRequired,
    RequestAuthentication,
)
from learn_to_cloud.routes.users_routes import delete_current_user, get_current_user

pytestmark = pytest.mark.unit


async def test_current_user_reuses_loaded_account():
    user = User(
        id=1,
        github_username="testuser",
        display_name="Test User",
        avatar_url=None,
        is_admin=False,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    identity = AuthenticatedUser(1, "testuser")
    request = MagicMock()
    request.state = State({"authentication": RequestAuthentication(identity, user)})
    result = await get_current_user(request, identity)
    assert result.id == 1
    assert result.github_username == "testuser"
    assert result.display_name == "Test User"
    assert set(result.model_dump()) == {
        "id",
        "github_username",
        "display_name",
        "avatar_url",
        "is_admin",
        "created_at",
    }


async def test_delete_uses_committed_lifecycle():
    request = MagicMock()
    with patch(
        "learn_to_cloud.routes.users_routes.mutate_account", autospec=True
    ) as mutate:
        assert (
            await delete_current_user(request, AuthenticatedUser(42, "testuser"))
            is None
        )
    mutate.assert_awaited_once_with(request, 42, delete_account=True)


async def test_deletion_recheck_failure_stays_unauthorized():
    with (
        patch(
            "learn_to_cloud.routes.users_routes.mutate_account",
            autospec=True,
            side_effect=AuthenticationRequired(),
        ),
        pytest.raises(AuthenticationRequired),
    ):
        await delete_current_user(MagicMock(), AuthenticatedUser(42, "testuser"))
