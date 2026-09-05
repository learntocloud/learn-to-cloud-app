"""Authentication contracts through real routes and signed-cookie middleware."""

import json
import logging
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner
from learn_to_cloud_shared.core.database import get_db
from learn_to_cloud_shared.models import User
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware

from learn_to_cloud.core.auth import SESSION_COOKIE_NAME, CurrentUser
from learn_to_cloud.core.middleware import TelemetrySanitizationMiddleware
from learn_to_cloud.core.routing import LoginRedirectRoute
from learn_to_cloud.routes import (
    auth_router,
    htmx_router,
    pages_router,
    users_router,
)

pytestmark = pytest.mark.unit

_SECRET = "auth-http-test-only-secret"
_PAGE_PATHS = [
    "/phase/1",
    "/phase/1/introduction",
    "/dashboard",
    "/account",
    "/verifications",
    "/verifications/phase/1",
]
_INVALID_IDENTITIES = (
    [
        pytest.param(
            {"user_id": value, "github_username": "private-name"}, id=f"id-{index}"
        )
        for index, value in enumerate(
            [True, False, 42.0, 42.5, "42", "private-id", None, [], {}, 0, -1, 2**63]
        )
    ]
    + [
        pytest.param({"user_id": 42, "github_username": value}, id=f"name-{index}")
        for index, value in enumerate(
            [
                None,
                True,
                [],
                {},
                "",
                "\t \u2003",
                "a" * 256,
                "private\x00name",
                "private\ud800name",
            ]
        )
    ]
    + [
        pytest.param({"user_id": 42}, id="missing-name"),
        pytest.param({"github_username": "private-name"}, id="missing-id"),
    ]
)


def _session_cookie(session: dict, *, expired: bool = False) -> str:
    payload = b64encode(json.dumps(session).encode())
    timestamp = int(time()) - (120 if expired else 0)
    with patch.object(TimestampSigner, "get_timestamp", return_value=timestamp):
        return TimestampSigner(_SECRET).sign(payload).decode()


@pytest.fixture
def user():
    return User(
        id=42,
        display_name="Test User",
        github_username="testuser",
        avatar_url=None,
        is_admin=False,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def api_services(user):
    with (
        patch(
            "learn_to_cloud.routes.users_routes.get_user_by_id",
            autospec=True,
            return_value=user,
        ) as get_user,
        patch(
            "learn_to_cloud.routes.users_routes.delete_user_account",
            autospec=True,
        ) as delete_user,
    ):
        yield get_user, delete_user


@pytest.fixture
def github():
    with patch("learn_to_cloud.routes.auth_routes.oauth") as oauth:
        client = oauth.create_client.return_value
        client.authorize_redirect = AsyncMock(
            return_value=RedirectResponse("/oauth-finished", status_code=302)
        )
        yield client


@pytest.fixture
def app(test_settings, user, api_services, github):
    app = FastAPI()
    app.add_middleware(TelemetrySanitizationMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=_SECRET,
        session_cookie=SESSION_COOKIE_NAME,
        max_age=60,
    )
    for router in (auth_router, users_router, htmx_router, pages_router):
        app.include_router(router)

    @app.get("/oauth-finished")
    async def oauth_finished():
        return PlainTextResponse("Login reached with GET")

    browser_router = APIRouter(route_class=LoginRedirectRoute)

    @browser_router.post("/browser-mutation")
    @browser_router.delete("/browser-mutation")
    async def browser_mutation(current_user: CurrentUser):
        return PlainTextResponse(str(current_user.user_id))

    @browser_router.get("/unrelated-error/{status_code:int}")
    async def unrelated_error(status_code: int):
        raise HTTPException(status_code=status_code, detail="Unrelated error")

    app.include_router(browser_router)

    async def database():
        yield AsyncMock()

    app.dependency_overrides[get_db] = database
    with (
        patch(
            "learn_to_cloud.routes.auth_routes.get_web_settings",
            return_value=test_settings,
        ),
        patch(
            "learn_to_cloud.routes.pages_routes.get_user_by_id",
            autospec=True,
            return_value=user,
        ) as page_user,
        patch(
            "learn_to_cloud.routes.pages_routes.get_curriculum_overview",
            return_value=(),
        ),
    ):
        app.state.page_user = page_user
        yield app


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        yield http


@pytest.fixture
async def telemetry_client(app):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client, exporter
    finally:
        FastAPIInstrumentor.uninstrument_app(app)
        provider.shutdown()


@pytest.fixture
def telemetry_logs():
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield exporter
    finally:
        root.removeHandler(handler)
        handler.close()
        provider.shutdown()


def _exported_telemetry(span_exporter, log_exporter, caplog):
    from learn_to_cloud_shared.core.logger import _json_formatter

    return "\n".join(
        [span.to_json() for span in span_exporter.get_finished_spans()]
        + [record.to_json() for record in log_exporter.get_finished_logs()]
        + [_json_formatter().format(record) for record in caplog.records]
    )


@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("accept", [None, "application/json", "text/html"])
@pytest.mark.parametrize("htmx", [False, True])
async def test_api_auth_failure(client, api_services, method, accept, htmx):
    client.headers.pop("accept", None)
    headers = {"HX-Request": "true"} if htmx else {}
    if accept is not None:
        headers["Accept"] = accept
    response = await client.request(
        method, "/api/user/me", headers=headers, follow_redirects=True
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert "location" not in response.headers
    assert response.history == []
    for service in api_services:
        service.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "path", "data"),
    [
        ("GET", "/htmx/verification/attempts/status?token=test", None),
        ("POST", "/htmx/github/submit", None),
        (
            "POST",
            "/htmx/steps/complete",
            {"step_uuid": "00000000-0000-0000-0000-000000000001"},
        ),
        ("DELETE", "/htmx/account", None),
    ],
)
@pytest.mark.parametrize("htmx", [False, True])
async def test_htmx_endpoint_auth_failure(client, method, path, data, htmx):
    response = await client.request(
        method,
        path,
        data=data,
        headers={"HX-Request": "true"} if htmx else {},
        follow_redirects=True,
    )
    assert response.status_code == 401
    assert "location" not in response.headers
    assert response.history == []


@pytest.mark.parametrize("path", _PAGE_PATHS)
async def test_browser_pages_follow_login_with_get(client, github, path):
    response = await client.get(path, follow_redirects=True)
    first, login = response.history
    assert first.status_code == 303
    assert first.headers["location"] == "/auth/login"
    assert login.request.url.path == "/auth/login"
    assert login.request.method == "GET"
    assert response.status_code == 200
    assert response.request.method == "GET"
    assert response.request.url.path == "/oauth-finished"
    github.authorize_redirect.assert_awaited_once()


@pytest.mark.parametrize("path", _PAGE_PATHS)
@pytest.mark.parametrize("boosted", [False, True])
async def test_htmx_browser_navigation_returns_401(client, github, path, boosted):
    headers = {"HX-Request": "true"}
    if boosted:
        headers["HX-Boosted"] = "true"
    response = await client.get(path, headers=headers, follow_redirects=True)
    assert response.status_code == 401
    assert "location" not in response.headers
    assert response.history == []
    github.authorize_redirect.assert_not_awaited()


@pytest.mark.parametrize("htmx", [False, True])
async def test_incomplete_session_requires_login_on_browser_page(client, htmx):
    client.cookies.set(
        SESSION_COOKIE_NAME,
        _session_cookie({"user_id": 42}),
        domain="testserver.local",
        path="/",
    )
    response = await client.get(
        "/account", headers={"HX-Request": "true"} if htmx else {}
    )
    assert response.status_code == (401 if htmx else 303)
    assert response.headers.get("location") == (None if htmx else "/auth/login")


@pytest.mark.parametrize("status_code", [401, 403, 422, 500])
async def test_page_policy_does_not_redirect_unrelated_errors(
    client, github, status_code
):
    response = await client.get(
        f"/unrelated-error/{status_code}", follow_redirects=True
    )
    assert response.status_code == status_code
    assert response.json() == {"detail": "Unrelated error"}
    assert "location" not in response.headers
    assert response.history == []
    github.authorize_redirect.assert_not_awaited()


@pytest.mark.parametrize("method", ["POST", "DELETE"])
async def test_browser_mutation_redirect_changes_method_to_get(client, method):
    response = await client.request(method, "/browser-mutation", follow_redirects=True)
    first, login = response.history
    assert first.request.method == method
    assert first.status_code == 303
    assert first.headers["location"] == "/auth/login"
    assert login.request.url.path == "/auth/login"
    assert login.request.method == "GET"
    assert response.status_code == 200
    assert response.request.method == "GET"


@pytest.mark.parametrize(
    "cookie_kind", ["missing", "valid", "stale", "expired", "invalid"]
)
async def test_logout_expires_cookie_and_is_repeatable(client, github, cookie_kind):
    if cookie_kind != "missing":
        session = {"user_id": 42}
        if cookie_kind != "stale":
            session["github_username"] = "testuser"
        cookie = (
            "invalid-signature"
            if cookie_kind == "invalid"
            else _session_cookie(session, expired=cookie_kind == "expired")
        )
        client.cookies.set(
            SESSION_COOKIE_NAME, cookie, domain="testserver.local", path="/"
        )

    for _ in range(2):
        response = await client.post("/auth/logout", follow_redirects=True)
        (logout,) = response.history
        assert logout.request.method == "POST"
        assert logout.status_code == 303
        assert logout.headers["location"] == "/"
        cookies = logout.headers.get_list("set-cookie")
        assert cookies
        for header in cookies:
            expired = SimpleCookie(header)[SESSION_COOKIE_NAME]
            assert expired["path"] == "/"
            assert expired["httponly"]
            assert expired["samesite"] == "lax"
            assert expired["max-age"] == "0" or "1970" in expired["expires"]
        assert SESSION_COOKIE_NAME not in client.cookies
        assert response.status_code == 200
        assert response.request.method == "GET"
        assert response.request.url.path == "/"
    github.authorize_redirect.assert_not_awaited()


@pytest.mark.parametrize("path", ["/api/user/me", "/account"])
async def test_signed_session_authenticates_real_routes(client, path):
    client.cookies.set(
        SESSION_COOKIE_NAME,
        _session_cookie({"user_id": 42, "github_username": "testuser"}),
        domain="testserver.local",
        path="/",
    )
    response = await client.get(path, follow_redirects=True)
    assert response.status_code == 200
    assert response.history == []
    if path == "/api/user/me":
        assert response.json()["id"] == 42
    else:
        assert "testuser" in response.text


async def test_authenticated_api_delete_keeps_204_contract(client, api_services):
    client.cookies.set(
        SESSION_COOKIE_NAME,
        _session_cookie({"user_id": 42, "github_username": "testuser"}),
        domain="testserver.local",
        path="/",
    )
    response = await client.delete("/api/user/me", follow_redirects=True)
    assert response.status_code == 204
    assert response.content == b""
    assert response.history == []
    assert SESSION_COOKIE_NAME not in client.cookies
    api_services[1].assert_awaited_once()


@pytest.mark.parametrize("identity", _INVALID_IDENTITIES)
@pytest.mark.parametrize("preserve_oauth", [False, True])
@pytest.mark.parametrize(
    ("path", "htmx", "status"),
    [
        ("/", False, 200),
        ("/curriculum", False, 200),
        ("/api/user/me", False, 401),
        ("/account", False, 303),
        ("/account", True, 401),
        ("/htmx/verification/attempts/status?token=private-token", False, 401),
        ("/htmx/verification/attempts/status?token=private-token", True, 401),
    ],
)
async def test_malformed_identity_is_cleaned_over_http(
    client, app, api_services, caplog, identity, preserve_oauth, path, htmx, status
):
    unrelated = (
        {"_state_github_probe": {"data": {"state": "private-oauth-state"}}}
        if preserve_oauth
        else {}
    )
    client.cookies.set(
        SESSION_COOKIE_NAME,
        _session_cookie({**unrelated, **identity}),
        domain="testserver.local",
        path="/",
    )
    headers = {"HX-Request": "true"} if htmx else {}

    response = await client.get(path, headers=headers)

    assert response.status_code == status
    assert response.headers.get("location") == (
        "/auth/login" if status == 303 else None
    )
    assert response.headers.get_list("set-cookie")
    if preserve_oauth:
        cookie = client.cookies.get(SESSION_COOKIE_NAME)
        cleaned = json.loads(b64decode(TimestampSigner(_SECRET).unsign(cookie)))
        assert cleaned == unrelated
    else:
        assert SESSION_COOKIE_NAME not in client.cookies
        expired = SimpleCookie(response.headers["set-cookie"])[SESSION_COOKIE_NAME]
        assert "1970" in expired["expires"]
    for service in api_services:
        service.assert_not_awaited()
    app.state.page_user.assert_not_awaited()

    again = await client.get(path, headers=headers)
    assert again.status_code == status
    assert "set-cookie" not in again.headers
    (record,) = [r for r in caplog.records if r.name == "learn_to_cloud.core.auth"]
    assert record.getMessage() == "auth.session.identity_rejected"
    assert record.args == ()
    assert record.exc_info is None
    assert set(key for key in record.__dict__ if key.startswith("auth.")) == {
        "auth.identity.reason"
    }


@pytest.mark.parametrize(
    "kind", ["missing", "valid", "expired", "tampered", "oauth-only"]
)
@pytest.mark.parametrize("path", ["/", "/curriculum", "/api/user/me", "/account"])
async def test_session_cookie_lifecycle_on_real_routes(client, caplog, kind, path):
    if kind != "missing":
        session = (
            {"_state_github_probe": {"data": {"state": "private-state"}}}
            if kind == "oauth-only"
            else {"user_id": 42, "github_username": "testuser"}
        )
        cookie = _session_cookie(session, expired=kind == "expired")
        if kind == "tampered":
            payload, timestamp, signature = cookie.split(".")
            cookie = ".".join((payload, timestamp, "a" if signature != "a" else "b"))
        client.cookies.set(
            SESSION_COOKIE_NAME, cookie, domain="testserver.local", path="/"
        )
    response = await client.get(path)
    status = 200
    if kind != "valid" and path == "/api/user/me":
        status = 401
    elif kind != "valid" and path == "/account":
        status = 303
    assert response.status_code == status
    assert "set-cookie" not in response.headers
    assert not [r for r in caplog.records if r.name == "learn_to_cloud.core.auth"]


@pytest.fixture
def oauth_callback(app, github, user):
    database = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = database
    context.__aexit__.return_value = False
    app.state.session_maker = MagicMock(return_value=context)
    github.authorize_access_token = AsyncMock(
        return_value={"access_token": "private-oauth-token"}
    )
    github.get = AsyncMock(
        return_value=httpx2.Response(
            200,
            json={"id": 42, "login": "TestUser"},
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )
    )
    with patch(
        "learn_to_cloud.routes.auth_routes.get_or_create_user_from_github",
        autospec=True,
        return_value=user,
    ) as upsert:
        yield database, upsert


async def test_oauth_issued_cookie_authenticates_next_request(client, oauth_callback):
    database, upsert = oauth_callback
    unrelated = {"_state_github_other": {"data": {"state": "private-other-state"}}}
    client.cookies.set(
        SESSION_COOKIE_NAME,
        _session_cookie(unrelated),
        domain="testserver.local",
        path="/",
    )
    response = await client.get("/auth/callback")
    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"
    cookie = client.cookies.get(SESSION_COOKIE_NAME)
    identity = json.loads(b64decode(TimestampSigner(_SECRET).unsign(cookie)))
    assert identity == {**unrelated, "user_id": 42, "github_username": "testuser"}
    database.commit.assert_awaited_once()
    assert upsert.call_args.kwargs["github_id"] == identity["user_id"]
    assert upsert.call_args.kwargs["github_username"] == identity["github_username"]
    authenticated = await client.get("/api/user/me")
    assert authenticated.status_code == 200
    assert authenticated.json()["id"] == 42


async def test_oauth_invariant_failure_remains_500(app, oauth_callback, user, caplog):
    database, _ = oauth_callback
    user.id = 43
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/auth/callback")
    assert response.status_code == 500
    assert "set-cookie" not in response.headers
    assert "location" not in response.headers
    database.commit.assert_not_awaited()
    assert "auth.callback.identity_rejected" not in caplog.text
    assert "auth.login.success" not in caplog.text


@pytest.mark.parametrize(
    ("profile", "expected", "warns"),
    [
        ({}, None, False),
        ({"name": None}, None, False),
        ({"name": ""}, None, False),
        ({"name": "\t \u2003\n"}, None, False),
        (
            {"name": "  Profile-Sentinel 李 e\u0301 🛰️  "},
            "  Profile-Sentinel 李 e\u0301 🛰️  ",
            False,
        ),
        ({"name": {"value": "Profile-Sentinel"}}, None, True),
        ({"name": "Profile-Sentinel\x00"}, None, True),
        ({"name": "Profile-Sentinel\ud800"}, None, True),
    ],
)
@pytest.mark.parametrize("failure", [None, "upsert", "commit"])
@pytest.mark.parametrize("error_kind", ["parameters", "driver_detail", "chain"])
async def test_callback_profile_privacy_and_session_contract(
    app,
    telemetry_client,
    telemetry_logs,
    github,
    user,
    caplog,
    profile,
    expected,
    warns,
    failure,
    error_kind,
):
    from learn_to_cloud.main import global_exception_handler

    app.add_exception_handler(Exception, global_exception_handler)
    _, exporter = telemetry_client
    caplog.set_level(logging.INFO)
    database = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = database
    context.__aexit__.return_value = False
    app.state.session_maker = MagicMock(return_value=context)
    github.authorize_access_token = AsyncMock(
        return_value={"access_token": "private-token"}
    )
    # json.dumps also represents malformed Unicode safely on the wire.
    github.get = AsyncMock(
        return_value=httpx2.Response(
            200,
            content=json.dumps({"id": 42, "login": "TestUser", **profile}).encode(),
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )
    )
    user.display_name = expected
    with patch(
        "learn_to_cloud.services.users_service.UserRepository", autospec=True
    ) as repository:
        upsert = repository.return_value.upsert
        upsert.return_value = user
        if failure:
            operation = upsert if failure == "upsert" else database.commit
            error = OperationalError(
                "UPDATE users SET display_name = :name",
                {"name": "Profile-Sentinel"},
                RuntimeError(
                    "Driver DETAIL: Profile-Sentinel"
                    if error_kind == "driver_detail"
                    else "Synthetic persistence failure"
                ),
                hide_parameters=error_kind != "parameters",
            )
            if error_kind == "chain":
                error.__cause__ = RuntimeError("Driver cause: Profile-Sentinel")
                error.__context__ = RuntimeError("Driver context: Profile-Sentinel")
            operation.side_effect = error
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/auth/callback")
            if failure:
                assert response.status_code == 500
                assert "set-cookie" not in response.headers
                assert SESSION_COOKIE_NAME not in client.cookies
                assert "auth.login.success" not in caplog.text
                assert "unhandled.exception" in caplog.text
                assert "Profile persistence failed (OperationalError)" in caplog.text
                assert response.json() == {
                    "detail": "An unexpected error occurred. Please try again."
                }
                if failure == "upsert":
                    database.commit.assert_not_awaited()
            else:
                assert response.status_code == 302
                assert response.headers["location"] == "/dashboard"
                database.commit.assert_awaited_once()
                cookie = client.cookies.get(SESSION_COOKIE_NAME)
                assert cookie is not None
                payload = json.loads(b64decode(TimestampSigner(_SECRET).unsign(cookie)))
                assert payload == {"user_id": 42, "github_username": "testuser"}
                assert "Profile-Sentinel" not in repr(payload)
                me = await client.get("/api/user/me")
                assert me.status_code == 200
                assert me.json() == {
                    "id": 42,
                    "github_username": "testuser",
                    "display_name": expected,
                    "avatar_url": None,
                    "is_admin": False,
                    "created_at": "2024-01-01T00:00:00Z",
                }
                assert "auth.login.success" in caplog.text
        upsert.assert_awaited_once_with(
            42, github_username="testuser", display_name=expected, avatar_url=None
        )
    warnings = [
        r
        for r in caplog.records
        if r.getMessage() == "auth.callback.display_name_ignored"
    ]
    assert len(warnings) == int(warns)
    for record in warnings:
        assert record.args == ()
        assert record.exc_info is None
        assert not any(key.startswith("auth.") for key in record.__dict__)
    assert "auth.callback.identity_rejected" not in caplog.text
    spans = exporter.get_finished_spans()
    assert any(span.kind == SpanKind.SERVER for span in spans)
    telemetry = _exported_telemetry(exporter, telemetry_logs, caplog)
    assert "Profile-Sentinel" not in telemetry
    for span in spans:
        assert (
            not {"display_name", "first_name", "last_name", "user.display_name"}
            & span.attributes.keys()
        )


@pytest.mark.integration
@pytest.mark.parametrize("failure", ["upsert", "commit"])
async def test_callback_instrumented_postgres_failure_is_private(
    app, github, test_engine, test_settings, telemetry_logs, caplog, failure
):
    from learn_to_cloud_shared.core.database import (
        create_engine,
        create_session_maker,
    )

    from learn_to_cloud.main import global_exception_handler

    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine.Engine")
    app.add_exception_handler(Exception, global_exception_handler)
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrumentor = SQLAlchemyInstrumentor()
    # Use the production engine factory and its listener ordering, with only
    # the telemetry destination replaced by an in-memory exporter.
    with patch(
        "learn_to_cloud_shared.core.database.instrument_database",
        side_effect=lambda engine: instrumentor.instrument(
            engine=engine.sync_engine, tracer_provider=provider
        ),
    ):
        engine = create_engine(test_settings.database)
    assert engine.sync_engine.hide_parameters is True
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    github.authorize_access_token = AsyncMock(return_value={"access_token": "token"})
    github.get = AsyncMock(
        return_value=httpx2.Response(
            200,
            json={"id": 42, "login": "TestUser", "name": "Profile-Sentinel"},
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )
    )
    try:
        async with engine.connect() as connection:
            # All writes target a connection-local table, never real users.
            await connection.execute(
                text("CREATE TEMP TABLE users (LIKE public.users INCLUDING ALL)")
            )
            await connection.execute(
                text(
                    "INSERT INTO pg_temp.users "
                    "(id, github_username, display_name, is_admin, "
                    "created_at, updated_at) "
                    "VALUES (42, 'testuser', 'Before', false, now(), now())"
                )
            )
            if failure == "upsert":
                await connection.execute(
                    text(
                        "ALTER TABLE pg_temp.users ADD CHECK "
                        "(length(display_name) < 10)"
                    )
                )
            else:
                await connection.execute(
                    text(
                        "CREATE FUNCTION pg_temp.reject_profile() RETURNS trigger "
                        "LANGUAGE plpgsql AS $$ BEGIN "
                        "RAISE EXCEPTION '%', NEW.display_name "
                        "USING ERRCODE = '23514'; END $$"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE CONSTRAINT TRIGGER reject_profile "
                        "AFTER INSERT OR UPDATE ON pg_temp.users "
                        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
                        "EXECUTE FUNCTION pg_temp.reject_profile()"
                    )
                )
            await connection.commit()
        app.state.session_maker = create_session_maker(engine)
        exporter.clear()
        telemetry_logs.clear()
        caplog.clear()

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/auth/callback")
            assert response.status_code == 500
            assert response.json() == {
                "detail": "An unexpected error occurred. Please try again."
            }
            assert "set-cookie" not in response.headers
            assert SESSION_COOKIE_NAME not in client.cookies
        async with engine.connect() as connection:
            assert not connection.in_transaction()
            assert (
                await connection.scalar(
                    text("SELECT display_name FROM pg_temp.users WHERE id = 42")
                )
                == "Before"
            )
            assert await connection.scalar(text("SELECT 1")) == 1

            spans = exporter.get_finished_spans()
            assert any(
                span.kind == SpanKind.SERVER
                and span.status.status_code == StatusCode.ERROR
                for span in spans
            )
            writes = [
                span
                for span in spans
                if span.kind == SpanKind.CLIENT and span.name.startswith("INSERT")
            ]
            assert len(writes) == 1
            assert writes[0].status.status_code == (
                StatusCode.ERROR if failure == "upsert" else StatusCode.UNSET
            )
            if failure == "upsert":
                assert writes[0].status.description == (
                    "Profile persistence failed (IntegrityError)"
                )
            assert "unhandled.exception" in caplog.text
            assert "Profile persistence failed (IntegrityError)" in caplog.text
            assert "auth.login.success" not in caplog.text
            telemetry = _exported_telemetry(exporter, telemetry_logs, caplog)
            assert "Profile-Sentinel" not in telemetry
            await connection.rollback()
            await connection.execute(text("DROP TABLE pg_temp.users"))
            if failure == "commit":
                await connection.execute(text("DROP FUNCTION pg_temp.reject_profile()"))
            await connection.commit()
    finally:
        # Disposing closes the connection and drops pg_temp resources even
        # when an assertion fails before explicit cleanup.
        await engine.dispose()
        instrumentor.uninstrument()
        FastAPIInstrumentor.uninstrument_app(app)
        provider.shutdown()


async def test_profile_openapi_has_only_new_name_field(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    properties = response.json()["components"]["schemas"]["UserResponse"]["properties"]
    assert set(properties) == {
        "id",
        "github_username",
        "display_name",
        "avatar_url",
        "is_admin",
        "created_at",
    }
    assert properties["display_name"]["anyOf"] == [{"type": "string"}, {"type": "null"}]


@pytest.mark.parametrize(
    ("path", "htmx", "status"),
    [
        ("/", False, 200),
        ("/api/user/me", False, 401),
        ("/account", False, 303),
        ("/account", True, 401),
    ],
)
async def test_malformed_identity_telemetry_has_no_private_values(
    telemetry_client, caplog, path, htmx, status
):
    client, exporter = telemetry_client
    cookie = _session_cookie(
        {"user_id": "private-user-id", "github_username": "private-username"}
    )
    client.cookies.set(SESSION_COOKIE_NAME, cookie, domain="testserver.local", path="/")
    response = await client.get(
        path,
        params={"token": "private-token"},
        headers={"HX-Request": "true"} if htmx else {},
    )
    assert response.status_code == status
    spans = exporter.get_finished_spans()
    (server,) = [span for span in spans if span.kind == SpanKind.SERVER]
    assert server.status.status_code == StatusCode.UNSET
    assert server.attributes["http.route"] == path
    assert (
        server.attributes.get(
            "http.response.status_code", server.attributes.get("http.status_code")
        )
        == status
    )
    for attribute in ("http.target", "http.url", "url.full", "url.path"):
        assert server.attributes[attribute] == path
    assert server.attributes["url.query"] == ""
    for span in spans:
        assert not any(event.name == "exception" for event in span.events)
        assert (
            not {"user_id", "github_username", "user.id", "session.id"}
            & span.attributes.keys()
        )
    records = [r for r in caplog.records if r.name == "learn_to_cloud.core.auth"]
    assert len(records) == 1
    log_payload = json.dumps(records[0].__dict__, default=str)
    telemetry = "\n".join(span.to_json() for span in spans) + log_payload
    for prohibited in ("private-user-id", "private-username", "private-token", cookie):
        assert prohibited not in telemetry


@pytest.mark.parametrize(
    ("method", "path", "htmx", "authenticated", "status", "route"),
    [
        ("GET", "/api/user/me", False, False, 401, "/api/user/me"),
        ("DELETE", "/api/user/me", False, False, 401, "/api/user/me"),
        (
            "GET",
            "/phase/1/private-topic-probe",
            False,
            False,
            303,
            "/phase/{phase_id:int}/{topic_slug}",
        ),
        (
            "GET",
            "/phase/1/private-topic-probe",
            True,
            False,
            401,
            "/phase/{phase_id:int}/{topic_slug}",
        ),
        ("GET", "/account", False, True, 200, "/account"),
        ("GET", "/api/user/me", False, True, 200, "/api/user/me"),
        ("GET", "/private-unmatched-probe", False, False, 404, None),
    ],
)
async def test_auth_request_telemetry_is_bounded_and_has_no_exception_events(
    telemetry_client, method, path, htmx, authenticated, status, route
):
    client, exporter = telemetry_client
    cookie = _session_cookie({"user_id": 42, "github_username": "testuser"})
    if authenticated:
        client.cookies.set(
            SESSION_COOKIE_NAME, cookie, domain="testserver.local", path="/"
        )

    response = await client.request(
        method,
        path,
        params={"token": "private-token-probe"},
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == status
    spans = exporter.get_finished_spans()
    (server,) = [span for span in spans if span.kind == SpanKind.SERVER]
    attributes = server.attributes
    assert attributes.get("http.route") == route
    assert (
        attributes.get("http.response.status_code", attributes.get("http.status_code"))
        == status
    )
    assert server.status.status_code == StatusCode.UNSET
    for attribute in ("http.target", "http.url", "url.full", "url.path"):
        assert attributes[attribute] == (route or "/unmatched")
    assert attributes["url.query"] == ""

    for span in spans:
        assert not any(event.name == "exception" for event in span.events)
        assert not {"user_id", "github_username", "user.id", "session.id"} & set(
            span.attributes
        )
    telemetry = "\n".join(span.to_json() for span in spans)
    for prohibited in (
        "private-topic-probe",
        "private-unmatched-probe",
        "private-token-probe",
        "testuser",
        cookie,
    ):
        assert prohibited not in telemetry
