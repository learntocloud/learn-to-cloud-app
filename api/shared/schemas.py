"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from .models import CompletionStatus, SubmissionType


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


# ============ Learning Step Schemas ============

class LearningStep(BaseModel):
    """A learning step/resource within a topic."""
    order: int
    text: str
    url: str | None = None


# ============ Topic Schemas ============

class TopicChecklistItem(BaseModel):
    """Checklist item within a topic."""
    id: str
    text: str
    order: int


class Topic(BaseModel):
    """Topic definition from static content."""
    id: str
    name: str
    slug: str
    description: str
    estimated_time: str | None = None
    order: int
    is_capstone: bool = False
    learning_steps: list[LearningStep] = []
    checklist: list[TopicChecklistItem] = []


class TopicChecklistItemWithProgress(TopicChecklistItem):
    """Topic checklist item with user's progress."""
    is_completed: bool = False
    completed_at: datetime | None = None


class TopicWithProgress(BaseModel):
    """Topic with user's checklist progress."""
    id: str
    name: str
    slug: str
    description: str
    estimated_time: str | None = None
    order: int
    is_capstone: bool = False
    learning_steps: list[LearningStep] = []
    checklist: list[TopicChecklistItemWithProgress] = []
    items_completed: int = 0
    items_total: int = 0


# ============ Phase Checklist Schemas ============

class ChecklistItem(BaseModel):
    """Phase-level checklist item definition."""
    id: str
    text: str
    order: int


class ChecklistItemWithProgress(ChecklistItem):
    """Checklist item with user's progress."""
    is_completed: bool = False
    completed_at: datetime | None = None


# ============ Phase Schemas ============

class PhaseProgress(BaseModel):
    """User's progress on a phase."""
    phase_id: int
    checklist_completed: int
    checklist_total: int
    percentage: float
    status: CompletionStatus


class Phase(BaseModel):
    """Phase definition from static content."""
    id: int
    name: str
    slug: str
    description: str
    estimated_weeks: str
    order: int
    prerequisites: list[str] = []
    topics: list[Topic] = []
    checklist: list[ChecklistItem] = []


class PhaseWithProgress(Phase):
    """Phase with user's progress summary."""
    progress: PhaseProgress | None = None


class PhaseDetailWithProgress(Phase):
    """Phase with full topic and checklist progress."""
    topics: list[TopicWithProgress] = []
    checklist: list[ChecklistItemWithProgress] = []
    progress: PhaseProgress | None = None


# ============ Dashboard Schemas ============

class DashboardResponse(BaseModel):
    """User dashboard with overall progress."""
    user: UserResponse
    phases: list[PhaseWithProgress]
    overall_progress: float
    total_completed: int
    total_items: int
    current_phase: int | None = None


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
    required_repo: str | None = None  # e.g., "learntocloud/linux-ctfs" for fork validation
    expected_endpoint: str | None = None  # e.g., "/entries" for deployed app validation


class GitHubSubmissionRequest(BaseModel):
    """Request to submit a URL for validation."""
    requirement_id: str
    submitted_url: str
    
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
    submission_type: str
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
    all_validated: bool
