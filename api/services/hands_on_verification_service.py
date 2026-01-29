"""Hands-on verification orchestration module.

This module provides the central orchestration for Phase 0, Phase 1, and Phase 2
hands-on verification:
- Routes submissions to appropriate validators
- Supports GitHub profile, profile README, repo fork, CTF token, and code analysis

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

from models import SubmissionType
from schemas import HandsOnRequirement, ValidationResult
from services.copilot_verification_service import analyze_repository_code
from services.ctf_service import verify_ctf_token
from services.github_hands_on_verification_service import (
    validate_github_profile,
    validate_profile_readme,
    validate_repo_fork,
)
from services.phase_requirements_service import (
    HANDS_ON_REQUIREMENTS,
    get_requirement_by_id,
    get_requirements_for_phase,
)

# Re-export for backwards compatibility
__all__ = [
    "HANDS_ON_REQUIREMENTS",
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
    ctf_result = verify_ctf_token(token, expected_username)

    return ValidationResult(
        is_valid=ctf_result.is_valid,
        message=ctf_result.message,
        username_match=ctf_result.is_valid,
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
        return await validate_github_profile(submitted_value, expected_username)

    elif requirement.submission_type == SubmissionType.PROFILE_README:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for profile README validation",
                username_match=False,
                repo_exists=False,
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

    elif requirement.submission_type == SubmissionType.CODE_ANALYSIS:
        if not expected_username:
            return ValidationResult(
                is_valid=False,
                message="GitHub username is required for code analysis",
                username_match=False,
            )
        return await analyze_repository_code(submitted_value, expected_username)

    else:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )
