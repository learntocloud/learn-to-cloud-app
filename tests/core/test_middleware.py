"""Unit tests for core.middleware module.

Tests ASGI middleware:
- SecurityHeadersMiddleware adds security headers to HTTP responses
- SecurityHeadersMiddleware skips non-HTTP scopes
- SecurityHeadersMiddleware adds cache-control for static paths
- TelemetrySanitizationMiddleware preserves paths without query credentials
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from starlette.responses import PlainTextResponse

from learn_to_cloud.core.middleware import (
    SecurityHeadersMiddleware,
    TelemetrySanitizationMiddleware,
)


def _receive() -> AsyncMock:
    return AsyncMock(return_value={"type": "http.request", "body": b""})


def _response_start(send: AsyncMock) -> dict:
    return send.await_args_list[0].args[0]


@pytest.mark.unit
class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware adds expected headers."""

    async def test_adds_security_headers(self):
        middleware = SecurityHeadersMiddleware(PlainTextResponse("OK"))
        scope = {"type": "http", "path": "/api/test"}
        send = AsyncMock()

        await middleware(scope, _receive(), send)

        response_start = _response_start(send)
        header_names = {h[0] for h in response_start["headers"]}

        assert b"x-content-type-options" in header_names
        assert b"x-frame-options" in header_names
        assert b"x-xss-protection" in header_names
        assert b"referrer-policy" in header_names
        assert b"content-security-policy" in header_names
        assert b"strict-transport-security" in header_names
        assert b"permissions-policy" in header_names

    async def test_csp_allows_frontend_telemetry_endpoints(self):
        middleware = SecurityHeadersMiddleware(PlainTextResponse("OK"))
        scope = {"type": "http", "path": "/"}
        send = AsyncMock()

        await middleware(scope, _receive(), send)

        response_start = _response_start(send)
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
        inner_app = AsyncMock()
        middleware = SecurityHeadersMiddleware(inner_app)
        scope = {"type": "websocket"}
        receive, send = _receive(), AsyncMock()

        await middleware(scope, receive, send)

        inner_app.assert_awaited_once_with(scope, receive, send)

    async def test_adds_cache_control_for_static_paths(self):
        middleware = SecurityHeadersMiddleware(PlainTextResponse("OK"))
        scope = {"type": "http", "path": "/static/css/styles.css"}
        send = AsyncMock()

        await middleware(scope, _receive(), send)

        response_start = _response_start(send)
        headers_dict = {h[0]: h[1] for h in response_start["headers"]}
        assert b"cache-control" in headers_dict
        assert b"immutable" in headers_dict[b"cache-control"]

    async def test_no_cache_control_for_non_static_paths(self):
        middleware = SecurityHeadersMiddleware(PlainTextResponse("OK"))
        scope = {"type": "http", "path": "/api/health"}
        send = AsyncMock()

        await middleware(scope, _receive(), send)

        response_start = _response_start(send)
        header_names = {h[0] for h in response_start["headers"]}
        assert b"cache-control" not in header_names

    async def test_preserves_existing_headers(self):
        middleware = SecurityHeadersMiddleware(
            PlainTextResponse("", headers={"x-custom": "value"})
        )
        scope = {"type": "http", "path": "/test"}
        send = AsyncMock()

        await middleware(scope, _receive(), send)

        response_start = _response_start(send)
        header_names = {h[0] for h in response_start["headers"]}
        assert b"x-custom" in header_names
        assert b"x-content-type-options" in header_names


@pytest.mark.unit
class TestTelemetrySanitizationMiddleware:
    @pytest.mark.parametrize("path", ["/steps/2ea4225e", "/unregistered/path"])
    @patch("learn_to_cloud.core.middleware.trace", autospec=True)
    async def test_preserves_path_without_query_credentials(self, mock_trace, path):
        span = MagicMock()
        span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = span

        middleware = TelemetrySanitizationMiddleware(PlainTextResponse("OK"))
        scope = {
            "type": "http",
            "scheme": "https",
            "headers": [(b"host", b"testserver")],
            "method": "GET",
            "path": path,
            "query_string": b"token=sensitive",
        }

        await middleware(scope, _receive(), AsyncMock())

        assert span.set_attribute.call_args_list == [
            call("http.target", path),
            call("http.url", f"https://testserver{path}"),
            call("url.full", f"https://testserver{path}"),
            call("url.path", path),
            call("url.query", ""),
        ]
        assert scope["query_string"] == b"token=sensitive"

    @patch("learn_to_cloud.core.middleware.trace", autospec=True)
    async def test_does_not_export_invalid_host_credentials(self, mock_trace):
        span = MagicMock()
        span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = span

        middleware = TelemetrySanitizationMiddleware(PlainTextResponse("OK"))
        scope = {
            "type": "http",
            "scheme": "https",
            "headers": [(b"host", b"username:password@testserver")],
            "path": "/arbitrary",
            "query_string": b"code=secret",
            "method": "GET",
        }

        await middleware(scope, _receive(), AsyncMock())

        span.set_attribute.assert_any_call("url.full", "/arbitrary")
