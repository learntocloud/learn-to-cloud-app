"""Unit tests for observability instrumentation helpers."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import httpx
import pytest
from opentelemetry.instrumentation.httpx import AsyncOpenTelemetryTransport, RequestInfo
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from learn_to_cloud_shared.core import observability


@pytest.fixture(autouse=True)
def _restore_telemetry_flag():
    """Restore module telemetry state after each test."""
    original_telemetry = observability._telemetry_enabled
    original_dependencies = observability._dependency_tracing_enabled
    original_fastapi = observability._fastapi_instrumented
    original_httpx = observability._httpx_instrumented
    observability._telemetry_enabled = False
    observability._dependency_tracing_enabled = False
    observability._fastapi_instrumented = False
    observability._httpx_instrumented = False
    yield
    observability._telemetry_enabled = original_telemetry
    observability._dependency_tracing_enabled = original_dependencies
    observability._fastapi_instrumented = original_fastapi
    observability._httpx_instrumented = original_httpx


@pytest.mark.unit
def test_configure_observability_logs_missing_destination(
    caplog: pytest.LogCaptureFixture,
):
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "learn_to_cloud_shared.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud_shared.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
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
def test_build_resource_uses_logger_namespace_without_platform_values():
    with patch.dict("os.environ", {}, clear=True):
        resource = observability._build_resource()

    assert resource.attributes["service.name"] == "learn_to_cloud"
    assert "service.version" not in resource.attributes
    assert "service.instance.id" not in resource.attributes


@pytest.mark.unit
def test_build_resource_maps_container_app_identity():
    with patch.dict(
        "os.environ",
        {
            "OTEL_SERVICE_NAME": "learn-to-cloud-api",
            "CONTAINER_APP_REVISION": "ca-ltc-api--rev42",
            "CONTAINER_APP_REPLICA_NAME": "ca-ltc-api--rev42-abc",
            "WEBSITE_INSTANCE_ID": "function-instance",
        },
        clear=True,
    ):
        resource = observability._build_resource()

    assert resource.attributes["service.name"] == "learn-to-cloud-api"
    assert resource.attributes["service.version"] == "ca-ltc-api--rev42"
    assert resource.attributes["service.instance.id"] == "ca-ltc-api--rev42-abc"


@pytest.mark.unit
def test_build_resource_maps_function_instance_identity():
    with patch.dict(
        "os.environ",
        {
            "OTEL_SERVICE_NAME": "learn-to-cloud-verification-functions",
            "WEBSITE_INSTANCE_ID": "function-instance",
        },
        clear=True,
    ):
        resource = observability._build_resource()

    assert (
        resource.attributes["service.name"] == "learn-to-cloud-verification-functions"
    )
    assert resource.attributes["service.instance.id"] == "function-instance"
    assert "service.version" not in resource.attributes


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
            "learn_to_cloud_shared.core.observability._build_resource",
            return_value=resource,
        ),
        patch(
            "learn_to_cloud_shared.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud_shared.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
        ) as fastapi_instrumentor,
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_called_once_with(resource)
    otlp.assert_not_called()
    httpx_instrumentor.return_value.instrument.assert_called_once_with(
        request_hook=observability._sanitize_httpx_span,
        async_request_hook=observability._sanitize_async_httpx_span,
    )
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
            "learn_to_cloud_shared.core.observability._build_resource",
            return_value=resource,
        ),
        patch(
            "learn_to_cloud_shared.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud_shared.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
        ) as fastapi_instrumentor,
    ):
        configured = observability.configure_observability()

    azure_monitor.assert_not_called()
    otlp.assert_called_once_with(resource)
    httpx_instrumentor.return_value.instrument.assert_called_once_with(
        request_hook=observability._sanitize_httpx_span,
        async_request_hook=observability._sanitize_async_httpx_span,
    )
    fastapi_instrumentor.return_value.instrument.assert_called_once_with()
    assert observability._telemetry_enabled is True
    assert configured is True


@pytest.mark.unit
def test_configure_otlp_observability_never_uses_azure_monitor():
    resource = MagicMock(spec=Resource)
    with (
        patch.dict(
            "os.environ",
            {
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            },
            clear=True,
        ),
        patch(
            "learn_to_cloud_shared.core.observability._build_resource",
            return_value=resource,
        ),
        patch(
            "learn_to_cloud_shared.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud_shared.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
        ) as fastapi_instrumentor,
    ):
        configured = observability.configure_otlp_observability()

    assert configured is True
    azure_monitor.assert_not_called()
    otlp.assert_called_once_with(resource)
    httpx_instrumentor.return_value.instrument.assert_called_once_with(
        request_hook=observability._sanitize_httpx_span,
        async_request_hook=observability._sanitize_async_httpx_span,
    )
    fastapi_instrumentor.assert_not_called()


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
            "learn_to_cloud_shared.core.observability._configure_azure_monitor",
            side_effect=RuntimeError("boom"),
        ) as azure_monitor,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
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
            "learn_to_cloud_shared.core.observability._configure_otlp",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
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
            "learn_to_cloud_shared.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
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
        "azure.monitor.opentelemetry.configure_azure_monitor"
    ) as configure_azure_monitor:
        observability._configure_azure_monitor(resource)

    configure_azure_monitor.assert_called_once()
    kwargs = configure_azure_monitor.call_args.kwargs
    assert kwargs["enable_live_metrics"] is True
    assert kwargs["enable_trace_based_sampling_for_logs"] is False
    assert kwargs["logger_name"] == "learn_to_cloud"
    assert "instrumentation_options" not in kwargs
    assert kwargs["resource"] is resource


@pytest.mark.unit
def test_local_functions_export_app_logs_once_without_host_forwarding():
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    app_loggers = [
        logging.getLogger(name) for name in ("learn_to_cloud", "learn_to_cloud_shared")
    ]
    original_loggers = [
        (logger, logger.handlers[:], logger.propagate, logger.level)
        for logger in app_loggers
    ]
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    handler = LoggingHandler(logger_provider=provider)
    handler.set_name(observability._OTLP_HANDLER_NAME)
    host_handler = MagicMock(spec=logging.Handler)
    host_handler.level = logging.NOTSET
    root.handlers = [handler, host_handler]
    try:
        with patch.object(observability, "_configure_observability", return_value=True):
            assert observability.configure_otlp_observability() is True
            assert observability.configure_otlp_observability() is True

        for app_logger in app_loggers:
            app_logger.setLevel(logging.INFO)
            logging.getLogger(f"{app_logger.name}.verification").info(
                "verification.attempt.completed",
                extra={"verification.attempt.id": "attempt-probe"},
            )

        records = exporter.get_finished_logs()
        assert len(records) == 2
        for record in records:
            assert record.log_record.body == "verification.attempt.completed"
            assert record.log_record.attributes["verification.attempt.id"] == (
                "attempt-probe"
            )
        host_handler.handle.assert_not_called()
        logging.getLogger("azure.functions").warning("framework-probe")
        host_handler.handle.assert_called_once()
        assert host_handler.handle.call_args.args[0].getMessage() == "framework-probe"
        assert root.handlers == [host_handler]
    finally:
        root.handlers = original_handlers
        for app_logger, handlers, propagate, level in original_loggers:
            app_logger.handlers = handlers
            app_logger.propagate = propagate
            app_logger.setLevel(level)
        provider.shutdown()


@pytest.mark.unit
def test_failed_local_setup_does_not_change_log_routing():
    root = logging.getLogger()
    handlers = root.handlers[:]
    app_logger = logging.getLogger("learn_to_cloud")
    propagation = app_logger.propagate
    with patch.object(observability, "_configure_observability", return_value=False):
        assert observability.configure_otlp_observability() is False
    assert root.handlers == handlers
    assert app_logger.propagate is propagation


@pytest.mark.unit
def test_fastapi_instrumentation_is_process_wide_and_idempotent():
    with patch(
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
    ) as instrumentor:
        assert observability.configure_fastapi_instrumentation() is True
        assert observability.configure_fastapi_instrumentation() is True
    instrumentor.return_value.instrument.assert_called_once_with()


@pytest.mark.unit
def test_configure_otlp_uses_env_driven_exporter_defaults():
    resource = observability._build_resource()
    with (
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter"
        ) as span_exporter,
        patch("opentelemetry.sdk.trace.TracerProvider") as tracer_provider,
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as span_processor,
        patch("opentelemetry.trace.set_tracer_provider") as set_tracer_provider,
        patch("opentelemetry._logs.set_logger_provider") as set_logger_provider,
        patch(
            "opentelemetry.exporter.otlp.proto.grpc._log_exporter.OTLPLogExporter"
        ) as log_exporter,
        patch(
            "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter"
        ) as metric_exporter,
        patch("opentelemetry.sdk._logs.LoggerProvider") as logger_provider,
        patch(
            "opentelemetry.sdk._logs.export.BatchLogRecordProcessor"
        ) as log_processor,
        patch("opentelemetry.metrics.set_meter_provider") as set_meter_provider,
        patch("opentelemetry.sdk.metrics.MeterProvider") as meter_provider,
        patch(
            "opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"
        ) as metric_reader,
        patch(
            "opentelemetry.instrumentation.logging.handler.LoggingHandler"
        ) as logging_handler,
        patch(
            "learn_to_cloud_shared.core.observability.logging.getLogger"
        ) as get_logger,
    ):
        observability._configure_otlp(resource)

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
def test_configure_otlp_uses_http_exporters_when_protocol_is_http():
    resource = observability._build_resource()
    with (
        patch.dict(
            "os.environ",
            {"OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf"},
            clear=True,
        ),
        patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as span_exporter,
        patch("opentelemetry.sdk.trace.TracerProvider") as tracer_provider,
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as span_processor,
        patch("opentelemetry.trace.set_tracer_provider") as set_tracer_provider,
        patch("opentelemetry._logs.set_logger_provider") as set_logger_provider,
        patch(
            "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"
        ) as log_exporter,
        patch(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
        ) as metric_exporter,
        patch("opentelemetry.sdk._logs.LoggerProvider") as logger_provider,
        patch(
            "opentelemetry.sdk._logs.export.BatchLogRecordProcessor"
        ) as log_processor,
        patch("opentelemetry.metrics.set_meter_provider") as set_meter_provider,
        patch("opentelemetry.sdk.metrics.MeterProvider") as meter_provider,
        patch(
            "opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"
        ) as metric_reader,
        patch(
            "opentelemetry.instrumentation.logging.handler.LoggingHandler"
        ) as logging_handler,
        patch(
            "learn_to_cloud_shared.core.observability.logging.getLogger"
        ) as get_logger,
    ):
        observability._configure_otlp(resource)

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
        "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
    ) as httpx_instrumentor:
        assert observability.configure_dependency_instrumentation() is True
        assert observability.configure_dependency_instrumentation() is True

    httpx_instrumentor.return_value.instrument.assert_called_once_with(
        request_hook=observability._sanitize_httpx_span,
        async_request_hook=observability._sanitize_async_httpx_span,
    )


@pytest.mark.unit
def test_httpx_hook_preserves_dependency_path_without_credentials():
    span = MagicMock()
    span.is_recording.return_value = True
    request = RequestInfo(
        b"GET",
        httpx.URL(
            "https://user:password@api.example.com/users/123?token=sensitive#secret"
        ),
        None,
        None,
        None,
    )

    observability._sanitize_httpx_span(span, request)

    assert span.set_attribute.call_args_list == [
        call("http.url", "https://api.example.com/users/123"),
        call("url.full", "https://api.example.com/users/123"),
        call("url.query", ""),
    ]


@pytest.mark.unit
@pytest.mark.parametrize("failed", [False, True])
async def test_httpx_exports_native_dependency_without_query_credentials(failed):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    def respond(request):
        assert request.url.params["token"] == "query-credential-sentinel"
        if failed:
            raise httpx.ConnectError("Connection failed", request=request)
        return httpx.Response(200)

    transport = AsyncOpenTelemetryTransport(
        httpx.MockTransport(respond),
        tracer_provider=provider,
        request_hook=observability._sanitize_async_httpx_span,
    )
    try:
        async with httpx.AsyncClient(transport=transport) as client:
            url = "https://example.com/users/123?token=query-credential-sentinel"
            if failed:
                with pytest.raises(httpx.ConnectError, match="Connection failed"):
                    await client.get(url)
            else:
                assert (await client.get(url)).status_code == 200
        (span,) = exporter.get_finished_spans()
        assert span.name == "GET"
        assert span.attributes["url.full"] == "https://example.com/users/123"
        assert span.end_time >= span.start_time
        assert "query-credential-sentinel" not in span.to_json()
        assert span.status.status_code == (
            StatusCode.ERROR if failed else StatusCode.UNSET
        )
        if failed:
            assert any(event.name == "exception" for event in span.events)
    finally:
        provider.shutdown()


@pytest.mark.unit
def test_instrument_database_noops_when_telemetry_disabled():
    engine = SimpleNamespace(sync_engine=object())

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as instrumentor_cls:
        observability.instrument_database(engine)

    instrumentor_cls.assert_not_called()


@pytest.mark.unit
def test_instrument_database_uses_the_created_sync_engine():
    sync_engine = object()
    engine = SimpleNamespace(sync_engine=sync_engine)
    observability._dependency_tracing_enabled = True

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as instrumentor_cls:
        observability.instrument_database(engine)

    instrumentor_cls.return_value.instrument.assert_called_once_with(engine=sync_engine)
