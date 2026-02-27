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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from authlib.integrations.starlette_client import OAuthError
from fastapi.responses import RedirectResponse

from routes.auth_routes import callback, login, logout


def _mock_request(*, session: dict | None = None) -> MagicMock:
    """Build a minimal mock Request with session support."""
    request = MagicMock()
    request.session = session if session is not None else {}
    request.url_for.return_value = "http://testserver/auth/callback"
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
            patch("routes.auth_routes.oauth") as mock_oauth,
            patch("routes.auth_routes.get_settings") as mock_settings,
        ):
            mock_settings.return_value.require_https = False
            mock_oauth.create_client.return_value = mock_github

            result = await login(request)

        mock_oauth.create_client.assert_called_once_with("github")
        mock_github.authorize_redirect.assert_awaited_once_with(
            request, "http://testserver/auth/callback", prompt="select_account"
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
            patch("routes.auth_routes.oauth") as mock_oauth,
            patch("routes.auth_routes.get_settings") as mock_settings,
        ):
            mock_settings.return_value.require_https = True
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
            patch("routes.auth_routes.oauth") as mock_oauth,
            patch("routes.auth_routes.get_settings") as mock_settings,
        ):
            mock_settings.return_value.require_https = False
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
        mock_db = AsyncMock()
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
        mock_user.id = 42
        mock_user.github_username = "testuser"

        with (
            patch("routes.auth_routes.oauth") as mock_oauth,
            patch(
                "routes.auth_routes.get_or_create_user_from_github",
                autospec=True,
                return_value=mock_user,
            ) as mock_get_or_create,
        ):
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request, mock_db)

        # Session should be populated
        assert request.session["user_id"] == 42
        assert request.session["github_username"] == "testuser"

        # Should redirect to /dashboard
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/dashboard"

        # User creation should have been called with parsed data
        mock_get_or_create.assert_awaited_once_with(
            db=mock_db,
            github_id=12345,
            first_name="Test",
            last_name="User",
            avatar_url="https://example.com/avatar.png",
            github_username="testuser",
        )

    async def test_callback_handles_oauth_error(self):
        """OAuthError during token exchange redirects to /."""
        request = _mock_request(session={})
        mock_db = AsyncMock()
        mock_github = MagicMock()
        mock_github.authorize_access_token = AsyncMock(
            side_effect=OAuthError(error="access_denied")
        )

        with patch("routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request, mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        # Session should remain empty
        assert "user_id" not in request.session

    async def test_callback_redirects_home_when_github_not_configured(self):
        """When GitHub OAuth is not configured, redirects to /."""
        request = _mock_request(session={})
        mock_db = AsyncMock()

        with patch("routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = None

            result = await callback(request, mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"

    async def test_callback_handles_missing_github_id(self):
        """Malformed GitHub response (no 'id') redirects to / gracefully."""
        request = _mock_request(session={})
        mock_db = AsyncMock()
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

        with patch("routes.auth_routes.oauth") as mock_oauth:
            mock_oauth.create_client.return_value = mock_github

            result = await callback(request, mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        # Session should remain empty — no user created
        assert "user_id" not in request.session

    async def test_callback_lowercases_github_username(self):
        """GitHub username is stored lowercase in the database."""
        request = _mock_request(session={})
        mock_db = AsyncMock()
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
        mock_user.id = 1
        mock_user.github_username = "mixedcase"

        with (
            patch("routes.auth_routes.oauth") as mock_oauth,
            patch(
                "routes.auth_routes.get_or_create_user_from_github",
                autospec=True,
                return_value=mock_user,
            ) as mock_get_or_create,
        ):
            mock_oauth.create_client.return_value = mock_github

            await callback(request, mock_db)

        # Verify github_username was lowercased before being passed
        call_kwargs = mock_get_or_create.call_args.kwargs
        assert call_kwargs["github_username"] == "mixedcase"


@pytest.mark.unit
class TestLogoutRoute:
    """Tests for POST /auth/logout."""

    async def test_logout_clears_session_and_redirects(self):
        """Logout clears session data and redirects to /."""
        request = _mock_request(session={"user_id": 42, "github_username": "testuser"})

        result = await logout(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
        assert request.session == {}

    async def test_logout_works_when_already_logged_out(self):
        """Logout on an empty session still succeeds."""
        request = _mock_request(session={})

        result = await logout(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"
