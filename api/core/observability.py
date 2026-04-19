"""Observability configuration — Azure Monitor telemetry.

Called once from ``main.py`` **before** FastAPI is imported so
auto-instrumentation hooks work.

Simplified to Azure Monitor only. OTLP and per-query SQL tracing removed
to reduce overhead for a low-traffic learning platform.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from agent_framework.observability import create_resource
from azure.monitor.opentelemetry import (
    configure_azure_monitor as _configure_azure_monitor_sdk,
)
from dotenv import load_dotenv
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

logger = logging.getLogger(__name__)

_telemetry_enabled: bool = False


def is_telemetry_enabled() -> bool:
    """Return whether OTel providers are active."""
    return _telemetry_enabled


def configure_observability() -> None:
    """Set up Azure Monitor telemetry if configured.

    Must be called **before** FastAPI or any instrumented library is imported.
    """
    global _telemetry_enabled

    load_dotenv()

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        return

    _telemetry_enabled = True

    try:
        resource = create_resource(
            service_name=os.getenv("OTEL_SERVICE_NAME", "learn-to-cloud-api"),
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
    except Exception as exc:
        logger.warning("telemetry.azure_monitor.failed", extra={"error": str(exc)})

    # Instrument httpx so OpenAI SDK calls appear as dependencies
    HTTPXClientInstrumentor().instrument()


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
