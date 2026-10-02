"""Unit tests for core.github_client lifecycle behavior."""

from unittest.mock import MagicMock, patch

import pytest

import learn_to_cloud.core.github_client as mod
from learn_to_cloud.core.github_client import (
    close_github_client,
    get_github_client,
)


@pytest.fixture(autouse=True)
async def _reset_github_client():
    """Reset the module-level singleton between tests."""

    yield
    await mod._pool.close()


@pytest.mark.unit
class TestGetGitHubClient:
    @pytest.mark.asyncio
    async def test_recreates_after_close(self):
        mock_settings = MagicMock()
        mock_settings.http.external_api_timeout = 10.0
        with patch(
            "learn_to_cloud.core.github_client.get_worker_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            c1 = await get_github_client()
            await close_github_client()
            c2 = await get_github_client()
        assert c2 is not c1
        assert not c2.is_closed
