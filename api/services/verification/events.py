"""In-process task registry for pending verification results.

Stores ``asyncio.Task`` references so the SSE endpoint can ``await``
them directly.  No hand-rolled pub/sub — just Python's built-in
task result delivery.

This is intentionally in-process (no Redis, no task queue).  The tradeoff:
if the process restarts mid-verification, the result is lost and the user
resubmits.  For 30-120s LLM calls on a learning platform, this is fine.
"""

from __future__ import annotations

import asyncio
import logging

from cachetools import TTLCache

from schemas import SubmissionResult

logger = logging.getLogger(__name__)

# Tasks expire after 10 minutes — more than enough for the SSE client
# to pick up the result.  The TTLCache also caps memory usage.
_RESULT_TTL = 600
_MAX_PENDING = 500

# Keyed by (user_id, requirement_id)
_pending_tasks: TTLCache[tuple[int, str], asyncio.Task[SubmissionResult]] = TTLCache(
    maxsize=_MAX_PENDING, ttl=_RESULT_TTL
)


def store_task(
    user_id: int, requirement_id: str, task: asyncio.Task[SubmissionResult]
) -> None:
    """Store a verification task.  Overwrites any existing one."""
    _pending_tasks[(user_id, requirement_id)] = task


def get_task(
    user_id: int, requirement_id: str
) -> asyncio.Task[SubmissionResult] | None:
    """Get a pending verification task, or None if not found / expired."""
    return _pending_tasks.get((user_id, requirement_id))


def remove_task(user_id: int, requirement_id: str) -> None:
    """Remove a pending task (cleanup after SSE delivery)."""
    _pending_tasks.pop((user_id, requirement_id), None)
