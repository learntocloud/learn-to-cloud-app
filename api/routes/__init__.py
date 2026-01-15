"""API route modules."""

from .activity import router as activity_router
from .certificates import router as certificates_router
from .dashboard import router as dashboard_router
from .github import router as github_router
from .health import router as health_router
from .questions import router as questions_router
from .steps import router as steps_router
from .users import router as users_router
from .webhooks import router as webhooks_router

__all__ = [
    "activity_router",
    "certificates_router",
    "dashboard_router",
    "github_router",
    "health_router",
    "questions_router",
    "steps_router",
    "users_router",
    "webhooks_router",
]
