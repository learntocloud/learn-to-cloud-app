"""Telemetry utilities — security headers and SQLAlchemy instrumentation."""

import logging
import os
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

TELEMETRY_ENABLED = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))


def instrument_sqlalchemy_engine(engine: Any) -> None:
    """Add OpenTelemetry instrumentation for query tracing."""
    if not TELEMETRY_ENABLED:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import (
            SQLAlchemyInstrumentor,
        )

        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            enable_commenter=True,
        )
        logger.info("SQLAlchemy instrumentation enabled")
    except Exception as e:
        logger.warning("sqlalchemy.instrumentation.failed: %s", e)


class SecurityHeadersMiddleware:
    """Adds security headers (X-Content-Type-Options, X-Frame-Options, CSP)."""

    SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"0"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (
            b"content-security-policy",
            b"default-src 'self';"
            b" script-src 'self' 'unsafe-inline' 'unsafe-eval';"
            b" style-src 'self' 'unsafe-inline';"
            b" img-src 'self' https://avatars.githubusercontent.com data:;"
            b" connect-src 'self' https://github.com;"
            b" font-src 'self';"
            b" frame-ancestors 'none'",
        ),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.extend(self.SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
