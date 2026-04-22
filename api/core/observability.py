"""Observability configuration — OTel telemetry pipeline.

Called once from ``main.py`` **before** FastAPI is imported so
auto-instrumentation hooks work.

Production: exports to Azure Monitor via APPLICATIONINSIGHTS_CONNECTION_STRING.
Local dev:  exports to any OTLP backend (Aspire, Jaeger) via
            OTEL_EXPORTER_OTLP_ENDPOINT.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

_telemetry_enabled: bool = False


def _configure_azure_monitor(resource: Resource) -> None:
    """Set up the Azure Monitor exporter for production."""
    from azure.monitor.opentelemetry import (
        configure_azure_monitor as _configure_azure_monitor_sdk,
    )
    from opentelemetry.context import get_value
    from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

    class _UserAttributeSpanProcessor(SpanProcessor):
        """Copy user identity from parent span to all child spans.

        The ``UserTrackingMiddleware`` sets ``enduser.id`` and
        ``enduser.name`` on the root request span, but Azure Monitor only
        exports ``CustomDimensions`` from the span that owns them.  This
        processor propagates those attributes to every child span so they
        appear in ``AppDependencies``, ``AppTraces``, and ``AppExceptions``.
        """

        def on_start(self, span: Span, parent_context: Any = None) -> None:
            parent = get_value("current-span", parent_context)
            if parent is None or not isinstance(parent, ReadableSpan):
                return
            parent_attrs = parent.attributes or {}
            for key in ("enduser.id", "enduser.name"):
                value = parent_attrs.get(key)
                if value is not None:
                    span.set_attribute(key, value)

    _configure_azure_monitor_sdk(
        resource=resource,
        enable_live_metrics=True,
        span_processors=[_UserAttributeSpanProcessor()],
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


def _configure_otlp(resource: Resource, endpoint: str) -> None:
    """Set up OTLP gRPC exporter for local dev (Aspire, Jaeger, etc.)."""
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )

    from opentelemetry import trace

    trace.set_tracer_provider(provider)

    # Bridge stdlib logs → OTel so they appear in the dashboard too.
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
        OTLPLogExporter,
    )
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(log_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=log_provider))


def configure_observability() -> None:
    """Set up the OTel telemetry pipeline."""
    global _telemetry_enabled

    load_dotenv()

    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", "learn-to-cloud-api")}
    )

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if conn_str:
        try:
            _configure_azure_monitor(resource)
        except Exception as exc:
            logger.warning("telemetry.azure_monitor.failed", extra={"error": str(exc)})
    elif otlp_endpoint:
        try:
            _configure_otlp(resource, otlp_endpoint)
        except Exception as exc:
            logger.warning("telemetry.otlp.failed", extra={"error": str(exc)})
    else:
        return

    _telemetry_enabled = True
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


def instrument_database(engine: Any) -> None:
    """Instrument a SQLAlchemy engine for database dependency spans."""
    if not _telemetry_enabled:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    try:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        logger.info("telemetry.sqlalchemy.instrumented")
    except Exception as exc:
        logger.warning(
            "telemetry.sqlalchemy.failed",
            extra={"error": str(exc)},
        )
