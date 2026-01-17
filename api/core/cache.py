"""In-memory TTL caching utilities.

Provides simple TTL-based caching for expensive operations.
Cache entries automatically expire after the configured TTL.

SCALABILITY NOTES:
- Cache is per-worker/replica, not shared across instances
- Suitable for data that can tolerate short-term staleness (30-60s)
- Do not use for data requiring strong consistency
"""

from dataclasses import dataclass
from typing import Any, TypeVar

from cachetools import TTLCache

# Default cache settings
DEFAULT_TTL_SECONDS = 60
DEFAULT_MAX_SIZE = 1000

T = TypeVar("T")


@dataclass
class CacheConfig:
    """Configuration for a cache instance."""

    maxsize: int = DEFAULT_MAX_SIZE
    ttl: int = DEFAULT_TTL_SECONDS


# User progress cache: keyed by user_id, stores UserProgress objects
# TTL of 60 seconds means progress may be slightly stale after step completion
# This is acceptable since UI updates optimistically
_progress_cache: TTLCache[str, Any] = TTLCache(
    maxsize=DEFAULT_MAX_SIZE,
    ttl=DEFAULT_TTL_SECONDS,
)

# Badge computation cache: keyed by (user_id, phases_hash), stores badge lists
# TTL of 60 seconds to match progress cache
_badge_cache: TTLCache[tuple[str, int], Any] = TTLCache(
    maxsize=DEFAULT_MAX_SIZE,
    ttl=DEFAULT_TTL_SECONDS,
)


def get_cached_progress(user_id: str) -> Any | None:
    """Get cached user progress if available.

    Returns:
        Cached UserProgress object or None if not cached/expired.
    """
    return _progress_cache.get(user_id)


def set_cached_progress(user_id: str, progress: Any) -> None:
    """Cache user progress.

    Args:
        user_id: User identifier
        progress: UserProgress object to cache
    """
    _progress_cache[user_id] = progress


def invalidate_progress_cache(user_id: str) -> None:
    """Invalidate cached progress for a user.

    Call this after operations that modify user progress
    (step completion, question answers, submissions).
    """
    _progress_cache.pop(user_id, None)
    # Also invalidate any badge cache entries for this user
    # Badge cache keys are (user_id, hash), so we need to scan
    keys_to_remove = [k for k in _badge_cache.keys() if k[0] == user_id]
    for key in keys_to_remove:
        _badge_cache.pop(key, None)


def get_cached_badges(user_id: str, progress_hash: int) -> Any | None:
    """Get cached badges if available.

    Args:
        user_id: User identifier
        progress_hash: Hash of phase completion data (for cache invalidation)

    Returns:
        Cached badge list or None if not cached/expired.
    """
    return _badge_cache.get((user_id, progress_hash))


def set_cached_badges(user_id: str, progress_hash: int, badges: Any) -> None:
    """Cache computed badges.

    Args:
        user_id: User identifier
        progress_hash: Hash of phase completion data
        badges: List of Badge objects
    """
    _badge_cache[(user_id, progress_hash)] = badges


def clear_all_caches() -> None:
    """Clear all caches. Useful for testing."""
    _progress_cache.clear()
    _badge_cache.clear()


# Simple stats for monitoring
def get_cache_stats() -> dict[str, dict[str, int]]:
    """Get cache statistics for monitoring.

    Returns:
        Dict with cache names and their current size/max size.
    """
    return {
        "progress_cache": {
            "current_size": len(_progress_cache),
            "max_size": _progress_cache.maxsize,
        },
        "badge_cache": {
            "current_size": len(_badge_cache),
            "max_size": _badge_cache.maxsize,
        },
    }
