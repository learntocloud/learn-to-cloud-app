"""Unit tests for observability instrumentation helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.resources import Resource

from learn_to_cloud_shared.core import observability


@pytest.fixture(autouse=True)
def _restore_telemetry_flag():
    """Restore module telemetry state after each test."""
    original = observability._telemetry_enabled
    observability._telemetry_enabled = False
    yield
    observability._telemetry_enabled = original


@pytest.mark.unit
def test_configure_observability_noops_without_exporter_env():
    with (
        patch.dict("os.environ", {}, clear=True),
        patch(
            "learn_to_cloud_shared.core.observability._configure_azure_monitor"
        ) as azure_monitor,
        patch("learn_to_cloud_shared.core.observability._configure_otlp") as otlp,
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
    ):
        observability.configure_observability()

    azure_monitor.assert_not_called()
    otlp.assert_not_called()
    httpx_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is False


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
def test_configure_observability_uses_azure_monitor_when_connection_string_set():
    resource = MagicMock(spec=Resource)
    with (
        patch.dict(
            "os.environ",
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test"},
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
    ):
        observability.configure_observability()

    azure_monitor.assert_called_once_with(resource)
    otlp.assert_not_called()
    httpx_instrumentor.return_value.instrument.assert_called_once_with()
    assert observability._telemetry_enabled is True


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
    ):
        observability.configure_observability()

    azure_monitor.assert_not_called()
    otlp.assert_called_once_with(resource)
    httpx_instrumentor.return_value.instrument.assert_called_once_with()
    assert observability._telemetry_enabled is True


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
        observability.configure_observability()

    azure_monitor.assert_called_once()
    httpx_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is False
    records = [
        record
        for record in caplog.records
        if record.message == "telemetry.configure.failed"
    ]
    assert len(records) == 1
    assert records[0].exc_info is not None


@pytest.mark.unit
def test_configure_observability_azure_failure_reraises_when_opted_in():
    with (
        patch.dict(
            "os.environ",
            {"APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test"},
            clear=True,
        ),
        patch(
            "learn_to_cloud_shared.core.observability._configure_azure_monitor",
            side_effect=RuntimeError("boom"),
        ),
        patch(
            "learn_to_cloud_shared.core.observability.HTTPXClientInstrumentor"
        ) as httpx_instrumentor,
        pytest.raises(RuntimeError, match="boom"),
    ):
        observability.configure_observability(fail_on_azure_error=True)

    httpx_instrumentor.assert_not_called()
    assert observability._telemetry_enabled is False


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
        observability.configure_observability()

    azure_monitor.assert_not_called()
    httpx_instrumentor.assert_not_called()


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
    assert kwargs["logger_name"] == "learn_to_cloud"
    assert "instrumentation_options" not in kwargs
    assert kwargs["resource"] is resource


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
def test_instrument_database_noops_when_telemetry_disabled():
    engine = SimpleNamespace(sync_engine=object())

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as instrumentor_cls:
        observability._telemetry_enabled = False

        observability.instrument_database(engine)

    instrumentor_cls.assert_not_called()


@pytest.mark.unit
def test_instrument_database_uses_sync_engine():
    sync_engine = object()
    engine = SimpleNamespace(sync_engine=sync_engine)

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as instrumentor_cls:
        observability._telemetry_enabled = True

        observability.instrument_database(engine)

    instrumentor_cls.return_value.instrument.assert_called_once_with(engine=sync_engine)
