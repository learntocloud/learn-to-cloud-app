"""Shared task definitions for verification graders."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from learn_to_cloud_shared.schemas import FrozenModel, TaskResult

EvidenceSource = Literal[
    "repo_files",
    "pr_diff",
    "deployed_api",
    "token",
    "submitted_text",
    "manual",
]
GraderKind = Literal[
    "file_presence",
    "api_probe",
    "token",
    "llm_rubric",
    "composite",
]


class EvidencePolicy(FrozenModel):
    """Evidence allowed for one verification task."""

    source: EvidenceSource
    path_patterns: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    max_files: int = 10
    max_file_size_bytes: int = 50 * 1024
    max_total_bytes: int = 200 * 1024
    redact_patterns: list[str] = Field(default_factory=list)


class EvidenceItem(FrozenModel):
    """One collected evidence item."""

    path: str
    content: str
    sha256: str | None = None
    truncated: bool = False


class EvidenceBundle(FrozenModel):
    """Evidence passed to a grader."""

    task_id: str
    source: EvidenceSource
    items: list[EvidenceItem] = Field(default_factory=list)
    total_bytes: int = 0
    missing_paths: list[str] = Field(default_factory=list)
    """Requested paths that could not be fetched, so absence is distinguishable
    from a file that was fetched and found empty. Recorded for every requested
    path, including ones a task lists as alternatives."""
    missing_required_paths: list[str] = Field(default_factory=list)
    """The subset of ``missing_paths`` the task declares as required.

    Tasks request mutually exclusive alternatives (``ci.yml`` or ``ci.yaml``),
    so a plain missing path is normal and only a missing *required* path means
    the grader was short evidence it needed.
    """
    dropped_paths: list[str] = Field(default_factory=list)
    """Paths fetched but excluded because a cap was already reached."""

    @property
    def truncated_paths(self) -> list[str]:
        """Paths whose content was cut short to fit the per-file size cap."""
        return [item.path for item in self.items if item.truncated]

    @property
    def sufficiency_warnings(self) -> list[str]:
        """Deterministic reasons this evidence may be too incomplete to grade.

        These are facts about collection, not a model's self-assessment: a
        truncated or dropped file means the grader judged content we cut, so a
        resulting failure may be ours rather than the learner's.
        """
        warnings: list[str] = []
        if self.missing_required_paths:
            warnings.append(
                f"Could not read: {', '.join(sorted(self.missing_required_paths))}"
            )
        if truncated := self.truncated_paths:
            warnings.append(
                f"Truncated to fit size limits: {', '.join(sorted(truncated))}"
            )
        if self.dropped_paths:
            warnings.append(
                f"Omitted after evidence limits were reached: "
                f"{', '.join(sorted(self.dropped_paths))}"
            )
        return warnings

    @property
    def is_sufficient(self) -> bool:
        """Whether the grader saw every byte of the evidence it asked for."""
        return not self.sufficiency_warnings


class FilePresenceGraderConfig(FrozenModel):
    """File/config presence grading config."""

    kind: Literal["file_presence"] = "file_presence"
    required_any: list[str] = Field(default_factory=list)
    required_all: list[str] = Field(default_factory=list)
    content_indicators: list[str] = Field(default_factory=list)


class ApiProbeGraderConfig(FrozenModel):
    """HTTP/API probe grading config."""

    kind: Literal["api_probe"] = "api_probe"
    probe_id: str


class TokenGraderConfig(FrozenModel):
    """Signed token grading config."""

    kind: Literal["token"] = "token"
    token_family: str
    required_challenges: int


class LLMRubricGraderConfig(FrozenModel):
    """Constrained LLM rubric grading config."""

    kind: Literal["llm_rubric"] = "llm_rubric"
    rubric_id: str
    prompt_id: str
    passing_score: float = Field(ge=0.0, le=1.0)
    model_deployment: str | None = None
    """Foundry *deployment* name to grade with, not a model name.

    ``None`` inherits the deployment configured by
    ``FOUNDRY_MODEL_DEPLOYMENT_NAME``, which is the normal case. Set this only
    to route one task to a different deployment, and only to a deployment that
    actually exists in the Foundry account.
    """


class CriterionVerdict(FrozenModel):
    """Whether one rubric criterion was met, and the evidence-backed reason."""

    index: int = Field(ge=0)
    """Position of the criterion in the task's ``criteria`` list."""
    met: bool
    justification: str = ""


class LLMGradingDecision(FrozenModel):
    """Structured decision returned by the LLM grader.

    Carries a rubric score, not a verdict: the pass threshold is applied by
    :func:`_decision_to_grading_result` so pass/fail has one source of truth.
    """

    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    next_steps: str = ""
    failure_reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    criteria: list[CriterionVerdict] = Field(default_factory=list)
    """One verdict per rubric criterion, in order.

    Diagnostic rather than authoritative: ``score`` still decides the outcome.
    These make feedback name the criterion a learner missed, and let offline
    evaluation measure which criteria the grader judges unreliably instead of
    only whether it agreed overall.
    """


class CompositeGraderConfig(FrozenModel):
    """Composite grading config for later multi-signal tasks."""

    kind: Literal["composite"] = "composite"
    required_pass_count: int = 1


GraderConfig = Annotated[
    FilePresenceGraderConfig
    | ApiProbeGraderConfig
    | TokenGraderConfig
    | LLMRubricGraderConfig
    | CompositeGraderConfig,
    Field(discriminator="kind"),
]


class VerificationTask(FrozenModel):
    """Stable internal definition for one verification task."""

    id: str
    phase_id: int
    requirement_slug: str | None = None
    name: str
    criteria: list[str] = Field(default_factory=list)
    evidence: EvidencePolicy
    grader: GraderConfig


class GradingResult(FrozenModel):
    """Normalized internal result from any grader strategy."""

    task_id: str
    task_name: str
    passed: bool
    feedback: str
    next_steps: str = ""
    grader_kind: GraderKind
    failure_reason: str | None = None
    score: float | None = None
    rubric_version: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    criteria: list[CriterionVerdict] = Field(default_factory=list)

    def to_task_result(self) -> TaskResult:
        """Convert to the current public task feedback schema."""
        return TaskResult(
            task_name=self.task_name,
            passed=self.passed,
            feedback=self.feedback,
            next_steps=self.next_steps,
        )


def require_file_presence_grader(task: VerificationTask) -> FilePresenceGraderConfig:
    """Return the task's file-presence grader or raise a configuration error."""
    if not isinstance(task.grader, FilePresenceGraderConfig):
        raise TypeError(f"Task {task.id} does not use a file-presence grader")
    return task.grader


def require_llm_rubric_grader(task: VerificationTask) -> LLMRubricGraderConfig:
    """Return the task's LLM rubric grader or raise a configuration error."""
    if not isinstance(task.grader, LLMRubricGraderConfig):
        raise TypeError(f"Task {task.id} does not use an LLM rubric grader")
    return task.grader
