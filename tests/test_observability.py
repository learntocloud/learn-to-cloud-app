"""Unit tests for observability instrumentation helpers."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from learn_to_cloud.core import observability


@pytest.fixture(autouse=True)
def _restore_telemetry_flag():
    """Restore module telemetry state after each test."""
    original_telemetry = observability._telemetry_enabled
    original_dependencies = observability._dependency_tracing_enabled
    original_httpx = observability._httpx_instrumented
    observability._telemetry_enabled = False
    observability._dependency_tracing_enabled = False
    observability._httpx_instrumented = False
    yield
    observability._telemetry_enabled = original_telemetry
    observability._dependency_tracing_enabled = original_dependencies
    observability._httpx_instrumented = original_httpx


@pytest.mark.unit
def test_configure_observability_logs_missing_destination(
    caplog: pytest.LogCaptureFixture,
):
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "learn_to_cloud.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        caplog.at_level("ERROR"),
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_not_called()
    otlp.assert_not_called()
    httpx_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is False
    assert configured is False
    records = [
        record
        for record in caplog.records
        if record.message == "telemetry.configure.failed"
    ]
    assert len(records) == 1
    assert (
        records[0].__dict__["telemetry.configuration.reason"]
        == "telemetry_destination_missing"
    )
    assert records[0].exc_info is None


@pytest.mark.unit
def test_build_resource_owns_service_name_without_platform_values():
    with patch.dict("os.environ", {"OTEL_SERVICE_NAME": "other"}, clear=True):
        resource = observability._build_resource()

    assert resource.attributes["service.name"] == "learn-to-cloud-api"
    assert "service.version" not in resource.attributes


@pytest.mark.unit
def test_build_resource_maps_container_app_identity():
    with patch.dict(
        "os.environ",
        {
            "CONTAINER_APP_REVISION": "ca-ltc-api--rev42",
            "CONTAINER_APP_REPLICA_NAME": "ca-ltc-api--rev42-abc",
        },
        clear=True,
    ):
        resource = observability._build_resource()

    assert resource.attributes["service.name"] == "learn-to-cloud-api"
    assert resource.attributes["service.version"] == "ca-ltc-api--rev42"
    assert resource.attributes["service.instance.id"] == "ca-ltc-api--rev42-abc"


@pytest.mark.unit
@pytest.mark.parametrize("otlp_endpoint", ["", "http://localhost:4317"])
def test_configure_observability_uses_azure_monitor_when_connection_string_set(
    otlp_endpoint,
):
    resource = MagicMock(spec=Resource)
    with (
        patch.dict(
            "os.environ",
            {
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
                "OTEL_EXPORTER_OTLP_ENDPOINT": otlp_endpoint,
            },
            clear=True,
        ),
        patch(
            "learn_to_cloud.core.observability._build_resource",
            return_value=resource,
        ),
        patch(
            "learn_to_cloud.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        patch(
            "learn_to_cloud.core.observability.FastAPIInstrumentor"
        ) as fastapi_instrumentor,
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_called_once_with(resource)
    otlp.assert_not_called()
    httpx_instrumentor.return_value.instrument.assert_called_once_with()
    fastapi_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is True
    assert configured is True


@pytest.mark.unit
def test_configure_observability_uses_otlp_when_endpoint_set():
    resource = MagicMock(spec=Resource)
    with (
        patch.dict(
            "os.environ",
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
            clear=True,
        ),
        patch(
            "learn_to_cloud.core.observability._build_resource",
            return_value=resource,
        ),
        patch(
            "learn_to_cloud.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_not_called()
    otlp.assert_called_once_with(resource)
    httpx_instrumentor.return_value.instrument.assert_called_once_with()
    assert observability._telemetry_enabled is True
    assert configured is True


@pytest.mark.unit
def test_configure_observability_azure_failure_is_nonfatal_by_default(
    caplog: pytest.LogCaptureFixture,
):
    with (
        patch.dict(
            "os.environ",
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test"},
            clear=True,
        ),
        patch(
            "learn_to_cloud.core.observability._configure_azure_monitor",
            side_effect=RuntimeError("boom"),
        ) as azure_monitor,
        patch(
            "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        caplog.at_level("ERROR"),
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_called_once()
    httpx_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is False
    assert configured is False
    records = [
        record
        for record in caplog.records
        if record.message == "telemetry.configure.failed"
    ]
    assert len(records) == 1
    assert records[0].exc_info is None
    assert records[0].__dict__["error.type"] == "RuntimeError"


@pytest.mark.unit
def test_configure_observability_otlp_failure_is_nonfatal(
    caplog: pytest.LogCaptureFixture,
):
    with (
        patch.dict(
            "os.environ",
            {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
            clear=True,
        ),
        patch(
            "learn_to_cloud.core.observability._configure_otlp",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        caplog.at_level("ERROR"),
    ):
        configured = observability.configure_observability()

    httpx_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is False
    assert configured is False
    records = [
        record
        for record in caplog.records
        if record.message == "telemetry.configure.failed"
    ]
    assert len(records) == 1
    assert records[0].exc_info is None
    assert records[0].__dict__["error.type"] == "RuntimeError"


@pytest.mark.unit
def test_configure_observability_noops_when_already_enabled():
    observability._telemetry_enabled = True

    with (
        patch(
            "learn_to_cloud.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch(
            "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_not_called()
    httpx_instrumentor.assert_not_called()
    assert configured is True


@pytest.mark.unit
def test_configure_azure_monitor_uses_distro_instrumentation_defaults():
    resource = observability._build_resource()
    with patch(
        "learn_to_cloud.core.observability.configure_azure_monitor"
    ) as configure_azure_monitor:
        observability._configure_azure_monitor(resource)

    configure_azure_monitor.assert_called_once()
    kwargs = configure_azure_monitor.call_args.kwargs
    assert kwargs["enable_live_metrics"] is True
    assert "enable_trace_based_sampling_for_logs" not in kwargs
    assert kwargs["logger_name"] == "learn_to_cloud"
    assert "instrumentation_options" not in kwargs
    assert kwargs["resource"] is resource


@pytest.mark.unit
@pytest.mark.parametrize("pipeline", ["azure", "otlp"])
def test_api_and_shared_logs_use_one_exporter(pipeline):
    root = logging.getLogger()
    app_loggers = [
        logging.getLogger(name) for name in ("learn_to_cloud", "learn_to_cloud")
    ]
    original_loggers = [
        (logger, logger.handlers[:], logger.propagate, logger.level)
        for logger in [root, *app_loggers]
    ]
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)
    destination = app_loggers[0] if pipeline == "azure" else root
    environment = (
        {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test"}
        if pipeline == "azure"
        else {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}
    )
    try:
        for app_logger in [root, *app_loggers]:
            app_logger.handlers = []
            app_logger.propagate = True
            app_logger.setLevel(logging.INFO)
        with (
            patch.dict("os.environ", environment, clear=True),
            patch(
                "learn_to_cloud.core.observability.configure_azure_monitor",
                side_effect=lambda **kwargs: destination.addHandler(handler),
            ),
            patch.object(
                observability,
                "_configure_otlp",
                side_effect=lambda resource: destination.addHandler(handler),
            ),
            patch.object(observability, "configure_dependency_instrumentation"),
        ):
            assert observability.configure_observability() is True
            assert observability.configure_observability() is True

        for app_logger in app_loggers:
            logging.getLogger(f"{app_logger.name}.verification").info(
                "verification.attempt.completed",
                extra={"verification.attempt.id": "attempt-probe"},
            )
        records = exporter.get_finished_logs()
        assert len(records) == 2
        for record in records:
            assert record.log_record.body == "verification.attempt.completed"
            assert record.log_record.attributes is not None
            assert record.log_record.attributes["verification.attempt.id"] == (
                "attempt-probe"
            )
    finally:
        for app_logger, handlers, propagate, level in original_loggers:
            app_logger.handlers = handlers
            app_logger.propagate = propagate
            app_logger.setLevel(level)
        provider.shutdown()


@pytest.mark.unit
def test_configure_otlp_uses_env_driven_exporter_defaults():
    resource = observability._build_resource()
    with (
        patch("learn_to_cloud.core.observability.OTLPSpanExporter") as span_exporter,
        patch("learn_to_cloud.core.observability.TracerProvider") as tracer_provider,
        patch("learn_to_cloud.core.observability.BatchSpanProcessor") as span_processor,
        patch("opentelemetry.trace.set_tracer_provider") as set_tracer_provider,
        patch(
            "learn_to_cloud.core.observability.set_logger_provider"
        ) as set_logger_provider,
        patch("learn_to_cloud.core.observability.OTLPLogExporter") as log_exporter,
        patch(
            "learn_to_cloud.core.observability.OTLPMetricExporter"
        ) as metric_exporter,
        patch("learn_to_cloud.core.observability.LoggerProvider") as logger_provider,
        patch(
            "learn_to_cloud.core.observability.BatchLogRecordProcessor"
        ) as log_processor,
        patch("opentelemetry.metrics.set_meter_provider") as set_meter_provider,
        patch("learn_to_cloud.core.observability.MeterProvider") as meter_provider,
        patch(
            "learn_to_cloud.core.observability.PeriodicExportingMetricReader"
        ) as metric_reader,
        patch("learn_to_cloud.core.observability.LoggingHandler") as logging_handler,
        patch("learn_to_cloud.core.observability.logging.getLogger") as get_logger,
        patch(
            "learn_to_cloud.core.observability.FastAPIInstrumentor"
        ) as fastapi_instrumentor,
    ):
        observability._configure_otlp(resource)

    fastapi_instrumentor.return_value.instrument.assert_called_once_with()
    span_exporter.assert_called_once_with()
    span_processor.assert_called_once_with(span_exporter.return_value)
    tracer_provider.assert_called_once_with(resource=resource)
    tracer_provider.return_value.add_span_processor.assert_called_once_with(
        span_processor.return_value
    )
    set_tracer_provider.assert_called_once_with(tracer_provider.return_value)
    log_exporter.assert_called_once_with()
    log_processor.assert_called_once_with(log_exporter.return_value)
    logger_provider.assert_called_once_with(resource=resource)
    logger_provider.return_value.add_log_record_processor.assert_called_once_with(
        log_processor.return_value
    )
    set_logger_provider.assert_called_once_with(logger_provider.return_value)
    logging_handler.assert_called_once_with(
        logger_provider=logger_provider.return_value
    )
    get_logger.return_value.addHandler.assert_called_once_with(
        logging_handler.return_value
    )
    metric_exporter.assert_called_once_with()
    metric_reader.assert_called_once_with(metric_exporter.return_value)
    meter_provider.assert_called_once_with(
        metric_readers=[metric_reader.return_value],
        resource=resource,
    )
    set_meter_provider.assert_called_once_with(meter_provider.return_value)


@pytest.mark.unit
def test_httpx_instrumentation_is_process_wide_and_idempotent():
    with patch(
        "learn_to_cloud.core.observability.HTTPXClientInstrumentor"
    ) as httpx_instrumentor:
        assert observability.configure_dependency_instrumentation() is True
        assert observability.configure_dependency_instrumentation() is True

    httpx_instrumentor.return_value.instrument.assert_called_once_with()


@pytest.mark.unit
def test_instrument_database_noops_when_telemetry_disabled():
    engine = SimpleNamespace(sync_engine=object())

    with patch(
        "learn_to_cloud.core.observability.SQLAlchemyInstrumentor"
    ) as instrumentor_cls:
        observability.instrument_database(engine)

    instrumentor_cls.assert_not_called()


@pytest.mark.unit
def test_instrument_database_uses_the_created_sync_engine():
    sync_engine = object()
    engine = SimpleNamespace(sync_engine=sync_engine)
    observability._dependency_tracing_enabled = True

    with patch(
        "learn_to_cloud.core.observability.SQLAlchemyInstrumentor"
    ) as instrumentor_cls:
        observability.instrument_database(engine)

    instrumentor_cls.return_value.instrument.assert_called_once_with(engine=sync_engine)


@pytest.mark.integration
async def test_database_spans_keep_statements_but_not_pool_checkouts(test_engine):

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    engine = create_async_engine(test_engine.url, poolclass=NullPool)
    observability._dependency_tracing_enabled = True
    try:
        with patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
            observability.instrument_database(engine)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        SQLAlchemyInstrumentor().uninstrument()
        await engine.dispose()
        provider.shutdown()

    names = [span.name for span in exporter.get_finished_spans()]
    assert "connect" not in names
    assert any(name.startswith("SELECT") for name in names)
