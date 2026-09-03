"""Single-pipeline Azure Monitor and OTLP configuration.

The API calls this before constructing FastAPI. Azure Monitor owns FastAPI
instrumentation in production; local OTLP configures it explicitly. HTTPX and
SQLAlchemy remain application-owned because the Azure distro does not bundle
those instrumentations. Verification Functions reuse only the dependency setup
and their host-owned OTLP pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlsplit

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource

from learn_to_cloud_shared.core.logger import APP_LOGGER_NAMESPACE

logger = logging.getLogger(__name__)

_telemetry_enabled: bool = False
_dependency_tracing_enabled: bool = False
_fastapi_instrumented: bool = False
_httpx_instrumented: bool = False


def _httpx_origin(request: Any) -> str:
    url = request.url
    if isinstance(url, tuple):
        scheme, host, port, _ = url
        scheme_text = scheme.decode() if isinstance(scheme, bytes) else scheme
        host_text = host.decode() if isinstance(host, bytes) else host
        return (
            f"{scheme_text}://{host_text}:{port}"
            if port is not None
            else f"{scheme_text}://{host_text}"
        )

    parsed = urlsplit(str(url))
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    return (
        f"{parsed.scheme}://{host}:{parsed.port}"
        if parsed.port is not None
        else f"{parsed.scheme}://{host}"
    )


def _sanitize_httpx_span(span: Any, request: Any) -> None:
    if not span.is_recording():
        return

    origin = _httpx_origin(request)
    span.set_attribute("http.target", "/")
    span.set_attribute("http.url", origin)
    span.set_attribute("url.full", origin)
    span.set_attribute("url.path", "/")
    span.set_attribute("url.query", "")


async def _sanitize_async_httpx_span(span: Any, request: Any) -> None:
    _sanitize_httpx_span(span, request)


def _build_resource() -> Resource:
    """Build the shared identity attached to every telemetry signal."""
    attributes = {
        "service.name": os.getenv("OTEL_SERVICE_NAME") or APP_LOGGER_NAMESPACE,
    }

    if revision := os.getenv("CONTAINER_APP_REVISION"):
        attributes["service.version"] = revision

    instance_id = os.getenv("CONTAINER_APP_REPLICA_NAME") or os.getenv(
        "WEBSITE_INSTANCE_ID"
    )
    if instance_id:
        attributes["service.instance.id"] = instance_id

    return Resource(attributes=attributes)


def _configure_azure_monitor(resource: Resource) -> None:
    """Set up the Azure Monitor exporter for production."""
    from azure.monitor.opentelemetry import (
        configure_azure_monitor as _configure_azure_monitor_sdk,
    )

    _configure_azure_monitor_sdk(
        enable_live_metrics=True,
        enable_trace_based_sampling_for_logs=False,
        logger_name=APP_LOGGER_NAMESPACE,
        resource=resource,
    )


def _configure_otlp_grpc(resource: Resource) -> None:
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

    _configure_otlp_exporters(
        OTLPSpanExporter,
        OTLPLogExporter,
        OTLPMetricExporter,
        resource,
    )


def _configure_otlp_http(resource: Resource) -> None:
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

    _configure_otlp_exporters(
        OTLPSpanExporter,
        OTLPLogExporter,
        OTLPMetricExporter,
        resource,
    )


def _configure_otlp_exporters(
    span_exporter_cls: type[Any],
    log_exporter_cls: type[Any],
    metric_exporter_cls: type[Any],
    resource: Resource,
) -> None:
    from opentelemetry.instrumentation.logging.handler import LoggingHandler
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(span_exporter_cls()))

    from opentelemetry import trace

    trace.set_tracer_provider(provider)

    # Bridge stdlib logs → OTel so they appear in the dashboard too.
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    log_provider = LoggerProvider(resource=resource)
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
            resource=resource,
        )
    )


def _configure_otlp(resource: Resource) -> None:
    """Set up OTLP exporter for local dev (Aspire, Jaeger, etc.)."""
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()
    if protocol == "grpc":
        _configure_otlp_grpc(resource)
    elif protocol in {"http/protobuf", "http"}:
        _configure_otlp_http(resource)
    else:
        raise ValueError(f"Unsupported OTLP protocol: {protocol}")


def _configure_observability(*, allow_azure_monitor: bool) -> bool:
    """Set up one telemetry pipeline and report whether it is active."""
    global _telemetry_enabled

    if _telemetry_enabled:
        return True

    conn_str = (
        os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
        if allow_azure_monitor
        else None
    )
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    resource = _build_resource()
    instrument_fastapi_for_otlp = False

    try:
        if conn_str:
            _configure_azure_monitor(resource)
        elif otlp_endpoint:
            _configure_otlp(resource)
            instrument_fastapi_for_otlp = allow_azure_monitor
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
    if instrument_fastapi_for_otlp:
        configure_fastapi_instrumentation()
    configure_dependency_instrumentation()
    return True


def configure_fastapi_instrumentation() -> bool:
    """Instrument FastAPI when the Azure Monitor distro is not active."""
    global _fastapi_instrumented

    if _fastapi_instrumented:
        return True

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    try:
        FastAPIInstrumentor().instrument()
    except Exception as exc:
        logger.warning(
            "telemetry.fastapi.failed",
            extra={"error.type": type(exc).__name__},
        )
        return False

    _fastapi_instrumented = True
    return True


def configure_dependency_instrumentation() -> bool:
    """Instrument dependencies not bundled by the Azure Monitor distro."""
    global _dependency_tracing_enabled, _httpx_instrumented

    _dependency_tracing_enabled = True
    if _httpx_instrumented:
        return True

    try:
        HTTPXClientInstrumentor().instrument(
            request_hook=_sanitize_httpx_span,
            async_request_hook=_sanitize_async_httpx_span,
        )
    except Exception as exc:
        logger.warning(
            "telemetry.httpx.failed",
            extra={"error.type": type(exc).__name__},
        )
        return False

    _httpx_instrumented = True
    return True


def configure_observability() -> bool:
    """Set up the API's Azure Monitor or local OTLP pipeline."""
    return _configure_observability(allow_azure_monitor=True)


def configure_otlp_observability() -> bool:
    """Set up OTLP without adding an application-owned Azure exporter."""
    return _configure_observability(allow_azure_monitor=False)


def instrument_database(engine: Any) -> None:
    """Instrument an engine created after telemetry setup."""
    if not _dependency_tracing_enabled:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    try:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception as exc:
        logger.warning(
            "telemetry.sqlalchemy.failed",
            extra={"error.type": type(exc).__name__},
        )
