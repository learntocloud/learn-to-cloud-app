"""Unit tests for core.auth module.

Tests session-based authentication utilities:
- get_user_id_from_session reads user_id from session
- require_auth raises HTTPException when unauthenticated
- optional_auth returns user_id or None without raising
- init_oauth registers GitHub OAuth provider
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from core.auth import (
    get_user_id_from_session,
    init_oauth,
    oauth,
    optional_auth,
    require_auth,
)


def _make_request(session: dict | None = None, headers: dict | None = None) -> Request:
    """Create a mock Request with session and headers support."""
    request = MagicMock(spec=Request)
    request.session = session or {}
    request.headers = headers or {}
    request.state = MagicMock()
    return request


@pytest.mark.unit
class TestGetUserIdFromSession:
    """Test get_user_id_from_session reads session correctly."""

    def test_returns_int_when_user_id_present(self):
        request = _make_request(session={"user_id": 12345})
        result = get_user_id_from_session(request)
        assert result == 12345

    def test_returns_int_when_user_id_is_string(self):
        request = _make_request(session={"user_id": "67890"})
        result = get_user_id_from_session(request)
        assert result == 67890

    def test_returns_none_when_user_id_missing(self):
        request = _make_request(session={})
        result = get_user_id_from_session(request)
        assert result is None

    def test_returns_none_when_session_empty(self):
        request = _make_request(session={})
        result = get_user_id_from_session(request)
        assert result is None


@pytest.mark.unit
class TestRequireAuth:
    """Test require_auth dependency."""

    def test_returns_user_id_when_authenticated(self):
        request = _make_request(session={"user_id": 42})
        result = require_auth(request)
        assert result == 42

    def test_sets_request_state_user_id(self):
        request = _make_request(session={"user_id": 42})
        require_auth(request)
        assert request.state.user_id == 42

    def test_raises_401_for_htmx_requests(self):
        request = _make_request(session={}, headers={"hx-request": "true"})
        with pytest.raises(HTTPException) as exc_info:
            require_auth(request)
        assert exc_info.value.status_code == 401

    def test_raises_307_redirect_for_regular_requests(self):
        request = _make_request(session={}, headers={})
        with pytest.raises(HTTPException) as exc_info:
            require_auth(request)
        assert exc_info.value.status_code == 307
        headers = exc_info.value.headers
        assert headers is not None
        assert headers["Location"] == "/auth/login"


@pytest.mark.unit
class TestOptionalAuth:
    """Test optional_auth dependency."""

    def test_returns_user_id_when_authenticated(self):
        request = _make_request(session={"user_id": 99})
        result = optional_auth(request)
        assert result == 99

    def test_sets_request_state_when_authenticated(self):
        request = _make_request(session={"user_id": 99})
        optional_auth(request)
        assert request.state.user_id == 99

    def test_returns_none_when_not_authenticated(self):
        request = _make_request(session={})
        result = optional_auth(request)
        assert result is None

    def test_does_not_set_request_state_when_not_authenticated(self):
        request = _make_request(session={})
        optional_auth(request)
        # user_id should not have been assigned — no setattr calls expected
        state = request.state
        for name, _, _ in state.mock_calls:
            assert name != "user_id"


@pytest.mark.unit
class TestInitOauth:
    """Test init_oauth registers GitHub provider."""

    @patch("core.auth.get_settings", autospec=True)
    def test_registers_github_when_client_id_set(self, mock_get_settings):
        mock_settings = MagicMock()
        mock_settings.github_client_id = "test-client-id"
        mock_settings.github_client_secret = "test-client-secret"
        mock_get_settings.return_value = mock_settings

        # Clear any existing registration
        oauth._clients.pop("github", None)

        init_oauth()

        assert "github" in oauth._clients

    @patch("core.auth.get_settings", autospec=True)
    def test_skips_registration_when_client_id_empty(self, mock_get_settings):
        mock_settings = MagicMock()
        mock_settings.github_client_id = ""
        mock_get_settings.return_value = mock_settings

        oauth._clients.pop("github", None)

        init_oauth()

        assert "github" not in oauth._clients
