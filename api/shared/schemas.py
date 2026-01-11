"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from .models import SubmissionType


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
