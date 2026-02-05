"""Unit tests for core.telemetry module.

Tests decorator pass-through when telemetry is disabled, log_business_event
behavior, and add_custom_attribute no-op behavior.
"""

from unittest.mock import patch

import pytest

from core.telemetry import (
    add_custom_attribute,
    log_business_event,
    track_dependency,
    track_operation,
)


@pytest.mark.unit
class TestTrackDependencyDisabled:
    """track_dependency should be a transparent pass-through when telemetry is off."""

    def test_sync_passthrough(self):
        @track_dependency("test_dep", "HTTP")
        def my_func(x: int) -> int:
            return x * 2

        assert my_func(5) == 10

    def test_sync_exception_propagates(self):
        @track_dependency("test_dep", "HTTP")
        def my_func():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            my_func()

    async def test_async_passthrough(self):
        @track_dependency("test_dep", "HTTP")
        async def my_func(x: int) -> int:
            return x * 2

        result = await my_func(5)
        assert result == 10

    async def test_async_exception_propagates(self):
        @track_dependency("test_dep", "HTTP")
        async def my_func():
            raise ValueError("async boom")

        with pytest.raises(ValueError, match="async boom"):
            await my_func()


@pytest.mark.unit
class TestTrackOperationDisabled:
    """track_operation should be a transparent pass-through when telemetry is off."""

    def test_sync_passthrough(self):
        @track_operation("test_op")
        def my_func(x: int, y: int) -> int:
            return x + y

        assert my_func(3, 4) == 7

    def test_sync_exception_propagates(self):
        @track_operation("test_op")
        def my_func():
            raise RuntimeError("op failed")

        with pytest.raises(RuntimeError, match="op failed"):
            my_func()

    async def test_async_passthrough(self):
        @track_operation("test_op")
        async def my_func(x: int, y: int) -> int:
            return x + y

        result = await my_func(3, 4)
        assert result == 7

    async def test_async_exception_propagates(self):
        @track_operation("test_op")
        async def my_func():
            raise RuntimeError("async op failed")

        with pytest.raises(RuntimeError, match="async op failed"):
            await my_func()


@pytest.mark.unit
class TestAddCustomAttribute:
    """add_custom_attribute should be a no-op when telemetry is disabled."""

    def test_no_op_when_disabled(self):
        # Should not raise even though there's no OTel span
        add_custom_attribute("test.key", "test_value")
        add_custom_attribute("test.int", 42)
        add_custom_attribute("test.bool", True)


@pytest.mark.unit
class TestLogBusinessEvent:
    """log_business_event should be a no-op when telemetry is disabled."""

    def test_no_op_when_disabled(self):
        # TELEMETRY_ENABLED is False in tests, so this should silently no-op
        log_business_event("test.event", 1, {"key": "value"})

    def test_logs_when_enabled(self):
        with (
            patch("core.telemetry.TELEMETRY_ENABLED", True),
            patch("core.telemetry.logger") as mock_logger,
        ):
            log_business_event("steps.completed", 1, {"phase": "phase1"})
            mock_logger.info.assert_called_once_with(
                "business.event",
                event_name="steps.completed",
                value=1,
                phase="phase1",
            )

    def test_logs_without_properties(self):
        with (
            patch("core.telemetry.TELEMETRY_ENABLED", True),
            patch("core.telemetry.logger") as mock_logger,
        ):
            log_business_event("users.registered", 1)
            mock_logger.info.assert_called_once_with(
                "business.event",
                event_name="users.registered",
                value=1,
            )


@pytest.mark.unit
class TestDecoratorPreservesFunctionMetadata:
    """Decorators should preserve __name__ and __doc__ via functools.wraps."""

    def test_track_dependency_preserves_name(self):
        @track_dependency("dep")
        def my_named_function():
            """My docstring."""

        assert my_named_function.__name__ == "my_named_function"
        assert my_named_function.__doc__ == "My docstring."

    def test_track_operation_preserves_name(self):
        @track_operation("op")
        async def my_async_function():
            """Async docstring."""

        assert my_async_function.__name__ == "my_async_function"
        assert my_async_function.__doc__ == "Async docstring."
