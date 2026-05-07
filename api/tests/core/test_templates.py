"""Unit tests for template context processors."""

from unittest.mock import MagicMock

import pytest
from learn_to_cloud_shared.core.config import clear_settings_cache

from learn_to_cloud.core.templates import _frontend_telemetry_context


@pytest.fixture(autouse=True)
def _clear_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.mark.unit
def test_frontend_telemetry_context_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FRONTEND_APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)

    context = _frontend_telemetry_context(MagicMock())

    assert context == {"frontend_telemetry": None}


@pytest.mark.unit
def test_frontend_telemetry_context_includes_connection_string(monkeypatch):
    conn_str = "InstrumentationKey=abc;IngestionEndpoint=https://example.invalid/"
    monkeypatch.setenv("FRONTEND_APPLICATIONINSIGHTS_CONNECTION_STRING", conn_str)

    context = _frontend_telemetry_context(MagicMock())

    assert context == {
        "frontend_telemetry": {
            "connection_string": conn_str,
        }
    }
