"""Unit tests for observability instrumentation helpers."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import observability


@pytest.fixture(autouse=True)
def _restore_telemetry_flag():
    """Restore module telemetry state after each test."""
    original = observability._telemetry_enabled
    yield
    observability._telemetry_enabled = original


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
