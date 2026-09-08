"""Shared verification contracts and exact-type check dispatch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import ClassVar

from pydantic import Field

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.schemas import FrozenModel, TaskResult, ValidationResult
from learn_to_cloud_shared.submission_values import SubmittedValue
from learn_to_cloud_shared.verification.repo_files import RepoFiles
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    LLMRubricGraderConfig,
    VerificationTask,
)
from learn_to_cloud_shared.verification_workflow import PreparedVerificationAttempt


class CheckParams(FrozenModel):
    """Base for typed check configuration and its stable diagnostic name."""

    check_name: ClassVar[str]


@dataclass(frozen=True, slots=True)
class Step:
    """One ordered workflow step selected by its typed params."""

    params: CheckParams
    task_id: str


class StepResult(FrozenModel):
    """Outcome of running one step.

    ``evidence`` is contributed to the run's bundle and made visible to later
    steps. ``stop_on_fail`` lets a failed gate short-circuit the remaining
    steps. ``validation_result`` is the authoritative passthrough a
    deterministic gate uses to carry its full result unchanged.
    ``grading_task`` marks that this step requested LLM rubric grading; the
    engine turns it into a recorded grading request once the deterministic
    result is aggregated.
    """

    passed: bool
    task_result: TaskResult | None = None
    evidence: list[EvidenceBundle] = Field(default_factory=list)
    stop_on_fail: bool = True
    validation_result: ValidationResult | None = None
    grading_task: VerificationTask | None = None


@dataclass(frozen=True, slots=True)
class StepContext:
    """Everything a check may read. Carries runtime clients, so not a model."""

    job: PreparedVerificationAttempt
    repository: GitHubRepositoryTarget | None
    submitted_value: SubmittedValue
    evidence_so_far: tuple[EvidenceBundle, ...] = ()
    repo_files: RepoFiles | None = None


@dataclass(frozen=True)
class VerificationWorkflow:
    """A submission type's declared verification workflow.

    An ordered list of :class:`Step`s plus the terminal LLM step's rubric and
    optional persona. ``requires_username`` guards types whose steps need the
    learner's GitHub username; :func:`run_verification` short-circuits when it is
    missing.
    """

    requires_username: bool
    steps: tuple[Step, ...] = ()
    system_prompt: str | None = None
    rubric: LLMRubricGraderConfig | None = None


CheckFn = Callable[[StepContext, CheckParams], Awaitable[StepResult]]


class CheckRegistry:
    """Exact-type dispatch with explicit, duplicate-safe registration."""

    def __init__(
        self, entries: Iterable[tuple[type[CheckParams], CheckFn]] = ()
    ) -> None:
        self._checks: dict[type[CheckParams], CheckFn] = {}
        for params_type, check in entries:
            self.register(params_type, check)

    def register(self, params_type: type[CheckParams], check: CheckFn) -> None:
        if params_type in self._checks:
            raise ValueError(f"Check already registered: {params_type.check_name}")
        self._checks[params_type] = check

    def check_for(self, params: CheckParams) -> CheckFn:
        """Resolve only the exact params type, never an inherited fallback."""
        try:
            return self._checks[type(params)]
        except KeyError:
            raise KeyError(f"No check registered for {params.check_name!r}") from None
