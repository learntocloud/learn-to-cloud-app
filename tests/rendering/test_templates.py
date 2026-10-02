"""Unit tests for template context processors."""

from unittest.mock import MagicMock

import pytest

from learn_to_cloud.rendering.templates import _frontend_telemetry_context
from tests.support.settings import clear_settings_cache


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.mark.unit
def test_frontend_telemetry_context(monkeypatch):
    monkeypatch.delenv(
        "FRONTEND_TELEMETRY__APPLICATIONINSIGHTS_CONNECTION_STRING",
        raising=False,
    )

    context = _frontend_telemetry_context(MagicMock(scope={}))

    assert context == {"frontend_telemetry": None}

    conn_str = "InstrumentationKey=abc;IngestionEndpoint=https://example.invalid/"
    monkeypatch.setenv(
        "FRONTEND_TELEMETRY__APPLICATIONINSIGHTS_CONNECTION_STRING",
        conn_str,
    )
    clear_settings_cache()

    context = _frontend_telemetry_context(MagicMock())

    assert context == {
        "frontend_telemetry": {
            "connection_string": conn_str,
            "sampling_percentage": 100.0,
        }
    }

    monkeypatch.setenv("FRONTEND_TELEMETRY__SAMPLING_PERCENTAGE", "10")
    clear_settings_cache()

    context = _frontend_telemetry_context(MagicMock(scope={}))

    assert context == {
        "frontend_telemetry": {
            "connection_string": conn_str,
            "sampling_percentage": 10.0,
        }
    }
