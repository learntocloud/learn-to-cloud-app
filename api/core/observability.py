"""Observability configuration — Azure Monitor telemetry.

Called once from ``main.py`` **before** FastAPI is imported so
auto-instrumentation hooks work.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from azure.monitor.opentelemetry import (
    configure_azure_monitor as _configure_azure_monitor_sdk,
)
from dotenv import load_dotenv
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

_telemetry_enabled: bool = False


def is_telemetry_enabled() -> bool:
    """Return whether OTel providers are active."""
    return _telemetry_enabled


def configure_observability() -> None:
    """Set up Azure Monitor telemetry if configured."""
    global _telemetry_enabled

    load_dotenv()

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        return

    _telemetry_enabled = True

    try:
        resource = Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", "learn-to-cloud-api"),
            }
        )
        _configure_azure_monitor_sdk(
            resource=resource,
            enable_live_metrics=True,
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "flask": {"enabled": False},
                "django": {"enabled": False},
                "fastapi": {"enabled": False},  # manual via instrument_app()
                "psycopg2": {"enabled": False},
                "requests": {"enabled": True},
                "urllib": {"enabled": True},
                "urllib3": {"enabled": True},
            },
        )
        logger.info("telemetry.azure_monitor.configured")
    except Exception as exc:
        logger.warning("telemetry.azure_monitor.failed", extra={"error": str(exc)})

    HTTPXClientInstrumentor().instrument()
    logger.info("telemetry.httpx.instrumented")


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI app with ASGI internal spans excluded."""
    if not _telemetry_enabled:
        return

    try:
        FastAPIInstrumentor.instrument_app(
            app,
            exclude_spans=["send", "receive"],
        )
        logger.info("telemetry.fastapi.instrumented")
    except Exception as exc:
        logger.warning(
            "telemetry.fastapi.failed",
            extra={"error": str(exc)},
        )
