"""Observability configuration — Azure Monitor/OpenTelemetry telemetry.

Called once from ``main.py`` before ``fastapi.FastAPI`` is instantiated so
Azure Monitor's FastAPI instrumentation can patch the framework.

Production: exports to Azure Monitor via APPLICATIONINSIGHTS_CONNECTION_STRING.
Local dev:  exports to any OTLP backend (Aspire, Jaeger) via
            OTEL_EXPORTER_OTLP_ENDPOINT.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE

logger = logging.getLogger(__name__)

_telemetry_enabled: bool = False


def _configure_azure_monitor() -> None:
    """Set up the Azure Monitor exporter for production."""
    from azure.monitor.opentelemetry import (
        configure_azure_monitor as _configure_azure_monitor_sdk,
    )

    _configure_azure_monitor_sdk(
        enable_live_metrics=True,
        logger_name=APP_LOGGER_NAMESPACE,
    )


def _configure_otlp_grpc() -> None:
    """Set up OTLP gRPC exporter."""
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
        OTLPLogExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    _configure_otlp_exporters(OTLPSpanExporter, OTLPLogExporter, OTLPMetricExporter)


def _configure_otlp_http() -> None:
    """Set up OTLP HTTP/protobuf exporter."""
    from opentelemetry.exporter.otlp.proto.http._log_exporter import (
        OTLPLogExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )

    _configure_otlp_exporters(OTLPSpanExporter, OTLPLogExporter, OTLPMetricExporter)


def _configure_otlp_exporters(
    span_exporter_cls: type[Any],
    log_exporter_cls: type[Any],
    metric_exporter_cls: type[Any],
) -> None:
    from opentelemetry.instrumentation.logging.handler import LoggingHandler
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(span_exporter_cls()))

    from opentelemetry import trace

    trace.set_tracer_provider(provider)

    # Bridge stdlib logs → OTel so they appear in the dashboard too.
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    log_provider = LoggerProvider()
    log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter_cls()))
    set_logger_provider(log_provider)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=log_provider))

    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    metrics.set_meter_provider(
        MeterProvider(
            metric_readers=[
                PeriodicExportingMetricReader(metric_exporter_cls()),
            ],
        )
    )


def _configure_otlp() -> None:
    """Set up OTLP exporter for local dev (Aspire, Jaeger, etc.)."""
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()
    if protocol == "grpc":
        _configure_otlp_grpc()
    elif protocol in {"http/protobuf", "http"}:
        _configure_otlp_http()
    else:
        raise ValueError(f"Unsupported OTLP protocol: {protocol}")


def configure_observability() -> None:
    """Set up the OTel telemetry pipeline."""
    global _telemetry_enabled

    if _telemetry_enabled:
        return

    load_dotenv()

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    try:
        if conn_str:
            _configure_azure_monitor()
        elif otlp_endpoint:
            _configure_otlp()
        else:
            return
    except Exception as exc:
        logger.warning("telemetry.configure.failed", extra={"error": str(exc)})
        return

    _telemetry_enabled = True
    HTTPXClientInstrumentor().instrument()


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
