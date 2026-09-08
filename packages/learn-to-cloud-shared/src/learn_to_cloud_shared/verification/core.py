"""Shared verification contracts for directly callable workflow steps."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import Field

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.schemas import FrozenModel, ValidationResult
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.repo_files import RepoFiles
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    LLMRubricGraderConfig,
    VerificationTask,
)
from learn_to_cloud_shared.verification_workflow import PreparedVerificationAttempt


@dataclass(frozen=True, slots=True)
class Step:
    """A check callable with stable telemetry and task identifiers."""

    name: str
    task_id: str
    check: CheckFn


class StepResult(FrozenModel):
    """Outcome of running one step.

    ``evidence`` supplies the grading request for this step.
    ``validation_result`` is the authoritative passthrough a
    deterministic gate uses to carry its full result unchanged.
    ``grading_task`` marks that this step requested LLM rubric grading; the
    engine turns it into a recorded grading request once the deterministic
    result is aggregated.
    """

    passed: bool
    evidence: list[EvidenceBundle] = Field(default_factory=list)
    validation_result: ValidationResult | None = None
    grading_task: VerificationTask | None = None


@dataclass(frozen=True, slots=True)
class StepContext:
    """Everything a check may read. Carries runtime clients, so not a model."""

    job: PreparedVerificationAttempt
    repository: GitHubRepositoryTarget | None
    submitted_value: SubmittedValue
    repo_files: RepoFiles | None = None


@dataclass(frozen=True)
class VerificationWorkflow:
    """A submission type's declared verification workflow.

    An ordered list of :class:`Step`s plus the terminal LLM step's rubric.
    ``requires_username`` guards types whose steps need the
    learner's GitHub username; :func:`run_verification` short-circuits when it is
    missing.
    """

    requires_username: bool
    steps: tuple[Step, ...] = ()
    rubric: LLMRubricGraderConfig | None = None


CheckFn = Callable[[StepContext], Awaitable[StepResult]]
