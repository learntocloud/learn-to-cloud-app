"""Submissions service for hands-on verification submissions.

This module handles:
- Verification job creation with pre-validation
- Data transformation helpers used by other services (e.g. progress)
- Already-validated short-circuit (skip re-verification for passed requirements)

Routes should delegate submission business logic to this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from learn_to_cloud_shared.models import VerificationJob
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    Phase,
    PhaseSubmissionContext,
    SubmissionData,
    SubmissionResult,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.dispatcher import is_sync_verifiable
from learn_to_cloud_shared.verification.execution import (
    execute_sync_submission_validation,
    to_submission_data,
)
from learn_to_cloud_shared.verification.requirements import (
    RequirementIndex,
    get_prerequisite_phase,
    load_requirement_index,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_phase_submission_context(
    db: AsyncSession,
    user_id: int,
    phase: Phase,
) -> PhaseSubmissionContext:
    """Build submission context for rendering a phase page.

    Fetches the latest submission per requirement for the user in
    ``phase``, converts each to a ``SubmissionData`` DTO, and parses
    stored feedback JSON into template-ready summaries.

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

    repo = SubmissionRepository(db)
    raw_submissions = await repo.get_latest_for_requirements(
        user_id, requirements_by_uuid.keys()
    )

    submissions_by_req: dict[str, SubmissionData] = {}
    feedback_by_req: dict[str, dict[str, object]] = {}

    for sub in raw_submissions:
        requirement = requirements_by_uuid.get(sub.requirement_uuid)
        if requirement is None:
            # Defensive: get_latest_for_requirements only returns rows whose
            # uuid is in the input list, but if curriculum drift slips one
            # past us we skip silently rather than crash the phase page.
            continue
        sub_data = to_submission_data(sub)
        submissions_by_req[requirement.slug] = sub_data

        # Surface rubric feedback for both passing and failing submissions
        # (#425). Stored as JSONB (#459) so the rows arrive as a list of
        # TaskResult dicts and we don't need json.loads / try / except.
        if sub.feedback_json:
            tasks = [
                {
                    "name": t.get("task_name", ""),
                    "passed": t.get("passed", False),
                    "message": t.get("feedback", ""),
                    "next_steps": t.get("next_steps", ""),
                }
                for t in sub.feedback_json
            ]
            passed = sum(1 for t in tasks if t["passed"])
            feedback_by_req[requirement.slug] = {
                "tasks": tasks,
                "passed": passed,
            }

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
class VerificationJobSubmission:
    """Result of creating or reusing a verification job (async Durable path).

    Carries the validated requirement (and the github_username used at
    submit time) so the route can build a complete
    ``PreparedVerificationJob`` payload for the Durable starter without
    re-deriving anything from the request.
    """

    job: VerificationJob
    created: bool
    requirement: HandsOnRequirement
    github_username: str | None


@dataclass(frozen=True, slots=True)
class SyncVerificationResult:
    """Result of running a sync verification inside the FastAPI request.

    Returned by :func:`create_verification_job` for submission types whose
    validators finish in well under a second (phases 0-2). No Durable
    Functions orchestration is started — the ``Submission`` row is already
    persisted by the time this is returned.
    """

    submission_result: SubmissionResult


# Tagged union returned by ``create_verification_job``. Callers use
# ``isinstance`` to pick the rendering path.
SubmissionDispatchResult = VerificationJobSubmission | SyncVerificationResult


async def _check_submission_preconditions(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    submitted_value: str | None = None,
) -> _PreValidationContext:
    """Shared pre-validation checks for submission paths.

    Validates requirement existence, already-validated status, and phase gating.

    Opens a short-lived DB session for reads, then releases it before returning.
    """
    async with session_maker() as read_session:
        index = await load_requirement_index(read_session)
        requirement = index.by_slug.get(requirement_slug)
        if not requirement:
            raise RequirementNotFoundError(f"Requirement not found: {requirement_slug}")

        phase_order = index.phase_order_by_req_slug.get(requirement_slug)
        if phase_order is None:
            raise RequirementNotFoundError(
                f"Requirement not mapped to a phase: {requirement_slug}"
            )

        submission_repo = SubmissionRepository(read_session)

        existing = await submission_repo.get_by_user_and_requirement(
            user_id, requirement.uuid
        )
        if existing is not None and existing.is_validated:
            raise AlreadyValidatedError("You have already completed this requirement.")

        # Sequential phase gating
        prereq_phase = get_prerequisite_phase(phase_order)
        if prereq_phase is not None:
            prereq_req_uuids = index.requirement_uuids_for_phase(prereq_phase)
            if prereq_req_uuids:
                all_done = await submission_repo.are_all_requirements_validated(
                    user_id, prereq_req_uuids
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


async def create_verification_job(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_slug: str,
    submitted_value: str,
    github_username: str | None,
) -> SubmissionDispatchResult:
    """Validate request preconditions and dispatch to the right execution path.

    Returns a :class:`SyncVerificationResult` for submission types whose
    validators run inside the FastAPI request (phases 0-2). Returns a
    :class:`VerificationJobSubmission` for types that go through Durable
    Functions (phases 3-6).
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

    if is_sync_verifiable(ctx.requirement.submission_type):
        submission_result = await execute_sync_submission_validation(
            session_maker=session_maker,
            user_id=user_id,
            requirement=ctx.requirement,
            submitted_value=typed_value.as_text,
            github_username=github_username,
        )
        return SyncVerificationResult(submission_result=submission_result)

    async with session_maker() as write_session:
        repo = VerificationJobRepository(write_session)
        job, created = await repo.create_or_get_active(
            user_id=user_id,
            requirement_uuid=ctx.requirement.uuid,
            submitted_value=typed_value,
        )
        await write_session.commit()

    return VerificationJobSubmission(
        job=job,
        created=created,
        requirement=ctx.requirement,
        github_username=github_username,
    )


# Synthetic user id for the read-only smoke check. It is never a real
# account (GitHub user ids are positive), so every read returns nothing
# and the check writes no rows.
_SMOKE_USER_ID = 0


async def run_submit_smoke_check(
    session_maker: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    """Exercise the verification submit read path without writing anything.

    Runs the same requirement loading, submissions read, phase gating, and
    typed-value parsing that :func:`create_verification_job` performs for a
    real submission, but against a synthetic user and an early phase, and
    stops before persisting anything.

    The goal is to catch a schema-versus-code mismatch (the class of bug
    behind incident #432) right after deploy: if the running code expects a
    column or value shape the migrated database does not have, the reads
    here raise and the post-deploy smoke test fails instead of letting real
    user submissions return 500s for days.

    Returns the slug it exercised so callers can log what was checked.
    """
    async with session_maker() as read_session:
        index = await load_requirement_index(read_session)

    requirement = _pick_smoke_requirement(index)

    # The synthetic user has no submissions, so preconditions read the
    # requirement index and the submissions table, then return cleanly.
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
