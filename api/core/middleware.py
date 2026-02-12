"""ASGI middleware — security headers and user tracking."""

from __future__ import annotations

from opentelemetry import trace
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Adds security headers (CSP, HSTS, X-Frame-Options, etc.)."""

    SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"0"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (
            b"content-security-policy",
            b"default-src 'self';"
            b" script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net;"
            b" style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;"
            b" img-src 'self' https://avatars.githubusercontent.com data:;"
            b" connect-src 'self' https://github.com https://cdn.jsdelivr.net;"
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


class UserTrackingMiddleware:
    """Stamps ``enduser.id`` on the active span from the session.

    Must sit AFTER SessionMiddleware so ``scope["session"]`` is populated.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        user_id = scope.get("session", {}).get("user_id")
        if user_id is not None:
            span = trace.get_current_span()
            if span.is_recording():
                span.set_attribute("enduser.id", str(user_id))

        await self.app(scope, receive, send)
