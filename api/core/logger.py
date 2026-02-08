"""Centralized logging configuration using stdlib logging.

Simple JSON logging for production, human-readable console for local dev.
Azure Monitor's OTel LoggingHandler picks up `extra` fields natively
as queryable attributes in Application Insights AppTraces.

Usage:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("user.login", extra={"user_id": "123", "method": "oauth"})
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime


class _JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Include extra fields (user_id, step_id, etc.)
        skip = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
        for key, value in record.__dict__.items():
            if key not in skip and isinstance(value, str | int | float | bool | None):
                log_entry[key] = value
        # Include exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def configure_logging() -> None:
    """Configure stdlib logging. Call once at application startup."""
    use_json = os.getenv("LOG_FORMAT", "").lower() != "console" and bool(
        os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    )
    level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)

    root = logging.getLogger()

    # Preserve OTel handlers added by configure_azure_monitor()
    otel_handlers = [h for h in root.handlers if "LoggingHandler" in type(h).__name__]
    root.handlers.clear()
    for h in otel_handlers:
        root.addHandler(h)

    # Add stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _JSONFormatter()
        if use_json
        else logging.Formatter("%(levelname)-5s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers
    for name in (
        "httpx",
        "httpcore",
        "uvicorn.access",
        "openai",
        "openai._base_client",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
