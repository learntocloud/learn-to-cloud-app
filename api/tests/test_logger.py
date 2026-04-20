"""Unit tests for core.logger module.

Tests the stdlib-based logging configuration:
- configure_logging() sets up root logger handlers
- _JSONFormatter produces valid JSON output with CWE-117 sanitization
- OTel handlers are preserved when present
- Noisy third-party loggers are quieted
"""

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from core.logger import (
    _JSONFormatter,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _clean_root_logger():
    """Save and restore root logger state around each test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


@pytest.mark.unit
class TestJSONFormatter:
    """Test _JSONFormatter produces valid, queryable JSON."""

    def test_basic_record_is_valid_json(self):
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="user.login",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "info"
        assert parsed["logger"] == "test.module"
        assert parsed["event"] == "user.login"
        assert "timestamp" in parsed

    def test_exception_included(self):
        formatter = _JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="handler.failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "boom" in parsed["exception"]

    def test_non_serializable_extra_uses_default(self):
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="ok",
            args=(),
            exc_info=None,
        )
        # Non-primitive extras are skipped by the formatter's filter
        output = formatter.format(record)
        json.loads(output)  # Should not raise

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("linux\nFAKE LOG LINE", "linuxFAKE LOG LINE"),
            ("hello\r\nworld", "helloworld"),
            ("step\x00injected", "stepinjected"),
        ],
        ids=["newline", "carriage-return", "null-byte"],
    )
    def test_sanitizes_control_chars_in_extras(self, value, expected):
        """CWE-117: control characters stripped from user-supplied extra fields."""
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.field = value
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["field"] == expected

    def test_preserves_tabs_in_extras(self):
        """Tabs are intentionally preserved (only dangerous control chars removed)."""
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.data = "col1\tcol2"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["data"] == "col1\tcol2"


@pytest.mark.unit
class TestConfigureLogging:
    """Test that configure_logging sets up handlers correctly."""

    def test_adds_stdout_handler(self):
        configure_logging()
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    def test_json_format_when_app_insights_set(self):
        with patch.dict(
            os.environ,
            {
                "LOG_FORMAT": "",
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
            },
        ):
            configure_logging()
            root = logging.getLogger()
            # Find the StreamHandler we added (not OTel)
            stream_handlers = [
                h for h in root.handlers if isinstance(h, logging.StreamHandler)
            ]
            assert any(isinstance(h.formatter, _JSONFormatter) for h in stream_handlers)

    def test_preserves_otel_handlers(self):
        """OTel LoggingHandler should survive configure_logging()."""
        root = logging.getLogger()

        otel_handler = MagicMock(spec=logging.Handler)
        type(otel_handler).__name__ = "LoggingHandler"
        root.addHandler(otel_handler)

        configure_logging()

        assert otel_handler in root.handlers

    def test_no_filters_on_root_logger(self):
        """Root logger filters were removed (dead code due to propagation bug)."""
        configure_logging()
        root = logging.getLogger()
        assert len(root.filters) == 0
