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
    created_at: datetime


# ============ Progress Schemas ============


class ProgressItem(BaseModel):
    """Single checklist progress item."""

    checklist_item_id: str
    is_completed: bool
    completed_at: datetime | None = None


class UserProgressResponse(BaseModel):
    """User's progress on all checklist items."""

    user_id: str
    items: list[ProgressItem]


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
    """Request to submit a URL for validation."""

    requirement_id: str = Field(max_length=100)
    submitted_url: str = Field(max_length=2048)  # Standard URL max length

    @field_validator("submitted_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure the URL is valid (GitHub or HTTPS)."""
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("URL must use HTTPS")
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


class ChecklistToggleResponse(BaseModel):
    """Response for checklist toggle."""

    success: bool
    item_id: str
    is_completed: bool


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


# ============ Daily Reflection Schemas ============


class ReflectionSubmitRequest(BaseModel):
    """Request to submit a daily reflection."""

    reflection_text: str = Field(min_length=10, max_length=1000)

    @field_validator("reflection_text")
    @classmethod
    def validate_reflection(cls, v: str) -> str:
        """Ensure reflection has meaningful content."""
        stripped = v.strip()
        if len(stripped) < 10:
            raise ValueError("Reflection must be at least 10 characters")
        return stripped


class ReflectionResponse(BaseModel):
    """Response for a reflection submission."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    reflection_date: date
    reflection_text: str
    ai_greeting: str | None = None
    created_at: datetime


class LatestGreetingResponse(BaseModel):
    """Response containing the latest AI-generated greeting."""

    has_greeting: bool
    greeting: str | None = None
    reflection_date: date | None = None
    user_first_name: str | None = None


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
    """Public user profile information."""

    username: str | None = None  # github_username or derived
    first_name: str | None = None
    avatar_url: str | None = None
    current_phase: int  # Highest unlocked phase
    completed_topics: int
    total_topics: int
    streak: StreakResponse
    activity_heatmap: ActivityHeatmapResponse
    member_since: datetime
    submissions: list[PublicSubmission] = []  # Validated GitHub submissions
