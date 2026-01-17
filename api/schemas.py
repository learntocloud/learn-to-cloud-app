"""Pydantic schemas for API request/response validation."""

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models import ActivityType, SubmissionType


class UserBase(BaseModel):
    """Base user schema."""

    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


class UserResponse(UserBase):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    is_admin: bool = False
    created_at: datetime


class HandsOnRequirement(BaseModel):
    """A hands-on requirement for phase completion.

    NOTE: This model serves dual purposes:
    1. API schema: Returned in API responses
    2. Business configuration: Used in services/hands_on_verification.py to
       define phase requirements (HANDS_ON_REQUIREMENTS constant)

    Using Pydantic for both is intentional - it ensures the same structure
    is used for configuration and API responses, reducing inconsistencies.

    Supports multiple verification types including GitHub-based validations,
    deployed application checks, CTF tokens, and API challenges.

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

    required_repo: str | None = None

    expected_endpoint: str | None = None

    # If True, validate the response body matches Journal API structure
    validate_response_body: bool = False

    challenge_config: dict | None = None

    # For REPO_WITH_FILES: file patterns to search for
    # (e.g., ["Dockerfile", "docker-compose"])
    required_file_patterns: list[str] | None = None
    # Human-readable description of the files being searched for
    file_description: str | None = None


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


class HandsOnSubmissionResponse(BaseModel):
    """Response for a hands-on submission."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    extracted_username: str | None = None
    is_validated: bool
    validated_at: datetime | None = None
    created_at: datetime


class HandsOnValidationResult(BaseModel):
    """Result of validating a hands-on submission."""

    is_valid: bool
    message: str
    username_match: bool
    repo_exists: bool
    submission: HandsOnSubmissionResponse | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


class WebhookResponse(BaseModel):
    """Response for webhook processing."""

    status: str
    event_type: str | None = None


class QuestionSubmitRequest(BaseModel):
    """Request to submit an answer to a knowledge question."""

    topic_id: str = Field(max_length=100)
    question_id: str = Field(max_length=100)
    user_answer: str = Field(min_length=10, max_length=2000)

    @field_validator("topic_id")
    @classmethod
    def validate_topic_id_format(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"^phase\d+-topic\d+$", v):
            raise ValueError("Invalid topic_id format. Expected: phase{N}-topic{M}")
        return v

    @field_validator("question_id")
    @classmethod
    def validate_question_id_format(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"^phase\d+-topic\d+-q\d+$", v):
            raise ValueError(
                "Invalid question_id format. Expected: phase{N}-topic{M}-q{X}"
            )
        return v

    @field_validator("user_answer")
    @classmethod
    def validate_answer_not_empty(cls, v: str) -> str:
        """Ensure answer has meaningful content."""
        stripped = v.strip()
        if len(stripped) < 10:
            raise ValueError("Answer must be at least 10 characters")
        return stripped


class QuestionSubmitResponse(BaseModel):
    """Response for a question submission."""

    model_config = ConfigDict(from_attributes=True)

    question_id: str
    is_passed: bool
    llm_feedback: str | None = None
    confidence_score: float | None = None
    attempt_id: int


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


class StepProgressResponse(BaseModel):
    """Response for a single step's progress."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: str
    step_order: int
    completed_at: datetime


class TopicStepProgressResponse(BaseModel):
    """Progress of all steps in a topic for a user."""

    topic_id: str
    completed_steps: list[int]
    total_steps: int
    next_unlocked_step: int


class StreakResponse(BaseModel):
    """Response containing user's streak information."""

    model_config = ConfigDict(from_attributes=True)

    current_streak: int
    longest_streak: int
    total_activity_days: int
    last_activity_date: date | None = None
    streak_alive: bool


class ActivityHeatmapDay(BaseModel):
    """Activity count for a single day (for heatmap display)."""

    model_config = ConfigDict(from_attributes=True)

    date: date
    count: int
    activity_types: list[ActivityType]


class ActivityHeatmapResponse(BaseModel):
    """Activity heatmap data for profile display."""

    model_config = ConfigDict(from_attributes=True)

    days: list[ActivityHeatmapDay]
    start_date: date
    end_date: date
    total_activities: int


class BadgeResponse(BaseModel):
    """A badge earned by a user."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    icon: str


class PublicSubmission(BaseModel):
    """A validated submission for public display."""

    model_config = ConfigDict(from_attributes=True)

    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_value: str
    name: str
    validated_at: datetime | None = None


class PublicProfileResponse(BaseModel):
    """Public user profile information.

    Progress is tracked at the phase level:
    - A phase is complete when all steps + questions + GitHub requirements are done
    - phases_completed counts fully completed phases
    - current_phase is the first incomplete phase (or highest if all done)
    """

    username: str | None = None
    first_name: str | None = None
    avatar_url: str | None = None
    current_phase: int
    phases_completed: int
    streak: StreakResponse
    activity_heatmap: ActivityHeatmapResponse
    member_since: datetime
    submissions: list[PublicSubmission] = Field(default_factory=list)
    badges: list[BadgeResponse] = Field(default_factory=list)


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


class CertificateResponse(BaseModel):
    """Response containing certificate data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    certificate_type: str
    verification_code: str
    recipient_name: str
    issued_at: datetime
    phases_completed: int
    total_phases: int


class CertificateVerifyResponse(BaseModel):
    """Response for certificate verification."""

    is_valid: bool
    certificate: CertificateResponse | None = None
    message: str


class UserCertificatesResponse(BaseModel):
    """All certificates for a user."""

    certificates: list[CertificateResponse]
    full_completion_eligible: bool


# ============ Dashboard & Content Schemas ============


class SecondaryLinkSchema(BaseModel):
    """A secondary link in a learning step description."""

    text: str
    url: str


class ProviderOptionSchema(BaseModel):
    """Cloud provider-specific option for a learning step."""

    provider: str  # "aws", "azure", "gcp"
    title: str
    url: str
    description: str | None = None


class LearningStepSchema(BaseModel):
    """A learning step within a topic."""

    order: int
    text: str
    action: str | None = None
    title: str | None = None
    url: str | None = None
    description: str | None = None
    code: str | None = None
    secondary_links: list[SecondaryLinkSchema] = Field(default_factory=list)
    options: list[ProviderOptionSchema] = Field(default_factory=list)


class QuestionSchema(BaseModel):
    """A knowledge check question."""

    id: str
    prompt: str
    expected_concepts: list[str]


class TopicProgressSchema(BaseModel):
    """Progress status for a topic."""

    steps_completed: int
    steps_total: int
    questions_passed: int
    questions_total: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class TopicSummarySchema(BaseModel):
    """Topic summary for phase listings."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    estimated_time: str
    is_capstone: bool
    steps_count: int
    questions_count: int
    progress: TopicProgressSchema | None = None
    is_locked: bool = False


class TopicDetailSchema(BaseModel):
    """Full topic detail with steps and questions."""

    id: str
    slug: str
    name: str
    description: str
    order: int
    estimated_time: str
    is_capstone: bool
    learning_steps: list[LearningStepSchema]
    questions: list[QuestionSchema]
    learning_objectives: list["LearningObjectiveSchema"] = Field(default_factory=list)
    progress: TopicProgressSchema | None = None
    completed_step_orders: list[int] = Field(default_factory=list)
    passed_question_ids: list[str] = Field(default_factory=list)
    is_locked: bool = False
    is_topic_locked: bool = False
    previous_topic_name: str | None = None


class LearningObjectiveSchema(BaseModel):
    """A learning objective for a topic."""

    id: str
    text: str
    order: int


class PhaseProgressSchema(BaseModel):
    """Progress status for a phase."""

    steps_completed: int
    steps_required: int
    questions_passed: int
    questions_required: int
    hands_on_validated: int
    hands_on_required: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class PhaseCapstoneOverviewSchema(BaseModel):
    """Public-friendly capstone overview for a phase."""

    model_config = ConfigDict(from_attributes=True)

    title: str
    summary: str
    includes: list[str] = Field(default_factory=list)
    topic_slug: str | None = None


class PhaseHandsOnVerificationOverviewSchema(BaseModel):
    """Public-friendly hands-on verification overview for a phase."""

    model_config = ConfigDict(from_attributes=True)

    summary: str
    includes: list[str] = Field(default_factory=list)


class PhaseSummarySchema(BaseModel):
    """Phase summary for dashboard/listings."""

    id: int
    name: str
    slug: str
    description: str
    short_description: str
    estimated_weeks: str
    order: int
    topics_count: int
    objectives: list[str] = Field(default_factory=list)
    capstone: PhaseCapstoneOverviewSchema | None = None
    hands_on_verification: PhaseHandsOnVerificationOverviewSchema | None = None
    progress: PhaseProgressSchema | None = None
    is_locked: bool = False


class PhaseDetailSchema(BaseModel):
    """Full phase detail with topics."""

    id: int
    name: str
    slug: str
    description: str
    short_description: str
    estimated_weeks: str
    order: int
    objectives: list[str]
    capstone: PhaseCapstoneOverviewSchema | None = None
    hands_on_verification: PhaseHandsOnVerificationOverviewSchema | None = None
    topics: list[TopicSummarySchema]
    progress: PhaseProgressSchema | None = None
    hands_on_requirements: list[HandsOnRequirement] = Field(default_factory=list)
    hands_on_submissions: list[HandsOnSubmissionResponse] = Field(default_factory=list)
    is_locked: bool = False
    # Computed fields - frontend should NOT recalculate these
    all_topics_complete: bool = False
    all_hands_on_validated: bool = False
    is_phase_complete: bool = False


class UserSummarySchema(BaseModel):
    """User summary for dashboard."""

    id: str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None
    is_admin: bool = False


class DashboardResponse(BaseModel):
    """Complete dashboard data for a user."""

    user: UserSummarySchema
    phases: list[PhaseSummarySchema]
    overall_progress: float
    phases_completed: int
    phases_total: int
    current_phase: int | None = None
    badges: list[BadgeResponse] = Field(default_factory=list)
