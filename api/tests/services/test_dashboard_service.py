"""Unit tests for dashboard_service.

Tests cover:
- _build_phase_summary builds PhaseSummaryData correctly
- Unauthenticated dashboard returns zeroed stats
- Authenticated dashboard returns correct progress and continue_phase
- Program-complete dashboard has no continue_phase
"""

from unittest.mock import AsyncMock, patch

import pytest

from schemas import (
    Phase,
    PhaseProgress,
    PhaseProgressData,
    UserProgress,
)
from services.dashboard_service import _build_phase_summary, get_dashboard_data

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_phase(phase_id: int, name: str = "", slug: str = "") -> Phase:
    """Create a minimal Phase for testing."""
    return Phase(
        id=phase_id,
        name=name or f"Phase {phase_id}",
        slug=slug or f"phase{phase_id}",
        order=phase_id,
        topics=[],
    )


def _make_phase_progress(
    phase_id: int,
    *,
    steps_completed: int = 0,
    steps_required: int = 5,
    hands_on_validated_count: int = 0,
    hands_on_required_count: int = 1,
    hands_on_validated: bool = False,
    hands_on_required: bool = True,
) -> PhaseProgress:
    return PhaseProgress(
        phase_id=phase_id,
        steps_completed=steps_completed,
        steps_required=steps_required,
        hands_on_validated_count=hands_on_validated_count,
        hands_on_required_count=hands_on_required_count,
        hands_on_validated=hands_on_validated,
        hands_on_required=hands_on_required,
    )


# ---------------------------------------------------------------------------
# _build_phase_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildPhaseSummary:
    def test_without_progress(self):
        phase = _make_phase(0)
        result = _build_phase_summary(phase, None)
        assert result.id == 0
        assert result.progress is None
        assert result.topics_count == 0

    def test_with_progress(self):
        phase = _make_phase(1)
        progress_data = PhaseProgressData(
            steps_completed=3,
            steps_required=5,
            hands_on_validated=1,
            hands_on_required=1,
            percentage=60.0,
            status="in_progress",
        )
        result = _build_phase_summary(phase, progress_data)
        assert result.progress is not None
        assert result.progress.steps_completed == 3

    def test_maps_all_phase_fields(self):
        phase = Phase(
            id=2,
            name="Networking",
            slug="phase2",
            description="Learn networking",
            short_description="Networking basics",
            order=2,
            objectives=["Obj A", "Obj B"],
            topics=[],
        )
        result = _build_phase_summary(phase, None)
        assert result.name == "Networking"
        assert result.description == "Learn networking"
        assert result.objectives == ["Obj A", "Obj B"]


# ---------------------------------------------------------------------------
# get_dashboard_data — unauthenticated
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDashboardDataUnauthenticated:
    @pytest.mark.asyncio
    async def test_returns_zeroed_stats(self):
        phases = (_make_phase(0), _make_phase(1))
        with patch(
            "services.dashboard_service.get_all_phases",
            autospec=True,
            return_value=phases,
        ):
            result = await get_dashboard_data(db=AsyncMock(), user_id=None)

        assert result.overall_percentage == 0.0
        assert result.phases_completed == 0
        assert result.total_phases == 2
        assert result.is_program_complete is False
        assert result.continue_phase is None

    @pytest.mark.asyncio
    async def test_includes_all_phases(self):
        phases = (_make_phase(0), _make_phase(1), _make_phase(2))
        with patch(
            "services.dashboard_service.get_all_phases",
            autospec=True,
            return_value=phases,
        ):
            result = await get_dashboard_data(db=AsyncMock(), user_id=None)

        assert len(result.phases) == 3


# ---------------------------------------------------------------------------
# get_dashboard_data — authenticated
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDashboardDataAuthenticated:
    @pytest.mark.asyncio
    async def test_partial_progress_has_continue_phase(self):
        """User with incomplete phase 0 gets continue_phase pointing to phase 0."""
        phases = (_make_phase(0), _make_phase(1))
        user_progress = UserProgress(
            user_id=42,
            phases={
                0: _make_phase_progress(0, steps_completed=2, steps_required=5),
                1: _make_phase_progress(1, steps_completed=0, steps_required=5),
            },
            total_phases=2,
        )
        progress_data = PhaseProgressData(
            steps_completed=2,
            steps_required=5,
            hands_on_validated=0,
            hands_on_required=1,
            percentage=33.3,
            status="in_progress",
        )

        with (
            patch(
                "services.dashboard_service.get_all_phases",
                autospec=True,
                return_value=phases,
            ),
            patch(
                "services.dashboard_service.fetch_user_progress",
                autospec=True,
                return_value=user_progress,
            ),
            patch(
                "services.dashboard_service.phase_progress_to_data",
                autospec=True,
                return_value=progress_data,
            ),
        ):
            result = await get_dashboard_data(db=AsyncMock(), user_id=42)

        assert result.continue_phase is not None
        assert result.continue_phase.phase_id == 0
        assert result.continue_phase.slug == "phase0"

    @pytest.mark.asyncio
    async def test_program_complete_no_continue_phase(self):
        """All phases complete → is_program_complete=True, continue_phase=None."""
        phases = (_make_phase(0),)
        user_progress = UserProgress(
            user_id=42,
            phases={
                0: _make_phase_progress(
                    0,
                    steps_completed=5,
                    steps_required=5,
                    hands_on_validated_count=1,
                    hands_on_required_count=1,
                    hands_on_validated=True,
                ),
            },
            total_phases=1,
        )
        progress_data = PhaseProgressData(
            steps_completed=5,
            steps_required=5,
            hands_on_validated=1,
            hands_on_required=1,
            percentage=100.0,
            status="completed",
        )

        with (
            patch(
                "services.dashboard_service.get_all_phases",
                autospec=True,
                return_value=phases,
            ),
            patch(
                "services.dashboard_service.fetch_user_progress",
                autospec=True,
                return_value=user_progress,
            ),
            patch(
                "services.dashboard_service.phase_progress_to_data",
                autospec=True,
                return_value=progress_data,
            ),
        ):
            result = await get_dashboard_data(db=AsyncMock(), user_id=42)

        assert result.is_program_complete is True
        assert result.continue_phase is None

    @pytest.mark.asyncio
    async def test_phase_without_progress_gets_none(self):
        """Phase with no matching progress entry gets progress=None."""
        phases = (_make_phase(0), _make_phase(1))
        # Only phase 0 has progress data
        user_progress = UserProgress(
            user_id=42,
            phases={
                0: _make_phase_progress(0, steps_completed=3, steps_required=5),
            },
            total_phases=2,
        )
        progress_data = PhaseProgressData(
            steps_completed=3,
            steps_required=5,
            hands_on_validated=0,
            hands_on_required=1,
            percentage=50.0,
            status="in_progress",
        )

        with (
            patch(
                "services.dashboard_service.get_all_phases",
                autospec=True,
                return_value=phases,
            ),
            patch(
                "services.dashboard_service.fetch_user_progress",
                autospec=True,
                return_value=user_progress,
            ),
            patch(
                "services.dashboard_service.phase_progress_to_data",
                autospec=True,
                return_value=progress_data,
            ),
        ):
            result = await get_dashboard_data(db=AsyncMock(), user_id=42)

        # Phase 1 should have progress=None since it's not in user_progress.phases
        phase1_summary = next(p for p in result.phases if p.id == 1)
        assert phase1_summary.progress is None
