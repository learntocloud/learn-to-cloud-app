"""Verification submission validation, input shapes, actions, and shared limits."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import (
    CareerReflectionRequirement,
)
from learn_to_cloud_shared.submission_values import MAX_TEXT_LENGTH
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_SUBMITTED_VALUE_LENGTH = 2_048
MAX_REFLECTION_ANSWER_LENGTH = 6_000


class VerificationInputShape(StrEnum):
    """Supported verification form shapes."""

    DERIVED = "derived"
    VALUE = "value"
    REFLECTION = "reflection"


_VALUE_SUBMISSION_TYPES = frozenset(
    {
        SubmissionType.CTF_TOKEN,
        SubmissionType.NETWORKING_TOKEN,
        SubmissionType.DEPLOYED_API,
    }
)


def input_shape_for_submission_type(
    submission_type: SubmissionType,
) -> VerificationInputShape:
    """Return the active HTTP form shape for a submission type."""
    if submission_type in {
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    }:
        return VerificationInputShape.DERIVED
    if submission_type in _VALUE_SUBMISSION_TYPES:
        return VerificationInputShape.VALUE
    if submission_type == SubmissionType.CAREER_REFLECTION:
        return VerificationInputShape.REFLECTION
    raise ValueError(f"Unsupported submission type: {submission_type!r}")


def verification_submit_action(
    requirement_slug: str,
    submission_type: SubmissionType,
) -> str:
    """Build the HTMX submission URL for an active requirement type."""
    shape = input_shape_for_submission_type(submission_type)
    return f"/htmx/verifications/{requirement_slug}/submit/{shape.value}"


class DerivedVerificationForm(BaseModel):
    """A server-derived verification submits no learner-controlled value."""

    model_config = ConfigDict(extra="forbid")


class ValueVerificationForm(BaseModel):
    """A verification with one learner-provided scalar value."""

    model_config = ConfigDict(extra="forbid")

    submitted_value: str = Field(
        min_length=1,
        max_length=MAX_SUBMITTED_VALUE_LENGTH,
    )


ReflectionAnswer = Annotated[
    str,
    StringConstraints(max_length=MAX_REFLECTION_ANSWER_LENGTH),
]


class ReflectionVerificationForm(BaseModel):
    """A career reflection submitted as repeated answer fields."""

    model_config = ConfigDict(extra="forbid")

    answers: list[ReflectionAnswer] = Field(min_length=1)


def combine_reflection_answers(
    requirement: CareerReflectionRequirement,
    answers: list[str],
) -> str:
    """Validate and label reflection answers for grading."""
    questions = list(requirement.type_config.questions)
    min_length = requirement.type_config.min_answer_length
    cleaned = [answer.strip() for answer in answers]

    if len(cleaned) != len(questions):
        raise ValueError("Please answer all of the reflection questions.")

    sections: list[str] = []
    for question, answer in zip(questions, cleaned, strict=True):
        if len(answer) < min_length:
            raise ValueError(
                f"Each answer needs at least {min_length} characters. "
                "Add more detail and try again."
            )
        if len(answer) > MAX_REFLECTION_ANSWER_LENGTH:
            raise ValueError(
                "One of your answers is too long. Please keep each answer "
                f"under {MAX_REFLECTION_ANSWER_LENGTH} characters."
            )
        sections.append(f"## {question.prompt}\n\n{answer}")

    combined = "\n\n".join(sections)
    if len(combined) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"Your combined answers must be at most {MAX_TEXT_LENGTH} characters."
        )
    return combined
