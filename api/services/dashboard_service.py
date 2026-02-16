"""Dashboard service.

Provides phase listing with user progress and summary stats
for the dashboard page.

Source of truth: .github/skills/progression-system/progression-system.md
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from schemas import (
    ContinuePhaseData,
    DashboardData,
    Phase,
    PhaseProgressData,
    PhaseSummaryData,
)
from services.content_service import get_all_phases
from services.progress_service import (
    fetch_user_progress,
    phase_progress_to_data,
)

logger = logging.getLogger(__name__)


def _build_phase_summary(
    phase: Phase,
    progress_data: PhaseProgressData | None,
) -> PhaseSummaryData:
    """Build PhaseSummaryData from a Phase and computed values."""
    return PhaseSummaryData(
        id=phase.id,
        name=phase.name,
        slug=phase.slug,
        description=phase.description,
        short_description=phase.short_description,
        order=phase.order,
        topics_count=len(phase.topics),
        objectives=list(phase.objectives),
        capstone=phase.capstone,
        hands_on_verification=phase.hands_on_verification,
        progress=progress_data,
    )


async def get_dashboard_data(
    db: AsyncSession,
    user_id: int | None,
) -> DashboardData:
    """Build the full dashboard payload.

    Returns phase list, overall stats, continue-phase pointer, and badges.
    For unauthenticated users, returns phases only with zeroed stats.
    """
    phases = get_all_phases()

    if user_id is None:
        return DashboardData(
            phases=[_build_phase_summary(phase, None) for phase in phases],
            overall_percentage=0.0,
            phases_completed=0,
            total_phases=len(phases),
            is_program_complete=False,
        )

    user_progress = await fetch_user_progress(db, user_id)

    phase_summaries = [
        _build_phase_summary(
            phase,
            phase_progress_to_data(progress)
            if (progress := user_progress.phases.get(phase.id))
            else None,
        )
        for phase in phases
    ]

    continue_phase: ContinuePhaseData | None = None
    if not user_progress.is_program_complete:
        current_id = user_progress.current_phase
        current = next((p for p in phases if p.id == current_id), None)
        if current is not None:
            continue_phase = ContinuePhaseData(
                phase_id=current.id,
                name=current.name,
                slug=current.slug,
                order=current.order,
            )

    logger.info(
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
