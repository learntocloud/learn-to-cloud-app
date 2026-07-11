"""Unit tests for dashboard_service.

Tests cover:
- _build_phase_summary builds PhaseSummaryData correctly
- Unauthenticated dashboard returns zeroed stats
- Authenticated dashboard returns correct progress and continue_phase
- Program-complete dashboard has no continue_phase
- Query-count regression against a real DB (curriculum read-shapes refactor)
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.models import CurriculumStep, StepProgress, User
from learn_to_cloud_shared.requirements import load_requirement_index
from learn_to_cloud_shared.schemas import (
    PhaseOverview,
    PhaseProgress,
    PhaseProgressData,
    UserProgress,
)
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.services.dashboard_service import (
    _build_phase_summary,
    get_dashboard_data,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_phase(phase_id: int, name: str = "", slug: str = "") -> PhaseOverview:
    """Create a minimal PhaseOverview for testing."""
    return PhaseOverview(
        uuid=uuid4(),
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
    hands_on_validated: int = 0,
    hands_on_required: int = 1,
) -> PhaseProgress:
    return PhaseProgress(
        phase_id=phase_id,
        steps_completed=steps_completed,
        steps_required=steps_required,
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
        assert result.order == 0
        assert result.progress is None

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
        phase = PhaseOverview(
            uuid=uuid4(),
            name="Networking",
            slug="phase2",
            description="Learn networking",
            short_description="Networking basics",
            order=2,
            topics=[],
        )
        result = _build_phase_summary(phase, None)
        assert result.name == "Networking"
        assert result.slug == "phase2"
        assert result.order == 2


# ---------------------------------------------------------------------------
# get_dashboard_data — unauthenticated
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetDashboardDataUnauthenticated:
    @pytest.mark.asyncio
    async def test_returns_zeroed_stats(self):
        phases = (_make_phase(0), _make_phase(1))
        with patch(
            "learn_to_cloud.services.dashboard_service.get_curriculum_overview",
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
            "learn_to_cloud.services.dashboard_service.get_curriculum_overview",
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
                "learn_to_cloud.services.dashboard_service.get_curriculum_overview",
                autospec=True,
                return_value=phases,
            ),
            patch(
                "learn_to_cloud.services.dashboard_service.fetch_user_progress",
                autospec=True,
                return_value=user_progress,
            ),
            patch(
                "learn_to_cloud.services.dashboard_service.phase_progress_to_data",
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
                    hands_on_validated=1,
                    hands_on_required=1,
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
                "learn_to_cloud.services.dashboard_service.get_curriculum_overview",
                autospec=True,
                return_value=phases,
            ),
            patch(
                "learn_to_cloud.services.dashboard_service.fetch_user_progress",
                autospec=True,
                return_value=user_progress,
            ),
            patch(
                "learn_to_cloud.services.dashboard_service.phase_progress_to_data",
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
                "learn_to_cloud.services.dashboard_service.get_curriculum_overview",
                autospec=True,
                return_value=phases,
            ),
            patch(
                "learn_to_cloud.services.dashboard_service.fetch_user_progress",
                autospec=True,
                return_value=user_progress,
            ),
            patch(
                "learn_to_cloud.services.dashboard_service.phase_progress_to_data",
                autospec=True,
                return_value=progress_data,
            ),
        ):
            result = await get_dashboard_data(db=AsyncMock(), user_id=42)

        # Phase 1 should have progress=None since it's not in user_progress.phases
        phase1_summary = next(p for p in result.phases if p.order == 1)
        assert phase1_summary.progress is None


# ---------------------------------------------------------------------------
# get_dashboard_data — query-count regression against a real DB
#
# This is the exact scenario the curriculum read-shapes refactor targeted:
# visiting /dashboard repeatedly should never re-fetch full curriculum
# content, and should scale with the number of phases (small, fixed), not
# with the number of steps (hundreds).
# ---------------------------------------------------------------------------


@contextmanager
def _count_queries() -> Iterator[list[str]]:
    statements: list[str] = []

    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", _before_cursor_execute)


@pytest.mark.integration
class TestGetDashboardDataQueryCount:
    @pytest.mark.asyncio
    async def test_dashboard_query_count_does_not_scale_with_step_count(
        self, db_session: AsyncSession
    ) -> None:
        """Query count stays small and fixed, regardless of curriculum size.

        Seeds the real curriculum (hundreds of steps across several
        phases), completes a handful of steps and validates one
        requirement for a user, then asserts the whole /dashboard flow
        stays in the low single digits of small, indexed queries --
        never a full 5-table tree walk over every step.
        """
        await sync_curriculum_to_db(db_session)

        user = User(id=1, github_username="octocat")
        db_session.add(user)
        await db_session.flush()

        req_index = await load_requirement_index(db_session)
        first_phase_order = min(req_index.by_phase_order)
        reqs = req_index.requirements_for_phase(first_phase_order)
        if reqs:
            from learn_to_cloud_shared.models import (
                CurriculumRequirement,
                SubmissionValueKind,
            )
            from learn_to_cloud_shared.repositories.submission_repository import (
                SubmissionRepository,
            )
            from learn_to_cloud_shared.submission_values import SubmittedValue

            req_row = (
                await db_session.execute(
                    select(CurriculumRequirement).where(
                        CurriculumRequirement.uuid == reqs[0].uuid
                    )
                )
            ).scalar_one()
            kind = SubmissionValueKind(req_row.submission_value_kind)
            value_kwargs = {
                SubmissionValueKind.GITHUB_URL: {"github_url": "https://x/y"},
                SubmissionValueKind.TOKEN: {"token_value": "tok"},
                SubmissionValueKind.DEPLOYED_URL: {"deployed_url": "https://x"},
                SubmissionValueKind.TEXT: {"text_value": "ok"},
            }[kind]

            await SubmissionRepository(db_session).create(
                user_id=user.id,
                requirement_uuid=reqs[0].uuid,
                submitted_value=SubmittedValue(kind=kind, **value_kwargs),
                extracted_username=None,
                is_validated=True,
            )

        first_step_uuid = (
            await db_session.execute(select(CurriculumStep.uuid).limit(1))
        ).scalar_one()
        db_session.add(StepProgress(user_id=user.id, step_uuid=first_step_uuid))
        await db_session.flush()

        with _count_queries() as statements:
            result = await get_dashboard_data(db_session, user_id=user.id)

        assert result.total_phases > 0
        # Small, fixed number of aggregate/overview queries -- not one row
        # scan per step. See progress_service.fetch_user_progress /
        # dashboard_service.get_dashboard_data for the exact breakdown.
        assert len(statements) == 6
