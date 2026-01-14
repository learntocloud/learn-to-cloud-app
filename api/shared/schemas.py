"""Pydantic schemas for API request/response validation."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import ActivityType, SubmissionType

# ============ User Schemas ============


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


# ============ GitHub Submission Schemas ============


class GitHubRequirement(BaseModel):
    """A requirement for phase completion (GitHub or deployed app)."""

    id: str  # e.g., "phase1-profile-readme"
    phase_id: int
    submission_type: SubmissionType
    name: str
    description: str
    example_url: str | None = None
    required_repo: str | None = (
        None  # e.g., "learntocloud/linux-ctfs" for fork validation
    )
    expected_endpoint: str | None = None  # e.g., "/entries" for deployed app validation


class GitHubSubmissionRequest(BaseModel):
    """Request to submit a URL or CTF token for validation."""

    requirement_id: str = Field(max_length=100)
    submitted_url: str = Field(max_length=4096)  # Increased for base64 CTF tokens

    @field_validator("submitted_url")
    @classmethod
    def validate_submission_value(cls, v: str) -> str:
        """Validate the submitted value (URL or CTF token).

        For URLs: must use HTTPS
        For CTF tokens: base64 encoded string (no protocol check)
        """
        v = v.strip()
        # Allow base64 CTF tokens (they don't start with a protocol)
        # CTF tokens are base64 encoded JSON, so they contain alphanumeric, +, /, =
        if not v:
            raise ValueError("Submission value cannot be empty")
        return v


class GitHubSubmissionResponse(BaseModel):
    """Response for a submission."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_url: str
    github_username: str | None = None
    is_validated: bool
    validated_at: datetime | None = None
    created_at: datetime


class GitHubValidationResult(BaseModel):
    """Result of validating a GitHub submission."""

    is_valid: bool
    message: str
    username_match: bool
    repo_exists: bool
    submission: GitHubSubmissionResponse | None = None


class PhaseGitHubRequirementsResponse(BaseModel):
    """GitHub requirements for a phase with user's submission status."""

    phase_id: int
    requirements: list[GitHubRequirement]
    submissions: list[GitHubSubmissionResponse]
    has_requirements: bool  # False if phase has no requirements defined
    all_validated: bool  # True if all requirements are validated (or no requirements)


class AllPhasesGitHubRequirementsResponse(BaseModel):
    """GitHub requirements for all phases (bulk endpoint)."""

    phases: list[PhaseGitHubRequirementsResponse]


# ============ Health Check Schema ============


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


class WebhookResponse(BaseModel):
    """Response for webhook processing."""

    status: str
    event_type: str | None = None


# ============ Question Attempt Schemas ============


class QuestionSubmitRequest(BaseModel):
    """Request to submit an answer to a knowledge question."""

    topic_id: str = Field(max_length=100)
    question_id: str = Field(max_length=100)
    user_answer: str = Field(min_length=10, max_length=2000)

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


class QuestionStatusResponse(BaseModel):
    """Status of a single question for a user."""

    question_id: str
    is_passed: bool
    attempts_count: int
    last_attempt_at: datetime | None = None


class TopicQuestionsStatusResponse(BaseModel):
    """Status of all questions in a topic for a user."""

    topic_id: str
    questions: list[QuestionStatusResponse]
    all_passed: bool
    total_questions: int
    passed_questions: int


# ============ Activity & Streak Schemas ============


class ActivityLogRequest(BaseModel):
    """Request to log a user activity."""

    activity_type: ActivityType
    reference_id: str | None = Field(default=None, max_length=100)


class ActivityResponse(BaseModel):
    """Response for a logged activity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_type: ActivityType
    activity_date: date
    reference_id: str | None = None
    created_at: datetime


# ============ Step Progress Schemas ============


class StepCompleteRequest(BaseModel):
    """Request to mark a learning step as complete."""

    topic_id: str = Field(max_length=100)
    step_order: int = Field(ge=1)


class StepProgressResponse(BaseModel):
    """Response for a single step's progress."""

    model_config = ConfigDict(from_attributes=True)

    topic_id: str
    step_order: int
    completed_at: datetime


class TopicStepProgressResponse(BaseModel):
    """Progress of all steps in a topic for a user."""

    topic_id: str
    completed_steps: list[int]  # List of step_order numbers that are complete
    total_steps: int
    next_unlocked_step: int  # The next step that can be completed (1-indexed)


class StreakResponse(BaseModel):
    """Response containing user's streak information."""

    current_streak: int  # Days in current streak
    longest_streak: int  # All-time longest streak
    total_activity_days: int  # Total days with any activity
    last_activity_date: date | None = None
    streak_alive: bool  # Is the streak still active (within forgiveness window)?


class ActivityHeatmapDay(BaseModel):
    """Activity count for a single day (for heatmap display)."""

    date: date
    count: int
    activity_types: list[ActivityType]


class ActivityHeatmapResponse(BaseModel):
    """Activity heatmap data for profile display."""

    days: list[ActivityHeatmapDay]
    start_date: date
    end_date: date
    total_activities: int


# ============ Badge Schemas ============


class BadgeResponse(BaseModel):
    """A badge earned by a user."""

    id: str
    name: str
    description: str
    icon: str


# ============ User Profile Schemas ============


class PublicSubmission(BaseModel):
    """A validated submission for public display."""

    requirement_id: str
    submission_type: SubmissionType
    phase_id: int
    submitted_url: str
    name: str  # Human-readable name from requirements
    validated_at: datetime | None = None


class PublicProfileResponse(BaseModel):
    """Public user profile information.

    Progress is tracked at the phase level:
    - A phase is complete when all steps + questions + GitHub requirements are done
    - phases_completed counts fully completed phases
    - current_phase is the first incomplete phase (or highest if all done)
    """

    username: str | None = None  # github_username or derived
    first_name: str | None = None
    avatar_url: str | None = None
    current_phase: int  # First incomplete phase (or highest if all done)
    phases_completed: int  # Count of fully completed phases (steps + questions + GitHub)
    streak: StreakResponse
    activity_heatmap: ActivityHeatmapResponse
    member_since: datetime
    submissions: list[PublicSubmission] = []  # Validated GitHub submissions
    badges: list[BadgeResponse] = []  # Earned badges


# ============ Certificate Schemas ============


class CertificateEligibilityResponse(BaseModel):
    """Response for checking certificate eligibility."""

    is_eligible: bool
    certificate_type: str  # "full_completion"
    topics_completed: int  # Actually questions passed, kept for API compatibility
    total_topics: int  # Actually total questions, kept for API compatibility
    completion_percentage: float
    already_issued: bool
    existing_certificate_id: int | None = None
    message: str


class CertificateRequest(BaseModel):
    """Request to generate a certificate."""

    certificate_type: str = Field(
        default="full_completion",
        pattern=r"^full_completion$",  # Only full completion certificate is supported
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
    topics_completed: int
    total_topics: int


class CertificateVerifyResponse(BaseModel):
    """Response for certificate verification."""

    is_valid: bool
    certificate: CertificateResponse | None = None
    message: str


class UserCertificatesResponse(BaseModel):
    """All certificates for a user."""

    certificates: list[CertificateResponse]
    full_completion_eligible: bool
