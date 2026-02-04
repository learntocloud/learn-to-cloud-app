"""Tests for badges_service.

Tests badge computation logic - these are pure functions
that don't require database access.

Note: Phase requirements are loaded from content JSON files.
"""

import pytest

from services.badges_service import (
    compute_all_badges,
    compute_phase_badges,
    get_badge_catalog,
)
from services.progress_service import get_phase_requirements

# Mark all tests in this module as unit tests (no database required)
pytestmark = pytest.mark.unit


class TestComputePhaseBadges:
    """Tests for compute_phase_badges()."""

    def _get_phase_badge(self, phase_id: int):
        phase_badges, _, _ = get_badge_catalog()
        return next(
            (badge for badge in phase_badges if badge.phase_id == phase_id),
            None,
        )

    def test_returns_empty_for_no_progress(self):
        """Should return no badges when no phases completed."""
        result = compute_phase_badges({})

        assert result == []

    def test_returns_badge_for_completed_phase(self):
        """Should return badge when all requirements met for a phase."""
        requirements = get_phase_requirements(0)
        badge_info = self._get_phase_badge(0)
        if not requirements or not badge_info:
            pytest.skip("Phase 0 requirements or badge not available in content")

        phase_completion = {
            0: (requirements.steps, True),
        }

        result = compute_phase_badges(phase_completion)

        assert len(result) == 1
        assert result[0].id == badge_info.id
        assert result[0].name == badge_info.name
        assert result[0].icon == badge_info.icon

    def test_no_badge_when_steps_incomplete(self):
        """Should not award badge when steps not completed."""
        requirements = get_phase_requirements(0)
        if not requirements or requirements.steps == 0:
            pytest.skip("Phase 0 requirements not available or zero steps")
        phase_completion = {
            0: (requirements.steps - 1, True),
        }

        result = compute_phase_badges(phase_completion)

        assert result == []

    def test_no_badge_when_hands_on_not_validated(self):
        """Should not award badge when hands-on not validated."""
        requirements = get_phase_requirements(0)
        if not requirements:
            pytest.skip("Phase 0 requirements not available")
        phase_completion = {
            0: (requirements.steps, False),
        }

        result = compute_phase_badges(phase_completion)

        assert result == []

    def test_multiple_phase_badges(self):
        """Should return multiple badges for multiple completed phases."""
        phase_badges, _, _ = get_badge_catalog()
        if len(phase_badges) < 2:
            pytest.skip("Not enough phase badges in content")

        phase_ids = [phase_badges[0].phase_id, phase_badges[1].phase_id]
        if any(phase_id is None for phase_id in phase_ids):
            pytest.skip("Phase badge missing phase_id")

        requirements = [get_phase_requirements(phase_id) for phase_id in phase_ids]
        if any(req is None for req in requirements):
            pytest.skip("Phase requirements missing for badge phases")

        phase_completion = {
            phase_ids[0]: (requirements[0].steps, True),
            phase_ids[1]: (requirements[1].steps, True),
        }

        result = compute_phase_badges(phase_completion)

        badge_ids = {b.id for b in result}
        assert phase_badges[0].id in badge_ids
        assert phase_badges[1].id in badge_ids

    def test_awards_badge_when_exceeds_requirements(self):
        """Should award badge when user exceeds requirements."""
        requirements = get_phase_requirements(0)
        if not requirements:
            pytest.skip("Phase 0 requirements not available")
        phase_completion = {
            0: (requirements.steps + 5, True),
        }

        result = compute_phase_badges(phase_completion)

        assert len(result) == 1
        assert result[0].id.startswith("phase_")


class TestComputeAllBadges:
    """Tests for compute_all_badges()."""

    def _get_phase_badge(self, phase_id: int):
        phase_badges, _, _ = get_badge_catalog()
        return next(
            (badge for badge in phase_badges if badge.phase_id == phase_id),
            None,
        )

    def test_returns_empty_for_no_progress(self):
        """Should return no badges when no progress."""
        result = compute_all_badges({})

        assert result == []

    def test_returns_phase_badges(self):
        """Should return phase badges for completed phases."""
        requirements = get_phase_requirements(0)
        badge_info = self._get_phase_badge(0)
        if not requirements or not badge_info:
            pytest.skip("Phase 0 requirements or badge not available in content")

        phase_completion = {
            0: (requirements.steps, True),
        }

        result = compute_all_badges(phase_completion)

        badge_ids = {b.id for b in result}
        assert badge_info.id in badge_ids

    def test_caches_with_user_id(self):
        """Should work with user_id for caching (functional test)."""
        requirements = get_phase_requirements(0)
        if not requirements:
            pytest.skip("Phase 0 requirements not available")
        phase_completion = {
            0: (requirements.steps, True),
        }

        # First call
        result1 = compute_all_badges(phase_completion, user_id="test-user-1")
        # Second call should use cache
        result2 = compute_all_badges(phase_completion, user_id="test-user-1")

        assert len(result1) == len(result2)
        assert {b.id for b in result1} == {b.id for b in result2}

    def test_different_progress_different_results(self):
        """Should return different results for different progress."""
        result1 = compute_all_badges({}, user_id="test-user-2")
        result2 = compute_all_badges({0: (15, True)}, user_id="test-user-3")

        assert len(result2) > len(result1)
