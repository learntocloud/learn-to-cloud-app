"""Authentication contracts through real routes and signed-cookie middleware."""

import json
from base64 import b64encode
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from time import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner
from learn_to_cloud_shared.core.database import get_db
from learn_to_cloud_shared.models import User
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
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


def _session_cookie(session: dict, *, expired: bool = False) -> str:
    payload = b64encode(json.dumps(session).encode())
    timestamp = int(time()) - (120 if expired else 0)
    with patch.object(TimestampSigner, "get_timestamp", return_value=timestamp):
        return TimestampSigner(_SECRET).sign(payload).decode()


@pytest.fixture
def user():
    return User(
        id=42,
        first_name="Test",
        last_name="User",
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

    @browser_router.api_route("/browser-mutation", methods=["POST", "DELETE"])
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
        ),
        patch(
            "learn_to_cloud.routes.pages_routes.get_curriculum_overview",
            return_value=(),
        ),
    ):
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
