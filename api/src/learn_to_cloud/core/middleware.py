"""ASGI middleware for security headers and telemetry sanitization."""

from __future__ import annotations

from typing import ClassVar

from opentelemetry import trace
from starlette.datastructures import URL
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Adds security headers (CSP, HSTS, X-Frame-Options, etc.)."""

    SECURITY_HEADERS: ClassVar[list[tuple[bytes, bytes]]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"0"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (
            b"content-security-policy",
            b"default-src 'self';"
            b" script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.monitor.azure.com;"
            b" style-src 'self' 'unsafe-inline';"
            b" img-src 'self' https://avatars.githubusercontent.com data:;"
            b" connect-src 'self' https://github.com"
            b" https://*.in.applicationinsights.azure.com"
            b" https://dc.services.visualstudio.com;"
            b" font-src 'self';"
            b" frame-ancestors 'none'",
        ),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_static = scope.get("path", "").startswith("/static/")

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.extend(self.SECURITY_HEADERS)
                if is_static:
                    headers.append(
                        (b"cache-control", b"public, max-age=31536000, immutable")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class TelemetrySanitizationMiddleware:
    """Keep credentials and query values out of request URL attributes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        span = trace.get_current_span()
        if span.is_recording():
            url = URL(scope=scope).replace(
                query="", fragment="", username=None, password=None
            )
            span.set_attribute("http.target", url.path)
            span.set_attribute("http.url", str(url))
            span.set_attribute("url.full", str(url))
            span.set_attribute("url.path", url.path)
            span.set_attribute("url.query", "")

        await self.app(scope, receive, send)
