"""Submissions service for hands-on verification submissions.

This module handles:
- Verification attempt creation with pre-validation
- Data transformation helpers used by other services (e.g. progress)
- Already-validated short-circuit (skip re-verification for passed requirements)

Routes should delegate submission business logic to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from learn_to_cloud.curriculum.catalog import get_curriculum_catalog
from learn_to_cloud.repositories.verification_attempt_repository import (
    AttemptAlreadyValidatedError,
    VerificationAttemptRepository,
)
from learn_to_cloud.schemas.curriculum import Phase
from learn_to_cloud.schemas.requirements import HandsOnRequirement
from learn_to_cloud.schemas.verification import PhaseSubmissionContext, SubmissionData
from learn_to_cloud.services.progress_reads import are_all_requirements_succeeded
from learn_to_cloud.services.requirements import (
    get_prerequisite_phase,
    load_requirement_index,
)
from learn_to_cloud.verification.attempt_snapshot import (
    ATTEMPT_PAYLOAD_VERSION,
    build_requirement_snapshot,
    compute_snapshot_hash,
)
from learn_to_cloud.verification.execution import (
    attempt_to_submission_data,
)
from learn_to_cloud.verification.submission_values import (
    SubmittedValue,
    submitted_value_matches_requirement,
)


async def get_phase_submission_context(
    db: AsyncSession,
    user_id: int,
    phase: Phase,
) -> PhaseSubmissionContext:
    """Build submission context for rendering a phase page.

    Fetches the latest terminal attempt per requirement and converts it to
    template-ready submission and feedback data.

    Takes the resolved ``Phase`` rather than a phase id so we can pull
    each requirement's UUID, slug, and submission_type out of the
    in-memory tree -- after Phase D.2 (#465) the ``submissions`` table
    no longer carries those denormalized fields.
    """
    requirements_by_uuid: dict[UUID, HandsOnRequirement] = {}
    if phase.hands_on_verification:
        requirements_by_uuid = {
            req.uuid: req for req in phase.hands_on_verification.requirements
        }

    attempt_repo = VerificationAttemptRepository(db)
    latest_attempts = await attempt_repo.get_latest_terminal_for_requirements(
        user_id, requirements_by_uuid.keys()
    )

    submissions_by_req: dict[str, SubmissionData] = {}
    feedback_by_req: dict[str, dict[str, object]] = {}

    for attempt in latest_attempts:
        requirement = requirements_by_uuid.get(attempt.requirement_uuid)
        if requirement is None:
            # Defensive: get_latest_terminal_for_requirements only returns
            # rows whose uuid is in the input list, but if curriculum drift
            # slips one past us we skip silently rather than crash the page.
            continue
        submissions_by_req[requirement.slug] = attempt_to_submission_data(attempt)
        feedback = feedback_context_from_json(attempt.feedback_json)
        if feedback is not None:
            feedback_by_req[requirement.slug] = feedback

    return PhaseSubmissionContext(
        submissions_by_req=submissions_by_req,
        feedback_by_req=feedback_by_req,
    )


def feedback_context_from_json(
    feedback_json: list[dict] | None,
) -> dict[str, object] | None:
    """Convert persisted rubric results into learner-facing feedback context."""
    if not feedback_json:
        return None

    tasks = [
        {
            "name": task.get("task_name", ""),
            "passed": task.get("passed", False),
            "message": task.get("feedback", ""),
            "next_steps": task.get("next_steps", ""),
            "criteria": [
                {
                    "id": criterion.get("criterion_id", ""),
                    "label": criterion.get("label", ""),
                    "kind": criterion.get("kind", "required"),
                    "status": criterion.get("status", "not_met"),
                    "explanation": criterion.get("explanation", ""),
                    "next_steps": criterion.get("next_steps", ""),
                    "evidence_refs": criterion.get("evidence_refs", []),
                }
                for criterion in task.get("criterion_results", [])
                if isinstance(criterion, dict)
            ],
        }
        for task in feedback_json
    ]
    return {
        "tasks": tasks,
        "passed": sum(1 for task in tasks if task["passed"]),
    }


class RequirementNotFoundError(Exception):
    pass


class InvalidSubmittedValueError(Exception):
    pass


class AlreadyValidatedError(Exception):
    """Raised when re-submitting a requirement that is already validated."""


class PriorPhaseNotCompleteError(Exception):
    """Raised when submitting for a phase whose prerequisite isn't fully verified."""


@dataclass(frozen=True, slots=True)
class VerificationAttemptSubmission:
    """Result of creating or reusing a verification attempt."""

    attempt_id: UUID
    created: bool


async def _check_submission_preconditions(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
) -> HandsOnRequirement:
    """Shared pre-validation checks for submission paths.

    Validates requirement existence, already-validated status, and phase gating.

    Opens a short-lived DB session for the learner-state reads (existing
    attempt and prior-phase verification), then releases it before returning.
    ``create_or_get_active`` still re-checks "already succeeded" under its
    advisory lock, so this is a fast-fail before the heavier snapshot work,
    not the only guard against a duplicate validated submission.
    """
    index = load_requirement_index()
    requirement = index.by_slug.get(requirement_slug)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_slug}")

    phase_order = index.phase_order_by_req_slug.get(requirement_slug)
    if phase_order is None:
        raise RequirementNotFoundError(
            f"Requirement not mapped to a phase: {requirement_slug}"
        )

    async with session_maker() as read_session:
        already_succeeded = await are_all_requirements_succeeded(
            read_session, user_id, [requirement.uuid]
        )
        if already_succeeded:
            raise AlreadyValidatedError("You have already completed this requirement.")

        # Sequential phase gating
        prereq_phase = get_prerequisite_phase(phase_order)
        if prereq_phase is not None:
            prereq_req_uuids = index.requirement_uuids_for_phase(prereq_phase)
            if prereq_req_uuids:
                all_done = await are_all_requirements_succeeded(
                    read_session, user_id, prereq_req_uuids
                )
                if not all_done:
                    raise PriorPhaseNotCompleteError(
                        f"You must complete all Phase {prereq_phase} "
                        f"verifications before submitting for Phase {phase_order}.",
                    )

    # read_session is now closed — connection returned to pool

    return requirement


async def create_verification_attempt(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    submitted_value: SubmittedValue,
    github_username: str | None,
) -> VerificationAttemptSubmission:
    """Validate request preconditions and create the unified verification attempt.

    Every submission type runs in the API worker. This validates the
    request, then -- inside one transaction, guarded by a transaction-scoped
    Postgres advisory lock on ``(user_id, requirement_uuid)`` -- creates or
    reuses the authoritative ``VerificationAttempt`` row.

    The advisory lock serializes concurrent submits for the same
    requirement so two racing requests can never both pass the active/succeeded
    checks and create two active attempts.
    """
    requirement = await _check_submission_preconditions(
        session_maker,
        user_id,
        requirement_slug,
    )
    if not submitted_value_matches_requirement(requirement, submitted_value):
        raise InvalidSubmittedValueError(
            "Submitted value type does not match this requirement."
        )

    catalog = get_curriculum_catalog()
    requirement_snapshot = build_requirement_snapshot(requirement)
    requirement_snapshot_hash = compute_snapshot_hash(requirement_snapshot)
    attempt_id = uuid4()

    async with session_maker() as write_session:
        attempt_repo = VerificationAttemptRepository(write_session)
        try:
            attempt, created = await attempt_repo.create_or_get_active(
                id=attempt_id,
                user_id=user_id,
                requirement_uuid=requirement.uuid,
                artifact_schema_version=catalog.artifact_schema_version,
                curriculum_version=catalog.curriculum_version,
                content_hash=catalog.content_hash,
                requirement_snapshot=requirement_snapshot,
                requirement_snapshot_hash=requirement_snapshot_hash,
                payload_version=ATTEMPT_PAYLOAD_VERSION,
                github_username_snapshot=github_username,
                submitted_value=submitted_value,
                cloud_provider=None,
            )
        except AttemptAlreadyValidatedError as exc:
            raise AlreadyValidatedError(
                "You have already completed this requirement."
            ) from exc

        await write_session.commit()

    return VerificationAttemptSubmission(attempt_id=attempt.id, created=created)
