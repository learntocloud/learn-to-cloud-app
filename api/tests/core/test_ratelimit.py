"""Unit tests for core.ratelimit module.

Tests rate limiting utilities:
- _get_request_identifier returns user-based or IP-based key
- rate_limit_exceeded_handler returns proper 429 JSON response
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from slowapi.errors import RateLimitExceeded

from core.ratelimit import _get_request_identifier, rate_limit_exceeded_handler


def _make_rate_limit_exc(
    detail: str = "5 per 1 minute", retry_after: int = 30
) -> RateLimitExceeded:
    """Create a RateLimitExceeded with a mock Limit object."""
    mock_limit = MagicMock()
    mock_limit.error_message = None
    mock_limit.limit = detail
    exc = RateLimitExceeded(mock_limit)
    object.__setattr__(exc, "retry_after", retry_after)
    return exc


def _make_request(user_id: int | None = None) -> Request:
    """Create a mock Request with optional user_id on state."""
    request = MagicMock(spec=Request)
    state = MagicMock()
    if user_id is not None:
        state.user_id = user_id
    else:
        # Simulate missing attribute
        del state.user_id
    request.state = state
    return request


@pytest.mark.unit
class TestGetRequestIdentifier:
    """Test _get_request_identifier key generation."""

    @patch("core.ratelimit.get_remote_address", autospec=True)
    def test_returns_user_key_when_authenticated(self, mock_get_remote):
        request = _make_request(user_id=42)
        result = _get_request_identifier(request)
        assert result == "user:42"
        mock_get_remote.assert_not_called()

    @patch("core.ratelimit.get_remote_address", autospec=True)
    def test_falls_back_to_ip_when_no_user_id(self, mock_get_remote):
        mock_get_remote.return_value = "192.168.1.1"
        request = _make_request(user_id=None)
        result = _get_request_identifier(request)
        assert result == "192.168.1.1"
        mock_get_remote.assert_called_once_with(request)


@pytest.mark.unit
class TestRateLimitExceededHandler:
    """Test rate_limit_exceeded_handler response."""

    def test_returns_429_with_retry_after(self):
        request = MagicMock(spec=Request)
        exc = _make_rate_limit_exc(retry_after=30)

        response = rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "30"

    def test_response_body_contains_detail(self):
        request = MagicMock(spec=Request)
        exc = _make_rate_limit_exc(detail="10 per 1 hour", retry_after=60)

        response = rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429
        body = json.loads(response.body)
        assert "Rate limit exceeded" in body["detail"]
        assert "retry_after" in body

    def test_handles_non_rate_limit_exception(self):
        request = MagicMock(spec=Request)
        exc = ValueError("something else")

        response = rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body["detail"] == "Unexpected error"
