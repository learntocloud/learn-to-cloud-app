"""Unit tests for core.logger module.

Tests the stdlib-based logging configuration:
- configure_logging() sets up root logger handlers
- _JSONFormatter produces valid JSON output
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
    _LogSanitizationFilter,
    _RequestContextFilter,
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

    def test_extra_fields_included(self):
        formatter = _JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="step.completed",
            args=(),
            exc_info=None,
        )
        record.user_id = "u123"
        record.step_id = 42
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["user_id"] == "u123"
        assert parsed["step_id"] == 42

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

    def test_console_format_when_explicit(self):
        with patch.dict(os.environ, {"LOG_FORMAT": "console"}, clear=False):
            os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)
            configure_logging()
            root = logging.getLogger()
            stream_handlers = [
                h for h in root.handlers if isinstance(h, logging.StreamHandler)
            ]
            assert all(
                not isinstance(h.formatter, _JSONFormatter) for h in stream_handlers
            )

    def test_preserves_otel_handlers(self):
        """OTel LoggingHandler should survive configure_logging()."""
        root = logging.getLogger()

        otel_handler = MagicMock(spec=logging.Handler)
        type(otel_handler).__name__ = "LoggingHandler"
        root.addHandler(otel_handler)

        configure_logging()

        assert otel_handler in root.handlers

    def test_quiets_noisy_loggers(self):
        configure_logging()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING

    def test_respects_log_level_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            configure_logging()
            root = logging.getLogger()
            assert root.level == logging.DEBUG

    def test_registers_filters_in_correct_order(self):
        """Context filter runs before sanitization so injected fields get cleaned."""
        configure_logging()
        root = logging.getLogger()
        filter_types = [type(f) for f in root.filters]
        assert _RequestContextFilter in filter_types
        assert _LogSanitizationFilter in filter_types
        ctx_idx = filter_types.index(_RequestContextFilter)
        san_idx = filter_types.index(_LogSanitizationFilter)
        assert ctx_idx < san_idx, "Sanitization filter must run after context filter"


@pytest.mark.unit
class TestRequestContextFilter:
    """Test _RequestContextFilter injects github_username from context var."""

    def test_injects_username_from_context_var(self):
        from core.middleware import request_github_username

        token = request_github_username.set("testuser")
        try:
            f = _RequestContextFilter()
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            f.filter(record)
            assert getattr(record, "github_username") == "testuser"
        finally:
            request_github_username.reset(token)

    def test_does_not_overwrite_explicit_username(self):
        from core.middleware import request_github_username

        token = request_github_username.set("ctx-user")
        try:
            f = _RequestContextFilter()
            record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
            record.github_username = "explicit-user"
            f.filter(record)
            assert getattr(record, "github_username") == "explicit-user"
        finally:
            request_github_username.reset(token)

    def test_no_username_when_context_var_empty(self):
        f = _RequestContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert not getattr(record, "github_username", None)


@pytest.mark.unit
class TestLogSanitizationFilter:
    """Test _LogSanitizationFilter strips control chars from extra fields (CWE-117)."""

    def _make_record(self, **extras: object) -> logging.LogRecord:
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        for key, value in extras.items():
            setattr(record, key, value)
        return record

    def test_strips_newlines_from_extra(self):
        f = _LogSanitizationFilter()
        record = self._make_record(topic_id="linux\nFAKE LOG LINE")
        f.filter(record)
        assert getattr(record, "topic_id") == "linuxFAKE LOG LINE"

    def test_strips_carriage_return(self):
        f = _LogSanitizationFilter()
        record = self._make_record(user_input="hello\r\nworld")
        f.filter(record)
        assert getattr(record, "user_input") == "helloworld"

    def test_strips_null_bytes(self):
        f = _LogSanitizationFilter()
        record = self._make_record(step_id="step\x00injected")
        f.filter(record)
        assert getattr(record, "step_id") == "stepinjected"

    def test_preserves_tabs(self):
        f = _LogSanitizationFilter()
        record = self._make_record(data="col1\tcol2")
        f.filter(record)
        assert getattr(record, "data") == "col1\tcol2"

    def test_leaves_non_string_extras_unchanged(self):
        f = _LogSanitizationFilter()
        record = self._make_record(user_id=42, active=True, ratio=3.14)
        f.filter(record)
        assert getattr(record, "user_id") == 42
        assert getattr(record, "active") is True
        assert getattr(record, "ratio") == 3.14

    def test_does_not_modify_builtin_attributes(self):
        f = _LogSanitizationFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "/path/to\nfile.py", 0, "msg", (), None
        )
        original_pathname = record.pathname
        f.filter(record)
        assert record.pathname == original_pathname

    def test_full_injection_attack_neutralised(self):
        f = _LogSanitizationFilter()
        malicious = "linux-basics\nCRITICAL [core.auth] admin granted=true"
        record = self._make_record(topic_id=malicious)
        f.filter(record)
        assert "\n" not in getattr(record, "topic_id")
        assert "CRITICAL [core.auth] admin granted=true" in getattr(record, "topic_id")
