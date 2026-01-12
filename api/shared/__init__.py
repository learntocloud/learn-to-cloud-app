"""Shared modules for Learn to Cloud API."""

from .config import get_settings, Settings
from .database import (
    init_db, Base, get_db, DbSession,
    get_engine, get_session_maker, reset_db_state,
    cleanup_old_webhooks, upsert_on_conflict,
)
from .models import User, ChecklistProgress, ProcessedWebhook, GitHubSubmission, SubmissionType
from .auth import get_user_id_from_request, require_auth, UserId
from .schemas import (
    UserResponse, ProgressItem, UserProgressResponse,
    GitHubRequirement, GitHubSubmissionRequest, GitHubSubmissionResponse,
    GitHubValidationResult, PhaseGitHubRequirementsResponse,
    AllPhasesGitHubRequirementsResponse,
    HealthResponse, ChecklistToggleResponse, WebhookResponse,
)
from .github import (
    get_requirements_for_phase, get_requirement_by_id,
    parse_github_url, validate_submission, ValidationResult,
    GITHUB_REQUIREMENTS
)
from .telemetry import (
    track_dependency,
    track_operation,
    add_custom_attribute,
    log_metric,
    RequestTimingMiddleware,
)

__all__ = [
    # Config
    "get_settings",
    "Settings",
    # Database
    "init_db",
    "Base",
    "get_db",
    "DbSession",
    "get_engine",
    "get_session_maker",
    "reset_db_state",
    "cleanup_old_webhooks",
    "upsert_on_conflict",
    # Models
    "User",
    "ChecklistProgress",
    "ProcessedWebhook",
    "GitHubSubmission",
    "SubmissionType",
    # Auth
    "get_user_id_from_request",
    "require_auth",
    "UserId",
    # Schemas
    "UserResponse",
    "ProgressItem",
    "UserProgressResponse",
    "GitHubRequirement",
    "GitHubSubmissionRequest",
    "GitHubSubmissionResponse",
    "GitHubValidationResult",
    "PhaseGitHubRequirementsResponse",
    "AllPhasesGitHubRequirementsResponse",
    "HealthResponse",
    "ChecklistToggleResponse",
    "WebhookResponse",
    # GitHub utilities
    "get_requirements_for_phase",
    "get_requirement_by_id",
    "parse_github_url",
    "validate_submission",
    "ValidationResult",
    "GITHUB_REQUIREMENTS",
    # Telemetry
    "track_dependency",
    "track_operation",
    "add_custom_attribute",
    "log_metric",
    "RequestTimingMiddleware",
]
