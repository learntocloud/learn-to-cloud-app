"""Unit tests for core.middleware module.

Tests ASGI middleware:
- SecurityHeadersMiddleware adds security headers to HTTP responses
- SecurityHeadersMiddleware skips non-HTTP scopes
- SecurityHeadersMiddleware adds cache-control for static paths
- TelemetrySanitizationMiddleware removes raw URLs and query strings
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from starlette.routing import Match

from learn_to_cloud.core.middleware import (
    SecurityHeadersMiddleware,
    TelemetrySanitizationMiddleware,
)


async def _noop_receive():
    return {"type": "http.request", "body": b""}


async def _noop_send(msg: object) -> None:
    pass


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

    async def test_csp_allows_frontend_telemetry_endpoints(self):
        middleware = SecurityHeadersMiddleware(_make_app_that_sends_response)
        scope = {"type": "http", "path": "/"}
        sent_messages = []

        async def mock_send(message):
            sent_messages.append(message)

        await middleware(scope, _noop_receive, mock_send)

        response_start = sent_messages[0]
        headers_dict = {h[0]: h[1] for h in response_start["headers"]}
        csp = headers_dict[b"content-security-policy"].decode()
        directives = {
            parts[0]: parts[1:]
            for directive in csp.split(";")
            if (parts := directive.strip().split())
        }
        script_sources = set(directives["script-src"])
        connect_sources = set(directives["connect-src"])

        assert "https://" + "js.monitor.azure.com" in script_sources
        assert "https://" + "*.in.applicationinsights.azure.com" in connect_sources
        assert "https://" + "dc.services.visualstudio.com" in connect_sources

    async def test_skips_non_http_scopes(self):
        called = False

        async def inner_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = SecurityHeadersMiddleware(inner_app)
        scope = {"type": "websocket"}

        await middleware(scope, _noop_receive, _noop_send)
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
class TestTelemetrySanitizationMiddleware:
    @patch("learn_to_cloud.core.middleware.trace", autospec=True)
    async def test_replaces_url_attributes_with_route_template(self, mock_trace):
        span = MagicMock()
        span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = span

        route = SimpleNamespace(
            path="/steps/{step_uuid}",
            matches=MagicMock(return_value=(Match.FULL, {})),
        )
        middleware = TelemetrySanitizationMiddleware(_make_app_that_sends_response)
        scope = {
            "type": "http",
            "path": "/steps/2ea4225e",
            "query_string": b"token=sensitive",
            "app": SimpleNamespace(router=SimpleNamespace(routes=[route])),
        }

        await middleware(scope, _noop_receive, _noop_send)

        assert span.set_attribute.call_args_list == [
            call("http.target", "/steps/{step_uuid}"),
            call("http.url", "/steps/{step_uuid}"),
            call("url.full", "/steps/{step_uuid}"),
            call("url.path", "/steps/{step_uuid}"),
            call("url.query", ""),
        ]

    @patch("learn_to_cloud.core.middleware.trace", autospec=True)
    async def test_uses_fixed_value_for_unmatched_routes(self, mock_trace):
        span = MagicMock()
        span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = span

        middleware = TelemetrySanitizationMiddleware(_make_app_that_sends_response)
        scope = {
            "type": "http",
            "path": "/arbitrary",
            "query_string": b"code=secret",
            "app": SimpleNamespace(router=SimpleNamespace(routes=[])),
        }

        await middleware(scope, _noop_receive, _noop_send)

        span.set_attribute.assert_any_call("url.full", "/unmatched")
