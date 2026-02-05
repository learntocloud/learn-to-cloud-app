"""API route modules."""

from routes.certificates_routes import router as certificates_router
from routes.clerk_routes import router as clerk_router
from routes.dashboard_routes import router as dashboard_router
from routes.github_routes import router as github_router
from routes.health_routes import router as health_router
from routes.steps_routes import router as steps_router
from routes.users_routes import router as users_router
from routes.webhooks_routes import router as webhooks_router

__all__ = [
    "certificates_router",
    "clerk_router",
    "dashboard_router",
    "github_router",
    "health_router",
    "steps_router",
    "users_router",
    "webhooks_router",
]
