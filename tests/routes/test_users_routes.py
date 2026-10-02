"""User routes reuse resolved accounts and committed lifecycle operations."""

from unittest.mock import MagicMock, patch

import pytest

from learn_to_cloud.core.auth import AuthenticatedUser, AuthenticationRequired
from learn_to_cloud.routes.users_routes import delete_current_user

pytestmark = pytest.mark.unit


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
