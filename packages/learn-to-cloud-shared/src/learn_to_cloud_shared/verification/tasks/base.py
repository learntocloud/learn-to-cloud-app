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
    "manual",
]
GraderKind = Literal[
    "indicator",
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


class IndicatorGraderConfig(FrozenModel):
    """Deterministic substring-based grading config."""

    kind: Literal["indicator"] = "indicator"
    pass_indicators: list[str] = Field(default_factory=list)
    fail_indicators: list[str] = Field(default_factory=list)
    min_pass_count: int = 1


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
    prompt_version: str
    passing_score: float = Field(ge=0.0, le=1.0)
    model: str | None = None


class LLMGradingDecision(FrozenModel):
    """Structured decision returned by the LLM grader."""

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    feedback: str
    next_steps: str = ""
    failure_reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class CompositeGraderConfig(FrozenModel):
    """Composite grading config for later multi-signal tasks."""

    kind: Literal["composite"] = "composite"
    required_pass_count: int = 1


GraderConfig = Annotated[
    IndicatorGraderConfig
    | FilePresenceGraderConfig
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
    requirement_id: str | None = None
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
    confidence: float | None = None
    rubric_version: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    def to_task_result(self) -> TaskResult:
        """Convert to the current public task feedback schema."""
        return TaskResult(
            task_name=self.task_name,
            passed=self.passed,
            feedback=self.feedback,
            next_steps=self.next_steps,
        )


def require_indicator_grader(task: VerificationTask) -> IndicatorGraderConfig:
    """Return the task's indicator grader or raise a configuration error."""
    if not isinstance(task.grader, IndicatorGraderConfig):
        raise TypeError(f"Task {task.id} does not use an indicator grader")
    return task.grader


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
