"""Pydantic schemas for API request/response validation.

This module contains all Pydantic schemas used throughout the application.
Schemas are used both for API request/response validation and as
service-layer response models.

All schemas use frozen=True for immutability where appropriate.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from models import SubmissionType


class FrozenModel(BaseModel):
    """Base class for immutable Pydantic models (replaces frozen dataclasses)."""

    model_config = ConfigDict(frozen=True)


class UserBase(BaseModel):
    """Base user schema."""

    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


class UserResponse(UserBase):
    """User response schema (also used as service-layer response model)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    is_admin: bool = False
    created_at: datetime


class HandsOnRequirement(FrozenModel):
    """A hands-on requirement for phase completion.

    Used both as API schema and for defining phase requirements
    in services/phase_requirements_service.py.

    Supports Phase 0 through Phase 6 verification types.

    To add a new verification type:
    1. Add the SubmissionType enum value in models.py
    2. Add optional fields here if needed (e.g., challenge_config)
    3. Implement the validator in hands_on_verification.py
    """

    id: str
    submission_type: SubmissionType
    name: str
    description: str
    placeholder: str | None = None

    # For REPO_FORK: the original repo to verify fork from
    required_repo: str | None = None

    # For PR_REVIEW: files the merged PR must have touched
    expected_files: list[str] | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


class StepProgressData(FrozenModel):
    """Step progress data for a topic (service-layer response model)."""

    topic_id: str
    completed_steps: list[str]
    total_steps: int


class StepCompletionResult(FrozenModel):
    """Result of completing a step (service-layer response model)."""

    topic_id: str
    step_id: str
    completed_at: datetime


_VALID_CLOUD_PROVIDERS = {"aws", "azure", "gcp"}


class ProviderOption(FrozenModel):
    """Cloud provider or platform-specific option for a learning step."""

    provider: str
    title: str
    url: str
    description: str | None = None


class TipItem(FrozenModel):
    """A tip, note, or warning callout for a learning step."""

    type: str = "tip"  # tip, note, warning, important
    text: str


class LearningStep(FrozenModel):
    """A learning step within a topic."""

    id: str
    order: int
    action: str | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    code: str | None = None
    options: list[ProviderOption] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    tips: list[TipItem] = Field(default_factory=list)
    done_when: str | None = None


class LearningObjective(FrozenModel):
    """A learning objective for a topic."""

    id: str
    text: str
    order: int


class Topic(FrozenModel):
    """A topic within a phase."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    learning_steps: list[LearningStep]
    learning_objectives: list[LearningObjective] = Field(default_factory=list)


class PhaseCapstoneOverview(FrozenModel):
    """High-level capstone overview for a phase (public summary)."""

    title: str
    summary: str
    includes: list[str] = Field(default_factory=list)
    topic_slug: str | None = None


class PhaseHandsOnVerificationOverview(FrozenModel):
    """High-level hands-on verification overview for a phase (public summary)."""

    requirements: list[HandsOnRequirement] = Field(default_factory=list)


class Phase(FrozenModel):
    """A phase in the curriculum."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    name: str
    slug: str
    description: str = ""
    short_description: str = ""
    order: int = 0
    objectives: list[str] = Field(default_factory=list)
    capstone: PhaseCapstoneOverview | None = None
    hands_on_verification: PhaseHandsOnVerificationOverview | None = None
    topic_slugs: list[str] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)


class TopicProgressData(FrozenModel):
    """Progress status for a topic (service-layer response model)."""

    steps_completed: int
    steps_total: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class PhaseDetailProgress(FrozenModel):
    """Combined per-topic and overall progress for the phase detail page.

    Computed from a single DB query — avoids redundant round-trips.
    """

    topic_progress: dict[str, TopicProgressData]
    steps_completed: int
    steps_total: int
    percentage: int


class PhaseProgressData(FrozenModel):
    """Progress status for a phase (service-layer response model)."""

    steps_completed: int
    steps_required: int
    hands_on_validated: int
    hands_on_required: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class PhaseSummaryData(FrozenModel):
    """Phase summary data (service-layer response model)."""

    id: int
    name: str
    slug: str
    description: str
    short_description: str
    order: int
    topics_count: int
    objectives: list[str] = Field(default_factory=list)
    capstone: PhaseCapstoneOverview | None = None
    hands_on_verification: PhaseHandsOnVerificationOverview | None = None
    progress: PhaseProgressData | None = None


class ContinuePhaseData(FrozenModel):
    """Pointer to the user's current in-progress phase."""

    phase_id: int
    name: str
    slug: str
    order: int


class DashboardData(FrozenModel):
    """Complete dashboard payload (service-layer response model)."""

    phases: list[PhaseSummaryData]
    overall_percentage: float
    phases_completed: int
    total_phases: int
    is_program_complete: bool
    continue_phase: ContinuePhaseData | None = None


class PhaseRequirements(FrozenModel):
    """Requirements to complete a phase."""

    phase_id: int
    name: str
    topics: int
    steps: int


class PhaseProgress(FrozenModel):
    """User's progress for a single phase."""

    phase_id: int
    steps_completed: int
    steps_required: int
    hands_on_validated_count: int
    hands_on_required_count: int
    hands_on_validated: bool
    hands_on_required: bool

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Phase is complete when all requirements are met."""
        return self.steps_completed >= self.steps_required and self.hands_on_validated

    @computed_field
    @property
    def hands_on_percentage(self) -> float:
        """Percentage of hands-on requirements validated for this phase."""
        if self.hands_on_required_count == 0:
            return 100.0
        return min(
            100.0, (self.hands_on_validated_count / self.hands_on_required_count) * 100
        )

    @computed_field
    @property
    def overall_percentage(self) -> float:
        """Phase completion percentage (steps + hands-on)."""
        total = self.steps_required + self.hands_on_required_count
        if total == 0:
            return 0.0

        completed = min(self.steps_completed, self.steps_required) + min(
            self.hands_on_validated_count, self.hands_on_required_count
        )
        return (completed / total) * 100

    @computed_field
    @property
    def step_percentage(self) -> float:
        """Percentage of steps completed."""
        if self.steps_required == 0:
            return 100.0
        return min(100.0, (self.steps_completed / self.steps_required) * 100)


class UserProgress(FrozenModel):
    """Complete progress summary for a user."""

    user_id: int
    phases: dict[int, PhaseProgress]
    total_phases: int

    @computed_field
    @property
    def phases_completed(self) -> int:
        """Count of fully completed phases."""
        return sum(1 for p in self.phases.values() if p.is_complete)

    @computed_field
    @property
    def current_phase(self) -> int:
        """First incomplete phase, or last phase if all done."""
        for phase_id in sorted(self.phases.keys()):
            if not self.phases[phase_id].is_complete:
                return phase_id
        return max(self.phases.keys()) if self.phases else 0

    @computed_field
    @property
    def is_program_complete(self) -> bool:
        """True if all phases are completed."""
        return self.phases_completed >= self.total_phases

    @computed_field
    @property
    def overall_percentage(self) -> float:
        """Overall completion percentage across all phases."""
        if not self.phases:
            return 0.0

        total_steps = sum(p.steps_required for p in self.phases.values())
        total_hands_on = sum(p.hands_on_required_count for p in self.phases.values())
        completed_steps = sum(p.steps_completed for p in self.phases.values())
        completed_hands_on = sum(
            p.hands_on_validated_count for p in self.phases.values()
        )

        if total_steps + total_hands_on == 0:
            return 0.0

        total = total_steps + total_hands_on
        completed = min(completed_steps, total_steps) + min(
            completed_hands_on, total_hands_on
        )
        return (completed / total) * 100


class SubmissionData(FrozenModel):
    """Submission data (service-layer response model)."""

    id: int
    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    extracted_username: str | None = None
    is_validated: bool
    validated_at: datetime | None = None
    verification_completed: bool = False
    feedback_json: str | None = None
    validation_message: str | None = None
    cloud_provider: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SubmissionResult(FrozenModel):
    """Result of a submission validation."""

    submission: SubmissionData
    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list["TaskResult"] | None = None

    @computed_field
    @property
    def is_server_error(self) -> bool:
        """Whether this failure was caused by a server-side error.

        True when validation failed but verification never completed
        (e.g. LLM timeout, external service down). These attempts are
        not counted against the user's cooldown or daily quota.
        """
        return not self.is_valid and not self.submission.verification_completed


class TaskResult(FrozenModel):
    """Result of verifying a single task in code analysis.

    Used by CODE_ANALYSIS validation to provide detailed per-task feedback.
    """

    task_name: str
    passed: bool
    feedback: str


class PhaseSubmissionContext(FrozenModel):
    """Pre-built submission context for rendering a phase page."""

    submissions_by_req: dict[str, SubmissionData]
    feedback_by_req: dict[str, dict[str, object]]


class ValidationResult(FrozenModel):
    """Result of validating a hands-on submission.

    This is the common result type for ALL validation types.

    Attributes:
        is_valid: Whether the submission passed validation.
        message: User-facing message explaining the result.
        username_match: For GitHub-based validations, whether the submitted
            URL matches the authenticated user. None for non-GitHub validations.
        repo_exists: For GitHub-based validations, whether the repository
            exists. None for non-GitHub validations.
        task_results: For CODE_ANALYSIS validations, detailed per-task feedback.
            None for non-code-analysis validations.
        server_error: True if validation failed due to a server-side issue
            (e.g., service unavailable, config error). When True, cooldowns
            should not be applied since the user isn't at fault.
        cloud_provider: Cloud provider for multi-cloud labs ("aws",
            "azure", "gcp"). None for non-multi-cloud validations.
        score: Percentage of tasks passed (0.0-100.0). None for
            validation types that don't have task-level grading.
    """

    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list[TaskResult] | None = None
    server_error: bool = False
    cloud_provider: str | None = None
    score: float | None = None


class CTFVerificationResult(FrozenModel):
    """Result of verifying a CTF token."""

    is_valid: bool
    message: str
    server_error: bool = False
    github_username: str | None = None
    completion_date: str | None = None
    completion_time: str | None = None
    challenges_completed: int | None = None


class NetworkingLabVerificationResult(FrozenModel):
    """Result of verifying a Networking Lab completion token."""

    is_valid: bool
    message: str
    server_error: bool = False
    github_username: str | None = None
    completion_date: str | None = None
    completion_time: str | None = None
    challenges_completed: int | None = None
    challenge_type: str | None = None


class ParsedGitHubUrl(FrozenModel):
    """Parsed components of a GitHub URL."""

    username: str
    repo_name: str | None = None
    file_path: str | None = None
    is_valid: bool = True
    error: str | None = None


class PhaseDistributionItem(FrozenModel):
    """Per-phase user counts for the engagement funnel."""

    phase_id: int
    phase_name: str
    users_reached: int
    users_completed_steps: int


class MonthlyTrend(FrozenModel):
    """A single month in a time-series trend."""

    month: str  # "YYYY-MM"
    count: int
    cumulative: int


class VerificationStat(FrozenModel):
    """Verification attempt statistics per phase."""

    phase_id: int
    phase_name: str
    total_attempts: int
    successful: int
    pass_rate: float


class DayActivity(FrozenModel):
    """Step completions aggregated by day of the week."""

    day_name: str  # "Monday", "Tuesday", etc.
    completions: int


class ProviderDistribution(FrozenModel):
    """Submission counts per cloud provider."""

    provider: str  # "aws", "azure", "gcp"
    count: int

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in _VALID_CLOUD_PROVIDERS:
            msg = (
                f"Invalid provider '{v}',"
                f" must be one of {sorted(_VALID_CLOUD_PROVIDERS)}"
            )
            raise ValueError(msg)
        return v


class CommunityAnalytics(FrozenModel):
    """Aggregate, anonymous community analytics.

    All data is privacy-safe — no individual user information is exposed.
    Designed for public dashboards, conference talks, and storytelling.
    """

    total_users: int
    active_learners_30d: int
    completion_rate: float
    phase_distribution: list[PhaseDistributionItem]
    signup_trends: list[MonthlyTrend]
    verification_stats: list[VerificationStat]
    activity_by_day: list[DayActivity]
    provider_distribution: list["ProviderDistribution"] = Field(default_factory=list)
    generated_at: datetime
