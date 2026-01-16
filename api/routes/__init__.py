"""API route modules."""

from routes.activity import router as activity_router
from routes.certificates import router as certificates_router
from routes.dashboard import router as dashboard_router
from routes.github import router as github_router
from routes.health import router as health_router
from routes.questions import router as questions_router
from routes.steps import router as steps_router
from routes.users import router as users_router
from routes.webhooks import router as webhooks_router

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
