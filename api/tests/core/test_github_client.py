"""Unit tests for core.github_client module.

Tests cover:
- get_github_client creates client on first call
- get_github_client returns same instance on subsequent calls
- get_github_client recreates client after close
- close_github_client closes and clears the singleton
- close_github_client is no-op when already None
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.github_client import close_github_client, get_github_client


@pytest.fixture(autouse=True)
async def _reset_github_client():
    """Reset the module-level singleton between tests."""
    import core.github_client as mod

    yield
    if mod._github_http_client is not None and not mod._github_http_client.is_closed:
        await mod._github_http_client.aclose()
    mod._github_http_client = None


@pytest.mark.unit
class TestGetGitHubClient:
    @pytest.mark.asyncio
    async def test_creates_client_on_first_call(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            client = await get_github_client()
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed

    @pytest.mark.asyncio
    async def test_returns_same_instance(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            c1 = await get_github_client()
            c2 = await get_github_client()
        assert c1 is c2

    @pytest.mark.asyncio
    async def test_recreates_after_close(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            c1 = await get_github_client()
            await close_github_client()
            c2 = await get_github_client()
        assert c2 is not c1
        assert not c2.is_closed


@pytest.mark.unit
class TestCloseGitHubClient:
    @pytest.mark.asyncio
    async def test_closes_client(self):
        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            client = await get_github_client()
        await close_github_client()
        assert client.is_closed

    @pytest.mark.asyncio
    async def test_noop_when_none(self):
        await close_github_client()

    @pytest.mark.asyncio
    async def test_sets_global_to_none(self):
        import core.github_client as mod

        mock_settings = MagicMock()
        mock_settings.http_timeout = 10.0
        with patch(
            "core.github_client.get_settings",
            autospec=True,
            return_value=mock_settings,
        ):
            await get_github_client()
        await close_github_client()
        assert mod._github_http_client is None
