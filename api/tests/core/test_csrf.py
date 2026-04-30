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
- No session → fail-closed on unsafe methods, pass-through on safe methods
- Origin / Referer verification (defence-in-depth)
"""

import re
from urllib.parse import urlencode

import pytest

from core.csrf import CSRFMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN = "test-csrf-token-value"
_TRUSTED_ORIGIN = "https://example.com"


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
    scope: dict[str, object] = {
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

    async def test_no_session_rejects_unsafe_method(self):
        """Unsafe methods without a session should be rejected (fail-closed)."""
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="POST")
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_no_session_allows_safe_method(self):
        """Safe methods without a session should still pass through."""
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(method="GET")
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


@pytest.mark.unit
class TestCSRFOriginVerification:
    """Test Origin / Referer defence-in-depth checks."""

    async def test_valid_origin_header_accepted(self):
        """POST with matching Origin header should pass."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=[_TRUSTED_ORIGIN],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"origin", b"https://example.com"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_invalid_origin_header_rejected(self):
        """POST with non-matching Origin header should return 403."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=[_TRUSTED_ORIGIN],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"origin", b"https://evil.com"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_valid_referer_accepted(self):
        """POST with matching Referer (no Origin) should pass."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=[_TRUSTED_ORIGIN],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"referer", b"https://example.com/some/page"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_invalid_referer_rejected(self):
        """POST with non-matching Referer (no Origin) should return 403."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=[_TRUSTED_ORIGIN],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"referer", b"https://evil.com/attack"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 403 for m in sent)

    async def test_no_origin_or_referer_falls_through_to_token_check(self):
        """Missing both Origin and Referer should fall through to token check."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=[_TRUSTED_ORIGIN],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[(b"x-csrftoken", _TOKEN.encode())],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_origin_check_skipped_when_no_trusted_origins(self):
        """Without trusted_origins configured, origin check is skipped."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(_make_app_that_sends_response)
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"origin", b"https://evil.com"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        # Should pass because origin check is not enforced.
        assert any(m.get("status") == 200 for m in sent)

    async def test_origin_normalization_strips_default_port(self):
        """Origin with default port should match the same origin without port."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=["https://example.com"],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"origin", b"https://example.com:443"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)

    async def test_origin_normalization_preserves_non_default_port(self):
        """Origin with non-default port should require exact match."""
        session = {"_csrf_token": _TOKEN}
        middleware = CSRFMiddleware(
            _make_app_that_sends_response,
            trusted_origins=["http://localhost:4280"],
        )
        scope = _http_scope(
            method="POST",
            session=session,
            headers=[
                (b"x-csrftoken", _TOKEN.encode()),
                (b"origin", b"http://localhost:4280"),
            ],
        )
        sent = []

        await middleware(scope, _noop_receive, _collect_send(sent))
        assert any(m.get("status") == 200 for m in sent)
