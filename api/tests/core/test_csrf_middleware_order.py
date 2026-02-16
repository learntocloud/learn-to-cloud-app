"""ASGI-level tests for CSRF middleware ordering.

`core.csrf` unit tests validate token logic, but they inject `scope["session"]`
directly and therefore can't catch wiring mistakes in `main.py`.

This test proves the expected behavior:
- Session wraps CSRF (correct) -> POST without token is rejected (403)
- CSRF wraps Session (wrong) -> CSRF becomes a no-op and POST succeeds (200)
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware

from core.csrf import CSRFMiddleware


def _build_app(*, correct_order: bool) -> FastAPI:
    app = FastAPI()

    @app.get("/csrf-token")
    async def csrf_token(request: Request) -> dict[str, str]:
        return {"csrf_token": request.scope.get("csrf_token", "")}

    @app.post("/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    if correct_order:
        # Correct: Session runs first at runtime, so CSRF can read scope["session"].
        app.add_middleware(CSRFMiddleware)
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
    else:
        # Wrong: CSRF runs before Session at runtime and becomes a silent no-op.
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.add_middleware(CSRFMiddleware)

    return app


@pytest.mark.unit
class TestCSRFMiddlewareOrdering:
    async def test_correct_order_enforces_csrf(self) -> None:
        app = _build_app(correct_order=True)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            token = (await client.get("/csrf-token")).json()["csrf_token"]
            assert token  # should be set by CSRFMiddleware on safe requests

            r = await client.post("/protected")
            assert r.status_code == 403

            r = await client.post("/protected", headers={"X-CSRFToken": token})
            assert r.status_code == 200

    async def test_wrong_order_disables_csrf(self) -> None:
        app = _build_app(correct_order=False)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            token = (await client.get("/csrf-token")).json()["csrf_token"]
            assert token == ""

            r = await client.post("/protected")
            assert r.status_code == 200
