"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from pydantic import BaseModel
from .models import CompletionStatus


# ============ User Schemas ============

class UserBase(BaseModel):
    """Base user schema."""
    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None


class UserResponse(UserBase):
    """User response schema."""
    id: str
    created_at: datetime
    
    class Config:
        from_attributes = True


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
