"""In-process event bus for pending verification results.

Provides a way for the SSE endpoint to wait for a background verification
task to complete.  Each pending submission gets an ``asyncio.Event`` that
the SSE endpoint awaits.  When the background task finishes, it sets the
event and stores the result.

This is intentionally in-process (no Redis, no task queue).  The tradeoff:
if the process restarts mid-verification, the result is lost and the user
resubmits.  For 30-120s LLM calls on a learning platform, this is fine.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from cachetools import TTLCache

from schemas import SubmissionResult

logger = logging.getLogger(__name__)

# Results expire after 10 minutes — more than enough for the SSE client
# to pick them up.  The TTLCache also caps memory usage.
_RESULT_TTL = 600
_MAX_PENDING = 500


@dataclass
class PendingVerification:
    """A verification that is running in the background."""

    event: asyncio.Event = field(default_factory=asyncio.Event)
    result: SubmissionResult | None = None
    error: Exception | None = None


# Keyed by (user_id, requirement_id)
_pending: TTLCache[tuple[int, str], PendingVerification] = TTLCache(
    maxsize=_MAX_PENDING, ttl=_RESULT_TTL
)


def create_pending(user_id: int, requirement_id: str) -> PendingVerification:
    """Register a new pending verification.  Overwrites any existing one."""
    pending = PendingVerification()
    _pending[(user_id, requirement_id)] = pending
    return pending


def get_pending(user_id: int, requirement_id: str) -> PendingVerification | None:
    """Get a pending verification, or None if not found / expired."""
    return _pending.get((user_id, requirement_id))


def complete_pending(
    user_id: int,
    requirement_id: str,
    result: SubmissionResult | None = None,
    error: Exception | None = None,
) -> None:
    """Mark a pending verification as complete and wake the SSE waiter."""
    pending = _pending.get((user_id, requirement_id))
    if pending is None:
        logger.debug(
            "pending.complete.not_found",
            extra={"user_id": user_id, "requirement_id": requirement_id},
        )
        return

    pending.result = result
    pending.error = error
    pending.event.set()


def remove_pending(user_id: int, requirement_id: str) -> None:
    """Remove a pending verification (cleanup after SSE delivery)."""
    _pending.pop((user_id, requirement_id), None)
