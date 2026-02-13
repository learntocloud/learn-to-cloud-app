"""In-memory TTL caching utilities.

Provides simple TTL-based caching for expensive operations.
Cache entries automatically expire after the configured TTL.

Note: Cache is per-worker/replica, not shared across instances.
Suitable for data that can tolerate short-term staleness (30-60s).

For scenarios that must survive container restarts, use database
persistence.
"""

from typing import TYPE_CHECKING

from cachetools import TTLCache

if TYPE_CHECKING:
    from schemas import BadgeData
    from services.progress_service import UserProgress

# Default cache settings
DEFAULT_TTL_SECONDS = 60
DEFAULT_MAX_SIZE = 1000

# User progress cache: keyed by user_id, stores UserProgress objects
# TTL of 60 seconds means progress may be slightly stale after step completion
# This is acceptable since UI updates optimistically
_progress_cache: TTLCache[int, "UserProgress"] = TTLCache(
    maxsize=DEFAULT_MAX_SIZE,
    ttl=DEFAULT_TTL_SECONDS,
)

# Badge computation cache: keyed by (user_id, phases_hash), stores badge lists
# TTL of 60 seconds to match progress cache
_badge_cache: TTLCache[tuple[int, int], list["BadgeData"]] = TTLCache(
    maxsize=DEFAULT_MAX_SIZE,
    ttl=DEFAULT_TTL_SECONDS,
)

# Phase-detail completed steps cache: keyed by (user_id, phase_id)
# Stores completed step IDs per topic for a specific phase.
# Write-through: updated directly on step complete/uncomplete instead of invalidated.
_phase_detail_cache: TTLCache[tuple[int, int], dict[str, set[str]]] = TTLCache(
    maxsize=DEFAULT_MAX_SIZE,
    ttl=DEFAULT_TTL_SECONDS,
)


def get_cached_progress(user_id: int) -> "UserProgress | None":
    return _progress_cache.get(user_id)


def set_cached_progress(user_id: int, progress: "UserProgress") -> None:
    _progress_cache[user_id] = progress


def get_cached_phase_detail(user_id: int, phase_id: int) -> dict[str, set[str]] | None:
    """Get cached completed step IDs by topic for a phase."""
    return _phase_detail_cache.get((user_id, phase_id))


def set_cached_phase_detail(
    user_id: int, phase_id: int, completed_by_topic: dict[str, set[str]]
) -> None:
    """Set cached completed step IDs by topic for a phase."""
    _phase_detail_cache[(user_id, phase_id)] = completed_by_topic


def update_cached_phase_detail_step(
    user_id: int, phase_id: int, topic_id: str, completed_steps: set[str]
) -> None:
    """Write-through update: update a single topic's completed step IDs.

    If the cache entry exists, updates it in place. If not, does nothing
    (the next read will populate it from DB).
    """
    key = (user_id, phase_id)
    cached = _phase_detail_cache.get(key)
    if cached is not None:
        cached[topic_id] = completed_steps


def invalidate_progress_cache(user_id: int) -> None:
    """Invalidate cached progress for a user.

    Call this after operations that modify user progress
    (step completion, submissions).
    """
    _progress_cache.pop(user_id, None)
    # Invalidate phase-detail cache entries for this user
    phase_detail_keys = [k for k in _phase_detail_cache.keys() if k[0] == user_id]
    for key in phase_detail_keys:
        _phase_detail_cache.pop(key, None)
    # Also invalidate any badge cache entries for this user
    # Badge cache keys are (user_id, hash), so we need to scan
    keys_to_remove = [k for k in _badge_cache.keys() if k[0] == user_id]
    for key in keys_to_remove:
        _badge_cache.pop(key, None)


def get_cached_badges(user_id: int, progress_hash: int) -> "list[BadgeData] | None":
    """progress_hash ensures cache invalidation when completion data changes."""
    return _badge_cache.get((user_id, progress_hash))


def set_cached_badges(
    user_id: int, progress_hash: int, badges: "list[BadgeData]"
) -> None:
    _badge_cache[(user_id, progress_hash)] = badges
