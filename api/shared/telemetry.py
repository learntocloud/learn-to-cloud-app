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

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Check if telemetry is enabled (Azure environment)
TELEMETRY_ENABLED = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))

# OpenTelemetry imports (only available when telemetry is enabled)
# These are conditionally imported based on Azure environment
if TELEMETRY_ENABLED:
    from opentelemetry import trace  # type: ignore[import-untyped]
    from opentelemetry.trace import Status, StatusCode  # type: ignore[import-untyped]

    tracer = trace.get_tracer(__name__)
else:
    trace = None  # type: ignore[assignment]
    tracer = None
    Status = None  # type: ignore[assignment,misc]
    StatusCode = None  # type: ignore[assignment,misc]


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
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        # Get the sync engine from async engine for instrumentation
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            enable_commenter=True,  # Add SQL comments with trace context
        )
        logger.info("SQLAlchemy instrumentation enabled")
    except Exception as e:
        logger.warning(f"Failed to instrument SQLAlchemy: {e}")


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add detailed request timing information.
    
    Adds custom spans and attributes for:
    - Total request duration
    - Route information
    - Response status
    - User context (if authenticated)
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.perf_counter()
        
        # Extract route info for better span names
        route = request.scope.get("route")
        route_path = route.path if route else request.url.path
        
        if TELEMETRY_ENABLED and tracer:
            client_ip = request.client.host if request.client else "unknown"
            with tracer.start_as_current_span(
                f"{request.method} {route_path}",
                attributes={
                    "http.method": request.method,
                    "http.route": route_path,
                    "http.url": str(request.url),
                    "http.client_ip": client_ip,
                },
            ) as span:
                response = await call_next(request)
                
                # Calculate duration
                duration_ms = (time.perf_counter() - start_time) * 1000
                
                # Add response attributes
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.duration_ms", duration_ms)
                
                # Set span status based on response code
                if response.status_code >= 500:
                    span.set_status(
                        Status(StatusCode.ERROR, f"HTTP {response.status_code}")
                    )
                elif response.status_code >= 400:
                    span.set_status(
                        Status(StatusCode.ERROR, f"Client error {response.status_code}")
                    )
                
                # Add timing header for debugging
                response.headers["X-Request-Duration-Ms"] = f"{duration_ms:.2f}"
                
                # Log slow requests
                if duration_ms > 1000:  # Over 1 second
                    logger.warning(
                        f"Slow request: {request.method} {route_path} "
                        f"took {duration_ms:.2f}ms"
                    )
                
                return response
        else:
            # Non-instrumented path (local development)
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-Duration-Ms"] = f"{duration_ms:.2f}"
            return response


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
        log_metric("checklist.items_completed", 5, {"phase": "phase1"})
    
    Args:
        name: Metric name
        value: Metric value
        properties: Optional properties/dimensions
    """
    if not TELEMETRY_ENABLED:
        return

    # Log as structured data that Azure Monitor can pick up
    extra = {"custom_metric": name, "metric_value": value}
    if properties:
        extra.update(properties)
    
    logger.info(f"Metric: {name}={value}", extra=extra)
