"""Per-submission-type validator registry and routing.

Runs inside the Durable Function verify step. ``validate_submission`` is
the single entry point: it looks up the submission type in
``_VALIDATOR_REGISTRY``, enforces the GitHub-username guard, dispatches to
the matching validator through a uniform adapter, records verification
metrics and spans, and returns a ``ValidationResult``. Repo- and
profile-based validators receive the ``GitHubTarget`` constructed upstream
(see ``submission_derivation.build_target``) rather than parsing a URL.

Supported types include GitHub profile, profile README, repo fork, CTF
token, networking token, deployed API, DevOps analysis, security
scanning, career reflection, and deployment architecture.

To add a new verification type:
1. Add the ``SubmissionType`` enum value in models.py.
2. Add a typed ``type_config`` to ``schemas.py`` if it needs one.
3. Create a validator function (here or in a new module).
4. Register a ``ValidatorDescriptor`` in ``_VALIDATOR_REGISTRY`` below,
   declaring its adapter and whether it needs a GitHub username.
5. If it verifies a GitHub location, extend ``build_target`` so its
   ``GitHubTarget`` is constructed.

For GitHub-specific validations, see github_profile.py.
For CTF and networking token validation, see token_base.py.
For CI-based code verification, see ci_status.py.
For requirement definitions, see requirements.py.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from opentelemetry import metrics, trace

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.models import SubmissionType
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
from learn_to_cloud_shared.verification.errors import VerificationError
from learn_to_cloud_shared.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
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
    target: GitHubTarget | None = None,
    expected_username: str | None = None,
) -> ValidationResult:
    """Validate a submission based on its requirement type.

    This is the main entry point for validating any hands-on submission.
    It routes to the appropriate validator based on the submission type.

    Args:
        requirement: The requirement being validated
        submitted_value: The value submitted by the user
            (URL, token, or challenge response)
        target: The GitHub location this requirement verifies against,
            constructed upstream. ``None`` for free-form types.
        expected_username: The expected GitHub username
            (required for GitHub-based validations)
    """
    sub_type = requirement.submission_type
    submission_type = sub_type.value if sub_type else "unknown"
    result_attr = "error"

    try:
        validation_result = await _dispatch_validation(
            requirement, submitted_value, target, expected_username
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
# (sync token functions, deployed_api taking only a value, and repo/profile
# validators taking the constructed GitHubTarget).
ValidatorAdapter = Callable[
    [HandsOnRequirement, "GitHubTarget | None", str, str],
    Awaitable[ValidationResult],
]

_MISSING_TARGET = ValidationResult(
    is_valid=False,
    message="Requirement configuration error: could not resolve GitHub target",
    username_match=True,
    repo_exists=False,
)


@dataclass(frozen=True)
class ValidatorDescriptor:
    """Everything the dispatcher needs to know about one submission type.

    Collapses the type-keyed routing into a single home, so a new
    verification type is declared in exactly one place.
    """

    adapter: ValidatorAdapter
    # Whether a GitHub username is required before the validator runs.
    requires_username: bool


async def _adapt_profile_readme(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    if target is None:
        return _MISSING_TARGET
    return await validate_profile_readme(target)


async def _adapt_repo_fork(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    if target is None:
        return _MISSING_TARGET
    return await validate_repo_fork(target)


async def _adapt_ctf_token(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return verify_ctf_token(submitted_value, username)


async def _adapt_networking_token(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return verify_networking_token(submitted_value, username)


async def _adapt_deployed_api(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return await validate_deployed_api(submitted_value)


async def _adapt_journal_api_verifier(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return await _verify_repo_backed(target, verify_ci_status)


async def _adapt_devops_analysis(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return await _verify_repo_backed(target, run_devops_workflow)


async def _adapt_security_scanning(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return await _verify_repo_backed(target, validate_security_scanning)


async def _adapt_career_reflection(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return validate_career_reflection(submitted_value)


async def _adapt_deployment_architecture(
    requirement: HandsOnRequirement,
    target: GitHubTarget | None,
    submitted_value: str,
    username: str,
) -> ValidationResult:
    return await validate_deployment_architecture(requirement, submitted_value, target)


# Single source of truth: each active submission type maps to one descriptor.
# Lookups use ``.get(...)`` so an unregistered type surfaces as the explicit
# "Unknown submission type" result instead of raising.
_VALIDATOR_REGISTRY: dict[SubmissionType, ValidatorDescriptor] = {
    SubmissionType.PROFILE_README: ValidatorDescriptor(
        adapter=_adapt_profile_readme,
        requires_username=True,
    ),
    SubmissionType.REPO_FORK: ValidatorDescriptor(
        adapter=_adapt_repo_fork,
        requires_username=True,
    ),
    SubmissionType.CTF_TOKEN: ValidatorDescriptor(
        adapter=_adapt_ctf_token,
        requires_username=True,
    ),
    SubmissionType.NETWORKING_TOKEN: ValidatorDescriptor(
        adapter=_adapt_networking_token,
        requires_username=True,
    ),
    SubmissionType.JOURNAL_API_VERIFIER: ValidatorDescriptor(
        adapter=_adapt_journal_api_verifier,
        requires_username=True,
    ),
    SubmissionType.DEVOPS_ANALYSIS: ValidatorDescriptor(
        adapter=_adapt_devops_analysis,
        requires_username=True,
    ),
    SubmissionType.DEPLOYED_API: ValidatorDescriptor(
        adapter=_adapt_deployed_api,
        requires_username=False,
    ),
    SubmissionType.SECURITY_SCANNING: ValidatorDescriptor(
        adapter=_adapt_security_scanning,
        requires_username=True,
    ),
    SubmissionType.CAREER_REFLECTION: ValidatorDescriptor(
        adapter=_adapt_career_reflection,
        requires_username=False,
    ),
    SubmissionType.DEPLOYMENT_ARCHITECTURE: ValidatorDescriptor(
        adapter=_adapt_deployment_architecture,
        requires_username=True,
    ),
}


def descriptor_for(
    submission_type: SubmissionType,
) -> ValidatorDescriptor | None:
    """Return the descriptor for a submission type, or None if unsupported."""
    return _VALIDATOR_REGISTRY.get(submission_type)


async def _dispatch_validation(
    requirement: HandsOnRequirement,
    submitted_value: str,
    target: GitHubTarget | None = None,
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
    return await descriptor.adapter(requirement, target, submitted_value, username)


async def _verify_repo_backed(
    target: GitHubTarget | None,
    verifier: Callable[[str, str], Awaitable[ValidationResult]],
) -> ValidationResult:
    """Run a repo verifier against the constructed target's owner/repo.

    The owner/repo come from the target built from the learner's username plus
    the requirement's ``required_repo``, so no ownership or fork-name re-check
    is needed. A missing target surfaces as a configuration failure.
    """
    if target is None or not target.repo:
        return ValidationResult(
            is_valid=False,
            message="Requirement configuration error: missing required_repo",
            username_match=True,
            repo_exists=False,
        )
    return await verifier(target.owner, target.repo)
