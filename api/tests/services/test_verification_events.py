"""Unit tests for the verification task registry.

Tests cover:
- Storing and retrieving tasks
- Awaiting task results
- Cleanup via remove_task
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from learn_to_cloud.services.verification.events import (
    get_task,
    remove_task,
    store_task,
)


@pytest.mark.unit
class TestVerificationEvents:
    """Tests for the in-process task registry."""

    def test_store_and_get_task(self):
        """Storing a task makes it retrievable."""
        mock_task = MagicMock(spec=asyncio.Task)
        store_task(user_id=1, requirement_id="req-1", task=mock_task)

        retrieved = get_task(user_id=1, requirement_id="req-1")
        assert retrieved is mock_task

        # Cleanup
        remove_task(1, "req-1")

    def test_get_task_returns_none_for_unknown(self):
        """Unknown user+requirement returns None."""
        assert get_task(user_id=999, requirement_id="nonexistent") is None

    def test_remove_task(self):
        """Removing a task clears it."""
        mock_task = MagicMock(spec=asyncio.Task)
        store_task(user_id=4, requirement_id="req-4", task=mock_task)
        remove_task(user_id=4, requirement_id="req-4")
        assert get_task(user_id=4, requirement_id="req-4") is None

    def test_remove_task_for_unknown_is_noop(self):
        """Removing a non-existent task is a no-op."""
        remove_task(user_id=999, requirement_id="ghost")

    @pytest.mark.asyncio
    async def test_awaiting_task_gets_result(self):
        """Awaiting a stored task returns its result."""
        mock_result = MagicMock()

        async def do_work():
            await asyncio.sleep(0.05)
            return mock_result

        task = asyncio.create_task(do_work())
        store_task(user_id=5, requirement_id="req-5", task=task)

        result = await task
        assert result is mock_result
        remove_task(5, "req-5")

    def test_store_overwrites_existing(self):
        """Storing a new task for the same key overwrites the old one."""
        old = MagicMock(spec=asyncio.Task)
        new = MagicMock(spec=asyncio.Task)
        store_task(user_id=6, requirement_id="req-6", task=old)
        store_task(user_id=6, requirement_id="req-6", task=new)

        assert get_task(6, "req-6") is new
        assert get_task(6, "req-6") is not old

        remove_task(6, "req-6")
