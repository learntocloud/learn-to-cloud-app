"""Page contexts for the dedicated verification experience."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from learn_to_cloud_shared.content_service import (
    get_curriculum_overview,
    get_phase_by_slug,
)
from learn_to_cloud_shared.models import SubmissionValueKind
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptHistoryProjection,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.requirements import is_phase_verification_locked
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    Phase,
    PhaseOverview,
    PhaseProgress,
)
from learn_to_cloud_shared.verification.execution import attempt_to_submission_data
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.rendering.context import build_requirement_card_context
from learn_to_cloud.services.progress_service import (
    fetch_phase_progress,
    fetch_user_progress,
)
from learn_to_cloud.services.verification_feedback import (
    FeedbackTaskContext,
    convert_feedback,
)
from learn_to_cloud.services.verification_history_cursors import (
    create_history_cursor,
    load_history_cursor,
)
from learn_to_cloud.services.verification_status_tokens import (
    create_verification_status_token,
)

HISTORY_PAGE_SIZE = 10


@dataclass(frozen=True, slots=True)
class VerificationOverviewPhase:
    phase: PhaseOverview
    progress: PhaseProgress


@dataclass(frozen=True, slots=True)
class VerificationOverviewContext:
    phases: tuple[VerificationOverviewPhase, ...]
    requirements_verified: int
    requirements_required: int
    percentage: float


@dataclass(frozen=True, slots=True)
class VerificationHistoryItem:
    id: UUID
    occurred_at: datetime
    outcome: str
    validation_message: str | None
    artifact_url: str | None
    feedback_tasks: list[FeedbackTaskContext]
    feedback_passed: int


@dataclass(frozen=True, slots=True)
class VerificationHistoryPage:
    items: tuple[VerificationHistoryItem, ...]
    next_cursor: str | None


RequirementPageState = Literal["passed", "current", "up_next", "locked"]


@dataclass(frozen=True, slots=True)
class RequirementVerificationContext:
    requirement: HandsOnRequirement
    card: dict[str, Any]
    page_state: RequirementPageState
    history: VerificationHistoryPage


@dataclass(frozen=True, slots=True)
class PhaseVerificationContext:
    phase: Phase
    progress: PhaseProgress
    requirements: tuple[RequirementVerificationContext, ...]
    verification_locked: bool
    prerequisite_phase_id: int | None


async def get_verification_overview(
    db: AsyncSession,
    user_id: int,
) -> VerificationOverviewContext:
    """Build verification progress across every current curriculum phase."""
    phase_overview = get_curriculum_overview()
    progress = await fetch_user_progress(
        db,
        user_id,
        phase_overview=phase_overview,
    )
    phases = tuple(
        VerificationOverviewPhase(phase=phase, progress=progress.phases[phase.order])
        for phase in phase_overview
    )
    required = sum(
        phase.progress.verification.requirements_required for phase in phases
    )
    verified = sum(
        phase.progress.verification.requirements_verified for phase in phases
    )
    percentage = 100.0 if required == 0 else round(verified / required * 100, 1)
    return VerificationOverviewContext(
        phases=phases,
        requirements_verified=verified,
        requirements_required=required,
        percentage=percentage,
    )


async def get_phase_verification_context(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
    *,
    github_username: str | None,
) -> PhaseVerificationContext | None:
    """Assemble one dedicated phase verification page."""
    phase = get_phase_by_slug(f"phase{phase_id}")
    if phase is None:
        return None

    catalog_requirements = tuple(
        phase.hands_on_verification.requirements
        if phase.hands_on_verification is not None
        else ()
    )
    requirement_by_uuid = {
        requirement.uuid: requirement for requirement in catalog_requirements
    }
    requirement_uuids = tuple(requirement_by_uuid)

    progress = await fetch_phase_progress(db, user_id, phase)
    verification_locked, prerequisite_phase_id = await is_phase_verification_locked(
        db, user_id, phase_id
    )
    repository = VerificationAttemptRepository(db)
    latest_attempts = await repository.get_latest_terminal_for_requirements(
        user_id, requirement_uuids
    )
    active_attempts = await repository.get_active_for_requirements(
        user_id, requirement_uuids
    )
    history_rows = await repository.get_terminal_history_for_requirements(
        user_id,
        requirement_uuids,
        per_requirement_limit=HISTORY_PAGE_SIZE + 1,
    )

    latest_by_uuid = {attempt.requirement_uuid: attempt for attempt in latest_attempts}
    active_by_uuid = {attempt.requirement_uuid: attempt for attempt in active_attempts}
    active_requirement_uuid = next(
        (
            requirement.uuid
            for requirement in catalog_requirements
            if requirement.uuid in active_by_uuid
        ),
        None,
    )
    history_by_uuid: dict[UUID, list[AttemptHistoryProjection]] = defaultdict(list)
    for row in history_rows:
        if row.requirement_uuid in requirement_by_uuid:
            history_by_uuid[row.requirement_uuid].append(row)

    contexts: list[RequirementVerificationContext] = []
    found_current = False
    for requirement in catalog_requirements:
        latest = latest_by_uuid.get(requirement.uuid)
        active = active_by_uuid.get(requirement.uuid)
        submission = attempt_to_submission_data(latest) if latest is not None else None
        feedback = (
            convert_feedback(latest.feedback_json) if latest is not None else None
        )
        card = build_requirement_card_context(
            requirement=requirement,
            github_username=github_username,
            submission=submission,
            feedback_tasks=feedback.tasks if feedback else [],
            feedback_passed=feedback.passed if feedback else 0,
            processing=active is not None,
            verification_status_token=(
                create_verification_status_token(
                    user_id=user_id,
                    job_id=active.id,
                    instance_id=str(active.id),
                    requirement_slug=requirement.slug,
                )
                if active is not None
                else None
            ),
        )
        if card["card_state"] == "passed":
            page_state: RequirementPageState = "passed"
        elif requirement.uuid == active_requirement_uuid:
            page_state = "current"
            found_current = True
        elif verification_locked:
            page_state = "locked"
        elif not found_current and active_requirement_uuid is None:
            page_state = "current"
            found_current = True
        else:
            page_state = "up_next"

        rows = history_by_uuid[requirement.uuid]
        contexts.append(
            RequirementVerificationContext(
                requirement=requirement,
                card=card,
                page_state=page_state,
                history=_history_page(
                    rows,
                    user_id=user_id,
                    requirement_uuid=requirement.uuid,
                ),
            )
        )

    return PhaseVerificationContext(
        phase=phase,
        progress=progress,
        requirements=tuple(contexts),
        verification_locked=verification_locked,
        prerequisite_phase_id=prerequisite_phase_id,
    )


async def get_verification_history_page(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
    requirement_slug: str,
    cursor: str,
) -> VerificationHistoryPage | None:
    """Load ten older terminal attempts for one current requirement."""
    phase = get_phase_by_slug(f"phase{phase_id}")
    requirements = (
        phase.hands_on_verification.requirements
        if phase is not None and phase.hands_on_verification is not None
        else ()
    )
    requirement = next(
        (item for item in requirements if item.slug == requirement_slug),
        None,
    )
    if requirement is None:
        return None

    decoded = load_history_cursor(
        cursor,
        expected_user_id=user_id,
        expected_requirement_uuid=requirement.uuid,
    )
    rows = await VerificationAttemptRepository(db).get_terminal_history(
        user_id,
        requirement.uuid,
        limit=HISTORY_PAGE_SIZE + 1,
        before=(decoded.created_at, decoded.attempt_id),
    )
    return _history_page(
        rows,
        user_id=user_id,
        requirement_uuid=requirement.uuid,
    )


def _history_page(
    rows: list[AttemptHistoryProjection],
    *,
    user_id: int,
    requirement_uuid: UUID,
) -> VerificationHistoryPage:
    visible = rows[:HISTORY_PAGE_SIZE]
    next_cursor = None
    if len(rows) > HISTORY_PAGE_SIZE:
        last = visible[-1]
        next_cursor = create_history_cursor(
            user_id=user_id,
            requirement_uuid=requirement_uuid,
            created_at=last.created_at,
            attempt_id=last.id,
        )
    return VerificationHistoryPage(
        items=tuple(_history_item(row) for row in visible),
        next_cursor=next_cursor,
    )


def _history_item(row: AttemptHistoryProjection) -> VerificationHistoryItem:
    feedback = convert_feedback(row.feedback_json)
    return VerificationHistoryItem(
        id=row.id,
        occurred_at=row.completed_at or row.created_at,
        outcome=row.outcome,
        validation_message=row.validation_message,
        artifact_url=_safe_artifact_url(
            row.submission_value_kind,
            row.submitted_value,
        ),
        feedback_tasks=feedback.tasks if feedback else [],
        feedback_passed=feedback.passed if feedback else 0,
    )


def _safe_artifact_url(value_kind: str, value: str) -> str | None:
    if value_kind not in {
        SubmissionValueKind.GITHUB_URL.value,
        SubmissionValueKind.DEPLOYED_URL.value,
    }:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return value
