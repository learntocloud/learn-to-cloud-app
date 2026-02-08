"""Centralized logging configuration using structlog.

This module provides consistent, structured logging across the application with:
- JSON output for production (LOG_FORMAT=json)
- Colored console output for local development (default)
- OpenTelemetry trace/span ID injection for correlation
- Automatic configuration of third-party library logs (uvicorn, sqlalchemy, httpx)

Usage:
    from core import get_logger
    logger = get_logger(__name__)
    logger.info("user.login", user_id="123", method="oauth")
"""

import logging
import os
import sys

import structlog
from structlog.types import EventDict, Processor

# Check if OpenTelemetry is available for trace correlation
_TELEMETRY_ENABLED = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))


def _add_open_telemetry_spans(
    _logger: logging.Logger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Add OpenTelemetry trace and span IDs to log entries for correlation."""
    if not _TELEMETRY_ENABLED:
        return event_dict

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            if ctx.is_valid:
                event_dict["trace_id"] = format(ctx.trace_id, "032x")
                event_dict["span_id"] = format(ctx.span_id, "016x")
    except Exception:
        # Don't let telemetry errors break logging
        pass

    return event_dict


def _get_log_level() -> int:
    """Get log level from environment, defaulting to INFO."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _is_json_format() -> bool:
    """Determine if JSON output is enabled (production mode)."""
    log_format = os.environ.get("LOG_FORMAT", "").lower()
    # Default to JSON in production (when telemetry is enabled), console otherwise
    if log_format == "json":
        return True
    if log_format == "console":
        return False
    return _TELEMETRY_ENABLED


def configure_logging() -> None:
    """Configure structlog and stdlib logging. Call once at application startup.

    This sets up:
    1. structlog processors for structured logging
    2. stdlib logging to use structlog's ProcessorFormatter
    3. Third-party library log formatting (uvicorn, sqlalchemy, etc.)
    """
    log_level = _get_log_level()
    use_json = _is_json_format()

    # Shared processors for both structlog and stdlib logs
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        _add_open_telemetry_spans,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if use_json:
        # Production: JSON output for log aggregation
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Development: Colored console output
        renderer = structlog.dev.ConsoleRenderer(
            colors=True, exception_formatter=structlog.dev.plain_traceback
        )

    # Configure structlog
    structlog.configure(
        processors=shared_processors
        + [
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging with ProcessorFormatter
    # This ensures third-party logs (uvicorn, sqlalchemy) get the same formatting
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    # Configure root logger — preserve OTel LoggingHandler if present
    root_logger = logging.getLogger()

    # Remove only non-OTel handlers (preserve azure-monitor's LoggingHandler)
    otel_handlers = [
        h for h in root_logger.handlers if "LoggingHandler" in type(h).__name__
    ]
    root_logger.handlers.clear()

    # Re-add OTel handlers first, then our structlog handler
    for h in otel_handlers:
        root_logger.addHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A structlog BoundLogger that supports structured key-value logging.

    Example:
        logger = get_logger(__name__)
        logger.info("user.created", user_id="123", email="test@example.com")
        logger.warning("rate.limit.exceeded", endpoint="/api/submit", ip="1.2.3.4")
    """
    return structlog.stdlib.get_logger(name)
