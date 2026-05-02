"""Centralized stdlib logging configuration.

Simple JSON logging for Azure Container Apps, human-readable console for
local dev. Azure Monitor/OpenTelemetry setup lives in ``core.observability``.

Usage::

    import logging
    logger = logging.getLogger(__name__)
    logger.info("user.login", extra={"user_id": "123", "method": "oauth"})
"""

import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter

APP_LOGGER_NAMESPACE = "learn_to_cloud"
_APP_HANDLER_NAME = "learn_to_cloud.stdout"


def _json_formatter() -> JsonFormatter:
    """Create the production JSON formatter."""
    return JsonFormatter(
        ["levelname", "name", "message"],
        rename_fields={
            "levelname": "level",
            "name": "logger",
            "message": "event",
            "exc_info": "exception",
        },
        timestamp="timestamp",
        json_ensure_ascii=False,
    )


def configure_logging() -> None:
    """Configure stdlib logging. Call once at application startup."""
    is_production = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    use_json = is_production and os.getenv("LOG_FORMAT", "").lower() != "console"
    level = getattr(
        logging,
        os.environ.get("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )

    root = logging.getLogger()

    for handler in list(root.handlers):
        if handler.get_name() == _APP_HANDLER_NAME:
            root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.set_name(_APP_HANDLER_NAME)
    console.setFormatter(
        _json_formatter()
        if use_json
        else logging.Formatter("%(levelname)-5s [%(name)s] %(message)s")
    )
    root.addHandler(console)
    root.setLevel(level)

    for name in (
        "httpx",
        "httpcore",
        "uvicorn.access",
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "azure.monitor.opentelemetry",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
