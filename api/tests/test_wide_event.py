"""Unit tests for core.wide_event module.

Tests the ContextVar-based wide event lifecycle: init, set, get, clear,
and safe no-op behavior outside request context.

NOTE: In production, RequestTimingMiddleware calls init_wide_event() and
immediately populates the dict with request context fields (making it truthy).
set_wide_event_fields() intentionally no-ops on an empty dict (falsy) to
safely ignore calls outside request context.
"""

import pytest

from core.wide_event import (
    clear_wide_event,
    get_wide_event,
    init_wide_event,
    set_wide_event_fields,
)


def _init_with_request_context() -> dict:
    """Mimic what RequestTimingMiddleware does: init + populate base fields."""
    event = init_wide_event()
    event["service_name"] = "test-api"
    event["request_id"] = "test-req-1"
    return event


@pytest.mark.unit
class TestWideEventLifecycle:
    """Test the full init → set → get → clear lifecycle."""

    def test_init_returns_empty_dict(self):
        event = init_wide_event()
        assert event == {}

    def test_set_and_get_fields(self):
        _init_with_request_context()
        set_wide_event_fields(user_id="u1", step_id="s1")
        event = get_wide_event()
        assert event["user_id"] == "u1"
        assert event["step_id"] == "s1"

    def test_set_fields_accumulates(self):
        _init_with_request_context()
        set_wide_event_fields(a=1)
        set_wide_event_fields(b=2)
        event = get_wide_event()
        assert event["a"] == 1
        assert event["b"] == 2

    def test_set_fields_overwrites_existing_key(self):
        _init_with_request_context()
        set_wide_event_fields(key="old")
        set_wide_event_fields(key="new")
        assert get_wide_event()["key"] == "new"

    def test_clear_resets_to_empty(self):
        _init_with_request_context()
        set_wide_event_fields(user_id="u1")
        clear_wide_event()
        assert get_wide_event() == {}

    def test_get_returns_empty_dict_when_not_initialized(self):
        """Simulates calling get_wide_event outside request context."""
        clear_wide_event()
        # After clear, get should return empty dict (not raise)
        event = get_wide_event()
        assert event == {}

    def test_direct_dict_mutation_reflected_in_get(self):
        """Middleware writes directly to the dict returned by init_wide_event.
        Verify this is the same object returned by get_wide_event."""
        event = init_wide_event()
        event["http_method"] = "POST"
        assert get_wide_event()["http_method"] == "POST"


@pytest.mark.unit
class TestWideEventNoOp:
    """Test that set_wide_event_fields is a safe no-op outside request context."""

    def test_set_fields_noop_on_empty_context(self):
        """set_wide_event_fields should silently no-op when wide event
        is an empty dict (after clear). Empty dict is falsy by design."""
        clear_wide_event()
        # Should not raise
        set_wide_event_fields(should_not="crash")
        # Event is still empty (no-op because empty dict is falsy)
        assert get_wide_event() == {}

    def test_set_fields_noop_on_bare_init(self):
        """A bare init_wide_event() without middleware populating fields
        results in an empty dict. set_wide_event_fields is a no-op.
        This is the expected behavior for tests and CLI scripts."""
        init_wide_event()
        set_wide_event_fields(should_not="appear")
        assert get_wide_event() == {}

    def test_init_then_set_works_after_clear(self):
        """Ensure re-init after clear works (mimics next request)."""
        _init_with_request_context()
        set_wide_event_fields(req=1)
        clear_wide_event()

        # New request
        _init_with_request_context()
        set_wide_event_fields(req=2)
        assert get_wide_event()["req"] == 2
