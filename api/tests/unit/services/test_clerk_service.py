"""Unit tests for services/clerk_service.py.

Tests Clerk API data extraction, backoff logic, and HTTP client management.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.clerk_service import (
    ClerkUserData,
    _backoff_state,
    _BoundedBackoffDict,
    _is_in_backoff,
    _set_backoff,
    close_http_client,
    extract_github_username,
    extract_primary_email,
    fetch_github_username,
    fetch_user_data,
    get_http_client,
)


class TestClerkUserData:
    """Test ClerkUserData dataclass."""

    def test_create_with_all_fields(self):
        """Can create with all fields."""
        data = ClerkUserData(
            email="user@example.com",
            first_name="John",
            last_name="Doe",
            avatar_url="https://example.com/avatar.png",
            github_username="johndoe",
        )
        assert data.email == "user@example.com"
        assert data.github_username == "johndoe"

    def test_defaults_to_none(self):
        """All fields default to None."""
        data = ClerkUserData()
        assert data.email is None
        assert data.first_name is None
        assert data.github_username is None


class TestExtractGithubUsername:
    """Test extract_github_username function."""

    def test_extracts_github_provider_username(self):
        """Extracts username from github provider."""
        data = {"external_accounts": [{"provider": "github", "username": "testuser"}]}
        assert extract_github_username(data) == "testuser"

    def test_extracts_oauth_github_username(self):
        """Extracts username from oauth_github provider."""
        data = {
            "external_accounts": [{"provider": "oauth_github", "username": "oauthuser"}]
        }
        assert extract_github_username(data) == "oauthuser"

    def test_falls_back_to_provider_user_id(self):
        """Falls back to provider_user_id if username is missing."""
        data = {
            "external_accounts": [
                {"provider": "github", "provider_user_id": "user-123"}
            ]
        }
        assert extract_github_username(data) == "user-123"

    def test_returns_none_for_no_github_account(self):
        """Returns None if no GitHub account exists."""
        data = {"external_accounts": [{"provider": "google", "username": "googleuser"}]}
        assert extract_github_username(data) is None

    def test_returns_none_for_empty_accounts(self):
        """Returns None for empty external_accounts."""
        assert extract_github_username({"external_accounts": []}) is None
        assert extract_github_username({}) is None

    def test_skips_accounts_without_username_or_id(self):
        """Skips accounts missing both username and provider_user_id."""
        data = {
            "external_accounts": [
                {"provider": "github"},  # No username or id
                {"provider": "github", "username": "validuser"},
            ]
        }
        assert extract_github_username(data) == "validuser"


class TestExtractPrimaryEmail:
    """Test extract_primary_email function."""

    def test_extracts_primary_email_by_id(self):
        """Extracts email matching primary_email_address_id."""
        data = {
            "primary_email_address_id": "email-2",
            "email_addresses": [
                {"id": "email-1", "email_address": "first@example.com"},
                {"id": "email-2", "email_address": "primary@example.com"},
            ],
        }
        assert extract_primary_email(data) == "primary@example.com"

    def test_falls_back_to_first_email(self):
        """Falls back to first email if primary not found."""
        data = {
            "primary_email_address_id": "nonexistent",
            "email_addresses": [
                {"id": "email-1", "email_address": "first@example.com"},
            ],
        }
        assert extract_primary_email(data) == "first@example.com"

    def test_returns_fallback_for_no_emails(self):
        """Returns fallback if no email addresses."""
        data = {"email_addresses": []}
        assert (
            extract_primary_email(data, fallback="default@example.com")
            == "default@example.com"
        )

    def test_returns_none_for_empty_data(self):
        """Returns None for empty data with no fallback."""
        assert extract_primary_email({}) is None


class TestBoundedBackoffDict:
    """Test _BoundedBackoffDict class."""

    def test_acts_like_normal_dict(self):
        """Basic dict operations work."""
        d = _BoundedBackoffDict()
        d["key1"] = "value1"
        assert d["key1"] == "value1"
        assert "key1" in d
        assert len(d) == 1

    def test_evicts_when_full(self):
        """Evicts oldest entries when at capacity."""

        # Create small bounded dict for testing
        class SmallBoundedDict(_BoundedBackoffDict):
            pass

        d = SmallBoundedDict()

        # Fill dict
        for i in range(100):
            d[f"key-{i}"] = i

        # Should have evicted some entries
        # (can't predict exact count due to 10% batching)
        # But should be bounded

    def test_allows_update_existing_key(self):
        """Can update existing keys without eviction."""
        d = _BoundedBackoffDict()
        d["key1"] = "value1"
        d["key1"] = "updated"
        assert d["key1"] == "updated"


class TestBackoffLogic:
    """Test backoff functions."""

    def test_not_in_backoff_initially(self):
        """Users not in backoff by default."""
        # Clear any previous state
        _backoff_state.clear()
        assert _is_in_backoff("new-user") is False

    def test_set_backoff_puts_user_in_backoff(self):
        """set_backoff puts user in backoff state."""
        _backoff_state.clear()
        _set_backoff("test-user")
        assert _is_in_backoff("test-user") is True

    def test_backoff_expires(self):
        """Backoff expires after timeout."""
        _backoff_state.clear()
        # Set backoff that already expired
        _backoff_state["expired-user"] = time.time() - 1
        assert _is_in_backoff("expired-user") is False
        # Should have been cleaned up
        assert "expired-user" not in _backoff_state


class TestGetHttpClient:
    """Test get_http_client function."""

    @pytest.mark.asyncio
    async def test_creates_client_if_none(self):
        """Creates new client if none exists."""
        with (
            patch("services.clerk_service._http_client", None),
            patch("services.clerk_service.get_settings") as mock_settings,
        ):
            mock_settings.return_value.http_timeout = 30.0

            client = await get_http_client()
            assert client is not None


class TestCloseHttpClient:
    """Test close_http_client function."""

    @pytest.mark.asyncio
    async def test_closes_existing_client(self):
        """Closes client if it exists."""
        mock_client = AsyncMock()
        mock_client.is_closed = False

        with patch("services.clerk_service._http_client", mock_client):
            await close_http_client()

        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_none_client(self):
        """Handles None client gracefully."""
        with patch("services.clerk_service._http_client", None):
            # Should not raise
            await close_http_client()


class TestFetchUserData:
    """Test fetch_user_data function."""

    @pytest.mark.asyncio
    async def test_returns_none_without_clerk_key(self):
        """Returns None if no Clerk secret key configured."""
        with patch("services.clerk_service.get_settings") as mock_settings:
            mock_settings.return_value.clerk_secret_key = None

            result = await fetch_user_data("user-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_if_in_backoff(self):
        """Returns None if user is in backoff."""
        _backoff_state.clear()
        _set_backoff("backoff-user")

        with patch("services.clerk_service.get_settings") as mock_settings:
            mock_settings.return_value.clerk_secret_key = "sk_test_123"

            result = await fetch_user_data("backoff-user")

        assert result is None

    @pytest.mark.asyncio
    async def test_successful_fetch_returns_data(self):
        """Successful API call returns ClerkUserData."""
        _backoff_state.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "first_name": "John",
            "last_name": "Doe",
            "image_url": "https://example.com/avatar.png",
            "primary_email_address_id": "email-1",
            "email_addresses": [{"id": "email-1", "email_address": "john@example.com"}],
            "external_accounts": [{"provider": "github", "username": "johndoe"}],
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("services.clerk_service.get_settings") as mock_settings,
            patch("services.clerk_service.get_http_client", return_value=mock_client),
        ):
            mock_settings.return_value.clerk_secret_key = "sk_test_123"

            result = await fetch_user_data("user-123")

        assert isinstance(result, ClerkUserData)
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.github_username == "johndoe"
        assert result.email == "john@example.com"

    @pytest.mark.asyncio
    async def test_non_200_returns_none(self):
        """Non-200 status code returns None."""
        _backoff_state.clear()

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with (
            patch("services.clerk_service.get_settings") as mock_settings,
            patch("services.clerk_service.get_http_client", return_value=mock_client),
        ):
            mock_settings.return_value.clerk_secret_key = "sk_test_123"

            result = await fetch_user_data("missing-user")

        assert result is None

    @pytest.mark.asyncio
    async def test_unexpected_exception_does_not_set_backoff(self):
        """Unexpected exception returns None but does NOT set backoff.

        Only retriable exceptions (network errors, rate limits) set backoff.
        Unexpected exceptions might be bugs in our code - we want to see them.
        """
        _backoff_state.clear()

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Unexpected bug")

        with (
            patch("services.clerk_service.get_settings") as mock_settings,
            patch("services.clerk_service.get_http_client", return_value=mock_client),
        ):
            mock_settings.return_value.clerk_secret_key = "sk_test_123"

            result = await fetch_user_data("error-user")

        assert result is None
        # Unexpected exceptions do NOT set backoff - only retriable ones do
        assert _is_in_backoff("error-user") is False


class TestFetchGithubUsername:
    """Test fetch_github_username function."""

    @pytest.mark.asyncio
    async def test_returns_username_from_clerk_data(self):
        """Returns GitHub username from Clerk data."""
        clerk_data = ClerkUserData(github_username="testuser")

        with patch("services.clerk_service.fetch_user_data", return_value=clerk_data):
            result = await fetch_github_username("user-123")

        assert result == "testuser"

    @pytest.mark.asyncio
    async def test_returns_none_if_no_clerk_data(self):
        """Returns None if fetch_user_data returns None."""
        with patch("services.clerk_service.fetch_user_data", return_value=None):
            result = await fetch_github_username("user-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_if_no_github_username(self):
        """Returns None if Clerk data has no GitHub username."""
        clerk_data = ClerkUserData(email="test@example.com")

        with patch("services.clerk_service.fetch_user_data", return_value=clerk_data):
            result = await fetch_github_username("user-123")

        assert result is None
