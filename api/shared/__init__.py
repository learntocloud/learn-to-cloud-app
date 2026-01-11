"""Shared modules for Azure Functions."""

from .config import get_settings, Settings
from .database import get_db, init_db, Base, async_session
from .models import User, ChecklistProgress, ProcessedWebhook, CompletionStatus
from .auth import get_user_id_from_request
from .content import get_all_phases, get_phase_by_id, get_phase_by_slug, get_topic_by_slug, get_total_checklist_items
from .schemas import (
    Phase, PhaseWithProgress, PhaseDetailWithProgress, PhaseProgress,
    TopicWithProgress, ChecklistItemWithProgress, TopicChecklistItemWithProgress,
    DashboardResponse, UserResponse, Topic
)

__all__ = [
    "get_settings",
    "Settings",
    "get_db",
    "init_db",
    "Base",
    "async_session",
    "User",
    "ChecklistProgress",
    "ProcessedWebhook",
    "CompletionStatus",
    "get_user_id_from_request",
    "get_all_phases",
    "get_phase_by_id",
    "get_phase_by_slug",
    "get_topic_by_slug",
    "get_total_checklist_items",
    "Phase",
    "PhaseWithProgress",
    "PhaseDetailWithProgress",
    "PhaseProgress",
    "TopicWithProgress",
    "ChecklistItemWithProgress",
    "TopicChecklistItemWithProgress",
    "DashboardResponse",
    "UserResponse",
    "Topic",
]
