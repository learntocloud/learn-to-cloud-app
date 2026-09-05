"""Tests for session identities, authentication policies, and OAuth registration."""

from importlib import import_module, util
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from learn_to_cloud_shared.core.config import OAuthConfig

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    AuthenticationRequired,
    get_authenticated_user_from_session,
    init_oauth,
    oauth,
    optional_authenticated_user,
    require_authenticated_user,
)


def test_authlib_uses_supported_http_client() -> None:
    """Require Authlib's supported transport when its compatibility shim exists."""
    module_name = "authlib.integrations.httpx_client._compat"
    if util.find_spec(module_name) is None:
        return

    compat = import_module(module_name)
    assert compat.httpx2.__name__ == "httpx2", (
        "Authlib is using its deprecated httpx fallback. Add httpx2 and update "
        "OAuth transport exception handling before upgrading Authlib."
    )


def _make_request(session: dict | None = None, headers: dict | None = None) -> Request:
    """Create a mock Request with session and headers support."""
    request = MagicMock(spec=Request)
    request.session = session or {}
    request.headers = headers or {}
    request.state = MagicMock()
    return request


@pytest.mark.unit
class TestGetAuthenticatedUserFromSession:
    """Test session identity extraction."""

    @pytest.mark.parametrize("user_id", [42, "42"])
    def test_returns_identity_with_integer_id(self, user_id):
        request = _make_request(
            session={"user_id": user_id, "github_username": "testuser"}
        )
        result = get_authenticated_user_from_session(request)
        assert result == AuthenticatedUser(user_id=42, github_username="testuser")

    def test_returns_none_without_username(self):
        request = _make_request(session={"user_id": 42})
        result = get_authenticated_user_from_session(request)
        assert result is None

    @pytest.mark.parametrize("username", [None, "", 42, []])
    def test_returns_none_for_invalid_username(self, username):
        request = _make_request(session={"user_id": 42, "github_username": username})
        assert get_authenticated_user_from_session(request) is None

    @pytest.mark.parametrize(
        "session",
        [
            {},
            {"github_username": "testuser"},
            {"user_id": None, "github_username": "testuser"},
        ],
    )
    def test_returns_none_when_user_id_missing(self, session):
        request = _make_request(session=session)
        result = get_authenticated_user_from_session(request)
        assert result is None


@pytest.mark.unit
class TestRequireAuthenticatedUser:
    """Test require_authenticated_user dependency."""

    def test_returns_identity_and_sets_state(self):
        request = _make_request(session={"user_id": 42, "github_username": "testuser"})
        result = require_authenticated_user(request)
        assert result == AuthenticatedUser(user_id=42, github_username="testuser")
        assert request.state.user_id == 42
        assert request.state.github_username == "testuser"

    @pytest.mark.parametrize("session", [{}, {"user_id": 42}])
    @pytest.mark.parametrize("htmx", [False, True])
    def test_raises_401_when_unauthenticated(self, session, htmx):
        request = _make_request(
            session=session, headers={"hx-request": "true"} if htmx else {}
        )
        with pytest.raises(AuthenticationRequired) as exc_info:
            require_authenticated_user(request)
        assert exc_info.value.status_code == 401
        assert exc_info.value.headers is None


@pytest.mark.unit
class TestOptionalAuthenticatedUser:
    """Test optional_authenticated_user dependency."""

    def test_returns_identity_and_sets_state(self):
        request = _make_request(session={"user_id": 99, "github_username": "user"})
        result = optional_authenticated_user(request)
        assert result == AuthenticatedUser(user_id=99, github_username="user")
        assert request.state.user_id == 99
        assert request.state.github_username == "user"

    def test_returns_none_when_not_authenticated(self):
        request = _make_request(session={})
        result = optional_authenticated_user(request)
        assert result is None


@pytest.mark.unit
class TestInitOauth:
    """Test init_oauth registers GitHub provider."""

    def test_registers_github_when_client_id_set(self):
        # Clear any existing registration
        oauth._clients.pop("github", None)

        init_oauth(
            OAuthConfig(client_id="test-client-id", client_secret="test-client-secret")
        )

        assert "github" in oauth._clients

    def test_skips_registration_when_client_id_empty(self):
        oauth._clients.pop("github", None)

        init_oauth(OAuthConfig(client_id=""))

        assert "github" not in oauth._clients
