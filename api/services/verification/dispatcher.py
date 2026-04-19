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

import logging
import time

from circuitbreaker import CircuitBreakerError

from core.llm_client import LLMClientError
from core.metrics import VERIFICATION_COUNTER, VERIFICATION_DURATION
from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.verification.ci_status import verify_ci_status
from services.verification.ctf import verify_ctf_token
from services.verification.deployed_api import validate_deployed_api
from services.verification.devops_analysis import run_devops_workflow
from services.verification.github_profile import (
    validate_github_profile,
    validate_profile_readme,
    validate_repo_fork,
)
from services.verification.llm_base import VerificationError, validate_repo_url
from services.verification.networking_lab import verify_networking_token
from services.verification.pull_request import validate_pr
from services.verification.security_scanning import validate_security_scanning
from services.verification.url_derivation import fork_name_from_required_repo

logger = logging.getLogger(__name__)


def validate_ctf_token_submission(
    token: str, expected_username: str
) -> ValidationResult:
    """Validate a CTF token submission.

    Args:
        token: The base64-encoded CTF completion token
        expected_username: The expected GitHub username from OAuth

    Returns:
        ValidationResult with verification status
    """
    ctf_result = verify_ctf_token(token, expected_username)

    return ValidationResult(
        is_valid=ctf_result.is_valid,
        message=ctf_result.message,
        username_match=ctf_result.is_valid,
        verification_completed=ctf_result.verification_completed,
    )


def validate_networking_token_submission(
    token: str, expected_username: str
) -> ValidationResult:
    """Validate a Networking Lab token submission.

    Args:
        token: The base64-encoded Networking Lab completion token
        expected_username: The expected GitHub username from OAuth

    Returns:
        ValidationResult with verification status and cloud_provider
    """
    result = verify_networking_token(token, expected_username)

    # Extract provider from challenge_type (e.g. "networking-lab-azure" -> "azure")
    cloud_provider = None
    if result.is_valid and result.challenge_type:
        cloud_provider = result.challenge_type.removeprefix("networking-lab-")

    return ValidationResult(
        is_valid=result.is_valid,
        message=result.message,
        username_match=result.is_valid,
        verification_completed=result.verification_completed,
        cloud_provider=cloud_provider,
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
        CircuitBreakerError,
        TimeoutError,
        VerificationError,
        LLMClientError,
    ) as e:
        logger.error(
            "verification.failed",
            extra={
                "submission_type": submission_type,
                "error_type": type(e).__name__,
                "error": str(e),
            },
        )
        return ValidationResult(
            is_valid=False,
            message="Verification failed. Please try again later.",
            verification_completed=False,
        )
    except Exception as e:
        logger.exception(
            "verification.unexpected_error",
            extra={
                "submission_type": submission_type,
                "error_type": type(e).__name__,
            },
        )
        return ValidationResult(
            is_valid=False,
            message="Verification failed. Please try again later.",
            verification_completed=False,
        )
    finally:
        elapsed = time.monotonic() - start
        attrs = {"submission_type": submission_type, "result": result_attr}
        VERIFICATION_COUNTER.add(1, attrs)
        VERIFICATION_DURATION.record(elapsed, attrs)


_USERNAME_NOT_REQUIRED: frozenset[SubmissionType] = frozenset(
    {SubmissionType.DEPLOYED_API}
)


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
        return validate_ctf_token_submission(submitted_value, username)

    elif requirement.submission_type == SubmissionType.NETWORKING_TOKEN:
        return validate_networking_token_submission(submitted_value, username)

    elif requirement.submission_type == SubmissionType.PR_REVIEW:
        return await validate_pr(submitted_value, requirement)

    elif requirement.submission_type == SubmissionType.CI_STATUS:
        expected_name = _expected_fork_name(requirement)
        result = validate_repo_url(submitted_value, username, expected_name)
        if isinstance(result, ValidationResult):
            return result
        owner, repo = result
        return await verify_ci_status(owner, repo)

    elif requirement.submission_type == SubmissionType.DEVOPS_ANALYSIS:
        expected_name = _expected_fork_name(requirement)
        result = validate_repo_url(submitted_value, username, expected_name)
        if isinstance(result, ValidationResult):
            return result
        owner, repo = result
        return await run_devops_workflow(owner, repo)

    elif requirement.submission_type == SubmissionType.DEPLOYED_API:
        return await validate_deployed_api(submitted_value)

    elif requirement.submission_type == SubmissionType.SECURITY_SCANNING:
        expected_name = _expected_fork_name(requirement)
        result = validate_repo_url(submitted_value, username, expected_name)
        if isinstance(result, ValidationResult):
            return result
        owner, repo = result
        return await validate_security_scanning(owner, repo)

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )


def _expected_fork_name(requirement: HandsOnRequirement) -> str | None:
    """Return the expected fork repo name from ``required_repo``, if set."""
    if not requirement.required_repo:
        return None
    try:
        return fork_name_from_required_repo(requirement.required_repo)
    except ValueError:
        return None
