"""Telemetry utilities — security headers, SQLAlchemy instrumentation, user tracking."""

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
        logger.info("telemetry.sqlalchemy.enabled")
    except Exception as e:
        logger.warning(
            "telemetry.sqlalchemy.failed",
            extra={"error": str(e)},
        )


def add_user_span_processor() -> None:
    """Register a SpanProcessor that stamps user_id from the session onto spans.

    This populates the ``UserId`` column in Application Insights ``AppRequests``
    and ``AppDependencies``, enabling per-user query correlation.
    """
    if not TELEMETRY_ENABLED:
        return

    try:
        from opentelemetry import context as otel_context
        from opentelemetry.context import Context
        from opentelemetry.sdk.trace import ReadableSpan, Span, TracerProvider
        from opentelemetry.trace import get_tracer_provider

        _USER_ID_KEY = otel_context.create_key("ltc.user_id")

        class _UserIdSpanProcessor:
            """Lightweight SpanProcessor — reads user_id from OTel context."""

            def on_start(
                self,
                span: Span,
                parent_context: Context | None = None,
            ) -> None:
                ctx = parent_context or otel_context.get_current()
                user_id = ctx.get(_USER_ID_KEY)
                if user_id is not None:
                    span.set_attribute("enduser.id", str(user_id))

            def on_end(self, span: ReadableSpan) -> None:
                pass

            def shutdown(self) -> None:
                pass

            def force_flush(self, timeout_millis: int = 30000) -> bool:
                return True

        provider = get_tracer_provider()
        if isinstance(provider, TracerProvider):
            provider.add_span_processor(_UserIdSpanProcessor())
            logger.info("telemetry.user_span_processor.enabled")

    except Exception as e:
        logger.warning(
            "telemetry.user_span_processor.failed",
            extra={"error": str(e)},
        )


class UserTrackingMiddleware:
    """ASGI middleware that injects user_id from the session into OTel context.

    Must be added AFTER SessionMiddleware so ``scope["session"]`` is populated.
    Works in tandem with ``add_user_span_processor()`` — this middleware sets
    the context value, the processor copies it onto every span.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session: dict = scope.get("session", {})  # type: ignore[assignment]
        user_id = session.get("user_id")

        if user_id is not None and TELEMETRY_ENABLED:
            from opentelemetry import context as otel_context

            _USER_ID_KEY = otel_context.create_key("ltc.user_id")
            ctx = otel_context.set_value(_USER_ID_KEY, user_id)
            token = otel_context.attach(ctx)
            try:
                await self.app(scope, receive, send)
            finally:
                otel_context.detach(token)
        else:
            await self.app(scope, receive, send)


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

        is_static = scope.get("path", "").startswith("/static/")

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.extend(self.SECURITY_HEADERS)
                # Cache-busted static files get long cache; others get no-cache
                if is_static:
                    headers.append(
                        (b"cache-control", b"public, max-age=31536000, immutable")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
