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

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.progress_reads import are_all_requirements_succeeded
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    AttemptAlreadyValidatedError,
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.requirements import (
    RequirementIndex,
    get_prerequisite_phase,
    load_requirement_index,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    Phase,
    PhaseSubmissionContext,
    SubmissionData,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.execution import (
    attempt_to_submission_data,
)
from learn_to_cloud_shared.verification_attempt_snapshot import (
    ATTEMPT_PAYLOAD_VERSION,
    build_requirement_snapshot,
    compute_snapshot_hash,
)
from opentelemetry.propagate import inject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


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

    def _record_feedback(
        requirement_slug: str, feedback_json: list[dict] | None
    ) -> None:
        # Surface rubric feedback for both passing and failing submissions
        # (#425). Stored as JSONB (#459) so the rows arrive as a list of
        # TaskResult dicts and we don't need json.loads / try / except.
        if not feedback_json:
            return
        tasks = [
            {
                "name": t.get("task_name", ""),
                "passed": t.get("passed", False),
                "message": t.get("feedback", ""),
                "next_steps": t.get("next_steps", ""),
            }
            for t in feedback_json
        ]
        passed = sum(1 for t in tasks if t["passed"])
        feedback_by_req[requirement_slug] = {"tasks": tasks, "passed": passed}

    for attempt in latest_attempts:
        requirement = requirements_by_uuid.get(attempt.requirement_uuid)
        if requirement is None:
            # Defensive: get_latest_terminal_for_requirements only returns
            # rows whose uuid is in the input list, but if curriculum drift
            # slips one past us we skip silently rather than crash the page.
            continue
        submissions_by_req[requirement.slug] = attempt_to_submission_data(attempt)
        _record_feedback(requirement.slug, attempt.feedback_json)

    return PhaseSubmissionContext(
        submissions_by_req=submissions_by_req,
        feedback_by_req=feedback_by_req,
    )


class RequirementNotFoundError(Exception):
    pass


class InvalidSubmittedValueError(Exception):
    pass


class AlreadyValidatedError(Exception):
    """Raised when re-submitting a requirement that is already validated."""


class PriorPhaseNotCompleteError(Exception):
    """Raised when submitting for a phase whose prerequisite isn't fully verified."""

    def __init__(self, message: str, prerequisite_phase: int):
        super().__init__(message)
        self.prerequisite_phase = prerequisite_phase


@dataclass(frozen=True, slots=True)
class _PreValidationContext:
    """Data collected during pre-validation checks.

    Returned by ``_check_submission_preconditions`` so callers don't repeat lookups.
    """

    requirement: HandsOnRequirement
    phase_order: int


@dataclass(frozen=True, slots=True)
class VerificationAttemptSubmission:
    """Result of creating or reusing a verification attempt."""

    attempt_id: UUID
    created: bool


def _current_traceparent() -> str | None:
    """Return the active W3C trace parent when telemetry is available."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier.get("traceparent")


async def _check_submission_preconditions(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    submitted_value: str | None = None,
) -> _PreValidationContext:
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
                        prerequisite_phase=prereq_phase,
                    )

    # read_session is now closed — connection returned to pool

    return _PreValidationContext(
        requirement=requirement,
        phase_order=phase_order,
    )


async def create_verification_attempt(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    submitted_value: str,
    github_username: str | None,
) -> VerificationAttemptSubmission:
    """Validate request preconditions and create the unified verification attempt.

    Every submission type runs through Durable Functions. This validates the
    request, then -- inside one transaction, guarded by a transaction-scoped
    Postgres advisory lock on ``(user_id, requirement_uuid)`` -- creates or
    reuses the authoritative ``VerificationAttempt`` row.

    The advisory lock serializes concurrent submits for the same
    requirement so two racing requests can never both pass the active/succeeded
    checks and create two active attempts. New attempts no longer create a
    compatibility ``verification_jobs`` row.
    """
    ctx = await _check_submission_preconditions(
        session_maker,
        user_id,
        requirement_slug,
        submitted_value,
    )
    try:
        typed_value = SubmittedValue.from_raw(ctx.requirement, submitted_value)
    except ValueError as exc:
        raise InvalidSubmittedValueError(str(exc)) from exc

    catalog = get_curriculum_catalog()
    requirement_snapshot = build_requirement_snapshot(ctx.requirement)
    requirement_snapshot_hash = compute_snapshot_hash(requirement_snapshot)
    attempt_id = uuid4()
    traceparent = _current_traceparent()

    async with session_maker() as write_session:
        attempt_repo = VerificationAttemptRepository(write_session)
        try:
            attempt, created = await attempt_repo.create_or_get_active(
                id=attempt_id,
                user_id=user_id,
                requirement_uuid=ctx.requirement.uuid,
                artifact_schema_version=catalog.artifact_schema_version,
                curriculum_version=catalog.curriculum_version,
                content_hash=catalog.content_hash,
                requirement_snapshot=requirement_snapshot,
                requirement_snapshot_hash=requirement_snapshot_hash,
                payload_version=ATTEMPT_PAYLOAD_VERSION,
                github_username_snapshot=github_username,
                submitted_value=typed_value,
                cloud_provider=None,
                traceparent=traceparent,
            )
        except AttemptAlreadyValidatedError as exc:
            raise AlreadyValidatedError(
                "You have already completed this requirement."
            ) from exc

        await write_session.commit()

    return VerificationAttemptSubmission(attempt_id=attempt.id, created=created)


# Synthetic user id for the read-only smoke check. It is never a real
# account (GitHub user ids are positive), so every read returns nothing
# and the check writes no rows.
_SMOKE_USER_ID = 0


async def run_submit_smoke_check(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Exercise the verification submit read path without writing anything.

    Runs the same requirement loading, submissions read, phase gating, and
    typed-value parsing that :func:`create_verification_attempt` performs for
    a real submission, but against a synthetic user and an early phase, and
    stops before persisting anything.

    The goal is to catch a schema-versus-code mismatch (the class of bug
    behind incident #432) right after deploy: if the running code expects a
    column or value shape the migrated database does not have, the reads
    here raise and the post-deploy smoke test fails instead of letting real
    user submissions return 500s for days.

    Returns the slug it exercised so callers can log what was checked.
    """
    index = load_requirement_index()

    requirement = _pick_smoke_requirement(index)

    # The synthetic user has no attempts, so preconditions return cleanly.
    # An early-phase requirement has no prerequisite phase, so the
    # sequential gating check does not raise for the synthetic user.
    ctx = await _check_submission_preconditions(
        session_maker,
        user_id=_SMOKE_USER_ID,
        requirement_slug=requirement.slug,
    )

    # Exercise the submission-type-to-value mapping. A value-validation
    # error here means the code ran fine, so it is not a health signal;
    # any other error (e.g. an unmapped submission type) propagates.
    try:
        SubmittedValue.from_raw(ctx.requirement, "smoke-test")
    except ValueError:
        # A value-format validation error means the parsing code ran fine,
        # so it is not a schema/code-health signal and is safe to ignore
        # here. Any other error type propagates and fails the smoke check.
        pass

    return {"requirement_slug": requirement.slug}


def _pick_smoke_requirement(index: RequirementIndex) -> HandsOnRequirement:
    """Pick the first requirement in the earliest phase that has one.

    The earliest phase has no prerequisite, so the precondition check runs
    to completion for the synthetic user instead of tripping phase gating.
    """
    for phase_order in sorted(index.by_phase_order):
        requirements = index.by_phase_order[phase_order]
        if requirements:
            return requirements[0]
    raise RuntimeError("Smoke check found no hands-on requirements to exercise.")
