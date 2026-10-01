"""In-memory capture of outbound dependency spans and metrics."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from learn_to_cloud_shared.core import outbound
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

DURATION_METRIC = "learn_to_cloud.dependency.duration"
METRIC_KEYS = frozenset(
    {
        outbound.DEPENDENCY_NAME,
        outbound.DEPENDENCY_OPERATION,
        outbound.DEPENDENCY_ATTEMPT,
        outbound.ERROR_TYPE,
        "http.response.status_code",
    }
)


class OutboundTelemetry:
    """Spans and duration points recorded by the outbound boundary."""

    def __init__(self, spans: InMemorySpanExporter, reader: InMemoryMetricReader):
        self._spans = spans
        self._reader = reader

    def spans(self) -> list[ReadableSpan]:
        return list(self._spans.get_finished_spans())

    def points(self) -> list[dict[str, Any]]:
        data = self._reader.get_metrics_data()
        if data is None:
            return []
        return [
            {"count": point.count, **dict(point.attributes or {})}
            for resource in data.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
            if metric.name == DURATION_METRIC
            for point in metric.data.data_points
            if isinstance(point, HistogramDataPoint)
        ]

    def dump(self) -> str:
        """Everything captured, serialized for forbidden-content checks."""
        return json.dumps(
            {
                "spans": [json.loads(span.to_json()) for span in self.spans()],
                "points": self.points(),
            },
            default=str,
        )

    def assert_bounded(self) -> None:
        """Every point uses only allowed keys and a known ``error.type``."""
        for point in self.points():
            assert set(point) - {"count"} <= METRIC_KEYS, point
            error_type = point.get(outbound.ERROR_TYPE, outbound.OTHER)
            assert error_type in outbound.ERROR_TYPES, point
            assert point[outbound.DEPENDENCY_ATTEMPT] in {"first", "retry"}


@contextmanager
def capture_outbound_telemetry() -> Iterator[OutboundTelemetry]:
    """Route the outbound boundary's tracer and histogram to in-memory exporters."""
    spans = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(spans))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    histogram = meter_provider.get_meter("test").create_histogram(
        DURATION_METRIC, unit="s"
    )
    try:
        with (
            patch.object(outbound, "_tracer", tracer_provider.get_tracer("test")),
            patch.object(outbound, "_DURATION", histogram),
        ):
            yield OutboundTelemetry(spans, reader)
    finally:
        tracer_provider.shutdown()
        meter_provider.shutdown()
