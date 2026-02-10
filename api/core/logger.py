"""Centralized logging configuration using stdlib logging.

Simple JSON logging for production, human-readable console for local dev.

In production, Azure Monitor's ``configure_azure_monitor()`` adds its own
OTel ``LoggingHandler`` to the root logger before this runs.

In local dev, ``core.observability._configure_otlp()`` adds an OTel
``LoggingHandler`` that bridges stdlib logs → OTel LoggerProvider → OTLP.

Both handlers are preserved here — we only add/replace the console handler.

Usage::

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
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def configure_logging() -> None:
    """Configure stdlib logging.  Call once at application startup.

    Preserves any OTel ``LoggingHandler`` instances already attached to
    the root logger by ``configure_azure_monitor()`` or our own
    ``_configure_otlp()`` so that logs flow to both the console *and*
    the OTel log pipeline.
    """
    is_production = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    use_json = is_production and os.getenv("LOG_FORMAT", "").lower() != "console"
    level = getattr(
        logging,
        os.environ.get("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )

    root = logging.getLogger()

    # Preserve any OTel handlers already added by observability setup.
    otel_handlers = [h for h in root.handlers if "LoggingHandler" in type(h).__name__]
    root.handlers.clear()
    for h in otel_handlers:
        root.addHandler(h)

    # Add our own console handler for stdout output.
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        _JSONFormatter()
        if use_json
        else logging.Formatter("%(levelname)-5s [%(name)s] %(message)s")
    )
    root.addHandler(console)
    root.setLevel(level)

    # Quiet noisy third-party loggers.
    for name in (
        "httpx",
        "httpcore",
        "uvicorn.access",
        "openai",
        "openai._base_client",
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.monitor.opentelemetry",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
