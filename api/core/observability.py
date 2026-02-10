"""Unified observability configuration — traces, metrics, logs.

Owns all OpenTelemetry provider setup.  Called once from ``main.py``
**before** FastAPI is imported so auto-instrumentation hooks work.

Two modes
---------
1. **Production** — ``APPLICATIONINSIGHTS_CONNECTION_STRING`` is set.
   Delegates entirely to ``configure_azure_monitor()`` which creates
   its own providers, exporters, and instrumentors.

2. **Local dev** — ``OTLP_ENDPOINT`` is set (no App Insights string).
   Explicitly creates TracerProvider / MeterProvider / LoggerProvider
   with OTLP gRPC exporters pointed at the endpoint (e.g. Aspire
   Dashboard on ``http://localhost:4317``).

In both modes the Agent Framework's ``OBSERVABILITY_SETTINGS.enable_otel``
flag is set directly — we do NOT call ``setup_observability()`` because it
creates duplicate providers and attaches a ``ConsoleLogExporter`` handler
to the root logger.  The framework's LLM tracing decorators resolve
tracers/meters through the global OTel providers (ours), so this is safe.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level flag set by configure_observability() at import time.
# Other modules (UserTrackingMiddleware, instrument_sqlalchemy_engine, etc.)
# check this before touching OTel APIs.
# ---------------------------------------------------------------------------
_telemetry_enabled: bool = False


def is_telemetry_enabled() -> bool:
    """Return whether OTel providers are active."""
    return _telemetry_enabled


# ---------------------------------------------------------------------------
# Public API called from main.py — the ONLY entry point
# ---------------------------------------------------------------------------


def configure_observability() -> None:
    """Set up all OTel providers and instrumentors.

    Must be called **before** FastAPI or any instrumented library is imported.
    """
    global _telemetry_enabled  # noqa: PLW0603

    # Load .env into os.environ early so OTLP_ENDPOINT, OTEL_SERVICE_NAME,
    # APPLICATIONINSIGHTS_CONNECTION_STRING, etc. are visible to os.getenv.
    from dotenv import load_dotenv

    load_dotenv()

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    otlp_endpoint = os.getenv("OTLP_ENDPOINT")

    if not conn_str and not otlp_endpoint:
        return

    _telemetry_enabled = True

    if conn_str:
        _configure_azure_monitor(conn_str, otlp_endpoint)
    else:
        _configure_otlp(otlp_endpoint)  # type: ignore[arg-type] — checked above

    # Agent Framework LLM instrumentation (token usage spans/metrics).
    # This only enables *its* instrumentors — we already own the providers.
    _enable_agent_framework_instrumentation()


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI app instance for HTTP tracing + metrics.

    Call this *after* the app is created.  In production the Azure Monitor
    distro handles this automatically; in OTLP-only mode we do it ourselves.
    """
    if not _telemetry_enabled:
        return

    # Azure Monitor's distro auto-instruments FastAPI at import time.
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("telemetry.fastapi.instrumented")
    except (ImportError, Exception) as exc:
        logger.warning(
            "telemetry.fastapi.failed",
            extra={"error": str(exc)},
        )


def instrument_sqlalchemy_engine(engine: Any) -> None:
    """Add OpenTelemetry instrumentation for SQLAlchemy query tracing."""
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


def add_user_span_processor() -> None:
    """Stamp ``enduser.id`` from the session onto every span.

    Populates the ``UserId`` column in App Insights ``AppRequests``
    and ``AppDependencies``.
    """
    if not _telemetry_enabled:
        return

    try:
        from opentelemetry import context as otel_context
        from opentelemetry.context import Context
        from opentelemetry.sdk.trace import (
            ReadableSpan,
            Span,
            SpanProcessor,
            TracerProvider,
        )
        from opentelemetry.trace import get_tracer_provider

        _USER_ID_KEY = otel_context.create_key("ltc.user_id")

        class _UserIdSpanProcessor(SpanProcessor):
            """Lightweight SpanProcessor — reads user_id from OTel context."""

            def on_start(
                self,
                span: Span,
                parent_context: Context | None = None,
            ) -> None:
                ctx = parent_context or otel_context.get_current()
                user_id = ctx.get(_USER_ID_KEY)
                if user_id is not None:
                    span.set_attribute("enduser.id", str(user_id))

            def on_end(self, span: ReadableSpan) -> None:
                pass

            def shutdown(self) -> None:
                pass

            def force_flush(self, timeout_millis: int = 30000) -> bool:
                return True

        provider = get_tracer_provider()
        if isinstance(provider, TracerProvider):
            provider.add_span_processor(_UserIdSpanProcessor())
            logger.info("telemetry.user_span_processor.enabled")
    except Exception as exc:
        logger.warning(
            "telemetry.user_span_processor.failed",
            extra={"error": str(exc)},
        )


# ---------------------------------------------------------------------------
# Middleware (no change in behaviour, just consolidated here)
# ---------------------------------------------------------------------------


class UserTrackingMiddleware:
    """ASGI middleware injecting user_id into OTel context.

    Must sit AFTER SessionMiddleware so ``scope["session"]`` is populated.
    Works with ``add_user_span_processor()`` — this sets the context value,
    the processor copies it onto every span.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session: dict = scope.get("session", {})
        user_id = session.get("user_id")

        if user_id is not None and _telemetry_enabled:
            from opentelemetry import context as otel_context

            _USER_ID_KEY = otel_context.create_key("ltc.user_id")
            ctx = otel_context.set_value(_USER_ID_KEY, user_id)
            token = otel_context.attach(ctx)
            try:
                await self.app(scope, receive, send)
            finally:
                otel_context.detach(token)
        else:
            await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Adds security headers (CSP, HSTS, X-Frame-Options, etc.)."""

    SECURITY_HEADERS: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"0"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (
            b"content-security-policy",
            b"default-src 'self';"
            b" script-src 'self' 'unsafe-inline' 'unsafe-eval';"
            b" style-src 'self' 'unsafe-inline';"
            b" img-src 'self' https://avatars.githubusercontent.com data:;"
            b" connect-src 'self' https://github.com;"
            b" font-src 'self';"
            b" frame-ancestors 'none'",
        ),
        (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_static = scope.get("path", "").startswith("/static/")

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.extend(self.SECURITY_HEADERS)
                if is_static:
                    headers.append(
                        (b"cache-control", b"public, max-age=31536000, immutable")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ===================================================================
# Private helpers — production (Azure Monitor) vs local dev (OTLP)
# ===================================================================


def _configure_azure_monitor(conn_str: str, otlp_endpoint: str | None) -> None:
    """Production: Azure Monitor creates all providers + instrumentors."""
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            enable_live_metrics=True,
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "flask": {"enabled": False},
                "django": {"enabled": False},
                "fastapi": {"enabled": True},
                "psycopg2": {"enabled": False},
                "requests": {"enabled": True},
                "urllib": {"enabled": True},
                "urllib3": {"enabled": True},
            },
        )
        logger.info("telemetry.azure_monitor.configured")
    except (ValueError, Exception) as exc:
        logger.warning("telemetry.azure_monitor.failed", extra={"error": str(exc)})


def _configure_otlp(endpoint: str) -> None:
    """Local dev: create our own providers with OTLP gRPC exporters.

    Follows the canonical pattern from the OTel Python SDK docs:
    one TracerProvider / MeterProvider / LoggerProvider, each with a
    BatchProcessor wrapping an OTLPExporter pointed at the collector.
    """
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

    # Bridge stdlib logging → OTel LoggerProvider so every logger.info()
    # call flows to the OTLP collector as a structured log record.
    otel_handler = LoggingHandler(
        level=logging.NOTSET,
        logger_provider=logger_provider,
    )
    logging.getLogger().addHandler(otel_handler)

    # ── Outbound HTTP instrumentation ─────────────────────────────────
    try:
        import importlib

        httpx_mod = importlib.import_module("opentelemetry.instrumentation.httpx")
        httpx_mod.HTTPXClientInstrumentor().instrument()
    except (ImportError, Exception):
        pass

    logger.info(
        "telemetry.otlp.configured",
        extra={"endpoint": endpoint, "service": service_name},
    )


def _enable_agent_framework_instrumentation() -> None:
    """Enable Agent Framework LLM instrumentation without provider conflicts.

    The framework's ``setup_observability()`` creates its own TracerProvider,
    MeterProvider, LoggerProvider (with ConsoleExporter fallbacks) and adds
    a ``LoggingHandler`` to the root logger — all of which conflict with
    providers we've already registered.

    Instead we skip ``setup_observability()`` entirely and flip the only
    flag the framework's tracing decorators actually check:
    ``OBSERVABILITY_SETTINGS.enable_otel``.  The decorators call
    ``get_tracer()`` / ``get_meter()`` which resolve through the global
    OTel providers — i.e., ours — so LLM spans and metrics flow to
    our exporters with zero duplication.
    """
    try:
        from agent_framework.observability import OBSERVABILITY_SETTINGS

        OBSERVABILITY_SETTINGS.enable_otel = True
    except (ImportError, Exception):
        pass
