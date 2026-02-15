"""Unit tests for core.middleware module.

Tests ASGI middleware:
- SecurityHeadersMiddleware adds security headers to HTTP responses
- SecurityHeadersMiddleware skips non-HTTP scopes
- SecurityHeadersMiddleware adds cache-control for static paths
- UserTrackingMiddleware sets OTel span attributes for authenticated users
- UserTrackingMiddleware sets/resets context var
"""

from unittest.mock import MagicMock, patch

import pytest

from core.middleware import (
    SecurityHeadersMiddleware,
    UserTrackingMiddleware,
    request_github_username,
)


async def _noop_receive():
    return {"type": "http.request", "body": b""}


async def _make_app_that_sends_response(scope, receive, send):
    """Simulate an ASGI app that sends a response."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"OK"})


@pytest.mark.unit
class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware adds expected headers."""

    async def test_adds_security_headers(self):
        middleware = SecurityHeadersMiddleware(_make_app_that_sends_response)
        scope = {"type": "http", "path": "/api/test"}
        sent_messages = []

        async def mock_send(message):
            sent_messages.append(message)

        await middleware(scope, _noop_receive, mock_send)

        response_start = sent_messages[0]
        header_names = {h[0] for h in response_start["headers"]}

        assert b"x-content-type-options" in header_names
        assert b"x-frame-options" in header_names
        assert b"x-xss-protection" in header_names
        assert b"referrer-policy" in header_names
        assert b"content-security-policy" in header_names
        assert b"strict-transport-security" in header_names
        assert b"permissions-policy" in header_names

    async def test_skips_non_http_scopes(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = SecurityHeadersMiddleware(inner_app)
        scope = {"type": "websocket"}

        await middleware(scope, _noop_receive, lambda msg: None)
        assert called

    async def test_adds_cache_control_for_static_paths(self):
        middleware = SecurityHeadersMiddleware(_make_app_that_sends_response)
        scope = {"type": "http", "path": "/static/css/styles.css"}
        sent_messages = []

        async def mock_send(message):
            sent_messages.append(message)

        await middleware(scope, _noop_receive, mock_send)

        response_start = sent_messages[0]
        headers_dict = {h[0]: h[1] for h in response_start["headers"]}
        assert b"cache-control" in headers_dict
        assert b"immutable" in headers_dict[b"cache-control"]

    async def test_no_cache_control_for_non_static_paths(self):
        middleware = SecurityHeadersMiddleware(_make_app_that_sends_response)
        scope = {"type": "http", "path": "/api/health"}
        sent_messages = []

        async def mock_send(message):
            sent_messages.append(message)

        await middleware(scope, _noop_receive, mock_send)

        response_start = sent_messages[0]
        header_names = {h[0] for h in response_start["headers"]}
        assert b"cache-control" not in header_names

    async def test_preserves_existing_headers(self):
        async def app_with_headers(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"x-custom", b"value")],
                }
            )

        middleware = SecurityHeadersMiddleware(app_with_headers)
        scope = {"type": "http", "path": "/test"}
        sent_messages = []

        async def mock_send(message):
            sent_messages.append(message)

        await middleware(scope, _noop_receive, mock_send)

        response_start = sent_messages[0]
        header_names = {h[0] for h in response_start["headers"]}
        assert b"x-custom" in header_names
        assert b"x-content-type-options" in header_names


@pytest.mark.unit
class TestUserTrackingMiddleware:
    """Test UserTrackingMiddleware sets OTel span attributes and context var."""

    @patch("core.middleware.trace", autospec=True)
    async def test_sets_span_attributes_when_authenticated(self, mock_trace):
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = mock_span

        async def inner_app(scope, receive, send):
            pass

        middleware = UserTrackingMiddleware(inner_app)
        scope = {
            "type": "http",
            "session": {"user_id": 42, "github_username": "testuser"},
        }

        await middleware(scope, _noop_receive, lambda msg: None)

        mock_span.set_attribute.assert_any_call("enduser.id", "42")
        mock_span.set_attribute.assert_any_call("enduser.name", "testuser")

    @patch("core.middleware.trace", autospec=True)
    async def test_sets_only_user_id_when_no_username(self, mock_trace):
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = mock_span

        async def inner_app(scope, receive, send):
            pass

        middleware = UserTrackingMiddleware(inner_app)
        scope = {"type": "http", "session": {"user_id": 42}}

        await middleware(scope, _noop_receive, lambda msg: None)

        mock_span.set_attribute.assert_called_once_with("enduser.id", "42")

    @patch("core.middleware.trace", autospec=True)
    async def test_sets_context_var(self, mock_trace):
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False
        mock_trace.get_current_span.return_value = mock_span

        captured_username = None

        async def inner_app(scope, receive, send):
            nonlocal captured_username
            captured_username = request_github_username.get()

        middleware = UserTrackingMiddleware(inner_app)
        scope = {
            "type": "http",
            "session": {"github_username": "testuser"},
        }

        await middleware(scope, _noop_receive, lambda msg: None)
        assert captured_username == "testuser"

    @patch("core.middleware.trace", autospec=True)
    async def test_resets_context_var_in_finally(self, mock_trace):
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False
        mock_trace.get_current_span.return_value = mock_span

        async def failing_app(scope, receive, send):
            raise RuntimeError("app error")

        middleware = UserTrackingMiddleware(failing_app)
        scope = {
            "type": "http",
            "session": {"github_username": "testuser"},
        }

        with pytest.raises(RuntimeError, match="app error"):
            await middleware(scope, _noop_receive, lambda msg: None)

        # Context var should be reset to default after finally block
        assert request_github_username.get() is None

    @patch("core.middleware.trace", autospec=True)
    async def test_skips_non_http_scopes(self, mock_trace):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = UserTrackingMiddleware(inner_app)
        scope = {"type": "websocket"}

        await middleware(scope, _noop_receive, lambda msg: None)

        assert called
        mock_trace.get_current_span.assert_not_called()

    @patch("core.middleware.trace", autospec=True)
    async def test_no_span_attributes_when_unauthenticated(self, mock_trace):
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = mock_span

        async def inner_app(scope, receive, send):
            pass

        middleware = UserTrackingMiddleware(inner_app)
        scope = {"type": "http", "session": {}}

        await middleware(scope, _noop_receive, lambda msg: None)

        mock_span.set_attribute.assert_not_called()
