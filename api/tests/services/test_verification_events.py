"""Unit tests for the verification event bus.

Tests cover:
- Creating and retrieving pending verifications
- Completing with result or error
- Event signaling for SSE waiters
- Cleanup via remove_pending
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from services.verification_events import (
    PendingVerification,
    complete_pending,
    create_pending,
    get_pending,
    remove_pending,
)


@pytest.mark.unit
class TestVerificationEvents:
    """Tests for the in-process event bus."""

    def test_create_and_get_pending(self):
        """Creating a pending verification makes it retrievable."""
        pending = create_pending(user_id=1, requirement_id="req-1")
        assert isinstance(pending, PendingVerification)
        assert not pending.event.is_set()
        assert pending.result is None
        assert pending.error is None

        retrieved = get_pending(user_id=1, requirement_id="req-1")
        assert retrieved is pending

        # Cleanup
        remove_pending(1, "req-1")

    def test_get_pending_returns_none_for_unknown(self):
        """Unknown user+requirement returns None."""
        assert get_pending(user_id=999, requirement_id="nonexistent") is None

    def test_complete_pending_with_result(self):
        """Completing with a result sets the event and stores the result."""
        pending = create_pending(user_id=2, requirement_id="req-2")
        mock_result = MagicMock()

        complete_pending(user_id=2, requirement_id="req-2", result=mock_result)

        assert pending.event.is_set()
        assert pending.result is mock_result
        assert pending.error is None

        remove_pending(2, "req-2")

    def test_complete_pending_with_error(self):
        """Completing with an error sets the event and stores the error."""
        pending = create_pending(user_id=3, requirement_id="req-3")
        error = RuntimeError("LLM exploded")

        complete_pending(user_id=3, requirement_id="req-3", error=error)

        assert pending.event.is_set()
        assert pending.result is None
        assert pending.error is error

        remove_pending(3, "req-3")

    def test_complete_pending_for_unknown_is_noop(self):
        """Completing a non-existent pending is a no-op (no crash)."""
        complete_pending(user_id=999, requirement_id="ghost", result=MagicMock())

    def test_remove_pending(self):
        """Removing a pending verification clears it."""
        create_pending(user_id=4, requirement_id="req-4")
        remove_pending(user_id=4, requirement_id="req-4")
        assert get_pending(user_id=4, requirement_id="req-4") is None

    def test_remove_pending_for_unknown_is_noop(self):
        """Removing a non-existent pending is a no-op."""
        remove_pending(user_id=999, requirement_id="ghost")

    @pytest.mark.asyncio
    async def test_event_wakes_waiter(self):
        """An asyncio waiter on the event is woken when completed."""
        pending = create_pending(user_id=5, requirement_id="req-5")
        mock_result = MagicMock()

        async def waiter():
            await asyncio.wait_for(pending.event.wait(), timeout=2)
            return pending.result

        # Complete after a short delay
        async def completer():
            await asyncio.sleep(0.05)
            complete_pending(user_id=5, requirement_id="req-5", result=mock_result)

        waiter_task = asyncio.create_task(waiter())
        completer_task = asyncio.create_task(completer())

        result = await waiter_task
        await completer_task

        assert result is mock_result
        remove_pending(5, "req-5")

    def test_create_overwrites_existing(self):
        """Creating a new pending for the same key overwrites the old one."""
        old = create_pending(user_id=6, requirement_id="req-6")
        new = create_pending(user_id=6, requirement_id="req-6")

        assert get_pending(6, "req-6") is new
        assert new is not old

        remove_pending(6, "req-6")
