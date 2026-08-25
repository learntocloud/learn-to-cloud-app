"""Tests for Functions worker telemetry startup and trace correlation."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import function_app
import pytest
from learn_to_cloud_shared.core.logger import _APP_HANDLER_NAME


@pytest.fixture(autouse=True)
def _restore_root_logger():
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def _app_handlers() -> list[logging.Handler]:
    return [
        handler
        for handler in logging.getLogger().handlers
        if handler.get_name() == _APP_HANDLER_NAME
    ]


def test_worker_telemetry_skips_manual_setup_and_keeps_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY", "true")
    monkeypatch.setenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING",
        "InstrumentationKey=test",
    )

    with (
        patch.object(function_app, "configure_otlp_observability") as configure_otlp,
        patch.object(
            function_app,
            "configure_dependency_instrumentation",
        ) as configure_dependencies,
    ):
        function_app._configure_function_telemetry()

    configure_otlp.assert_not_called()
    configure_dependencies.assert_called_once_with()
    assert len(_app_handlers()) == 1


def test_local_otlp_removes_only_app_stdout_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY",
        raising=False,
    )
    external_handler = logging.NullHandler()
    logging.getLogger().addHandler(external_handler)

    with patch.object(
        function_app,
        "configure_otlp_observability",
        return_value=True,
    ):
        function_app._configure_function_telemetry()

    assert _app_handlers() == []
    assert external_handler in logging.getLogger().handlers


def test_failed_local_setup_keeps_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY",
        raising=False,
    )

    with patch.object(
        function_app,
        "configure_otlp_observability",
        return_value=False,
    ):
        function_app._configure_function_telemetry()

    assert len(_app_handlers()) == 1


def test_invocation_context_attaches_function_trace_context() -> None:
    context = SimpleNamespace(
        trace_context=SimpleNamespace(
            trace_parent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            trace_state="vendor=value",
        )
    )
    extracted_context = object()
    token = object()

    with (
        patch.object(
            function_app, "extract", return_value=extracted_context
        ) as extract,
        patch.object(function_app.otel_context, "attach", return_value=token) as attach,
        patch.object(function_app.otel_context, "detach") as detach,
        function_app._attached_invocation_context(context),
    ):
        pass

    extract.assert_called_once_with(
        {
            "traceparent": context.trace_context.trace_parent,
            "tracestate": context.trace_context.trace_state,
        }
    )
    attach.assert_called_once_with(extracted_context)
    detach.assert_called_once_with(token)
