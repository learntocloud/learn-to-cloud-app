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

from learn_to_cloud_shared.models import SubmissionType, VerificationJob
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.verification_job_repository import (
    VerificationJobRepository,
)
from learn_to_cloud_shared.schemas import (
    HandsOnRequirement,
    PhaseSubmissionContext,
    SubmissionData,
)
from learn_to_cloud_shared.verification.execution import to_submission_data
from learn_to_cloud_shared.verification.requirements import (
    get_phase_id_for_requirement,
    get_prerequisite_phase,
    get_requirement_by_id,
    get_requirement_ids_for_phase,
)
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_phase_submission_context(
    db: AsyncSession,
    user_id: int,
    phase_id: int,
) -> PhaseSubmissionContext:
    """Build submission context for rendering a phase page.

    Fetches all submissions for the user in a phase, converts them to
    DTOs, and parses stored feedback JSON into template-ready summaries.
    Calculates remaining time for async submission types.

    Returns:
        PhaseSubmissionContext with submissions and feedback keyed by
        requirement ID.
    """
    repo = SubmissionRepository(db)
    raw_submissions = await repo.get_by_user_and_phase(user_id, phase_id)

    submissions_by_req: dict[str, SubmissionData] = {}
    feedback_by_req: dict[str, dict[str, object]] = {}

    for sub in raw_submissions:
        sub_data = to_submission_data(sub)
        submissions_by_req[sub.requirement_id] = sub_data

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

                feedback_by_req[sub.requirement_id] = {
                    "tasks": tasks,
                    "passed": passed,
                }
            except (json.JSONDecodeError, TypeError):
                span = trace.get_current_span()
                span.add_event(
                    "feedback_parse_failed",
                    {"requirement_id": sub.requirement_id},
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


class DuplicatePrError(Exception):
    """Raised when the same PR URL is used for a different requirement."""

    def __init__(self, message: str, conflicting_requirement_id: str):
        super().__init__(message)
        self.conflicting_requirement_id = conflicting_requirement_id


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
    """Result of creating or reusing a verification job."""

    job: VerificationJob
    created: bool


async def _check_submission_preconditions(
    session_maker: async_sessionmaker[AsyncSession],
    user_id: int,
    requirement_id: str,
    github_username: str | None,
    submitted_value: str | None = None,
) -> _PreValidationContext:
    """Shared pre-validation checks for submission paths.

    Validates requirement existence, already-validated status, phase gating,
    PR uniqueness, and GitHub username requirement.

    Opens a short-lived DB session for reads, then releases it before returning.
    """
    requirement = get_requirement_by_id(requirement_id)
    if not requirement:
        raise RequirementNotFoundError(f"Requirement not found: {requirement_id}")

    phase_id = get_phase_id_for_requirement(requirement_id)
    if phase_id is None:
        raise RequirementNotFoundError(
            f"Requirement not mapped to a phase: {requirement_id}"
        )

    async with session_maker() as read_session:
        submission_repo = SubmissionRepository(read_session)

        existing = await submission_repo.get_by_user_and_requirement(
            user_id, requirement_id
        )
        if existing is not None and existing.is_validated:
            raise AlreadyValidatedError("You have already completed this requirement.")

        # Sequential phase gating
        prereq_phase = get_prerequisite_phase(phase_id)
        if prereq_phase is not None:
            prereq_req_ids = get_requirement_ids_for_phase(prereq_phase)
            if prereq_req_ids:
                all_done = await submission_repo.are_all_requirements_validated(
                    user_id, prereq_req_ids
                )
                if not all_done:
                    raise PriorPhaseNotCompleteError(
                        f"You must complete all Phase {prereq_phase} "
                        f"verifications before submitting for Phase {phase_id}.",
                        prerequisite_phase=prereq_phase,
                    )

        # PR uniqueness: same PR URL cannot be reused for a different
        # requirement within the same phase.
        if submitted_value and requirement.submission_type == SubmissionType.PR_REVIEW:
            conflicting = await submission_repo.find_validated_by_value_in_phase(
                user_id, phase_id, submitted_value, requirement_id
            )
            if conflicting:
                raise DuplicatePrError(
                    "This PR was already used for a different requirement. "
                    "Each task must have its own PR — follow the branching "
                    "workflow in the journal-starter README.",
                    conflicting_requirement_id=conflicting,
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
            SubmissionType.CI_STATUS,
            SubmissionType.DEVOPS_ANALYSIS,
            SubmissionType.SECURITY_SCANNING,
            SubmissionType.PR_REVIEW,
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
) -> VerificationJobSubmission:
    """Validate request preconditions and create or reuse an active job."""
    ctx = await _check_submission_preconditions(
        session_maker,
        user_id,
        requirement_id,
        github_username,
        submitted_value,
    )

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
