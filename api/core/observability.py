"""Unified observability configuration — traces, metrics, logs.

Called once from ``main.py`` **before** FastAPI is imported so
auto-instrumentation hooks work.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_telemetry_enabled: bool = False


def is_telemetry_enabled() -> bool:
    """Return whether OTel providers are active."""
    return _telemetry_enabled


def configure_observability() -> None:
    """Set up all OTel providers and instrumentors.

    Must be called **before** FastAPI or any instrumented library is imported.
    """
    global _telemetry_enabled

    from dotenv import load_dotenv

    load_dotenv()

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")

    if not conn_str and not otlp_endpoint:
        return

    _telemetry_enabled = True

    if conn_str:
        _configure_azure_monitor(conn_str)
    else:
        _configure_otlp(otlp_endpoint)  # type: ignore[arg-type] — checked above

    _enable_agent_framework_instrumentation()


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI app with ASGI internal spans excluded.

    Azure Monitor's FastAPI auto-instrumentation is disabled so we can
    pass ``exclude_spans`` to suppress InProc ``http send``/``receive``
    spans.  See https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2802
    """
    if not _telemetry_enabled:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

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


def instrument_sqlalchemy_engine(engine: Any) -> None:
    """Instrument a SQLAlchemy engine for query tracing."""
    if not _telemetry_enabled:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import (
            SQLAlchemyInstrumentor,
        )

        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            enable_commenter=True,
        )
        logger.info("telemetry.sqlalchemy.instrumented")
    except Exception as exc:
        logger.warning(
            "telemetry.sqlalchemy.failed",
            extra={"error": str(exc)},
        )


def _configure_azure_monitor(conn_str: str) -> None:
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
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


def _configure_otlp(endpoint: str) -> None:
    from opentelemetry import metrics, trace
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
        OTLPLogExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    insecure = endpoint.startswith("http://")
    service_name = os.getenv("OTEL_SERVICE_NAME", "learn-to-cloud-api")
    resource = Resource.create({SERVICE_NAME: service_name})

    # ── Traces ────────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
    )
    trace.set_tracer_provider(tracer_provider)

    # ── Metrics ───────────────────────────────────────────────────────
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=insecure),
        export_interval_millis=15_000,  # 15s for snappy local dev feedback
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ── Logs ──────────────────────────────────────────────────────────
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=insecure))
    )
    set_logger_provider(logger_provider)

    # Bridge stdlib logging → OTel LoggerProvider.
    otel_handler = LoggingHandler(
        level=logging.NOTSET,
        logger_provider=logger_provider,
    )
    logging.getLogger().addHandler(otel_handler)

    try:
        import importlib

        httpx_mod = importlib.import_module("opentelemetry.instrumentation.httpx")
        httpx_mod.HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass

    logger.info(
        "telemetry.otlp.configured",
        extra={"endpoint": endpoint, "service": service_name},
    )


def _enable_agent_framework_instrumentation() -> None:
    """Flip ``enable_otel`` so the framework's decorators use our providers."""
    try:
        from agent_framework.observability import OBSERVABILITY_SETTINGS

        OBSERVABILITY_SETTINGS.enable_otel = True
    except ImportError:
        pass
