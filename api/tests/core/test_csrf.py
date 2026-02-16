"""Unit tests for core.csrf — CSRF middleware.

Tests the Synchronizer Token Pattern:
- Token auto-generated in session on first request
- GET/HEAD/OPTIONS/TRACE skip CSRF checks
- POST/DELETE/PUT/PATCH require a valid token
- Token accepted from X-CSRFToken header
- Token accepted from csrf_token form field
- 403 on missing or wrong token
- Exempt URLs skip checks
- Non-HTTP scopes pass through
- No session → middleware is a no-op
"""

import re
from urllib.parse import urlencode

import pytest

from core.csrf import CSRFMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN = "test-csrf-token-value"


async def _noop_receive():
    return {"type": "http.request", "body": b""}


async def _noop_send(message):
    pass


async def _make_app_that_sends_response(scope, receive, send):
    """Simulate an ASGI app that sends a 200 OK."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"OK"})


def _http_scope(
    method: str = "GET",
    path: str = "/test",
    headers: list[tuple[bytes, bytes]] | None = None,
    session: dict | None = None,
) -> dict:
    """Build a minimal HTTP ASGI scope."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "server": ("localhost", 8000),
    }
    if session is not None:
        scope["session"] = session
    return scope


def _collect_send(sent: list):
    """Return an async send callable that appends messages to *sent*."""

    async def send(message):
        sent.append(message)

    return send


def _form_body_receive(data: dict):
    """Return a receive callable that yields url-encoded form data."""
    body = urlencode(data).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCSRFMiddleware:
    """Test CSRFMiddleware enforces Synchronizer Token Pattern."""

    async def test_get_request_passes_without_token(self):
        """Safe methods should not require a CSRF token."""
        session: dict = {}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="GET", session=session)
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))

        assert any(m.get("status") == 200 for m in sent)
        # Token should have been auto-generated in the session.
        assert "_csrf_token" in session

    async def test_head_request_passes(self):
        session: dict = {}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="HEAD", session=session)
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_post_rejected_without_token(self):
        """POST without CSRF token should return 403."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="POST", session=session)
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_delete_rejected_without_token(self):
        """DELETE without CSRF token should return 403."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="DELETE", session=session)
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_post_accepted_with_valid_header(self):
        """POST with valid X-CSRFToken header should pass."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[(b"x-csrftoken", _TOKEN.encode())],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_post_accepted_with_valid_form_field(self):
        """POST with valid csrf_token form field should pass."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"content-type", b"application/x-www-form-urlencoded"),
            ],
        )
        sent = []
        receive = _form_body_receive({"csrf_token": _TOKEN})

        await middleware(scope, receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_post_rejected_with_wrong_token(self):
        """POST with incorrect CSRF token should return 403."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[(b"x-csrftoken", b"wrong-token")],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_exempt_url_skips_check(self):
        """Exempt URLs should bypass CSRF validation."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            exempt_urls=[re.compile(r"^/auth/callback$")],
        )
        scope = _http_scope(method="POST", path="/auth/callback", session=session)
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_non_exempt_url_still_checked(self):
        """Non-exempt URLs should still enforce CSRF."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            exempt_urls=[re.compile(r"^/auth/callback$")],
        )
        scope = _http_scope(method="POST", path="/htmx/steps/complete", session=session)
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_non_http_scope_passes_through(self):
        """WebSocket and other non-HTTP scopes should pass through."""
        called = False

        async def inner(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFMiddleware(inner)
        scope = {"type": "websocket"}

        await middleware(scope, _noop_receive, _noop_send)
        assert called

    async def test_no_session_passes_through(self):
        """If no session is available, middleware should not enforce CSRF."""
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="POST")
        # No "session" key in scope.
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_token_set_on_scope(self):
        """Middleware should expose csrf_token on scope for templates."""
        session: dict = {}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="GET", session=session)

        await middleware(scope, _noop_receive, _noop_send)

        assert "csrf_token" in scope
        assert scope["csrf_token"] == session["_csrf_token"]

    async def test_htmx_error_response(self):
        """HTMX requests should get a user-friendly 403 message."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[(b"hx-request", b"true")],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)
        body_msg = next((m for m in sent if m.get("type") == "http.response.body"), {})
        assert b"refresh" in body_msg.get("body", b"").lower()
