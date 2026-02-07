"""Dashboard service.

Provides phase listing with user progress for the dashboard page.

Source of truth: .github/skills/progression-system/progression-system.md
"""

from sqlalchemy.ext.asyncio import AsyncSession

from schemas import (
    Phase,
    PhaseProgressData,
    PhaseSummaryData,
)
from services.content_service import get_all_phases
from services.progress_service import (
    fetch_user_progress,
    phase_progress_to_data,
)


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


async def get_phases_list(
    db: AsyncSession,
    user_id: int | None,
) -> list[PhaseSummaryData]:
    """Get all phases with progress for a user.

    If user_id is None (unauthenticated), no progress data is shown.
    """
    phases = get_all_phases()

    if user_id is None:
        return [_build_phase_summary(phase, None) for phase in phases]

    user_progress = await fetch_user_progress(db, user_id)

    return [
        _build_phase_summary(
            phase,
            phase_progress_to_data(progress)
            if (progress := user_progress.phases.get(phase.id))
            else None,
        )
        for phase in phases
    ]
