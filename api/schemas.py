"""Pydantic schemas for API request/response validation.

This module contains all Pydantic schemas used throughout the application.
Schemas are used both for API request/response validation and as
service-layer response models.

All schemas use frozen=True for immutability where appropriate.
"""

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from models import ActivityType, SubmissionType

# =============================================================================
# Base Configuration
# =============================================================================


class FrozenModel(BaseModel):
    """Base class for immutable Pydantic models (replaces frozen dataclasses)."""

    model_config = ConfigDict(frozen=True)


class FrozenORMModel(BaseModel):
    """Base class for immutable models that can be created from ORM objects."""

    model_config = ConfigDict(frozen=True, from_attributes=True)


# =============================================================================
# User Schemas
# =============================================================================


class UserBase(BaseModel):
    """Base user schema."""

    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


class UserResponse(UserBase):
    """User response schema (also used as service-layer response model)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    is_admin: bool = False
    created_at: datetime


# =============================================================================
# Hands-On Requirements & Submissions
# =============================================================================


class HandsOnRequirement(FrozenModel):
    """A hands-on requirement for phase completion.

    Used both as API schema and for defining phase requirements
    in services/phase_requirements_service.py.

    Currently supports Phase 0 and Phase 1 verification types.

    To add a new verification type:
    1. Add the SubmissionType enum value in models.py
    2. Add optional fields here if needed (e.g., challenge_config)
    3. Implement the validator in hands_on_verification.py
    """

    id: str
    phase_id: int
    submission_type: SubmissionType
    name: str
    description: str
    example_url: str | None = None
    note: str | None = None  # Optional note displayed separately (e.g., cooldown info)

    # For REPO_FORK: the original repo to verify fork from
    required_repo: str | None = None


class HandsOnSubmissionRequest(BaseModel):
    """Request to submit a value for hands-on validation."""

    requirement_id: str = Field(max_length=100)
    submitted_value: str = Field(max_length=4096)

    @field_validator("submitted_value")
    @classmethod
    def validate_submitted_value(cls, v: str) -> str:
        """Validate the submitted value.

        Accepts URLs, CTF tokens, or challenge responses.
        """
        v = v.strip()
        if not v:
            raise ValueError("Submission value cannot be empty")
        return v


class HandsOnSubmissionResponse(FrozenORMModel):
    """Response for a hands-on submission.

    Also used as service-layer response model.
    """

    id: int
    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    extracted_username: str | None = None
    is_validated: bool
    validated_at: datetime | None = None
    created_at: datetime
    feedback_json: str | None = None  # JSON-serialized task results


class HandsOnValidationResult(FrozenModel):
    """Result of validating a hands-on submission."""

    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    submission: HandsOnSubmissionResponse | None = None
    task_results: list["TaskResult"] | None = None
    next_retry_at: str | None = None  # ISO timestamp when retry is allowed


# =============================================================================
# Health Check Schemas
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


class PoolStatusResponse(BaseModel):
    """Connection pool status."""

    pool_size: int
    checked_out: int
    overflow: int
    checked_in: int


class DetailedHealthResponse(BaseModel):
    """Detailed health check response with component status."""

    status: str
    service: str
    database: bool
    azure_auth: bool | None = None
    pool: PoolStatusResponse | None = None


class WebhookResponse(BaseModel):
    """Response for webhook processing."""

    status: str
    event_type: str | None = None


class StepCompleteRequest(BaseModel):
    """Request to mark a learning step as complete."""

    topic_id: str = Field(max_length=100)
    step_order: int = Field(ge=1)

    @field_validator("topic_id")
    @classmethod
    def validate_topic_id_format(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"^phase\d+-topic\d+$", v):
            raise ValueError("Invalid topic_id format. Expected: phase{N}-topic{M}")
        return v


class StepProgressResponse(FrozenORMModel):
    """Response for a single step's progress."""

    topic_id: str
    step_order: int
    completed_at: datetime


class StepProgressData(FrozenModel):
    """Step progress data for a topic (service-layer response model)."""

    topic_id: str
    completed_steps: list[int]
    total_steps: int
    next_unlocked_step: int


# Alias for route compatibility
TopicStepProgressResponse = StepProgressData


class StepCompletionResult(FrozenModel):
    """Result of completing a step (service-layer response model)."""

    topic_id: str
    step_order: int
    completed_at: datetime


class StepUncompleteResponse(FrozenModel):
    """Response for uncompleting a step."""

    status: str
    deleted_count: int


class BadgeData(FrozenModel):
    """Badge information (service-layer response model)."""

    id: str
    name: str
    description: str
    icon: str


class PhaseThemeData(FrozenModel):
    """Phase theme metadata for UI display."""

    phase_id: int
    icon: str
    bg_class: str
    border_class: str
    text_class: str


class BadgeCatalogItem(FrozenModel):
    """Badge metadata for catalog display."""

    id: str
    name: str
    description: str
    icon: str
    num: str
    how_to: str
    phase_id: int | None = None
    phase_name: str | None = None


class BadgeCatalogResponse(BaseModel):
    """Badge catalog response."""

    phase_badges: list[BadgeCatalogItem]
    total_badges: int
    phase_themes: list[PhaseThemeData]


# Alias for route compatibility
BadgeResponse = BadgeData


class PublicSubmission(FrozenORMModel):
    """A validated submission for public display."""

    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    name: str
    description: str | None = None
    validated_at: datetime | None = None


class PublicSubmissionInfo(FrozenModel):
    """Public submission information for profile display.

    Also used as service-layer response model.
    """

    requirement_id: str
    submission_type: str
    phase_id: int
    submitted_value: str
    name: str
    description: str | None = None
    validated_at: object | None = None


class PublicProfileData(FrozenModel):
    """Complete public profile data (service-layer response model)."""

    username: str | None
    first_name: str | None
    avatar_url: str | None
    current_phase: int
    phases_completed: int
    member_since: datetime
    submissions: list[PublicSubmissionInfo]
    badges: list[BadgeData]


class PublicProfileResponse(BaseModel):
    """Public user profile information.

    Progress is tracked at the phase level:
    - A phase is complete when all steps + hands-on requirements are done
    - phases_completed counts fully completed phases
    - current_phase is the first incomplete phase (or highest if all done)
    """

    username: str | None = None
    first_name: str | None = None
    avatar_url: str | None = None
    current_phase: int
    phases_completed: int
    member_since: datetime
    submissions: list[PublicSubmission] = Field(default_factory=list)
    badges: list[BadgeData] = Field(default_factory=list)


# =============================================================================
# Certificate Schemas
# =============================================================================


class CertificateData(FrozenModel):
    """Certificate data (service-layer response model)."""

    id: int
    certificate_type: str
    verification_code: str
    recipient_name: str
    issued_at: datetime
    phases_completed: int
    total_phases: int


class EligibilityResult(FrozenModel):
    """Result of certificate eligibility check (service-layer response model)."""

    is_eligible: bool
    phases_completed: int
    total_phases: int
    completion_percentage: float
    existing_certificate: CertificateData | None = None
    message: str


class CreateCertificateResult(FrozenModel):
    """Result of certificate creation (service-layer response model)."""

    certificate: CertificateData
    verification_code: str


class CertificateVerificationResult(FrozenModel):
    """Result of certificate verification (service-layer response model)."""

    is_valid: bool
    certificate: CertificateData | None = None
    message: str


class CertificateEligibilityResponse(BaseModel):
    """Response for checking certificate eligibility."""

    is_eligible: bool
    certificate_type: str
    phases_completed: int
    total_phases: int
    completion_percentage: float
    already_issued: bool
    existing_certificate_id: int | None = None
    message: str


class CertificateRequest(BaseModel):
    """Request to generate a certificate."""

    certificate_type: str = Field(
        default="full_completion",
        pattern=r"^full_completion$",
    )
    recipient_name: str = Field(min_length=2, max_length=100)

    @field_validator("recipient_name")
    @classmethod
    def validate_recipient_name(cls, v: str) -> str:
        """Validate and clean recipient name."""
        cleaned = " ".join(v.strip().split())
        if len(cleaned) < 2:
            raise ValueError("Name must be at least 2 characters")
        return cleaned


# Alias for route compatibility
CertificateResponse = CertificateData


class CertificateVerifyResponse(BaseModel):
    """Response for certificate verification."""

    is_valid: bool
    certificate: CertificateData | None = None
    message: str


class UserCertificatesResponse(BaseModel):
    """All certificates for a user."""

    certificates: list[CertificateData]
    full_completion_eligible: bool


# =============================================================================
# Content Schemas (loaded from JSON files)
# =============================================================================


class SecondaryLink(FrozenModel):
    """A secondary link in a learning step description."""

    text: str
    url: str


# Alias for route compatibility
SecondaryLinkSchema = SecondaryLink


class ProviderOption(FrozenModel):
    """Cloud provider-specific option for a learning step."""

    provider: str  # "aws", "azure", "gcp"
    title: str
    url: str
    description: str | None = None


# Alias for route compatibility
ProviderOptionSchema = ProviderOption


class LearningStep(FrozenModel):
    """A learning step within a topic."""

    order: int
    text: str
    action: str | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    code: str | None = None
    secondary_links: list[SecondaryLink] = Field(default_factory=list)
    options: list[ProviderOption] = Field(default_factory=list)


# Alias for route compatibility
LearningStepSchema = LearningStep


class LearningObjective(FrozenModel):
    """A learning objective for a topic."""

    id: str
    text: str
    order: int


# Alias for route compatibility
LearningObjectiveSchema = LearningObjective


class Topic(FrozenModel):
    """A topic within a phase."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    is_capstone: bool
    learning_steps: list[LearningStep]
    learning_objectives: list[LearningObjective] = Field(default_factory=list)


class PhaseCapstoneOverview(FrozenModel):
    """High-level capstone overview for a phase (public summary)."""

    title: str
    summary: str
    includes: list[str] = Field(default_factory=list)
    topic_slug: str | None = None


# Alias for route compatibility
PhaseCapstoneOverviewSchema = PhaseCapstoneOverview


class PhaseHandsOnVerificationOverview(FrozenModel):
    """High-level hands-on verification overview for a phase (public summary)."""

    summary: str
    includes: list[str] = Field(default_factory=list)
    requirements: list[HandsOnRequirement] = Field(default_factory=list)


class PhaseBadgeMeta(FrozenModel):
    """Badge metadata for a phase (content-driven)."""

    name: str
    description: str
    icon: str


class PhaseThemeMeta(FrozenModel):
    """Theme metadata for a phase (content-driven)."""

    icon: str
    bg_class: str
    border_class: str
    text_class: str


# Alias for route compatibility
PhaseHandsOnVerificationOverviewSchema = PhaseHandsOnVerificationOverview


class Phase(FrozenModel):
    """A phase in the curriculum."""

    id: int
    name: str
    slug: str
    description: str
    short_description: str
    order: int
    objectives: list[str]
    capstone: PhaseCapstoneOverview | None = None
    hands_on_verification: PhaseHandsOnVerificationOverview | None = None
    badge: PhaseBadgeMeta | None = None
    theme: PhaseThemeMeta | None = None
    topic_slugs: list[str] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)


# =============================================================================
# Progress Schemas
# =============================================================================


class TopicProgressData(FrozenModel):
    """Progress status for a topic (service-layer response model)."""

    steps_completed: int
    steps_total: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


# Alias for route compatibility
TopicProgressSchema = TopicProgressData


class TopicSummaryData(FrozenModel):
    """Topic summary data (service-layer response model)."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    is_capstone: bool
    steps_count: int
    progress: TopicProgressData | None = None
    is_locked: bool = False


# Alias for route compatibility
TopicSummarySchema = TopicSummaryData


class TopicDetailData(FrozenModel):
    """Full topic detail with steps (service-layer response model)."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    is_capstone: bool
    learning_steps: list[LearningStep]
    learning_objectives: list[LearningObjective] = Field(default_factory=list)
    progress: TopicProgressData | None = None
    completed_step_orders: list[int] = Field(default_factory=list)
    is_locked: bool = False
    is_topic_locked: bool = False
    previous_topic_name: str | None = None


# Alias for route compatibility
TopicDetailSchema = TopicDetailData


class PhaseProgressData(FrozenModel):
    """Progress status for a phase (service-layer response model)."""

    steps_completed: int
    steps_required: int
    hands_on_validated: int
    hands_on_required: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


# Alias for route compatibility
PhaseProgressSchema = PhaseProgressData


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
    is_locked: bool = False


# Alias for route compatibility
PhaseSummarySchema = PhaseSummaryData


class PhaseDetailData(FrozenModel):
    """Full phase detail with topics (service-layer response model)."""

    id: int
    name: str
    slug: str
    description: str
    short_description: str
    order: int
    objectives: list[str]
    capstone: PhaseCapstoneOverview | None = None
    hands_on_verification: PhaseHandsOnVerificationOverview | None = None
    topics: list[TopicSummaryData]
    progress: PhaseProgressData | None = None
    hands_on_requirements: list[HandsOnRequirement] = Field(default_factory=list)
    hands_on_submissions: list[HandsOnSubmissionResponse] = Field(default_factory=list)
    is_locked: bool = False
    all_topics_complete: bool = False
    all_hands_on_validated: bool = False
    is_phase_complete: bool = False


# Alias for route compatibility
PhaseDetailSchema = PhaseDetailData


class UserSummaryData(FrozenModel):
    """User summary data (service-layer response model)."""

    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None
    is_admin: bool = False


# Alias for route compatibility
UserSummarySchema = UserSummaryData


class DashboardData(FrozenModel):
    """Complete dashboard data (service-layer response model)."""

    user: UserSummaryData
    phases: list[PhaseSummaryData]
    overall_progress: float
    phases_completed: int
    phases_total: int
    current_phase: int | None = None
    badges: list[BadgeData] = Field(default_factory=list)


# Alias for route compatibility
DashboardResponse = DashboardData


# =============================================================================
# Progress Service Schemas (with computed fields)
# =============================================================================


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

    user_id: str
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


# =============================================================================
# Activity Service Schemas
# =============================================================================


class ActivityResult(FrozenModel):
    """Result of logging an activity."""

    id: int
    activity_type: ActivityType
    activity_date: date
    reference_id: str | None = None
    created_at: datetime


class ActivityHeatmapDay(FrozenModel):
    """A single day's activity count for the heatmap."""

    date: date
    count: int


class ActivityHeatmapResponse(FrozenModel):
    """Activity heatmap data for a user's public profile."""

    days: list[ActivityHeatmapDay]


# =============================================================================
# Submission Service Schemas
# =============================================================================


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
    verification_completed: bool = True
    created_at: datetime


class SubmissionResult(FrozenModel):
    """Result of a submission validation."""

    submission: SubmissionData
    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list["TaskResult"] | None = None


class TaskResult(FrozenModel):
    """Result of verifying a single task in code analysis.

    Used by CODE_ANALYSIS validation to provide detailed per-task feedback.
    """

    task_name: str
    passed: bool
    feedback: str


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
    """

    is_valid: bool
    message: str
    username_match: bool | None = None
    repo_exists: bool | None = None
    task_results: list[TaskResult] | None = None
    server_error: bool = False


# =============================================================================
# CTF Verification Schema
# =============================================================================


class CTFVerificationResult(FrozenModel):
    """Result of verifying a CTF token."""

    is_valid: bool
    message: str
    github_username: str | None = None
    completion_date: str | None = None
    completion_time: str | None = None
    challenges_completed: int | None = None


class NetworkingLabVerificationResult(FrozenModel):
    """Result of verifying a Networking Lab completion token."""

    is_valid: bool
    message: str
    github_username: str | None = None
    completion_date: str | None = None
    completion_time: str | None = None
    challenges_completed: int | None = None
    challenge_type: str | None = None


# =============================================================================
# Clerk Service Schema
# =============================================================================


class ClerkUserData(FrozenModel):
    """Data fetched from Clerk API for a user."""

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


# =============================================================================
# GitHub URL Parsing Schema
# =============================================================================


class ParsedGitHubUrl(FrozenModel):
    """Parsed components of a GitHub URL."""

    username: str
    repo_name: str | None = None
    file_path: str | None = None
    is_valid: bool = True
    error: str | None = None
