"""Unit tests for core.cache module.

Tests in-memory TTL caching utilities:
- Progress cache: get/set/invalidate
- Phase detail cache: get/set/update
- Invalidation clears all related caches for a user
"""

import pytest

from core.cache import (
    _phase_detail_cache,
    _progress_cache,
    get_cached_phase_detail,
    get_cached_progress,
    invalidate_progress_cache,
    set_cached_phase_detail,
    set_cached_progress,
    update_cached_phase_detail_step,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear all caches before and after each test."""
    _progress_cache.clear()
    _phase_detail_cache.clear()
    yield
    _progress_cache.clear()
    _phase_detail_cache.clear()


@pytest.mark.unit
class TestProgressCache:
    """Test progress cache get/set."""

    def test_set_and_get(self):
        progress = {"phases": [1, 2, 3]}
        set_cached_progress(1, progress)
        assert get_cached_progress(1) == progress

    def test_get_returns_none_when_not_cached(self):
        assert get_cached_progress(999) is None

    def test_overwrites_existing(self):
        set_cached_progress(1, {"old": True})
        set_cached_progress(1, {"new": True})
        assert get_cached_progress(1) == {"new": True}


@pytest.mark.unit
class TestPhaseDetailCache:
    """Test phase detail cache get/set/update."""

    def test_set_and_get(self):
        completed = {"topic-1": {"step-a", "step-b"}}
        set_cached_phase_detail(1, 10, completed)
        assert get_cached_phase_detail(1, 10) == completed

    def test_get_returns_none_when_not_cached(self):
        assert get_cached_phase_detail(1, 99) is None

    def test_different_user_phase_combos_are_independent(self):
        set_cached_phase_detail(1, 10, {"topic-1": {"a"}})
        set_cached_phase_detail(2, 10, {"topic-1": {"b"}})
        assert get_cached_phase_detail(1, 10) == {"topic-1": {"a"}}
        assert get_cached_phase_detail(2, 10) == {"topic-1": {"b"}}


@pytest.mark.unit
class TestUpdateCachedPhaseDetailStep:
    """Test write-through update of phase detail cache."""

    def test_updates_existing_cache_entry(self):
        set_cached_phase_detail(1, 10, {"topic-1": {"step-a"}})
        update_cached_phase_detail_step(1, 10, "topic-1", {"step-a", "step-b"})
        cached = get_cached_phase_detail(1, 10)
        assert cached is not None
        assert cached["topic-1"] == {"step-a", "step-b"}

    def test_adds_new_topic_to_existing_cache(self):
        set_cached_phase_detail(1, 10, {"topic-1": {"step-a"}})
        update_cached_phase_detail_step(1, 10, "topic-2", {"step-x"})
        cached = get_cached_phase_detail(1, 10)
        assert cached is not None
        assert cached["topic-2"] == {"step-x"}

    def test_noop_when_not_cached(self):
        # Should not raise or create a cache entry
        update_cached_phase_detail_step(1, 10, "topic-1", {"step-a"})
        assert get_cached_phase_detail(1, 10) is None


@pytest.mark.unit
class TestInvalidateProgressCache:
    """Test invalidation clears progress and phase_detail caches."""

    def test_clears_progress_cache(self):
        set_cached_progress(1, {"data": True})
        invalidate_progress_cache(1)
        assert get_cached_progress(1) is None

    def test_clears_phase_detail_caches_for_user(self):
        set_cached_phase_detail(1, 10, {"t": {"s"}})
        set_cached_phase_detail(1, 20, {"t": {"s"}})
        invalidate_progress_cache(1)
        assert get_cached_phase_detail(1, 10) is None
        assert get_cached_phase_detail(1, 20) is None

    def test_does_not_affect_other_users(self):
        set_cached_progress(1, {"user1": True})
        set_cached_progress(2, {"user2": True})
        set_cached_phase_detail(1, 10, {"t": {"s"}})
        set_cached_phase_detail(2, 10, {"t": {"s"}})

        invalidate_progress_cache(1)

        assert get_cached_progress(1) is None
        assert get_cached_progress(2) == {"user2": True}
        assert get_cached_phase_detail(2, 10) == {"t": {"s"}}

    def test_noop_when_nothing_cached(self):
        # Should not raise
        invalidate_progress_cache(999)
