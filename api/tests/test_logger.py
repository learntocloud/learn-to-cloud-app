"""Unit tests for core.logger module.

Tests log format detection, log level parsing, and the get_logger factory.
These tests do NOT require OpenTelemetry or Application Insights.
"""

import logging
import os
from unittest.mock import patch

import pytest
import structlog

from core.logger import _get_log_level, _is_json_format, configure_logging, get_logger


@pytest.mark.unit
class TestIsJsonFormat:
    """Test the _is_json_format() logic with its 3 branches."""

    def test_explicit_json(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
            assert _is_json_format() is True

    def test_explicit_console(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "console"}):
            assert _is_json_format() is False

    def test_defaults_to_json_when_telemetry_enabled(self):
        with patch.dict(
            os.environ,
            {
                "LOG_FORMAT": "",
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
            },
        ):
            # Need to reimport to pick up env change for _TELEMETRY_ENABLED
            # Instead, patch the module-level flag directly
            with patch("core.logger._TELEMETRY_ENABLED", True):
                assert _is_json_format() is True

    def test_defaults_to_console_when_no_telemetry(self):
        with patch.dict(
            os.environ,
            {"LOG_FORMAT": ""},
            clear=False,
        ):
            with patch("core.logger._TELEMETRY_ENABLED", False):
                assert _is_json_format() is False

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "JSON"}):
            assert _is_json_format() is True
        with patch.dict(os.environ, {"LOG_FORMAT": "Console"}):
            assert _is_json_format() is False


@pytest.mark.unit
class TestGetLogLevel:
    """Test log level resolution from environment."""

    def test_default_is_info(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            assert _get_log_level() == logging.INFO

    def test_debug(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            assert _get_log_level() == logging.DEBUG

    def test_warning(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            assert _get_log_level() == logging.WARNING

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            assert _get_log_level() == logging.DEBUG

    def test_invalid_falls_back_to_info(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "BOGUS"}):
            assert _get_log_level() == logging.INFO


@pytest.mark.unit
class TestGetLogger:
    """Test the get_logger factory."""

    def test_returns_bound_logger_proxy(self):
        logger = get_logger("test.module")
        # structlog.stdlib.get_logger returns a BoundLoggerLazyProxy
        # which lazily resolves to BoundLogger on first use
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")
        assert hasattr(logger, "exception")

    def test_different_names_return_loggers(self):
        a = get_logger("module.a")
        b = get_logger("module.b")
        assert hasattr(a, "info")
        assert hasattr(b, "info")

    def test_none_name_works(self):
        logger = get_logger(None)
        assert hasattr(logger, "info")


@pytest.mark.unit
class TestConfigureLogging:
    """Test that configure_logging sets up handlers correctly."""

    def test_configures_root_logger(self):
        configure_logging()
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        # Handler should use ProcessorFormatter
        handler = root.handlers[0]
        assert isinstance(handler.formatter, structlog.stdlib.ProcessorFormatter)

    def test_quiets_noisy_loggers(self):
        configure_logging()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
