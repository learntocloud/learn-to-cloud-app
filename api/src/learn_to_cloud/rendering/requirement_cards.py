"""Requirement-card states and builders for templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from learn_to_cloud_shared.schemas import HandsOnRequirement, SubmissionData

from learn_to_cloud.rendering.feedback import (
    FeedbackTaskContext,
    incomplete_verification_message,
    prepare_card_feedback,
)
from learn_to_cloud.rendering.verification_forms import (
    VerificationFormContext,
    build_verification_form_context,
)


@dataclass(frozen=True, slots=True)
class _RequirementCardBase:
    """Fields shared by every requirement-card state."""

    requirement: HandsOnRequirement
    feedback_tasks: list[FeedbackTaskContext]
    feedback_passed: int


@dataclass(frozen=True, slots=True)
class NotStartedCardContext(_RequirementCardBase):
    """A submittable requirement with no completed attempt."""

    verification_form: VerificationFormContext
    error_message: str | None = None
    kind: Literal["not_started"] = field(init=False, default="not_started")


@dataclass(frozen=True, slots=True)
class CheckingCardContext(_RequirementCardBase):
    """An active verification attempt."""

    verification_attempt_id: UUID
    verification_status_delay_seconds: int
    kind: Literal["checking"] = field(init=False, default="checking")


@dataclass(frozen=True, slots=True)
class FailedCardContext(_RequirementCardBase):
    """A completed learner attempt that did not pass."""

    verification_form: VerificationFormContext
    error_message: str
    kind: Literal["failed"] = field(init=False, default="failed")


@dataclass(frozen=True, slots=True)
class UnavailableCardContext(_RequirementCardBase):
    """A verification-service failure."""

    verification_form: VerificationFormContext
    message: str
    kind: Literal["unavailable"] = field(init=False, default="unavailable")


@dataclass(frozen=True, slots=True)
class PassedCardContext(_RequirementCardBase):
    """A successfully verified requirement."""

    submission: SubmissionData
    graded_url: str | None
    kind: Literal["passed"] = field(init=False, default="passed")

    @property
    def graded_label(self) -> str | None:
        if not self.graded_url:
            return None
        parsed = urlparse(self.graded_url)
        if parsed.netloc == "github.com":
            return parsed.path.strip("/")
        return parsed.netloc or self.graded_url


type RequirementCardContext = (
    NotStartedCardContext
    | CheckingCardContext
    | FailedCardContext
    | UnavailableCardContext
    | PassedCardContext
)

_URL_SCHEMES = ("https://", "http://")


def _graded_url(submission: SubmissionData) -> str | None:
    """Return a URL summary without echoing tokens or free-text submissions."""
    value = submission.submitted_value or ""
    return value if value.startswith(_URL_SCHEMES) else None


def build_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    github_username: str,
    submission: SubmissionData | None = None,
    feedback_tasks: list[FeedbackTaskContext] | None = None,
    feedback_passed: int = 0,
) -> RequirementCardContext:
    """Build a card state from the latest persisted submission."""
    graded_url = _graded_url(submission) if submission is not None else None
    tasks, passed = prepare_card_feedback(feedback_tasks, feedback_passed, graded_url)
    if submission is not None and submission.is_validated:
        return PassedCardContext(
            requirement=requirement,
            feedback_tasks=tasks,
            feedback_passed=passed,
            submission=submission,
            graded_url=graded_url,
        )
    verification_form = build_verification_form_context(
        requirement,
        github_username,
        submission,
    )
    if submission is None:
        return NotStartedCardContext(
            requirement=requirement,
            feedback_tasks=tasks,
            feedback_passed=passed,
            verification_form=verification_form,
        )
    if submission.verification_completed:
        return FailedCardContext(
            requirement=requirement,
            feedback_tasks=tasks,
            feedback_passed=passed,
            verification_form=verification_form,
            error_message=(
                submission.validation_message or "Verification did not pass."
            ),
        )
    return UnavailableCardContext(
        requirement=requirement,
        feedback_tasks=[],
        feedback_passed=0,
        verification_form=verification_form,
        message=incomplete_verification_message(
            submission.validation_message, submission.error_code
        ),
    )


def build_checking_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    verification_attempt_id: UUID,
    verification_status_delay_seconds: int,
) -> CheckingCardContext:
    """Build the active-attempt card variant."""
    return CheckingCardContext(
        requirement=requirement,
        feedback_tasks=[],
        feedback_passed=0,
        verification_attempt_id=verification_attempt_id,
        verification_status_delay_seconds=verification_status_delay_seconds,
    )


def build_input_error_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    github_username: str,
    message: str,
) -> NotStartedCardContext:
    """Build a submittable card with a learner input error."""
    return NotStartedCardContext(
        requirement=requirement,
        feedback_tasks=[],
        feedback_passed=0,
        verification_form=build_verification_form_context(
            requirement,
            github_username,
            None,
        ),
        error_message=message,
    )


def build_unavailable_requirement_card_context(
    *,
    requirement: HandsOnRequirement,
    github_username: str,
    message: str,
) -> UnavailableCardContext:
    """Build an explicit verification-service failure card."""
    return UnavailableCardContext(
        requirement=requirement,
        feedback_tasks=[],
        feedback_passed=0,
        verification_form=build_verification_form_context(
            requirement,
            github_username,
            None,
        ),
        message=incomplete_verification_message(message),
    )
