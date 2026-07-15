"""Dashboard service.

Provides phase listing with user progress and summary stats
for the dashboard page.
"""

import logging

from learn_to_cloud_shared.content_service import get_curriculum_overview
from learn_to_cloud_shared.schemas import (
    ContinuePhaseData,
    DashboardData,
    PhaseOverview,
    PhaseProgressData,
    PhaseSummaryData,
)
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.services.progress_service import (
    fetch_user_progress,
    phase_progress_to_data,
)

logger = logging.getLogger(__name__)


def _build_phase_summary(
    phase: PhaseOverview,
    progress_data: PhaseProgressData | None,
) -> PhaseSummaryData:
    """Build PhaseSummaryData from a PhaseOverview and computed progress."""
    return PhaseSummaryData(
        order=phase.order,
        name=phase.name,
        slug=phase.slug,
        progress=progress_data,
    )


async def get_dashboard_data(
    db: AsyncSession,
    user_id: int | None,
) -> DashboardData:
    """Build the full dashboard payload.

    Returns phase list, overall stats, and continue-phase pointer.
    For unauthenticated users, returns phases only with zeroed stats.
    """
    phases = get_curriculum_overview()

    if user_id is None:
        return DashboardData(
            phases=[_build_phase_summary(phase, None) for phase in phases],
            overall_percentage=0.0,
            phases_completed=0,
            total_phases=len(phases),
            is_program_complete=False,
        )

    user_progress = await fetch_user_progress(db, user_id, phase_overview=phases)

    phase_summaries = [
        _build_phase_summary(
            phase,
            phase_progress_to_data(progress)
            if (progress := user_progress.phases.get(phase.order))
            else None,
        )
        for phase in phases
    ]

    continue_phase: ContinuePhaseData | None = None
    if not user_progress.is_program_complete:
        current_id = user_progress.current_phase
        current = next((p for p in phases if p.order == current_id), None)
        if current is not None:
            continue_phase = ContinuePhaseData(
                phase_id=current.order,
                name=current.name,
                slug=current.slug,
                order=current.order,
            )

    logger.debug(
        "dashboard.built",
        extra={
            "user_id": user_id,
            "phases_completed": user_progress.phases_completed,
        },
    )

    return DashboardData(
        phases=phase_summaries,
        overall_percentage=round(user_progress.overall_percentage, 1),
        phases_completed=user_progress.phases_completed,
        total_phases=user_progress.total_phases,
        is_program_complete=user_progress.is_program_complete,
        continue_phase=continue_phase,
    )
