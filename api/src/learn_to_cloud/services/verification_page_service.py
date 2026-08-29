"""View data for the dedicated verification workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from learn_to_cloud_shared.content_service import get_curriculum_overview
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.requirements import (
    get_prerequisite_phase,
    is_phase_verification_locked,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    Phase,
    PhaseOverview,
    PhaseProgress,
    VerificationProgress,
)
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.rendering.context import (
    build_requirement_card_context,
    feedback_tasks_and_passed,
)
from learn_to_cloud.services.progress_service import (
    fetch_phase_progress,
    fetch_user_progress,
)
from learn_to_cloud.services.submissions_service import get_phase_submission_context
from learn_to_cloud.services.verification_status_tokens import (
    create_verification_status_token,
)


@dataclass(frozen=True, slots=True)
class VerificationPhaseSummary:
    """One phase row in the verification hub."""

    phase: PhaseOverview
    progress: VerificationProgress
    is_locked: bool
    prerequisite_phase_id: int | None

    @property
    def status(self) -> str:
        if self.is_locked:
            return "locked"
        if self.progress.is_complete:
            return "complete"
        if self.progress.requirements_verified > 0:
            return "in_progress"
        return "not_started"


@dataclass(frozen=True, slots=True)
class VerificationsOverview:
    """Aggregate progress and phase rows for the verification hub."""

    phases: list[VerificationPhaseSummary]
    requirements_verified: int
    requirements_required: int
    next_phase: VerificationPhaseSummary | None

    @property
    def percentage(self) -> float:
        if self.requirements_required == 0:
            return 0.0
        return round(
            min(
                100.0,
                (self.requirements_verified / self.requirements_required) * 100,
            ),
            1,
        )

    @property
    def is_complete(self) -> bool:
        return (
            self.requirements_required > 0
            and self.requirements_verified >= self.requirements_required
        )


@dataclass(frozen=True, slots=True)
class PhaseVerificationWorkspace:
    """All state needed to render one phase's verification workflow."""

    phase: Phase
    phase_progress: PhaseProgress
    requirements: list[HandsOnRequirement]
    card_contexts_by_req: dict[str, dict[str, Any]]
    verification_locked: bool
    prerequisite_phase_id: int | None


async def get_verifications_overview(
    db: AsyncSession,
    user_id: int,
) -> VerificationsOverview:
    """Build verification progress without loading attempt details."""
    phases = get_curriculum_overview()
    user_progress = await fetch_user_progress(db, user_id, phase_overview=phases)

    summaries: list[VerificationPhaseSummary] = []
    for phase in phases:
        phase_progress = user_progress.phases.get(phase.order)
        if (
            phase_progress is None
            or phase_progress.verification.requirements_required == 0
        ):
            continue

        prerequisite_phase_id = get_prerequisite_phase(phase.order)
        prerequisite_progress = (
            user_progress.phases.get(prerequisite_phase_id)
            if prerequisite_phase_id is not None
            else None
        )
        is_locked = (
            prerequisite_progress is not None
            and not prerequisite_progress.verification.is_complete
        )
        summaries.append(
            VerificationPhaseSummary(
                phase=phase,
                progress=phase_progress.verification,
                is_locked=is_locked,
                prerequisite_phase_id=prerequisite_phase_id if is_locked else None,
            )
        )

    next_phase = next(
        (
            summary
            for summary in summaries
            if not summary.is_locked and not summary.progress.is_complete
        ),
        None,
    )
    return VerificationsOverview(
        phases=summaries,
        requirements_verified=sum(
            summary.progress.requirements_verified for summary in summaries
        ),
        requirements_required=sum(
            summary.progress.requirements_required for summary in summaries
        ),
        next_phase=next_phase,
    )


async def get_phase_verification_workspace(
    db: AsyncSession,
    user_id: int,
    phase: Phase,
    github_username: str | None,
) -> PhaseVerificationWorkspace:
    """Build cards, polling state, progress, and gating for one phase."""
    phase_progress = await fetch_phase_progress(db, user_id, phase)
    requirements = (
        list(phase.hands_on_verification.requirements)
        if phase.hands_on_verification
        else []
    )

    submission_context = await get_phase_submission_context(db, user_id, phase)
    requirements_by_uuid = {
        requirement.uuid: requirement for requirement in requirements
    }
    active_attempts = await VerificationAttemptRepository(
        db
    ).get_active_for_requirements(user_id, requirements_by_uuid)
    active_attempts_by_slug = {
        requirements_by_uuid[attempt.requirement_uuid].slug: attempt
        for attempt in active_attempts
        if attempt.requirement_uuid in requirements_by_uuid
    }

    card_contexts_by_req: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        feedback_tasks, feedback_passed = feedback_tasks_and_passed(
            submission_context.feedback_by_req.get(requirement.slug)
        )
        active_attempt = active_attempts_by_slug.get(requirement.slug)
        status_token = (
            create_verification_status_token(
                user_id=user_id,
                job_id=active_attempt.id,
                instance_id=str(active_attempt.id),
                requirement_slug=requirement.slug,
            )
            if active_attempt is not None
            else None
        )
        card_contexts_by_req[requirement.slug] = build_requirement_card_context(
            requirement=requirement,
            github_username=github_username,
            submission=submission_context.submissions_by_req.get(requirement.slug),
            feedback_tasks=feedback_tasks,
            feedback_passed=feedback_passed,
            processing=active_attempt is not None,
            verification_status_token=status_token,
        )

    verification_locked, prerequisite_phase_id = await is_phase_verification_locked(
        db, user_id, phase.order
    )
    return PhaseVerificationWorkspace(
        phase=phase,
        phase_progress=phase_progress,
        requirements=requirements,
        card_contexts_by_req=card_contexts_by_req,
        verification_locked=verification_locked,
        prerequisite_phase_id=prerequisite_phase_id,
    )
