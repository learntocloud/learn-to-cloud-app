"""Small helpers for annotating the active backend telemetry span."""

from __future__ import annotations

from collections.abc import Mapping

from opentelemetry import trace
from opentelemetry.util.types import AttributeValue

SpanAttributes = Mapping[str, AttributeValue]


def add_span_event(name: str, attributes: SpanAttributes) -> None:
    """Add an event to the current span when telemetry is active."""
    span = trace.get_current_span()
    if span.is_recording():
        span.add_event(name, attributes)


def record_span_exception(
    exc: Exception,
    attributes: SpanAttributes | None = None,
) -> None:
    """Record an exception on the current span when telemetry is active."""
    span = trace.get_current_span()
    if not span.is_recording():
        return

    span.record_exception(exc)
    span.set_attribute("error.type", type(exc).__name__)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
