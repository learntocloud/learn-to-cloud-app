"""API route modules."""

from routes.activity_routes import router as activity_router
from routes.certificates_routes import router as certificates_router
from routes.dashboard_routes import router as dashboard_router
from routes.github_routes import router as github_router
from routes.health_routes import router as health_router
from routes.questions_routes import router as questions_router
from routes.steps_routes import router as steps_router
from routes.users_routes import router as users_router
from routes.webhooks_routes import router as webhooks_router

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
