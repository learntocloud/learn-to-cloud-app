"""Unit tests for auth routes.

Tests cover:
- GET /auth/login — initiates GitHub OAuth redirect
- GET /auth/callback — exchanges code, creates session, redirects
- POST /auth/logout — clears session, redirects home

Testing approach:
- Call handler functions directly with mocked dependencies
- Use mock.patch for module-level imports (oauth, get_settings)
- Use autospec=True for all mocks to catch signature mismatches

These are unit tests: no HTTP client, no real OAuth, no database.
"""

import json
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from authlib.integrations.starlette_client import OAuthError
from fastapi.responses import RedirectResponse

from learn_to_cloud.core.auth import SESSION_COOKIE_NAME
from learn_to_cloud.routes.auth_routes import callback, login, logout


def _mock_request(*, session: dict | None = None) -> MagicMock:
    """Build a minimal mock Request with session support."""
    request = MagicMock()
    request.session = session if session is not None else {}
    request.url_for.return_value = "http://testserver/auth/callback"

    # session_maker context manager used by callback() for scoped DB access
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session_maker = MagicMock(return_value=mock_cm)
    request.app.state.session_maker = mock_session_maker
    request._mock_db_session = mock_session  # exposed for test assertions

    return request


@pytest.mark.unit
class TestLoginRoute:
    """Tests for GET /auth/login."""

    async def test_login_redirects_to_github(self):
        """Login creates a GitHub OAuth client and calls authorize_redirect."""
        request = _mock_request()
        mock_github = MagicMock()
        mock_github.authorize_redirect = AsyncMock(
            return_value=RedirectResponse(
                url="https://github.com/login/oauth/authorize"
            )
        )

        with (
            patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth,
            patch(
                "learn_to_cloud.routes.auth_routes.get_web_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.web_security.require_https = False
            mock_oauth.create_client.return_value = mock_github

            result = await login(request)

        mock_oauth.create_client.assert_called_once_with("github")
        mock_github.authorize_redirect.assert_awaited_once_with(
            request, "http://testserver/auth/callback"
        )
        assert isinstance(result, RedirectResponse)

    async def test_login_forces_https_redirect_uri_when_required(self):
        """When require_https=True, redirect_uri is rewritten to https."""
        request = _mock_request()
        mock_github = MagicMock()
        mock_github.authorize_redirect = AsyncMock(
            return_value=RedirectResponse(
                url="https://github.com/login/oauth/authorize"
            )
        )

        with (
            patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth,
            patch(
                "learn_to_cloud.routes.auth_routes.get_web_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.web_security.require_https = True
            mock_oauth.create_client.return_value = mock_github

            await login(request)

        # The redirect_uri should have been rewritten to https
        call_args = mock_github.authorize_redirect.call_args
        redirect_uri = call_args[0][1]
        assert redirect_uri.startswith("https://")

    async def test_login_returns_home_redirect_when_github_not_configured(self):
        """When GitHub OAuth is not configured, redirects to /."""
        request = _mock_request()

        with (
            patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth,
            patch(
                "learn_to_cloud.routes.auth_routes.get_web_settings"
            ) as mock_settings,
        ):
            mock_settings.return_value.web_security.require_https = False
            mock_oauth.create_client.return_value = None

            result = await login(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"


@pytest.mark.unit
class TestCallbackRoute:
    """Tests for GET /auth/callback."""

    async def test_callback_creates_session_on_success(self):
        """Successful OAuth callback sets session and redirects to /dashboard."""
        request = _mock_request(session={})
        mock_github = MagicMock()

        token = {"access_token": "gho_fake_token"}
        mock_github.authorize_access_token = AsyncMock(return_value=token)

        github_user_data = {
            "id": 12345,
            "login": "testuser",
            "avatar_url": "https://example.com/avatar.png",
            "name": "Test User",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = github_user_data
        mock_github.get = AsyncMock(return_value=mock_response)

        mock_user = MagicMock()
        mock_user.id = 12345
        mock_user.github_username = "testuser"

        with (
            patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth,
            patch(
                "learn_to_cloud.routes.auth_routes.get_or_create_user_from_github",
                autospec=True,
                return_value=mock_user,
            ) as mock_get_or_create,
        ):
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request)

        # Session should be populated
        assert request.session["user_id"] == 12345
        assert request.session["github_username"] == "testuser"

        # Should redirect to /dashboard
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/dashboard"

        # User creation should have been called with the scoped DB session
        mock_get_or_create.assert_awaited_once_with(
            db=request._mock_db_session,
            github_id=12345,
            first_name="Test",
            last_name="User",
            avatar_url="https://example.com/avatar.png",
            github_username="testuser",
        )

    async def test_callback_handles_oauth_error(self):
        """OAuthError during token exchange redirects to /."""
        request = _mock_request(session={})
        mock_github = MagicMock()
        mock_github.authorize_access_token = AsyncMock(
            side_effect=OAuthError(error="access_denied")
        )

        with patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        # Session should remain empty
        assert "user_id" not in request.session

    async def test_callback_handles_connect_timeout_on_token_exchange(self):
        """httpx2.ConnectTimeout during token exchange redirects to / (not 500)."""
        request = _mock_request(session={})
        mock_github = MagicMock()
        mock_github.authorize_access_token = AsyncMock(
            side_effect=httpx2.ConnectTimeout("connect timed out")
        )

        with patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        assert "user_id" not in request.session

    async def test_callback_handles_connect_timeout_on_profile_fetch(self):
        """httpx2.ConnectTimeout fetching the user profile redirects to / (not 500)."""
        request = _mock_request(session={})
        mock_github = MagicMock()
        mock_github.authorize_access_token = AsyncMock(
            return_value={"access_token": "gho_fake"}
        )
        mock_github.get = AsyncMock(
            side_effect=httpx2.ConnectTimeout("connect timed out")
        )

        with patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        assert "user_id" not in request.session

    async def test_callback_redirects_home_when_github_not_configured(self):
        """When GitHub OAuth is not configured, redirects to /."""
        request = _mock_request(session={})

        with patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = None

            result = await callback(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"

    async def test_callback_handles_missing_github_id(self):
        """Malformed GitHub response (no 'id') redirects to / gracefully."""
        request = _mock_request(session={})
        mock_github = MagicMock()
        mock_github.authorize_access_token = AsyncMock(
            return_value={"access_token": "gho_fake"}
        )

        # Simulate GitHub returning an error response (e.g., 401)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": "Bad credentials",
            "documentation_url": "https://docs.github.com",
        }
        mock_response.status_code = 401
        mock_github.get = AsyncMock(return_value=mock_response)

        with patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        # Session should remain empty — no user created
        assert "user_id" not in request.session

    async def test_callback_lowercases_github_username(self):
        """GitHub username is stored lowercase in the database."""
        request = _mock_request(session={})
        mock_github = MagicMock()
        mock_github.authorize_access_token = AsyncMock(
            return_value={"access_token": "gho_fake"}
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": 999,
            "login": "MiXeDcAsE",
            "avatar_url": None,
            "name": "",
        }
        mock_github.get = AsyncMock(return_value=mock_response)

        mock_user = MagicMock()
        mock_user.id = 999
        mock_user.github_username = "mixedcase"

        with (
            patch("learn_to_cloud.routes.auth_routes.oauth") as mock_oauth,
            patch(
                "learn_to_cloud.routes.auth_routes.get_or_create_user_from_github",
                autospec=True,
                return_value=mock_user,
            ) as mock_get_or_create,
        ):
            mock_oauth.create_client.return_value = mock_github

            await callback(request)

        # Verify github_username was lowercased before being passed
        call_kwargs = mock_get_or_create.call_args.kwargs
        assert call_kwargs["github_username"] == "mixedcase"


@pytest.fixture
def callback_context():
    request = _mock_request(
        session={
            "user_id": 99,
            "github_username": "existing-user",
            "_state_github_other": {"data": {"state": "private-state"}},
        }
    )
    github = MagicMock()
    github.authorize_access_token = AsyncMock(
        return_value={"access_token": "private-oauth-token"}
    )
    github.get = AsyncMock(
        return_value=httpx2.Response(
            200,
            json={"id": 42, "login": "testuser"},
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )
    )
    user = SimpleNamespace(id=42, github_username="testuser")
    with (
        patch("learn_to_cloud.routes.auth_routes.oauth") as oauth,
        patch(
            "learn_to_cloud.routes.auth_routes.get_or_create_user_from_github",
            autospec=True,
            return_value=user,
        ) as upsert,
    ):
        oauth.create_client.return_value = github
        yield request, github, user, upsert


@pytest.mark.unit
class TestCallbackIdentityContract:
    @pytest.mark.parametrize(
        ("profile", "reason"),
        [
            ({}, "invalid_user_id"),
            ({"id": True, "login": "testuser"}, "invalid_user_id"),
            ({"id": 42.0, "login": "testuser"}, "invalid_user_id"),
            ({"id": "42", "login": "testuser"}, "invalid_user_id"),
            ({"id": 0, "login": "testuser"}, "invalid_user_id"),
            ({"id": -1, "login": "testuser"}, "invalid_user_id"),
            ({"id": 2**63, "login": "testuser"}, "invalid_user_id"),
            ({"id": [], "login": "testuser"}, "invalid_user_id"),
            ({"id": 42}, "invalid_github_username"),
            ({"id": 42, "login": []}, "invalid_github_username"),
            ({"id": 42, "login": " \t"}, "invalid_github_username"),
            ({"id": 42, "login": "x" * 256}, "invalid_github_username"),
            ({"id": 42, "login": "\u0130" * 128}, "invalid_github_username"),
            ({"id": 42, "login": "private\x00name"}, "invalid_github_username"),
            ({"id": 42, "login": "private\ud800name"}, "invalid_github_username"),
            (None, "invalid_response_format"),
            ([], "invalid_response_format"),
            ("private-profile", "invalid_response_format"),
        ],
    )
    async def test_rejects_before_persistence_and_preserves_session(
        self, callback_context, caplog, profile, reason
    ):
        request, github, _, upsert = callback_context
        original = request.session.copy()
        github.get.return_value = httpx2.Response(
            200,
            content=json.dumps(profile).encode(),
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )

        response = await callback(request)

        assert response.status_code == 302
        assert response.headers["location"] == "/"
        assert request.session == original
        request.app.state.session_maker.assert_not_called()
        upsert.assert_not_awaited()
        (record,) = caplog.records
        assert record.getMessage() == "auth.callback.identity_rejected"
        assert record.__dict__["auth.identity.reason"] == reason
        assert record.args == ()
        assert record.exc_info is None

    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (200, b"private-provider-body"),
            (200, b"\xff"),
            (401, b"private-provider-body"),
            (403, b"private-provider-body"),
            (500, b"private-provider-body"),
        ],
    )
    async def test_bad_provider_response_does_not_issue_identity(
        self, callback_context, caplog, status, body
    ):
        request, github, _, upsert = callback_context
        original = request.session.copy()
        github.get.return_value = httpx2.Response(
            status,
            content=body,
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )
        response = await callback(request)
        assert response.status_code == 302
        assert request.session == original
        request.app.state.session_maker.assert_not_called()
        upsert.assert_not_awaited()
        assert "private-provider-body" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)

    @pytest.mark.parametrize(
        ("user_id", "username"), [(42, None), (43, "testuser"), (42, "different-user")]
    )
    async def test_invalid_persisted_identity_is_an_internal_failure(
        self, callback_context, caplog, user_id, username
    ):
        request, _, user, _ = callback_context
        original = request.session.copy()
        user.id, user.github_username = user_id, username
        with pytest.raises(
            RuntimeError,
            match="^Persisted OAuth identity does not match validated identity$",
        ):
            await callback(request)
        request._mock_db_session.commit.assert_not_awaited()
        exit_args = (
            request.app.state.session_maker.return_value.__aexit__.call_args.args
        )
        assert exit_args[0] is RuntimeError
        assert request.session == original
        assert caplog.records == []

    @pytest.mark.parametrize("stage", ["upsert", "commit"])
    async def test_database_failure_does_not_issue_identity(
        self, callback_context, caplog, stage
    ):
        request, _, _, upsert = callback_context
        original = request.session.copy()
        operation = upsert if stage == "upsert" else request._mock_db_session.commit
        operation.side_effect = RuntimeError("database-failure-probe")
        with pytest.raises(RuntimeError, match="database-failure-probe"):
            await callback(request)
        assert request.session == original
        assert "auth.login.success" not in caplog.text

    async def test_commit_precedes_session_issuance(self, callback_context, caplog):
        request, _, _, upsert = callback_context
        original = request.session.copy()

        async def commit():
            assert request.session == original
            upsert.assert_awaited_once()

        request._mock_db_session.commit.side_effect = commit
        with caplog.at_level("INFO", logger="learn_to_cloud.routes.auth_routes"):
            response = await callback(request)
        assert response.status_code == 302
        assert request.session == {
            **original,
            "user_id": 42,
            "github_username": "testuser",
        }
        request._mock_db_session.commit.assert_awaited_once()
        assert [r.getMessage() for r in caplog.records] == ["auth.login.success"]


@pytest.mark.unit
class TestLogoutRoute:
    """Tests for POST /auth/logout."""

    @pytest.mark.parametrize(
        "session", [{}, {"user_id": 42}, {"user_id": 42, "github_username": "testuser"}]
    )
    @pytest.mark.parametrize("secure", [False, True])
    async def test_logout_clears_session_and_redirects(self, session, secure):
        """Logout clears session data and redirects to /."""
        request = _mock_request(session=session.copy())

        with patch(
            "learn_to_cloud.routes.auth_routes.get_web_settings"
        ) as mock_settings:
            mock_settings.return_value.web_security.require_https = secure
            result = await logout(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        assert result.headers["location"] == "/"
        assert request.session == {}
        cookie = SimpleCookie(result.headers["set-cookie"])[SESSION_COOKIE_NAME]
        assert cookie["max-age"] == "0"
        assert cookie["path"] == "/"
        assert cookie["httponly"]
        assert cookie["samesite"] == "lax"
        assert bool(cookie["secure"]) is secure
