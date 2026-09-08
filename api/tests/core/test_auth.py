"""Tests for session identities, authentication policies, and OAuth registration."""

import logging
from importlib import import_module, util
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from learn_to_cloud_shared.core.config import OAuthConfig
from learn_to_cloud_shared.models import User
from learn_to_cloud_shared.repositories.auth_session_repository import (
    ResolvedSession,
    SessionRejection,
)
from starlette.datastructures import State

from learn_to_cloud.core.auth import (
    AuthenticatedUser,
    AuthenticationRequired,
    CurrentUser,
    IdentityRejectionReason,
    OptionalCurrentUser,
    init_oauth,
    oauth,
    optional_authenticated_account,
    optional_authenticated_user,
    require_authenticated_account,
    require_authenticated_user,
    validate_identity,
)
from learn_to_cloud.core.session_cookies import AUTH_COOKIE_NAME


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
    request.session = session if session is not None else {}
    request.headers = headers or {}
    request.state = State()
    request.cookies = {}
    return request


@pytest.mark.unit
class TestOptionalAuthenticatedAccount:
    """Test session account resolution."""

    async def test_loaded_account_is_cached_without_duplicate_identity_state(self):
        request = _make_request()
        request.cookies[AUTH_COOKIE_NAME] = "A" * 43
        account = User(id=42, github_username="current-name")
        db = AsyncMock()
        transaction = AsyncMock()
        db.begin = MagicMock(return_value=transaction)
        request.app.state.session_maker.return_value.__aenter__ = AsyncMock(
            return_value=db
        )
        with patch(
            "learn_to_cloud.core.auth.AuthSessionRepository", autospec=True
        ) as repository:
            repository.return_value.resolve_and_touch.return_value = ResolvedSession(
                session=MagicMock(), user=account
            )
            assert await optional_authenticated_account(request) is account
            transaction.__aexit__.assert_awaited_once_with(None, None, None)
            request.app.state.session_maker.return_value.__aexit__.assert_awaited_once()
            assert await optional_authenticated_account(request) is account
            assert require_authenticated_account(account) is account
            assert (
                require_authenticated_user(account)
                == optional_authenticated_user(account)
                == AuthenticatedUser(42, "current-name")
            )
            repository.return_value.resolve_and_touch.assert_awaited_once()
        assert request.state.auth_account is account
        assert not hasattr(request.state, "user_id")
        assert not hasattr(request.state, "github_username")

    @pytest.mark.parametrize("path", ["/optional", "/required", "/both"])
    async def test_one_account_override_serves_optional_and_required_paths(self, path):
        app = FastAPI()
        account = User(id=42, github_username="current-name")
        calls = []

        def account_source():
            calls.append(account)
            return account

        @app.get("/optional")
        async def optional(user: OptionalCurrentUser):
            return user

        @app.get("/required")
        async def required(user: CurrentUser):
            return user

        @app.get("/both")
        async def both(optional: OptionalCurrentUser, required: CurrentUser):
            assert optional == required
            return required

        app.dependency_overrides[optional_authenticated_account] = account_source
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get(path)

        assert response.status_code == 200
        assert response.json() == {"user_id": 42, "github_username": "current-name"}
        assert calls == [account]

    @pytest.mark.parametrize("failure", ["lookup", "commit"])
    async def test_store_failure_is_not_cached_as_anonymous(self, failure):
        request = _make_request()
        request.cookies[AUTH_COOKIE_NAME] = "A" * 43
        db = AsyncMock()
        transaction = AsyncMock()
        db.begin = MagicMock(return_value=transaction)
        request.app.state.session_maker.return_value.__aenter__ = AsyncMock(
            return_value=db
        )
        with patch(
            "learn_to_cloud.core.auth.AuthSessionRepository", autospec=True
        ) as repository:
            operation = (
                repository.return_value.resolve_and_touch
                if failure == "lookup"
                else transaction.__aexit__
            )
            operation.side_effect = RuntimeError("store unavailable")
            for _ in range(2):
                with pytest.raises(RuntimeError, match="store unavailable"):
                    await optional_authenticated_account(request)
                assert not getattr(request.state, "auth_resolved", False)
                assert not hasattr(request.state, "user_id")
                assert not hasattr(request.state, "clear_auth_cookie")
            assert repository.return_value.resolve_and_touch.await_count == 2

    @pytest.mark.parametrize("reason", list(SessionRejection))
    async def test_store_rejection_severity_and_request_cache(self, reason, caplog):
        request = _make_request()
        request.cookies[AUTH_COOKIE_NAME] = "A" * 43
        db = AsyncMock()
        db.begin = MagicMock(return_value=AsyncMock())
        request.app.state.session_maker.return_value.__aenter__ = AsyncMock(
            return_value=db
        )
        caplog.set_level(logging.INFO)
        with patch(
            "learn_to_cloud.core.auth.AuthSessionRepository", autospec=True
        ) as repository:
            repository.return_value.resolve_and_touch.return_value = reason
            assert await optional_authenticated_account(request) is None
            assert await optional_authenticated_account(request) is None
            repository.return_value.resolve_and_touch.assert_awaited_once()
        (record,) = caplog.records
        assert record.getMessage() == "auth.session.rejected"
        assert record.__dict__["auth.session.reason"] == reason.value
        assert record.levelno == (
            logging.WARNING
            if reason == SessionRejection.ACCOUNT_MISSING
            else logging.INFO
        )
        assert request.state.clear_auth_cookie is True

    @pytest.mark.parametrize("user_id", [1, 42, 2**63 - 1])
    async def test_legacy_identity_never_authenticates(self, user_id):
        request = _make_request(
            session={"user_id": user_id, "github_username": "testuser"}
        )
        result = await optional_authenticated_account(request)
        assert result is None
        assert request.session == {}

    async def test_returns_none_without_username(self):
        request = _make_request(session={"user_id": 42})
        result = await optional_authenticated_account(request)
        assert result is None

    @pytest.mark.parametrize("username", [None, "", 42, []])
    async def test_returns_none_for_invalid_username(self, username):
        request = _make_request(session={"user_id": 42, "github_username": username})
        assert await optional_authenticated_account(request) is None

    @pytest.mark.parametrize(
        "session",
        [
            {},
            {"github_username": "testuser"},
            {"user_id": None, "github_username": "testuser"},
        ],
    )
    async def test_returns_none_when_user_id_missing(self, session):
        request = _make_request(session=session)
        result = await optional_authenticated_account(request)
        assert result is None


@pytest.mark.unit
class TestValidateIdentity:
    @pytest.mark.parametrize(
        "user_id",
        [
            True,
            False,
            42.0,
            42.5,
            "42",
            "private-invalid-id",
            None,
            [],
            {},
            0,
            -1,
            2**63,
        ],
    )
    def test_rejects_invalid_ids_without_coercion(self, user_id):
        assert (
            validate_identity(user_id, "testuser")
            == IdentityRejectionReason.INVALID_USER_ID
        )

    @pytest.mark.parametrize(
        "username",
        [
            None,
            True,
            42,
            [],
            {},
            "",
            " ",
            "\t\r\n",
            "\u2003",
            "a" * 256,
            "private\x00name",
            "private\ud800name",
        ],
    )
    def test_rejects_unusable_usernames(self, username):
        assert (
            validate_identity(42, username)
            == IdentityRejectionReason.INVALID_GITHUB_USERNAME
        )

    @pytest.mark.parametrize(
        "username",
        ["a", "a" * 255, "\u00e9" * 255, "MiXeD", "name_company", " user ", "a.b"],
    )
    def test_preserves_names_without_signup_rules(self, username):
        assert validate_identity(42, username) == AuthenticatedUser(42, username)


@pytest.mark.unit
class TestSessionIdentityCleanup:
    @pytest.mark.parametrize(
        ("identity", "reason"),
        [
            ({"user_id": 42}, "incomplete_identity"),
            ({"github_username": "private-name"}, "incomplete_identity"),
            ({"user_id": None, "github_username": "private-name"}, "invalid_user_id"),
            ({"user_id": "private-id", "github_username": []}, "invalid_user_id"),
            ({"user_id": 42, "github_username": "\ud800"}, "invalid_github_username"),
        ],
    )
    async def test_cleans_in_place_preserves_oauth_and_logs_once(
        self, caplog, identity, reason
    ):
        caplog.set_level(logging.INFO)
        unrelated = {"_state_github_probe": {"data": {"state": "private-state"}}}
        session = {**unrelated, **identity}
        request = _make_request(session)
        assert await optional_authenticated_account(request) is None
        assert request.session is session
        assert session == unrelated
        assert not hasattr(request.state, "user_id")
        assert not hasattr(request.state, "github_username")
        assert await optional_authenticated_account(request) is None
        (record,) = caplog.records
        assert record.getMessage() == "auth.session.rejected"
        assert record.__dict__["auth.session.reason"] == "legacy"
        assert record.args == ()
        assert record.exc_info is None
        assert (
            not {"user_id", "github_username", "session", "cookie"}
            & record.__dict__.keys()
        )

    @pytest.mark.parametrize(
        "session", [{}, {"_state_github_probe": {"data": {"state": "private-state"}}}]
    )
    async def test_absent_identity_does_not_mutate_or_log(self, caplog, session):
        original = session.copy()
        assert await optional_authenticated_account(_make_request(session)) is None
        assert session == original
        assert caplog.records == []

    async def test_complete_legacy_identity_is_removed(self, caplog):
        session = {"user_id": 42, "github_username": "MiXeD", "other": "private-state"}
        assert await optional_authenticated_account(_make_request(session)) is None
        assert session == {"other": "private-state"}


@pytest.mark.unit
class TestRequireAuthenticatedUser:
    """Test require_authenticated_user dependency."""

    def test_returns_identity(self):
        account = User(id=42, github_username="testuser")
        assert require_authenticated_account(account) is account
        result = require_authenticated_user(account)
        assert result == AuthenticatedUser(user_id=42, github_username="testuser")

    @pytest.mark.parametrize("session", [{}, {"user_id": 42}])
    @pytest.mark.parametrize("htmx", [False, True])
    async def test_raises_401_when_unauthenticated(self, session, htmx):
        request = _make_request(
            session=session, headers={"hx-request": "true"} if htmx else {}
        )
        with pytest.raises(AuthenticationRequired) as exc_info:
            require_authenticated_account(await optional_authenticated_account(request))
        assert exc_info.value.status_code == 401
        assert exc_info.value.headers is None


@pytest.mark.unit
class TestOptionalAuthenticatedUser:
    """Test optional_authenticated_user dependency."""

    def test_returns_identity(self):
        result = optional_authenticated_user(User(id=99, github_username="user"))
        assert result == AuthenticatedUser(user_id=99, github_username="user")

    def test_returns_none_when_not_authenticated(self):
        assert optional_authenticated_user(None) is None


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
