"""Display models and preparation for verification forms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from learn_to_cloud_shared.schemas import (
    CareerReflectionQuestion,
    CareerReflectionRequirement,
    CtfTokenRequirement,
    DeployedApiRequirement,
    HandsOnRequirement,
    NetworkingTokenRequirement,
    SubmissionData,
)
from learn_to_cloud_shared.submission_derivation import (
    derive_submission_value,
    is_derivable,
)

from learn_to_cloud.verification_forms import (
    MAX_REFLECTION_ANSWER_LENGTH,
    verification_submit_action,
)


@dataclass(frozen=True, slots=True)
class DerivedFormContext:
    """Rendering data for a server-derived URL form."""

    action: str
    url: str
    kind: Literal["derived"] = field(init=False, default="derived")
    template: str = field(
        init=False,
        default="partials/verification_forms/derived.html",
    )


@dataclass(frozen=True, slots=True)
class TokenFormContext:
    """Rendering data for a completion-token form."""

    action: str
    placeholder: str
    min_length: int
    max_length: int
    kind: Literal["token"] = field(init=False, default="token")
    template: str = field(
        init=False,
        default="partials/verification_forms/token.html",
    )


@dataclass(frozen=True, slots=True)
class DeployedUrlFormContext:
    """Rendering data for a deployed-URL form."""

    action: str
    placeholder: str
    min_length: int
    max_length: int
    value: str
    kind: Literal["deployed_url"] = field(init=False, default="deployed_url")
    template: str = field(
        init=False,
        default="partials/verification_forms/deployed_url.html",
    )


@dataclass(frozen=True, slots=True)
class ReflectionFormContext:
    """Rendering data for a career-reflection form."""

    action: str
    questions: tuple[CareerReflectionQuestion, ...]
    min_answer_length: int
    max_answer_length: int
    kind: Literal["reflection"] = field(init=False, default="reflection")
    template: str = field(
        init=False,
        default="partials/verification_forms/reflection.html",
    )


@dataclass(frozen=True, slots=True)
class UnsupportedFormContext:
    """Rendering data for a known requirement without an active form."""

    message: str
    kind: Literal["unsupported"] = field(init=False, default="unsupported")


type VerificationFormContext = (
    DerivedFormContext
    | TokenFormContext
    | DeployedUrlFormContext
    | ReflectionFormContext
    | UnsupportedFormContext
)


def build_verification_form_context(
    requirement: HandsOnRequirement,
    github_username: str,
    submission: SubmissionData | None,
) -> VerificationFormContext:
    """Build exactly one valid rendering model for a requirement form."""
    action = verification_submit_action(
        requirement.slug,
        requirement.submission_type,
    )
    if action is None:
        return UnsupportedFormContext(
            message="Verification is not currently available for this requirement."
        )

    if is_derivable(requirement.submission_type):
        return DerivedFormContext(
            action=action,
            url=derive_submission_value(
                requirement=requirement,
                github_username=github_username,
            ).github_url,
        )

    if isinstance(requirement, CtfTokenRequirement | NetworkingTokenRequirement):
        return TokenFormContext(
            action=action,
            placeholder=(
                requirement.type_config.placeholder
                or "Paste your completion token here"
            ),
            min_length=requirement.type_config.min_length,
            max_length=requirement.type_config.max_length,
        )

    if isinstance(requirement, DeployedApiRequirement):
        return DeployedUrlFormContext(
            action=action,
            placeholder=(
                requirement.type_config.placeholder or "https://your-api.example.com"
            ),
            min_length=requirement.type_config.min_length,
            max_length=requirement.type_config.max_length,
            value=getattr(submission, "submitted_value", "") if submission else "",
        )

    if isinstance(requirement, CareerReflectionRequirement):
        return ReflectionFormContext(
            action=action,
            questions=tuple(requirement.type_config.questions),
            min_answer_length=requirement.type_config.min_answer_length,
            max_answer_length=MAX_REFLECTION_ANSWER_LENGTH,
        )

    raise ValueError(
        f"Submission type {requirement.submission_type.value!r} has an HTTP "
        "action but no rendering form model."
    )
