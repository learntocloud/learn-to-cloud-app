"""Shared task definitions for verification graders."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from learn_to_cloud_shared.schemas import CriterionResult, FrozenModel

EvidenceSource = Literal["repo_files", "submitted_text"]
RubricCriterionKind = Literal["required", "quality", "bonus"]


class RubricCriterion(FrozenModel):
    """One stable learner-facing rubric criterion."""

    id: str
    label: str
    instruction: str
    kind: RubricCriterionKind = "required"


class EvidencePolicy(FrozenModel):
    """Evidence allowed for one verification task."""

    source: EvidenceSource
    required_files: list[str] = Field(default_factory=list)
    optional_files: list[str] = Field(default_factory=list)
    criterion_evidence: dict[str, list[str]] = Field(default_factory=dict)
    max_files: int = 10
    max_file_size_bytes: int = 50 * 1024
    max_total_bytes: int = 200 * 1024


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
    selected_paths: list[str]
    optional_presence: dict[str, bool]


class LLMRubricGraderConfig(FrozenModel):
    """Constrained LLM rubric grading config."""

    kind: Literal["llm_rubric"] = "llm_rubric"
    rubric_id: str
    prompt_version: str
    passing_score: float = Field(ge=0.0, le=1.0)


class LLMGradingDecision(FrozenModel):
    """Structured decision returned by the LLM grader."""

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    feedback: str
    next_steps: str = ""
    failure_reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    criterion_results: list[CriterionResult] = Field(default_factory=list)


class VerificationTask(FrozenModel):
    """Stable internal definition for one verification task."""

    id: str
    phase_id: int
    requirement_slug: str | None = None
    name: str
    criteria: list[RubricCriterion | str] = Field(default_factory=list)
    grading_instructions: list[str] = Field(default_factory=list)
    evidence: EvidencePolicy
    grader: LLMRubricGraderConfig
