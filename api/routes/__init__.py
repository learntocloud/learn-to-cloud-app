"""API route modules."""

from routes.auth_routes import router as auth_router
from routes.certificates_routes import router as certificates_router
from routes.dashboard_routes import router as dashboard_router
from routes.github_routes import router as github_router
from routes.health_routes import router as health_router
from routes.htmx_routes import router as htmx_router
from routes.pages_routes import router as pages_router
from routes.steps_routes import router as steps_router
from routes.users_routes import router as users_router

__all__ = [
    "auth_router",
    "certificates_router",
    "dashboard_router",
    "github_router",
    "health_router",
    "htmx_router",
    "pages_router",
    "steps_router",
    "users_router",
]
