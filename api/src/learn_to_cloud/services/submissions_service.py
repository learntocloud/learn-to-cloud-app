"""Submissions service for hands-on verification submissions.

This module handles:
- Verification job creation with pre-validation
- Data transformation helpers used by other services (e.g. progress)
- Already-validated short-circuit (skip re-verification for passed requirements)

Routes should delegate submission business logic to this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from learn_to_cloud_shared.models import SubmissionType, VerificationJob
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
from learn_to_cloud_shared.verification.dispatcher import is_sync_verifiable
from learn_to_cloud_shared.verification.execution import (
    execute_sync_submission_validation,
    to_submission_data,
)
from learn_to_cloud_shared.verification.requirements import (
    get_prerequisite_phase,
    load_requirement_index,
)
from opentelemetry import trace
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
        sub_data = to_submission_data(
            sub,
            requirement_id=requirement.id,
            submission_type=requirement.submission_type,
            phase_id=phase.id,
        )
        submissions_by_req[requirement.id] = sub_data

        if sub.feedback_json and not sub.is_validated:
            try:
                raw_tasks = json.loads(sub.feedback_json)
                tasks = [
                    {
                        "name": t.get("task_name", ""),
                        "passed": t.get("passed", False),
                        "message": t.get("feedback", ""),
                        "next_steps": t.get("next_steps", ""),
                    }
                    for t in raw_tasks
                ]
                passed = sum(1 for t in tasks if t["passed"])

                feedback_by_req[requirement.id] = {
                    "tasks": tasks,
                    "passed": passed,
                }
            except (json.JSONDecodeError, TypeError):
                span = trace.get_current_span()
                span.add_event(
                    "feedback_parse_failed",
                    {"requirement_id": requirement.id},
                )

    return PhaseSubmissionContext(
        submissions_by_req=submissions_by_req,
        feedback_by_req=feedback_by_req,
    )


class RequirementNotFoundError(Exception):
    pass


class GitHubUsernameRequiredError(Exception):
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
    phase_id: int


@dataclass(frozen=True, slots=True)
class VerificationJobSubmission:
    """Result of creating or reusing a verification job (async Durable path)."""

    job: VerificationJob
    created: bool


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
    requirement_id: str,
    github_username: str | None,
    submitted_value: str | None = None,
) -> _PreValidationContext:
    """Shared pre-validation checks for submission paths.

    Validates requirement existence, already-validated status, phase gating,
    and GitHub username requirement.

    Opens a short-lived DB session for reads, then releases it before returning.
    """
    async with session_maker() as read_session:
        index = await load_requirement_index(read_session)
        requirement = index.by_id.get(requirement_id)
        if not requirement:
            raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

        phase_id = index.phase_id_by_req_id.get(requirement_id)
        if phase_id is None:
            raise RequirementNotFoundError(
                f"Requirement not mapped to a phase: {requirement_id}"
            )

        submission_repo = SubmissionRepository(read_session)

        existing = await submission_repo.get_by_user_and_requirement(
            user_id, requirement.uuid
        )
        if existing is not None and existing.is_validated:
            raise AlreadyValidatedError("You have already completed this requirement.")

        # Sequential phase gating
        prereq_phase = get_prerequisite_phase(phase_id)
        if prereq_phase is not None:
            prereq_req_uuids = index.requirement_uuids_for_phase(prereq_phase)
            if prereq_req_uuids:
                all_done = await submission_repo.are_all_requirements_validated(
                    user_id, prereq_req_uuids
                )
                if not all_done:
                    raise PriorPhaseNotCompleteError(
                        f"You must complete all Phase {prereq_phase} "
                        f"verifications before submitting for Phase {phase_id}.",
                        prerequisite_phase=prereq_phase,
                    )

    # read_session is now closed — connection returned to pool

    if (
        requirement.submission_type
        in (
            SubmissionType.GITHUB_PROFILE,
            SubmissionType.PROFILE_README,
            SubmissionType.REPO_FORK,
            SubmissionType.CTF_TOKEN,
            SubmissionType.NETWORKING_TOKEN,
            SubmissionType.JOURNAL_API_VERIFIER,
            SubmissionType.DEVOPS_ANALYSIS,
            SubmissionType.SECURITY_SCANNING,
        )
        and not github_username
    ):
        raise GitHubUsernameRequiredError(
            "You need to link your GitHub account to submit. "
            "Please sign out and sign in with GitHub."
        )

    return _PreValidationContext(
        requirement=requirement,
        phase_id=phase_id,
    )


async def create_verification_job(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_id: str,
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
        requirement_id,
        github_username,
        submitted_value,
    )

    if is_sync_verifiable(ctx.requirement.submission_type):
        submission_result = await execute_sync_submission_validation(
            session_maker=session_maker,
            user_id=user_id,
            requirement=ctx.requirement,
            phase_id=ctx.phase_id,
            submitted_value=submitted_value,
            github_username=github_username,
        )
        return SyncVerificationResult(submission_result=submission_result)

    async with session_maker() as write_session:
        repo = VerificationJobRepository(write_session)
        job, created = await repo.create_or_get_active(
            user_id=user_id,
            requirement_id=requirement_id,
            submission_type=ctx.requirement.submission_type,
            phase_id=ctx.phase_id,
            submitted_value=submitted_value,
        )
        await write_session.commit()

    return VerificationJobSubmission(job=job, created=created)
