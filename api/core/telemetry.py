"""Telemetry and monitoring utilities for performance tracking.

This module provides:
- SQLAlchemy query instrumentation (automatic via OpenTelemetry)
- Custom metrics for business-level tracking
- Request timing middleware
- Dependency call tracking
"""

import logging
import os
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

TELEMETRY_ENABLED = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))

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
    """
    Instrument a SQLAlchemy engine for query tracing.
    
    This adds OpenTelemetry instrumentation to track:
    - Query execution time
    - Query text (parameterized)
    - Database connection info
    
    Args:
        engine: SQLAlchemy AsyncEngine to instrument
    """
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
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")

class SecurityHeadersMiddleware:
    """
    Middleware to add security headers to all responses.
    
    Adds headers to protect against common web vulnerabilities:
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-Frame-Options: Prevents clickjacking
    - X-XSS-Protection: Legacy XSS protection for older browsers
    - Referrer-Policy: Controls referrer information
    - Content-Security-Policy: Restricts resource loading (API-appropriate policy)
    """

    SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"1; mode=block"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
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
    """
    Middleware to add detailed request timing information.
    
    Adds custom spans and attributes for:
    - Total request duration
    - Route information
    - Response status
    - User context (if authenticated)
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
                message["headers"] = headers

            elif message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                duration_ms = (time.perf_counter() - start_time) * 1000

                route = scope.get("route")
                route_path = getattr(route, "path", None) or path

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
                        elif response_status >= 400:
                            span.set_status(
                                Status(
                                    StatusCode.ERROR,
                                    f"Client error {response_status}",
                                )
                            )

                if duration_ms > 1000:
                    logger.warning(
                        f"Slow request: {method} {route_path} took {duration_ms:.2f}ms"
                    )

            await send(message)

        if TELEMETRY_ENABLED and tracer:
            with tracer.start_as_current_span(
                f"{method} {path}",
                attributes={
                    "http.method": method,
                    "http.route": path,
                    "http.url": scope.get("raw_path", path),
                    "http.client_ip": client_ip,
                },
            ):
                await self.app(scope, receive, send_wrapper)
                return

        await self.app(scope, receive, send_wrapper)

def track_dependency(name: str, dependency_type: str = "custom"):
    """
    Decorator to track external dependency calls (APIs, services, etc.).
    
    Usage:
        @track_dependency("github_api", "HTTP")
        async def call_github(repo: str):
            ...
    
    Args:
        name: Name of the dependency (e.g., "github_api", "clerk_auth")
        dependency_type: Type of dependency (e.g., "HTTP", "Database", "Cache")
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not TELEMETRY_ENABLED or not tracer:
                return await func(*args, **kwargs)

            with tracer.start_as_current_span(
                name,
                attributes={
                    "dependency.type": dependency_type,
                    "dependency.name": name,
                },
            ) as span:
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("dependency.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("dependency.success", False)
                    span.set_attribute("dependency.error", str(e))
                    if Status is not None and StatusCode is not None:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("dependency.duration_ms", duration_ms)

        return wrapper
    return decorator

def track_operation(operation_name: str):
    """
    Decorator to track custom business operations.
    
    Usage:
        @track_operation("user_registration")
        async def register_user(data: UserCreate):
            ...
    
    Args:
        operation_name: Name of the operation for tracking
    """
    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not TELEMETRY_ENABLED or not tracer:
                return await func(*args, **kwargs)

            with tracer.start_as_current_span(
                operation_name,
                attributes={"operation.name": operation_name},
            ) as span:
                start_time = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("operation.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("operation.success", False)
                    span.record_exception(e)
                    if Status is not None and StatusCode is not None:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("operation.duration_ms", duration_ms)

        return wrapper
    return decorator

def add_custom_attribute(key: str, value: str | int | float | bool) -> None:
    """
    Add a custom attribute to the current span.
    
    Useful for adding business context to traces.
    
    Usage:
        add_custom_attribute("user.tier", "premium")
        add_custom_attribute("items.count", len(items))
    
    Args:
        key: Attribute key
        value: Attribute value
    """
    if not TELEMETRY_ENABLED or trace is None:
        return

    span = trace.get_current_span()
    if span:
        span.set_attribute(key, value)

def log_metric(
    name: str, value: float, properties: dict[str, str] | None = None
) -> None:
    """
    Log a custom metric for aggregation in Application Insights.
    
    Usage:
        log_metric("questions.passed", 5, {"phase": "phase1"})
    
    Args:
        name: Metric name
        value: Metric value
        properties: Optional properties/dimensions
    """
    if not TELEMETRY_ENABLED:
        return

    extra = {"custom_metric": name, "metric_value": value}
    if properties:
        extra.update(properties)
    
    logger.info(f"Metric: {name}={value}", extra=extra)
