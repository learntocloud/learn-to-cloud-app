"""Telemetry and monitoring utilities for performance tracking."""

import os
import time
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.logger import get_logger
from core.wide_event import clear_wide_event, get_wide_event, init_wide_event

logger = get_logger(__name__)

TELEMETRY_ENABLED = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))

# Infrastructure context - keep minimal for a single-service app
SERVICE_NAME = os.getenv("SERVICE_NAME", "learn-to-cloud-api")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")

if TELEMETRY_ENABLED:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    tracer = trace.get_tracer(__name__)
else:
    trace = None
    tracer = None
    Status = None
    StatusCode = None

P = ParamSpec("P")
R = TypeVar("R")


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
        logger.warning("sqlalchemy.instrumentation.failed", error=str(e))


class SecurityHeadersMiddleware:
    """Adds security headers (X-Content-Type-Options, X-Frame-Options, CSP, etc)."""

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


class RequestTimingMiddleware:
    """Enriches spans with timing, route info, emits wide event at request end.

    - One wide event per request (canonical log line)
    - High cardinality fields (user_id, request_id)
    - Tail sampling (always keep errors/slow, sample success)
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "")

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        request_id = str(uuid.uuid4())

        # Initialize wide event with request context
        wide_event = init_wide_event()
        wide_event["service_name"] = SERVICE_NAME
        wide_event["service_version"] = SERVICE_VERSION
        wide_event["request_id"] = request_id
        wide_event["http_method"] = method
        wide_event["http_path"] = path
        wide_event["http_client_ip"] = client_ip

        response_status: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal response_status

            if message.get("type") == "http.response.start":
                response_status = int(message.get("status", 0))
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                duration_ms = (time.perf_counter() - start_time) * 1000
                headers.append(
                    (b"x-request-duration-ms", f"{duration_ms:.2f}".encode())
                )
                # Include request_id in response for user correlation
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers

            elif message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                duration_ms = (time.perf_counter() - start_time) * 1000

                route = scope.get("route")
                route_path = getattr(route, "path", None) or path

                # Enrich OpenTelemetry span
                if (
                    TELEMETRY_ENABLED
                    and tracer
                    and trace is not None
                    and Status is not None
                    and StatusCode is not None
                    and response_status is not None
                ):
                    span = trace.get_current_span() if trace else None
                    if span:
                        span.set_attribute("http.route", route_path)
                        span.set_attribute("http.status_code", response_status)
                        span.set_attribute("http.duration_ms", duration_ms)

                        if response_status >= 500:
                            span.set_status(
                                Status(StatusCode.ERROR, f"HTTP {response_status}")
                            )
                        # 4xx: Leave span status unset per OTel semantic conventions
                        # (client errors are not server errors)

                # Finalize and emit wide event
                event = get_wide_event()
                event["http_route"] = route_path
                event["http_status_code"] = response_status
                event["duration_ms"] = round(duration_ms, 2)
                event["outcome"] = (
                    "success" if response_status and response_status < 400 else "error"
                )

                # Emit wide event - always for errors/slow, sample otherwise
                should_emit = (
                    response_status is None
                    or response_status >= 400
                    or duration_ms > 1000
                    or event.get("user_id")  # Always emit authenticated requests
                )

                if should_emit:
                    logger.info("request.completed", **event)

                clear_wide_event()

            await send(message)

        try:
            if TELEMETRY_ENABLED and tracer:
                with tracer.start_as_current_span(
                    f"{method} {path}",
                    attributes={
                        "http.method": method,
                        "http.route": path,
                        "http.url": scope.get("raw_path", path),
                        "http.client_ip": client_ip,
                        "request.id": request_id,
                        "service.name": SERVICE_NAME,
                        "service.version": SERVICE_VERSION,
                    },
                ):
                    await self.app(scope, receive, send_wrapper)
                    return

            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            # Emit wide event for unhandled exceptions
            duration_ms = (time.perf_counter() - start_time) * 1000
            route = scope.get("route")
            route_path = getattr(route, "path", None) or path
            event = get_wide_event()
            event["http_route"] = route_path
            event["duration_ms"] = round(duration_ms, 2)
            event["outcome"] = "exception"
            event["exception_type"] = type(exc).__name__
            logger.info("request.completed", **event)
            clear_wide_event()
            raise


def _traced_span(
    span_name: str,
    attributes: dict[str, str],
    *,
    record_exceptions: bool = False,
):
    """Shared decorator logic for tracing sync/async functions with OpenTelemetry.

    Args:
        span_name: Name for the OTel span.
        attributes: Initial span attributes (e.g., dependency.type, operation.name).
        record_exceptions: If True, call span.record_exception() on errors
            (used by track_operation for business ops; track_dependency skips
            this since the exception propagates to the parent span).
    """
    prefix = next(iter(attributes)).split(".")[0]  # "dependency" or "operation"

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        import asyncio

        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                if not TELEMETRY_ENABLED or not tracer:
                    return await func(*args, **kwargs)

                with tracer.start_as_current_span(
                    span_name, attributes=attributes
                ) as span:
                    start_time = time.perf_counter()
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute(f"{prefix}.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute(f"{prefix}.success", False)
                        if record_exceptions:
                            span.record_exception(e)
                        else:
                            span.set_attribute(f"{prefix}.error", str(e))
                        if Status is not None and StatusCode is not None:
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
                    finally:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute(f"{prefix}.duration_ms", duration_ms)

            return cast(Callable[P, R], async_wrapper)
        else:

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                if not TELEMETRY_ENABLED or not tracer:
                    return func(*args, **kwargs)

                with tracer.start_as_current_span(
                    span_name, attributes=attributes
                ) as span:
                    start_time = time.perf_counter()
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute(f"{prefix}.success", True)
                        return result
                    except Exception as e:
                        span.set_attribute(f"{prefix}.success", False)
                        if record_exceptions:
                            span.record_exception(e)
                        else:
                            span.set_attribute(f"{prefix}.error", str(e))
                        if Status is not None and StatusCode is not None:
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
                    finally:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute(f"{prefix}.duration_ms", duration_ms)

            return sync_wrapper

    return decorator


def track_dependency(name: str, dependency_type: str = "custom"):
    """Decorator to track external dependency calls (APIs, services)."""
    return _traced_span(
        name,
        {"dependency.type": dependency_type, "dependency.name": name},
        record_exceptions=False,
    )


def track_operation(operation_name: str):
    """Decorator to track custom business operations."""
    return _traced_span(
        operation_name,
        {"operation.name": operation_name},
        record_exceptions=True,
    )


def add_custom_attribute(key: str, value: str | int | float | bool) -> None:
    """Add a custom attribute to the current span."""
    if not TELEMETRY_ENABLED or trace is None:
        return

    span = trace.get_current_span()
    if span:
        span.set_attribute(key, value)


def log_business_event(
    name: str, value: float, properties: dict[str, str] | None = None
) -> None:
    """Log a structured business event for observability.

    NOTE: This emits a structured log line (appears in Application Insights
    *traces* table), NOT an OpenTelemetry metric (customMetrics table).
    Use for counting business events you want to query in logs.
    """
    if not TELEMETRY_ENABLED:
        return

    logger.info("business.event", event_name=name, value=value, **(properties or {}))
