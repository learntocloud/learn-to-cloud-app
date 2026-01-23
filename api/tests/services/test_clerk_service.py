"""Tests for clerk service."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

# Mark all tests in this module as unit tests (no database required)
pytestmark = pytest.mark.unit

from services.clerk_service import (
    ClerkServerError,
    _BoundedBackoffDict,
    _is_in_backoff,
    _parse_retry_after,
    _set_backoff,
    close_http_client,
    extract_github_username,
    extract_primary_email,
    fetch_github_username,
    fetch_user_data,
    get_http_client,
    reset_backoff_state,
    reset_http_client,
)


@pytest.fixture(autouse=True)
def reset_clerk_state():
    """Reset clerk service state before and after each test."""
    reset_http_client()
    reset_backoff_state()
    yield
    reset_http_client()
    reset_backoff_state()


class TestExtractGithubUsername:
    """Tests for extract_github_username."""

    def test_extracts_github_username(self):
        """Test extracting GitHub username from external_accounts."""
        data = {
            "external_accounts": [
                {"provider": "oauth_github", "username": "testuser"},
            ]
        }
        result = extract_github_username(data)
        assert result == "testuser"

    def test_extracts_from_github_provider(self):
        """Test extracting from 'github' provider."""
        data = {
            "external_accounts": [
                {"provider": "github", "username": "anotheruser"},
            ]
        }
        result = extract_github_username(data)
        assert result == "anotheruser"

    def test_falls_back_to_provider_user_id(self):
        """Test fallback to provider_user_id if username missing."""
        data = {
            "external_accounts": [
                {"provider": "oauth_github", "provider_user_id": "12345"},
            ]
        }
        result = extract_github_username(data)
        assert result == "12345"

    def test_returns_none_for_no_github_account(self):
        """Test returns None when no GitHub account linked."""
        data = {
            "external_accounts": [
                {"provider": "google", "username": "googleuser"},
            ]
        }
        result = extract_github_username(data)
        assert result is None

    def test_returns_none_for_empty_external_accounts(self):
        """Test returns None for empty external_accounts."""
        data = {"external_accounts": []}
        result = extract_github_username(data)
        assert result is None

    def test_returns_none_for_missing_external_accounts(self):
        """Test returns None when external_accounts missing."""
        data = {}
        result = extract_github_username(data)
        assert result is None


class TestExtractPrimaryEmail:
    """Tests for extract_primary_email."""

    def test_extracts_primary_email(self):
        """Test extracting primary email based on primary_email_address_id."""
        data = {
            "email_addresses": [
                {"id": "email_1", "email_address": "first@example.com"},
                {"id": "email_2", "email_address": "primary@example.com"},
            ],
            "primary_email_address_id": "email_2",
        }
        result = extract_primary_email(data)
        assert result == "primary@example.com"

    def test_falls_back_to_first_email(self):
        """Test fallback to first email if primary not found."""
        data = {
            "email_addresses": [
                {"id": "email_1", "email_address": "first@example.com"},
            ],
            "primary_email_address_id": "nonexistent",
        }
        result = extract_primary_email(data)
        assert result == "first@example.com"

    def test_uses_fallback_for_empty_emails(self):
        """Test using fallback when no emails present."""
        data = {"email_addresses": []}
        result = extract_primary_email(data, fallback="fallback@example.com")
        assert result == "fallback@example.com"

    def test_returns_none_without_fallback(self):
        """Test returns None when no emails and no fallback."""
        data = {"email_addresses": []}
        result = extract_primary_email(data)
        assert result is None


class TestParseRetryAfter:
    """Tests for _parse_retry_after."""

    def test_parses_seconds(self):
        """Test parsing seconds value."""
        result = _parse_retry_after("30")
        assert result == 30.0

    def test_parses_float_seconds(self):
        """Test parsing float seconds value."""
        result = _parse_retry_after("2.5")
        assert result == 2.5

    def test_returns_none_for_invalid_format(self):
        """Test returns None for invalid format."""
        result = _parse_retry_after("not-a-number")
        assert result is None

    def test_returns_none_for_none_input(self):
        """Test returns None for None input."""
        result = _parse_retry_after(None)
        assert result is None


class TestBoundedBackoffDict:
    """Tests for _BoundedBackoffDict."""

    def test_basic_operations(self):
        """Test basic dict operations work."""
        d = _BoundedBackoffDict()
        d["key1"] = "value1"
        assert d["key1"] == "value1"

    def test_evicts_when_full(self):
        """Test that oldest entries are evicted when full."""
        # Create a small bounded dict
        from services.clerk_service import _MAX_BACKOFF_ENTRIES

        d = _BoundedBackoffDict()

        # Fill it up
        for i in range(_MAX_BACKOFF_ENTRIES):
            d[f"key{i}"] = i

        # Add one more - should trigger eviction
        d["new_key"] = "new_value"

        # Should still have the new key
        assert "new_key" in d

        # Size should be less than or equal to max
        assert len(d) <= _MAX_BACKOFF_ENTRIES


class TestBackoffFunctions:
    """Tests for backoff state management."""

    def test_set_and_check_backoff(self):
        """Test setting and checking backoff state."""
        test_user_id = "test-backoff-user-123"

        # Initially not in backoff
        assert _is_in_backoff(test_user_id) is False

        # Set backoff
        _set_backoff(test_user_id)

        # Now should be in backoff
        assert _is_in_backoff(test_user_id) is True


class TestClerkServerError:
    """Tests for ClerkServerError exception."""

    def test_basic_error(self):
        """Test basic error creation."""
        exc = ClerkServerError("Server error")
        assert str(exc) == "Server error"
        assert exc.retry_after is None

    def test_error_with_retry_after(self):
        """Test error with retry_after value."""
        exc = ClerkServerError("Rate limited", retry_after=30.0)
        assert exc.retry_after == 30.0


class TestHttpClient:
    """Tests for HTTP client management."""

    async def test_get_http_client_creates_client(self):
        """Test that get_http_client creates a client."""
        client = await get_http_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)

    async def test_get_http_client_reuses_client(self):
        """Test that get_http_client reuses existing client."""
        client1 = await get_http_client()
        client2 = await get_http_client()

        assert client1 is client2

    async def test_close_http_client(self):
        """Test closing the HTTP client."""
        client = await get_http_client()
        await close_http_client()

        # Should be able to get a new client after closing
        new_client = await get_http_client()
        assert new_client is not None
        assert new_client is not client  # Should be a different instance

    def test_reset_http_client(self):
        """Test that reset_http_client clears state for testing."""
        # This is a sync function for test fixtures
        reset_http_client()
        # After reset, next get should create fresh client
        # (verified by other tests)


class TestFetchUserData:
    """Tests for fetch_user_data."""

    @pytest.mark.asyncio
    @patch("services.clerk_service.get_settings")
    async def test_returns_none_when_no_secret_key(self, mock_settings):
        """Test returns None when clerk_secret_key not configured."""
        mock_settings.return_value = MagicMock(clerk_secret_key=None)

        result = await fetch_user_data("user-123")
        assert result is None

    @pytest.mark.asyncio
    @patch("services.clerk_service._is_in_backoff", return_value=True)
    @patch("services.clerk_service.get_settings")
    async def test_returns_none_when_in_backoff(self, mock_settings, mock_is_backoff):
        """Test returns None when user is in backoff period."""
        mock_settings.return_value = MagicMock(clerk_secret_key="test-key")

        result = await fetch_user_data("user-in-backoff")
        assert result is None


class TestFetchGithubUsername:
    """Tests for fetch_github_username."""

    @pytest.mark.asyncio
    @patch("services.clerk_service.fetch_user_data")
    async def test_returns_github_username(self, mock_fetch):
        """Test returning GitHub username from user data."""
        mock_fetch.return_value = MagicMock(github_username="testuser")

        result = await fetch_github_username("user-123")
        assert result == "testuser"

    @pytest.mark.asyncio
    @patch("services.clerk_service.fetch_user_data")
    async def test_returns_none_when_no_user_data(self, mock_fetch):
        """Test returns None when fetch_user_data returns None."""
        mock_fetch.return_value = None

        result = await fetch_github_username("user-123")
        assert result is None
