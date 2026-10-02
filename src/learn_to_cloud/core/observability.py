"""Single-pipeline Azure Monitor and OTLP configuration.

Azure Monitor owns FastAPI instrumentation in production; local OTLP configures
it explicitly with SDK defaults. HTTPX and SQLAlchemy are application-owned.
Clients the app builds are measured by ``core.outbound``; the global HTTPX
instrumentors cover third-party clients such as openai's (httpx) and authlib's
GitHub OAuth (httpx2).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import (
    HTTPX2ClientInstrumentor,
    HTTPXClientInstrumentor,
)
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.engine import Engine

from learn_to_cloud.core.logger import APP_LOGGER_NAMESPACE

logger = logging.getLogger(__name__)

SERVICE_NAME = "learn-to-cloud-api"

_telemetry_enabled: bool = False
_dependency_tracing_enabled: bool = False
_httpx_instrumented: bool = False


def _build_resource() -> Resource:
    """Build the shared identity attached to every telemetry signal."""
    attributes = {"service.name": SERVICE_NAME}

    if revision := os.getenv("CONTAINER_APP_REVISION"):
        attributes["service.version"] = revision

    if instance_id := os.getenv("CONTAINER_APP_REPLICA_NAME"):
        attributes["service.instance.id"] = instance_id

    return Resource.create(attributes)


def _configure_azure_monitor(resource: Resource) -> None:
    """Set up the Azure Monitor exporter for production."""
    configure_azure_monitor(
        enable_live_metrics=True,
        logger_name=APP_LOGGER_NAMESPACE,
        resource=resource,
    )


def _configure_otlp(resource: Resource) -> None:
    """Set up the OTLP gRPC exporter for local dev (Aspire, Jaeger, etc.)."""
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    # Bridge stdlib logs → OTel so they appear in the dashboard too.
    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(log_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=log_provider))

    metrics.set_meter_provider(
        MeterProvider(
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
            resource=resource,
        )
    )

    FastAPIInstrumentor().instrument()


def configure_observability() -> bool:
    """Set up the API's Azure Monitor or local OTLP pipeline."""
    global _telemetry_enabled

    if _telemetry_enabled:
        return True

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = _build_resource()

    try:
        if conn_str:
            _configure_azure_monitor(resource)
        elif otlp_endpoint:
            _configure_otlp(resource)
        else:
            logger.error(
                "telemetry.configure.failed",
                extra={
                    "telemetry.configuration.reason": "telemetry_destination_missing"
                },
            )
            return False
    except Exception as exc:
        logger.error(
            "telemetry.configure.failed",
            extra={"error.type": type(exc).__name__},
        )
        return False

    _telemetry_enabled = True
    configure_dependency_instrumentation()
    return True


def configure_dependency_instrumentation() -> bool:
    """Instrument dependencies not bundled by the Azure Monitor distro."""
    global _dependency_tracing_enabled, _httpx_instrumented

    _dependency_tracing_enabled = True
    if _httpx_instrumented:
        return True

    try:
        HTTPXClientInstrumentor().instrument()
        HTTPX2ClientInstrumentor().instrument()
    except Exception as exc:
        logger.warning(
            "telemetry.httpx.failed",
            extra={"error.type": type(exc).__name__},
        )
        return False

    _httpx_instrumented = True
    return True


def instrument_database(engine: Any) -> None:
    """Instrument an engine created after telemetry setup."""
    if not _dependency_tracing_enabled:
        return

    try:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        # Engine.connect spans are pool checkouts; physical connects are
        # measured by the asyncpg creator instead.
        unwrap(Engine, "connect")
    except Exception as exc:
        logger.warning(
            "telemetry.sqlalchemy.failed",
            extra={"error.type": type(exc).__name__},
        )
