"""Shared modules for Azure Functions."""

from .config import get_settings, Settings
from .database import get_db, init_db, Base, async_session
from .models import User, ChecklistProgress, ProcessedWebhook, CompletionStatus, GitHubSubmission, SubmissionType
from .auth import get_user_id_from_request
from .schemas import (
    UserResponse, ProgressItem, UserProgressResponse,
    GitHubRequirement, GitHubSubmissionRequest, GitHubSubmissionResponse,
    GitHubValidationResult, PhaseGitHubRequirementsResponse
)
from .github import (
    get_requirements_for_phase, get_requirement_by_id,
    parse_github_url, validate_submission, ValidationResult,
    GITHUB_REQUIREMENTS
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
    "GitHubSubmission",
    "SubmissionType",
    "get_user_id_from_request",
    "UserResponse",
    "ProgressItem",
    "UserProgressResponse",
    "GitHubRequirement",
    "GitHubSubmissionRequest",
    "GitHubSubmissionResponse",
    "GitHubValidationResult",
    "PhaseGitHubRequirementsResponse",
    "get_requirements_for_phase",
    "get_requirement_by_id",
    "parse_github_url",
    "validate_submission",
    "ValidationResult",
    "GITHUB_REQUIREMENTS",
]
