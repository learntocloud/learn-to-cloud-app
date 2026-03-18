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
For AI-powered code analysis, see code_analysis.py
For phase requirements, see requirements.py
"""

import logging
import time

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult

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
    from services.verification.ctf import verify_ctf_token

    ctf_result = verify_ctf_token(token, expected_username)

    return ValidationResult(
        is_valid=ctf_result.is_valid,
        message=ctf_result.message,
        username_match=ctf_result.is_valid,
        server_error=ctf_result.server_error,
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
    from services.verification.networking_lab import verify_networking_token

    result = verify_networking_token(token, expected_username)

    # Extract provider from challenge_type (e.g. "networking-lab-azure" -> "azure")
    cloud_provider = None
    if result.is_valid and result.challenge_type:
        cloud_provider = result.challenge_type.removeprefix("networking-lab-")

    return ValidationResult(
        is_valid=result.is_valid,
        message=result.message,
        username_match=result.is_valid,
        server_error=result.server_error,
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
    from core.metrics import VERIFICATION_COUNTER, VERIFICATION_DURATION

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
        from services.verification.github_profile import validate_github_profile

        return await validate_github_profile(submitted_value, username)

    elif requirement.submission_type == SubmissionType.PROFILE_README:
        from services.verification.github_profile import validate_profile_readme

        return await validate_profile_readme(submitted_value, username)

    elif requirement.submission_type == SubmissionType.REPO_FORK:
        if not requirement.required_repo:
            return ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=False,
                repo_exists=False,
            )
        from services.verification.github_profile import validate_repo_fork

        return await validate_repo_fork(
            submitted_value, username, requirement.required_repo
        )

    elif requirement.submission_type == SubmissionType.CTF_TOKEN:
        return validate_ctf_token_submission(submitted_value, username)

    elif requirement.submission_type == SubmissionType.NETWORKING_TOKEN:
        return validate_networking_token_submission(submitted_value, username)

    elif requirement.submission_type == SubmissionType.PR_REVIEW:
        from services.verification.pull_request import validate_pr

        return await validate_pr(submitted_value, username, requirement)

    elif requirement.submission_type == SubmissionType.CODE_ANALYSIS:
        from services.verification.code_analysis import analyze_repository_code

        return await analyze_repository_code(submitted_value, username)

    elif requirement.submission_type == SubmissionType.DEVOPS_ANALYSIS:
        from services.verification.devops_analysis import analyze_devops_repository

        return await analyze_devops_repository(submitted_value, username)

    elif requirement.submission_type == SubmissionType.DEPLOYED_API:
        from services.verification.deployed_api import validate_deployed_api

        return await validate_deployed_api(submitted_value)

    elif requirement.submission_type == SubmissionType.SECURITY_SCANNING:
        from services.verification.security_scanning import validate_security_scanning

        return await validate_security_scanning(submitted_value, username)

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )
