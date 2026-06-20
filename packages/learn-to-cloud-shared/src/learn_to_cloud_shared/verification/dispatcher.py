"""Hands-on verification orchestration module.

This module provides the central orchestration for Phase 0 through Phase 6
hands-on verification:
- Routes submissions to appropriate validators
- Supports GitHub profile, profile README, repo fork, CTF token, networking token,
  code analysis, and evidence URL validations

Phase requirements are defined in phase_requirements.py.

EXTENSIBILITY:
To add a new verification type:
1. Add the SubmissionType enum value in models.py
2. Add optional fields to HandsOnRequirement in schemas.py if needed
3. Create a validator function (here or in a new module):
   - async def validate_<type>(url: str, ...) -> ValidationResult
4. Add routing case in validate_submission() below

For GitHub-specific validations, see github_profile.py
For CTF token validation, see ctf.py
For CI-based code verification, see ci_status.py
For phase requirements, see requirements.py
"""

import time
from collections.abc import Awaitable, Callable

from opentelemetry import metrics, trace

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.deployed_api import validate_deployed_api
from learn_to_cloud_shared.verification.devops_analysis import run_devops_workflow
from learn_to_cloud_shared.verification.github_profile import (
    validate_github_profile,
    validate_profile_readme,
    validate_repo_fork,
)
from learn_to_cloud_shared.verification.repo_utils import (
    VerificationError,
    resolve_repository,
)
from learn_to_cloud_shared.verification.security_scanning import (
    validate_security_scanning,
)
from learn_to_cloud_shared.verification.token_base import (
    verify_ctf_token,
    verify_networking_token,
)

_meter = metrics.get_meter("learn_to_cloud")
_VERIFICATION_COUNTER = _meter.create_counter(
    name="verification.attempt",
    description="Number of hands-on verification attempts",
    unit="{attempt}",
)
_VERIFICATION_DURATION = _meter.create_histogram(
    name="verification.duration",
    description="Time taken to complete a verification attempt",
    unit="s",
)


async def validate_submission(
    requirement: HandsOnRequirement,
    submitted_value: str,
    expected_username: str | None = None,
) -> ValidationResult:
    """Validate a submission based on its requirement type.

    This is the main entry point for validating any hands-on submission.
    It routes to the appropriate validator based on the submission type.

    Args:
        requirement: The requirement being validated
        submitted_value: The value submitted by the user
            (URL, token, or challenge response)
        expected_username: The expected GitHub username
            (required for GitHub-based validations)
    """
    start = time.monotonic()
    sub_type = requirement.submission_type
    submission_type = sub_type.value if sub_type else "unknown"
    result_attr = "error"

    try:
        validation_result = await _dispatch_validation(
            requirement, submitted_value, expected_username
        )
        result_attr = "pass" if validation_result.is_valid else "fail"
        return validation_result
    except (
        TimeoutError,
        VerificationError,
    ) as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.add_event(
            "verification_failed",
            {"submission_type": submission_type, "error_type": type(e).__name__},
        )
        return ValidationResult(
            is_valid=False,
            message="Verification failed. Please try again later.",
            verification_completed=False,
        )
    except Exception as e:
        span = trace.get_current_span()
        span.record_exception(e)
        span.add_event(
            "verification_unexpected_error",
            {"submission_type": submission_type, "error_type": type(e).__name__},
        )
        return ValidationResult(
            is_valid=False,
            message="Verification failed. Please try again later.",
            verification_completed=False,
        )
    finally:
        elapsed = time.monotonic() - start
        attrs = {"submission_type": submission_type, "result": result_attr}
        _VERIFICATION_COUNTER.add(1, attrs)
        _VERIFICATION_DURATION.record(elapsed, attrs)


_USERNAME_NOT_REQUIRED: frozenset[SubmissionType] = frozenset(
    {SubmissionType.DEPLOYED_API}
)


# Submission types that finish in well under a second (one GitHub API call
# or a constant-time token compare) and can run inside the FastAPI request
# instead of going through Durable Functions.  Phase 3+ types involve LLM
# grading, fan-out, or external probes with retries and stay on the async
# Durable path.
SYNC_VERIFIABLE_SUBMISSION_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.GITHUB_PROFILE,
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.CTF_TOKEN,
        SubmissionType.NETWORKING_TOKEN,
    }
)


def is_sync_verifiable(submission_type: SubmissionType) -> bool:
    """Return True if the submission type runs synchronously in FastAPI."""
    return submission_type in SYNC_VERIFIABLE_SUBMISSION_TYPES


# Submission types whose persisted value is a server-derived GitHub repo URL
# (``https://github.com/<user>/<fork>``). Their owner/repo identity can be
# parsed straight from the validated submission value -- see
# ``repo_utils.resolve_repository``.
_REPO_BACKED_SUBMISSION_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    }
)


def is_repo_backed(submission_type: SubmissionType) -> bool:
    """Return True if the submission value is a server-derived GitHub repo URL."""
    return submission_type in _REPO_BACKED_SUBMISSION_TYPES


async def _dispatch_validation(
    requirement: HandsOnRequirement,
    submitted_value: str,
    expected_username: str | None = None,
) -> ValidationResult:
    """Route to the appropriate validator based on submission type."""
    # Most submission types require a GitHub username — check once up front.
    if (
        requirement.submission_type not in _USERNAME_NOT_REQUIRED
        and not expected_username
    ):
        return ValidationResult(
            is_valid=False,
            message="GitHub username is required for this verification",
            username_match=False,
        )

    # Narrow type: after the guard above, username is str for all branches
    # that require it. DEPLOYED_API never reads it.
    username: str = expected_username or ""

    if requirement.submission_type == SubmissionType.GITHUB_PROFILE:
        return await validate_github_profile(submitted_value, username)

    elif requirement.submission_type == SubmissionType.PROFILE_README:
        return await validate_profile_readme(submitted_value, username)

    elif requirement.submission_type == SubmissionType.REPO_FORK:
        if not requirement.required_repo:
            return ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=False,
                repo_exists=False,
            )
        return await validate_repo_fork(
            submitted_value, username, requirement.required_repo
        )

    elif requirement.submission_type == SubmissionType.CTF_TOKEN:
        return verify_ctf_token(submitted_value, username)

    elif requirement.submission_type == SubmissionType.NETWORKING_TOKEN:
        return verify_networking_token(submitted_value, username)

    elif requirement.submission_type == SubmissionType.JOURNAL_API_VERIFIER:
        return await _verify_repo_backed(submitted_value, verify_ci_status)

    elif requirement.submission_type == SubmissionType.DEVOPS_ANALYSIS:
        return await _verify_repo_backed(submitted_value, run_devops_workflow)

    elif requirement.submission_type == SubmissionType.DEPLOYED_API:
        return await validate_deployed_api(submitted_value)

    elif requirement.submission_type == SubmissionType.SECURITY_SCANNING:
        return await _verify_repo_backed(submitted_value, validate_security_scanning)

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )


async def _verify_repo_backed(
    submitted_value: str,
    verifier: Callable[[str, str], Awaitable[ValidationResult]],
) -> ValidationResult:
    """Resolve the repo identity from the validated submission value and verify.

    The owner/repo come straight from the server-derived, DB-validated
    submission URL, so no ownership or fork-name re-check is needed here (see
    ``resolve_repository``). A malformed URL surfaces as a ``ValidationResult``.
    """
    repo = resolve_repository(submitted_value)
    if isinstance(repo, ValidationResult):
        return repo
    return await verifier(repo.owner, repo.repo)
