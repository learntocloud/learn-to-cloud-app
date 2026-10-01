"""Cookie cleanup on handled responses without clobbering a replacement."""

from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from httpx import ASGITransport, AsyncClient

from learn_to_cloud.core.session_cookies import (
    AUTH_COOKIE_NAME,
    SessionResponseMiddleware,
    issue_cookie,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("secure", [False, True])
@pytest.mark.parametrize("status", [200, 401, 303])
async def test_handled_cleanup_flags_and_vary(test_settings, secure, status):
    settings = test_settings.model_copy(
        update={
            "web_security": test_settings.web_security.model_copy(
                update={"require_https": secure}
            )
        }
    )
    app = FastAPI()
    app.add_middleware(SessionResponseMiddleware)

    @app.get("/")
    async def page(request: Request):
        request.state.auth_resolved = True
        request.state.clear_auth_cookie = True
        raise HTTPException(status, headers={"Vary": "Accept-Encoding"})

    with patch(
        "learn_to_cloud.core.session_cookies.get_web_settings", return_value=settings
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/")
    assert response.status_code == status
    assert response.headers["vary"] == "Accept-Encoding, Cookie"
    assert response.headers["cache-control"] == "private, no-store"
    cookie = SimpleCookie(response.headers["set-cookie"])[AUTH_COOKIE_NAME]
    assert cookie["max-age"] == "0"
    assert cookie["path"] == "/"
    assert not cookie["domain"]
    assert bool(cookie["secure"]) is secure
    assert cookie["httponly"] and cookie["samesite"] == "lax"


async def test_fresh_cookie_wins_over_requested_cleanup():
    app = FastAPI()
    app.add_middleware(SessionResponseMiddleware)

    @app.get("/auth/callback")
    async def page(request: Request):
        request.state.clear_auth_cookie = True
        response = Response(headers={"Vary": "cookie, Accept-Encoding"})
        issue_cookie(
            request, response, "new-credential", datetime.now(UTC) + timedelta(days=30)
        )
        return response

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/auth/callback")
    headers = response.headers.get_list("set-cookie")
    assert len(headers) == 1
    assert SimpleCookie(headers[0])[AUTH_COOKIE_NAME].value == "new-credential"
    assert response.headers["vary"] == "cookie, Accept-Encoding"
