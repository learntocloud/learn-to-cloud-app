"""Committed PostgreSQL credentials through independent HTTP applications."""

import asyncio
import json
import logging
import re
from base64 import b64decode, b64encode
from contextlib import asynccontextmanager
from datetime import timedelta
from time import time
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx2
import pytest
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner
from learn_to_cloud_shared.content_service import get_phase_by_slug
from learn_to_cloud_shared.models import AuthSession, User, VerificationAttempt
from learn_to_cloud_shared.repositories.auth_session_repository import (
    AuthSessionRepository,
)
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.submission_values import GitHubUrlValue
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from learn_to_cloud.core.auth import CurrentUser, get_authenticated_user_from_session
from learn_to_cloud.core.middleware import TelemetrySanitizationMiddleware
from learn_to_cloud.core.session_cookies import (
    AUTH_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SessionResponseMiddleware,
    token_digest,
)
from learn_to_cloud.main import global_exception_handler
from learn_to_cloud.routes import auth_router, htmx_router, pages_router, users_router
from learn_to_cloud.services.sessions_service import issue_session

pytestmark = pytest.mark.integration


def build_app(engine, settings):
    app = FastAPI()
    app.state.session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_middleware(TelemetrySanitizationMiddleware)
    app.add_middleware(SessionResponseMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session.secret_key,
        session_cookie=SESSION_COOKIE_NAME,
        max_age=settings.session.oauth_state_max_age_seconds,
    )
    for router in (auth_router, users_router, htmx_router, pages_router):
        app.include_router(router)

    @app.get("/health")
    @app.get("/static/probe")
    async def untouched():
        return {"ok": True}

    @app.get("/reuse")
    async def reuse(request: Request, current_user: CurrentUser):
        again = await get_authenticated_user_from_session(request)
        assert again is current_user
        return {"id": again.user_id}

    return app


@pytest.fixture
async def session_apps(test_engine, test_settings):
    apps = (
        build_app(test_engine, test_settings),
        build_app(test_engine, test_settings),
    )
    async with apps[0].state.session_maker() as db, db.begin():
        db.add_all(
            [
                User(id=42, github_username="testuser"),
                User(id=43, github_username="unrelated"),
            ]
        )
    with (
        patch("learn_to_cloud.core.auth.get_web_settings", return_value=test_settings),
        patch(
            "learn_to_cloud.core.session_cookies.get_web_settings",
            return_value=test_settings,
        ),
        patch(
            "learn_to_cloud.services.sessions_service.get_web_settings",
            return_value=test_settings,
        ),
        patch(
            "learn_to_cloud.routes.auth_routes.get_web_settings",
            return_value=test_settings,
        ),
        patch(
            "learn_to_cloud.services.community_service.get_latest_curriculum_commits",
            new=AsyncMock(return_value=[]),
        ),
    ):
        yield apps


async def mint(app, settings, user_id=42):
    async with app.state.session_maker() as db, db.begin():
        issued = await issue_session(db, settings.session, user_id)
    return issued.token


@asynccontextmanager
async def browser(app, token=None, *, raise_errors=True):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=raise_errors),
        base_url="http://testserver",
    ) as client:
        if token is not None:
            client.cookies.set(
                AUTH_COOKIE_NAME, token, domain="testserver.local", path="/"
            )
        yield client


async def csrf(client):
    response = await client.get("/account")
    assert response.status_code == 200
    assert 'hx-boost="false"' in response.text
    assert "including this one" in response.text
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match is not None
    return match[1]


async def test_current_logout_replay_cross_app_and_independent_browser(
    session_apps, test_settings
):
    first, second = session_apps
    original = await mint(first, test_settings)
    independent = await mint(second, test_settings)
    async with browser(first, original) as client:
        assert (await client.get("/api/user/me")).status_code == 200
        response = await client.post("/auth/logout")
        assert response.status_code == 303
        assert response.headers["cache-control"] == "private, no-store"
        assert AUTH_COOKIE_NAME not in client.cookies
        assert (await client.post("/auth/logout")).status_code == 303
    for app in session_apps:
        async with browser(app, original) as replay:
            response = await replay.get("/api/user/me")
            assert response.status_code == 401
            assert AUTH_COOKIE_NAME not in replay.cookies
    async with browser(second, independent) as client:
        assert (await client.get("/api/user/me")).status_code == 200


async def test_global_logout_csrf_all_browsers_and_later_login(
    session_apps, test_settings
):
    first, second = session_apps
    tokens = [await mint(app, test_settings) for app in session_apps]
    other = await mint(second, test_settings, 43)
    async with browser(first, tokens[0]) as client:
        confirmation = await csrf(client)
        for value in ("", "wrong", "é", tokens[0]):
            response = await client.post("/auth/logout-all", data={"csrf": value})
            assert response.status_code == 403
        async with browser(second, tokens[1]) as other_browser:
            assert (
                await other_browser.post(
                    "/auth/logout-all", data={"csrf": confirmation}
                )
            ).status_code == 403
        response = await client.post("/auth/logout-all", data={"csrf": confirmation})
        assert response.status_code == 303
        assert response.headers["location"] == "/"
    for token in tokens:
        async with browser(second, token) as replay:
            assert (await replay.get("/api/user/me")).status_code == 401
    for token in (other, await mint(first, test_settings)):
        async with browser(second, token) as client:
            assert (await client.get("/api/user/me")).status_code == 200


@pytest.mark.parametrize(
    "endpoint, status", [("/api/user/me", 204), ("/htmx/account", 200)]
)
async def test_delete_cascade_public_anonymous_and_recreation(
    session_apps, test_settings, endpoint, status
):
    first, second = session_apps
    tokens = [await mint(app, test_settings) for app in session_apps]
    async with browser(first, tokens[0]) as client:
        response = await client.delete(endpoint)
        assert response.status_code == status
        assert response.content == b""
        if endpoint == "/htmx/account":
            assert response.headers["HX-Redirect"] == "/"
        assert AUTH_COOKIE_NAME not in client.cookies
    async with browser(second, tokens[1]) as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert AUTH_COOKIE_NAME not in client.cookies
    async with first.state.session_maker() as db, db.begin():
        assert await db.get(User, 42) is None
        assert await db.get(User, 43) is not None
        db.add(User(id=42, github_username="recreated"))
    for token in tokens:
        async with browser(second, token) as replay:
            assert (await replay.get("/api/user/me")).status_code == 401
    async with browser(second, await mint(first, test_settings)) as client:
        assert (await client.get("/api/user/me")).json()[
            "github_username"
        ] == "recreated"


@pytest.mark.parametrize("expiry", ["idle", "absolute"])
async def test_server_expiry_overrides_browser_extension(
    session_apps, test_settings, expiry
):
    first, second = session_apps
    token = await mint(first, test_settings)
    values = (
        {
            "last_seen_at": func.statement_timestamp()
            - timedelta(seconds=test_settings.session.idle_timeout_seconds)
        }
        if expiry == "idle"
        else {"expires_at": func.statement_timestamp()}
    )
    async with first.state.session_maker() as db, db.begin():
        await db.execute(
            update(AuthSession)
            .where(AuthSession.token_digest == token_digest(token))
            .values(**values)
        )
    async with browser(second, token) as client:
        response = await client.get("/account")
        assert response.status_code == 303
        assert AUTH_COOKIE_NAME not in client.cookies


async def test_touch_once_reuses_account_and_skips_static_health(
    session_apps, test_settings, test_engine
):
    first, _ = session_apps
    token = await mint(first, test_settings)
    async with first.state.session_maker() as db, db.begin():
        await db.execute(
            update(AuthSession).values(
                last_seen_at=func.statement_timestamp() - timedelta(hours=1)
            )
        )
    async with first.state.session_maker() as db:
        before = await db.get(AuthSession, token_digest(token))
    queries = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        queries.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", record)
    try:
        async with browser(first, token) as client:
            for path in ("/static/probe", "/health"):
                assert (await client.get(path)).status_code == 200
            assert queries == []
            phase = get_phase_by_slug("phase1")
            assert phase is not None
            for path in (
                "/api/user/me",
                "/account",
                "/reuse",
                "/",
                "/curriculum",
                "/phase/1",
                f"/phase/1/{phase.topics[0].slug}",
                "/verifications",
                "/verifications/phase/1",
                "/dashboard",
                "/community",
                "/htmx/verification/attempts/status?token=invalid",
                "/faq",
                "/privacy",
                "/terms",
            ):
                queries.clear()
                response = await client.get(path)
                assert response.status_code == (
                    400 if path.startswith("/htmx/verification/attempts/") else 200
                )
                assert sum("UPDATE auth_sessions" in q for q in queries) == 1
                assert not any(q.startswith("SELECT users.") for q in queries)
                assert "Cookie" in response.headers["vary"]
            topic = next(topic for topic in phase.topics if topic.learning_steps)
            step = topic.learning_steps[0]
            for method, path, data in (
                ("POST", "/htmx/steps/complete", {"step_uuid": str(step.uuid)}),
                ("DELETE", f"/htmx/steps/{step.uuid}", None),
            ):
                queries.clear()
                response = await client.request(method, path, data=data)
                assert response.status_code == 200
                assert sum("UPDATE auth_sessions" in q for q in queries) == 1
                assert not any(q.startswith("SELECT users.") for q in queries)
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", record)
    async with first.state.session_maker() as db:
        after = await db.get(AuthSession, token_digest(token))
        assert after.last_seen_at > before.last_seen_at
        assert after.expires_at == before.expires_at
        assert after.created_at == before.created_at


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/user/me"),
        ("DELETE", "/api/user/me"),
        ("POST", "/htmx/steps/complete"),
        ("DELETE", "/htmx/steps/00000000-0000-0000-0000-000000000001"),
        ("POST", "/htmx/verifications/test/submit/derived"),
        ("POST", "/htmx/verifications/test/submit/value"),
        ("POST", "/htmx/verifications/test/submit/reflection"),
        ("POST", "/htmx/github/submit"),
        ("GET", "/htmx/verification/attempts/status?token=private-token"),
        ("DELETE", "/htmx/account"),
    ],
)
async def test_revoked_cookie_cannot_reach_protected_work(
    session_apps, test_settings, method, path
):
    first, second = session_apps
    token = await mint(first, test_settings)
    async with browser(first, token) as client:
        assert (await client.post("/auth/logout")).status_code == 303
    async with browser(second, token) as client:
        response = await client.request(method, path)
        assert response.status_code == 401
        assert AUTH_COOKIE_NAME not in client.cookies


async def test_no_connection_held_during_route_or_provider_work(
    session_apps, test_settings, test_engine
):
    first, _ = session_apps
    token = await mint(first, test_settings)
    active = 0

    def checked_out(*_args):
        nonlocal active
        active += 1

    def checked_in(*_args):
        nonlocal active
        active -= 1

    @first.get("/remote")
    async def remote(current_user: CurrentUser):
        assert active == 0
        await asyncio.sleep(0)
        assert active == 0
        return {"id": current_user.user_id}

    async def profile(*_args, **_kwargs):
        assert active == 0
        return httpx2.Response(
            200,
            json={"id": 42, "login": "testuser"},
            request=httpx2.Request("GET", "https://api.github.com/user"),
        )

    github = AsyncMock()
    github.get.side_effect = profile
    github.authorize_access_token.return_value = {"access_token": "private-token"}
    event.listen(test_engine.sync_engine, "checkout", checked_out)
    event.listen(test_engine.sync_engine, "checkin", checked_in)
    try:
        with patch("learn_to_cloud.routes.auth_routes.oauth") as oauth:
            oauth.create_client.return_value = github
            async with browser(first, token) as client:
                assert (await client.get("/remote")).status_code == 200
                assert (await client.get("/auth/callback")).status_code == 302
        assert active == 0
    finally:
        event.remove(test_engine.sync_engine, "checkout", checked_out)
        event.remove(test_engine.sync_engine, "checkin", checked_in)


@pytest.mark.parametrize("cookie", ["", "short", "x" * 5000, "é", "a" * 43])
async def test_malformed_cookie_has_no_database_lookup(session_apps, cookie):
    first, _ = session_apps
    # A noncanonical final base64 character must not be accepted.
    if cookie == "a" * 43:
        assert token_digest(cookie) is None
    with patch.object(
        first.state, "session_maker", side_effect=AssertionError("database called")
    ):
        async with browser(first) as client:
            response = await client.get(
                "/api/user/me",
                headers={b"cookie": f"{AUTH_COOKIE_NAME}={cookie}".encode("latin-1")},
            )
            assert response.status_code == 401


async def test_oauth_issues_rotates_preserves_states_and_releases_connections(
    session_apps, test_settings
):
    first, second = session_apps
    old = await mint(first, test_settings)
    states = {"_state_github_other": {"data": {"state": "other"}, "exp": time() + 600}}
    signed = (
        TimestampSigner(test_settings.session.secret_key)
        .sign(b64encode(json.dumps(states).encode()))
        .decode()
    )
    github = AsyncMock()
    github.authorize_access_token.return_value = {
        "access_token": "private-provider-token"
    }
    github.get.return_value = httpx2.Response(
        200,
        json={"id": 42, "login": "TestUser"},
        request=httpx2.Request("GET", "https://api.github.com/user"),
    )
    with patch("learn_to_cloud.routes.auth_routes.oauth") as oauth:
        oauth.create_client.return_value = github
        async with browser(first, old) as client:
            client.cookies.set(
                SESSION_COOKIE_NAME, signed, domain="testserver.local", path="/"
            )
            response = await client.get("/auth/callback")
            assert response.status_code == 302
            new = client.cookies.get(AUTH_COOKIE_NAME)
            assert len(new) == 43 and new != old
            assert client.cookies.get(SESSION_COOKIE_NAME) == signed
            assert "user_id" not in response.headers["set-cookie"]
            assert (await client.get("/api/user/me")).status_code == 200
    async with browser(second, old) as replay:
        assert (await replay.get("/api/user/me")).status_code == 401


@pytest.mark.parametrize("operation", ["lookup", "logout", "global", "delete"])
async def test_store_failure_is_500_not_anonymous_or_success(
    session_apps, test_settings, caplog, operation
):
    first, _ = session_apps
    token = await mint(first, test_settings)
    caplog.set_level(logging.INFO)
    async with browser(first, token, raise_errors=False) as client:
        confirmation = await csrf(client)
        with patch.object(
            first.state, "session_maker", side_effect=RuntimeError("store unavailable")
        ):
            if operation == "lookup":
                response = await client.get("/")
            elif operation == "logout":
                response = await client.post("/auth/logout")
            elif operation == "global":
                response = await client.post(
                    "/auth/logout-all", data={"csrf": confirmation}
                )
            else:
                response = await client.delete("/api/user/me")
        assert response.status_code == 500
        assert "location" not in response.headers
        assert "set-cookie" not in response.headers
        assert client.cookies.get(AUTH_COOKIE_NAME) == token
        assert (await client.get("/api/user/me")).status_code == 200
    assert "auth.session.revoked" not in caplog.text
    assert "user.account_deleted" not in caplog.text
    assert token not in caplog.text
    digest = token_digest(token)
    assert digest is not None
    assert digest.hex() not in caplog.text


async def test_concurrent_touch_logout_never_resurrects(session_apps, test_settings):
    first, second = session_apps
    token = await mint(first, test_settings)
    async with browser(first, token) as reader, browser(second, token) as logout:
        responses = await asyncio.gather(
            reader.get("/api/user/me"), logout.post("/auth/logout")
        )
        assert responses[0].status_code in (200, 401)
        assert responses[1].status_code == 303
    async with browser(first, token) as replay:
        assert (await replay.get("/api/user/me")).status_code == 401
    async with first.state.session_maker() as db:
        assert await db.get(AuthSession, token_digest(token)) is None


async def test_login_waits_for_account_global_revocation_order(
    session_apps, test_settings
):
    first, second = session_apps
    old = await mint(first, test_settings)
    acquired = asyncio.Event()
    release = asyncio.Event()

    async def revoke():
        async with first.state.session_maker() as db, db.begin():
            repo = AuthSessionRepository(db, test_settings.session)
            await repo.lock_user(42)
            acquired.set()
            await release.wait()
            await repo.delete_all(42)

    revocation = asyncio.create_task(revoke())
    await acquired.wait()
    issuance = asyncio.create_task(mint(second, test_settings))
    await asyncio.sleep(0.03)
    assert not issuance.done()
    release.set()
    await revocation
    new = await issuance
    async with browser(second, old) as client:
        assert (await client.get("/api/user/me")).status_code == 401
    async with browser(first, new) as client:
        assert (await client.get("/api/user/me")).status_code == 200


async def test_real_authlib_parallel_states_and_expired_wrong_callbacks(
    session_apps, test_settings
):
    app, _ = session_apps
    oauth = OAuth()
    github = oauth.register(
        "github",
        client_id="local-test",
        client_secret="local-test",
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
    )
    old = await mint(app, test_settings)
    with (
        patch("learn_to_cloud.routes.auth_routes.oauth", oauth),
        patch.object(
            github,
            "fetch_access_token",
            new=AsyncMock(return_value={"access_token": "private-token"}),
        ) as exchange,
        patch.object(
            github,
            "get",
            new=AsyncMock(
                return_value=httpx2.Response(
                    200,
                    json={"id": 42, "login": "testuser"},
                    request=httpx2.Request("GET", "https://api.github.com/user"),
                )
            ),
        ),
    ):
        async with browser(app, old) as client:
            states = []
            for _ in range(2):
                response = await client.get("/auth/login")
                states.append(
                    parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
                )
                assert "Max-Age=600" in response.headers["set-cookie"]
                assert AUTH_COOKIE_NAME not in response.headers["set-cookie"]
            assert github.framework.expires_in == 600
            signer = TimestampSigner(test_settings.session.secret_key)
            payload = json.loads(
                b64decode(signer.unsign(client.cookies.get(SESSION_COOKIE_NAME)))
            )
            assert all(f"_state_github_{state}" in payload for state in states)
            response = await client.get(
                "/auth/callback", params={"state": "wrong", "code": "test"}
            )
            assert response.headers["location"] == "/"
            assert client.cookies.get(AUTH_COOKIE_NAME) == old
            exchange.assert_not_awaited()
            payload[f"_state_github_{states[0]}"]["exp"] = time() - 1
            signed = signer.sign(b64encode(json.dumps(payload).encode())).decode()
            client.cookies.set(
                SESSION_COOKIE_NAME, signed, domain="testserver.local", path="/"
            )
            response = await client.get(
                "/auth/callback", params={"state": states[0], "code": "test"}
            )
            assert response.headers["location"] == "/"
            exchange.assert_not_awaited()
            response = await client.get(
                "/auth/callback", params={"state": states[1], "code": "test"}
            )
            assert response.headers["location"] == "/dashboard"
            assert client.cookies.get(AUTH_COOKIE_NAME) != old
            exchange.assert_awaited_once()


async def test_account_deletion_serializes_with_submission_and_preserves_foreign_key(
    session_apps, test_settings
):
    first, second = session_apps
    token = await mint(first, test_settings)
    inserted = asyncio.Event()
    release = asyncio.Event()
    requirement_uuid = uuid4()

    async def submit():
        async with first.state.session_maker() as db, db.begin():
            await VerificationAttemptRepository(db).create_or_get_active(
                id=uuid4(),
                user_id=42,
                requirement_uuid=requirement_uuid,
                artifact_schema_version=1,
                curriculum_version=1,
                content_hash="a" * 64,
                requirement_snapshot={},
                requirement_snapshot_hash="b" * 64,
                payload_version=1,
                github_username_snapshot="testuser",
                submitted_value=GitHubUrlValue("https://github.com/testuser/repo"),
                cloud_provider=None,
            )
            inserted.set()
            await release.wait()

    submission = asyncio.create_task(submit())
    await asyncio.wait_for(inserted.wait(), timeout=5)
    async with browser(second, token) as client:
        deletion = asyncio.create_task(client.delete("/api/user/me"))
        await asyncio.sleep(0.03)
        assert not deletion.done()
        release.set()
        await submission
        assert (await deletion).status_code == 204
    async with first.state.session_maker() as db:
        assert await db.get(User, 42) is None
        assert (
            await db.scalar(select(func.count()).select_from(VerificationAttempt)) == 0
        )
    # A request authorized before deletion cannot insert an orphan afterwards.
    with pytest.raises(IntegrityError):
        async with first.state.session_maker() as db, db.begin():
            await VerificationAttemptRepository(db).create_or_get_active(
                id=uuid4(),
                user_id=42,
                requirement_uuid=requirement_uuid,
                artifact_schema_version=1,
                curriculum_version=1,
                content_hash="a" * 64,
                requirement_snapshot={},
                requirement_snapshot_hash="b" * 64,
                payload_version=1,
                github_username_snapshot="testuser",
                submitted_value=GitHubUrlValue("https://github.com/testuser/repo"),
                cloud_provider=None,
            )
