"""Shared modules for Learn to Cloud API."""

from .auth import UserId, get_user_id_from_request, require_auth
from .config import Settings, get_settings
from .ctf import CTFVerificationResult, verify_ctf_token
from .database import (
    Base,
    DbSession,
    cleanup_old_webhooks,
    get_db,
    get_engine,
    get_session_maker,
    init_db,
    reset_db_state,
    upsert_on_conflict,
)
from .github import (
    GITHUB_REQUIREMENTS,
    ValidationResult,
    get_requirement_by_id,
    get_requirements_for_phase,
    parse_github_url,
    validate_submission,
)
from .models import (
    GitHubSubmission,
    ProcessedWebhook,
    SubmissionType,
    User,
)
from .schemas import (
    AllPhasesGitHubRequirementsResponse,
    GitHubRequirement,
    GitHubSubmissionRequest,
    GitHubSubmissionResponse,
    GitHubValidationResult,
    HealthResponse,
    PhaseGitHubRequirementsResponse,
    UserResponse,
    WebhookResponse,
)
from .telemetry import (
    RequestTimingMiddleware,
    add_custom_attribute,
    log_metric,
    track_dependency,
    track_operation,
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
    "ProcessedWebhook",
    "GitHubSubmission",
    "SubmissionType",
    # Auth
    "get_user_id_from_request",
    "require_auth",
    "UserId",
    # Schemas
    "UserResponse",
    "GitHubRequirement",
    "GitHubSubmissionRequest",
    "GitHubSubmissionResponse",
    "GitHubValidationResult",
    "PhaseGitHubRequirementsResponse",
    "AllPhasesGitHubRequirementsResponse",
    "HealthResponse",
    "WebhookResponse",
    # GitHub utilities
    "get_requirements_for_phase",
    "get_requirement_by_id",
    "parse_github_url",
    "validate_submission",
    "ValidationResult",
    "GITHUB_REQUIREMENTS",
    # CTF verification
    "verify_ctf_token",
    "CTFVerificationResult",
    # Telemetry
    "track_dependency",
    "track_operation",
    "add_custom_attribute",
    "log_metric",
    "RequestTimingMiddleware",
]
