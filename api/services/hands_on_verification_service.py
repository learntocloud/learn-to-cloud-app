"""Hands-on verification orchestration module.

This module provides the central orchestration for Phase 0 through Phase 6
hands-on verification:
- Routes submissions to appropriate validators
- Supports GitHub profile, profile README, repo fork, CTF token, networking token,
  journal API response, code analysis, and evidence URL validations

Phase requirements are defined in phase_requirements.py.

EXTENSIBILITY:
To add a new verification type:
1. Add the SubmissionType enum value in models.py
2. Add optional fields to HandsOnRequirement in schemas.py if needed
3. Create a validator function (here or in a new module):
   - async def validate_<type>(url: str, ...) -> ValidationResult
4. Add routing case in validate_submission() below

For GitHub-specific validations, see github_hands_on_verification.py
For CTF token validation, see ctf_service.py
For AI-powered code analysis, see copilot_verification_service.py
For phase requirements, see phase_requirements.py
"""

from urllib.parse import urlparse

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.phase_requirements_service import (
    get_requirement_by_id,
    get_requirements_for_phase,
)

__all__ = [
    "get_requirement_by_id",
    "get_requirements_for_phase",
    "validate_submission",
    "ValidationResult",
]


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
    from services.ctf_service import verify_ctf_token

    ctf_result = verify_ctf_token(token, expected_username)

    return ValidationResult(
        is_valid=ctf_result.is_valid,
        message=ctf_result.message,
        username_match=ctf_result.is_valid,
    )


def validate_networking_token_submission(
    token: str, expected_username: str
) -> ValidationResult:
    """Validate a Networking Lab token submission.

    Args:
        token: The base64-encoded Networking Lab completion token
        expected_username: The expected GitHub username from OAuth

    Returns:
        ValidationResult with verification status
    """
    from services.networking_lab_service import verify_networking_token

    result = verify_networking_token(token, expected_username)

    return ValidationResult(
        is_valid=result.is_valid,
        message=result.message,
        username_match=result.is_valid,
    )


def _is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_evidence_url_submission(submitted_value: str) -> ValidationResult:
    """Validate a generic evidence URL submission."""
    value = submitted_value.strip()
    if not value:
        return ValidationResult(
            is_valid=False,
            message="Please submit a valid URL.",
        )

    if not _is_valid_url(value):
        return ValidationResult(
            is_valid=False,
            message="Please submit a valid http(s) URL.",
        )

    return ValidationResult(
        is_valid=True,
        message="Submission verified.",
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
    if requirement.submission_type == SubmissionType.GITHUB_PROFILE:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for profile validation",
                username_match=False,
                repo_exists=False,
            )
        from services.github_hands_on_verification_service import (
            validate_github_profile,
        )

        return await validate_github_profile(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.PROFILE_README:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for profile README validation",
                username_match=False,
                repo_exists=False,
            )
        from services.github_hands_on_verification_service import (
            validate_profile_readme,
        )

        return await validate_profile_readme(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.REPO_FORK:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for repository fork validation",
                username_match=False,
                repo_exists=False,
            )
        if not requirement.required_repo:
            return ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=False,
                repo_exists=False,
            )
        from services.github_hands_on_verification_service import (
            validate_repo_fork,
        )

        return await validate_repo_fork(
            submitted_value, expected_username, requirement.required_repo
        )

    elif requirement.submission_type == SubmissionType.CTF_TOKEN:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for CTF token validation",
                username_match=False,
                repo_exists=False,
            )
        return validate_ctf_token_submission(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.NETWORKING_TOKEN:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for networking token validation",
                username_match=False,
                repo_exists=False,
            )
        return validate_networking_token_submission(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.JOURNAL_API_RESPONSE:
        from services.journal_verification_service import (
            validate_journal_api_response,
        )

        return validate_journal_api_response(submitted_value)

    elif requirement.submission_type == SubmissionType.CODE_ANALYSIS:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for code analysis",
                username_match=False,
            )
        from services.copilot_verification_service import analyze_repository_code

        return await analyze_repository_code(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.DEVOPS_ANALYSIS:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for DevOps analysis",
                username_match=False,
            )
        from services.devops_verification_service import analyze_devops_repository

        return await analyze_devops_repository(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.DEPLOYED_API:
        from services.deployed_api_verification_service import validate_deployed_api

        return await validate_deployed_api(submitted_value)

    elif requirement.submission_type == SubmissionType.SECURITY_SCANNING:
        return validate_evidence_url_submission(submitted_value)

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )
