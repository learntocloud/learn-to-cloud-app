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
4. Register a ValidatorDescriptor for it in _VALIDATOR_REGISTRY below:
   declare its adapter callable, execution mode (INLINE vs BACKGROUND),
   whether it needs a GitHub username, and whether it is repo-backed.

For GitHub-specific validations, see github_profile.py
For CTF token validation, see ctf.py
For CI-based code verification, see ci_status.py
For phase requirements, see requirements.py
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from opentelemetry import metrics, trace

from learn_to_cloud_shared.models import ExecutionMode, SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement, ValidationResult
from learn_to_cloud_shared.verification.career_reflection import (
    validate_career_reflection,
)
from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.deployed_api import validate_deployed_api
from learn_to_cloud_shared.verification.deployment_architecture import (
    validate_deployment_architecture,
)
from learn_to_cloud_shared.verification.devops_analysis import run_devops_workflow
from learn_to_cloud_shared.verification.github_profile import (
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
        attrs = {"submission_type": submission_type, "result": result_attr}
        _VERIFICATION_COUNTER.add(1, attrs)


# Uniform call shape for every validator, regardless of how the underlying
# function is written. Adapters below absorb the per-validator differences
# (sync token functions, the repo_fork config path, deployed_api taking only
# a value, and repo-backed owner/repo resolution).
ValidatorAdapter = Callable[
    [HandsOnRequirement, str, str],
    Awaitable[ValidationResult],
]


@dataclass(frozen=True)
class ValidatorDescriptor:
    """Everything the dispatcher needs to know about one submission type.

    Collapses what used to be four separate type-keyed structures (the
    if/elif routing chain plus three frozensets) into a single home, so a
    new verification type is declared in exactly one place.
    """

    adapter: ValidatorAdapter
    # Where the check runs: INLINE finishes in the request, BACKGROUND goes
    # through Durable Functions. This is a property of the work itself, so it
    # lives with the validator rather than in requirement content.
    execution_mode: ExecutionMode
    # Whether a GitHub username is required before the validator runs.
    requires_username: bool
    # Whether the submitted value is a server-derived GitHub repo URL whose
    # owner/repo identity can be parsed straight from it.
    repo_backed: bool


async def _adapt_profile_readme(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return await validate_profile_readme(submitted_value, username)


async def _adapt_repo_fork(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
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


async def _adapt_ctf_token(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return verify_ctf_token(submitted_value, username)


async def _adapt_networking_token(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return verify_networking_token(submitted_value, username)


async def _adapt_deployed_api(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return await validate_deployed_api(submitted_value)


async def _adapt_journal_api_verifier(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return await _verify_repo_backed(submitted_value, verify_ci_status)


async def _adapt_devops_analysis(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return await _verify_repo_backed(submitted_value, run_devops_workflow)


async def _adapt_security_scanning(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return await _verify_repo_backed(submitted_value, validate_security_scanning)


async def _adapt_career_reflection(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return validate_career_reflection(submitted_value)


async def _adapt_deployment_architecture(
    requirement: HandsOnRequirement, submitted_value: str, username: str
) -> ValidationResult:
    return await validate_deployment_architecture(
        requirement, submitted_value, username
    )


# Single source of truth: each active submission type maps to one descriptor.
# Lookups use ``.get(...)`` so an unregistered type surfaces as the explicit
# "Unknown submission type" result instead of raising.
_VALIDATOR_REGISTRY: dict[SubmissionType, ValidatorDescriptor] = {
    SubmissionType.PROFILE_README: ValidatorDescriptor(
        adapter=_adapt_profile_readme,
        execution_mode=ExecutionMode.INLINE,
        requires_username=True,
        repo_backed=False,
    ),
    SubmissionType.REPO_FORK: ValidatorDescriptor(
        adapter=_adapt_repo_fork,
        execution_mode=ExecutionMode.INLINE,
        requires_username=True,
        repo_backed=False,
    ),
    SubmissionType.CTF_TOKEN: ValidatorDescriptor(
        adapter=_adapt_ctf_token,
        execution_mode=ExecutionMode.INLINE,
        requires_username=True,
        repo_backed=False,
    ),
    SubmissionType.NETWORKING_TOKEN: ValidatorDescriptor(
        adapter=_adapt_networking_token,
        execution_mode=ExecutionMode.INLINE,
        requires_username=True,
        repo_backed=False,
    ),
    SubmissionType.JOURNAL_API_VERIFIER: ValidatorDescriptor(
        adapter=_adapt_journal_api_verifier,
        execution_mode=ExecutionMode.BACKGROUND,
        requires_username=True,
        repo_backed=True,
    ),
    SubmissionType.DEVOPS_ANALYSIS: ValidatorDescriptor(
        adapter=_adapt_devops_analysis,
        execution_mode=ExecutionMode.BACKGROUND,
        requires_username=True,
        repo_backed=True,
    ),
    SubmissionType.DEPLOYED_API: ValidatorDescriptor(
        adapter=_adapt_deployed_api,
        execution_mode=ExecutionMode.BACKGROUND,
        requires_username=False,
        repo_backed=False,
    ),
    SubmissionType.SECURITY_SCANNING: ValidatorDescriptor(
        adapter=_adapt_security_scanning,
        execution_mode=ExecutionMode.BACKGROUND,
        requires_username=True,
        repo_backed=True,
    ),
    SubmissionType.CAREER_REFLECTION: ValidatorDescriptor(
        adapter=_adapt_career_reflection,
        execution_mode=ExecutionMode.BACKGROUND,
        requires_username=False,
        repo_backed=False,
    ),
    SubmissionType.DEPLOYMENT_ARCHITECTURE: ValidatorDescriptor(
        adapter=_adapt_deployment_architecture,
        execution_mode=ExecutionMode.BACKGROUND,
        requires_username=True,
        repo_backed=False,
    ),
}


def descriptor_for(
    submission_type: SubmissionType,
) -> ValidatorDescriptor | None:
    """Return the descriptor for a submission type, or None if unsupported."""
    return _VALIDATOR_REGISTRY.get(submission_type)


def execution_mode_for(
    submission_type: SubmissionType,
) -> ExecutionMode | None:
    """Return the execution mode for a submission type, or None if unsupported."""
    descriptor = _VALIDATOR_REGISTRY.get(submission_type)
    return descriptor.execution_mode if descriptor is not None else None


def is_inline(submission_type: SubmissionType) -> bool:
    """Return True if the submission type runs inline in the FastAPI request."""
    return execution_mode_for(submission_type) is ExecutionMode.INLINE


def is_repo_backed(submission_type: SubmissionType) -> bool:
    """Return True if the submission value is a server-derived GitHub repo URL."""
    descriptor = _VALIDATOR_REGISTRY.get(submission_type)
    return descriptor.repo_backed if descriptor is not None else False


async def _dispatch_validation(
    requirement: HandsOnRequirement,
    submitted_value: str,
    expected_username: str | None = None,
) -> ValidationResult:
    """Route to the appropriate validator based on submission type."""
    descriptor = _VALIDATOR_REGISTRY.get(requirement.submission_type)
    if descriptor is None:
        return ValidationResult(
            is_valid=False,
            message=f"Unknown submission type: {requirement.submission_type}",
            username_match=False,
            repo_exists=False,
        )

    # Most submission types require a GitHub username — check once up front.
    if descriptor.requires_username and not expected_username:
        return ValidationResult(
            is_valid=False,
            message="GitHub username is required for this verification",
            username_match=False,
        )

    # Narrow type: after the guard above, username is str for all branches
    # that require it. Validators that don't need it ignore the value.
    username: str = expected_username or ""
    return await descriptor.adapter(requirement, submitted_value, username)


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
