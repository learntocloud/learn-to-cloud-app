"""Unit tests for core.logger module.

Tests the stdlib-based logging configuration:
- configure_logging() sets up root logger handlers
- JSON formatter produces valid JSON output with extra={} fields
- configure_logging() only replaces the app-owned stdout handler
- Noisy third-party loggers are quieted
"""

import io
import json
import logging
import os
from unittest.mock import patch

import pytest
from pythonjsonlogger.json import JsonFormatter

from learn_to_cloud.core.logger import (
    _APP_HANDLER_NAME,
    _json_formatter,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _clean_root_logger():
    """Save and restore root logger state around each test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_filters = root.filters[:]
    original_level = root.level
    root.handlers = []
    root.filters = []
    yield
    root.handlers = original_handlers
    root.filters = original_filters
    root.setLevel(original_level)


def _app_handlers() -> list[logging.Handler]:
    return [
        handler
        for handler in logging.getLogger().handlers
        if handler.get_name() == _APP_HANDLER_NAME
    ]


@pytest.mark.unit
class TestJSONFormatter:
    """Test production JSON logs are valid and queryable."""

    def test_basic_record_is_valid_json(self):
        formatter = _json_formatter()
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

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.module"
        assert parsed["event"] == "user.login"
        assert "timestamp" in parsed

    def test_exception_included(self):
        formatter = _json_formatter()
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

    def test_non_serializable_extra_uses_library_default(self):
        formatter = _json_formatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="ok",
            args=(),
            exc_info=None,
        )
        record.data = object()

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["data"] == str(record.data)

    @pytest.mark.parametrize(
        "value",
        [
            "linux\nFAKE LOG LINE",
            "hello\r\nworld",
            "step\x00injected",
        ],
        ids=["newline", "carriage-return", "null-byte"],
    )
    def test_json_encoding_escapes_control_chars_in_extras(self, value):
        formatter = _json_formatter()
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
        assert parsed["field"] == value
        assert "\n" not in output
        assert "\r" not in output
        assert "\x00" not in output

    def test_preserves_tabs_in_extras(self):
        formatter = _json_formatter()
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

    def test_preserves_explicit_github_username_extra(self):
        formatter = _json_formatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.github_username = "octocat"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["github_username"] == "octocat"

    def test_preserves_explicit_trace_context_extras(self):
        formatter = _json_formatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        record.span_id = "00f067aa0ba902b7"

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert parsed["span_id"] == "00f067aa0ba902b7"


@pytest.mark.unit
class TestConfigureLogging:
    """Test that configure_logging sets up handlers correctly."""

    def test_adds_single_app_stdout_handler(self):
        configure_logging()

        handlers = _app_handlers()

        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)

    def test_reconfiguring_replaces_app_handler(self):
        configure_logging()
        first_handler = _app_handlers()[0]

        configure_logging()
        handlers = _app_handlers()

        assert len(handlers) == 1
        assert handlers[0] is not first_handler

    def test_json_format_when_app_insights_set(self):
        with patch.dict(
            os.environ,
            {
                "LOG_FORMAT": "",
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
            },
        ):
            configure_logging()
            assert isinstance(_app_handlers()[0].formatter, JsonFormatter)

    def test_preserves_external_handlers(self):
        """Handlers not owned by the app should survive configure_logging()."""
        root = logging.getLogger()
        external_handler = logging.NullHandler()
        root.addHandler(external_handler)

        configure_logging()

        assert external_handler in root.handlers

    def test_child_logger_output_does_not_auto_add_github_username(self):
        with patch.dict(
            os.environ,
            {
                "LOG_FORMAT": "",
                "APPLICATIONINSIGHTS_CONNECTION_STRING": "InstrumentationKey=test",
            },
        ):
            configure_logging()
            stream = io.StringIO()
            _app_handlers()[0].setStream(stream)

            child_logger = logging.getLogger("test.child")
            child_logger.setLevel(logging.NOTSET)
            child_logger.propagate = True
            child_logger.info("child.event")

        parsed = json.loads(stream.getvalue())

        assert "github_username" not in parsed
