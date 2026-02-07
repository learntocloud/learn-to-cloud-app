"""API route modules."""

from routes.analytics_routes import router as analytics_router
from routes.auth_routes import router as auth_router
from routes.certificates_routes import router as certificates_router
from routes.health_routes import router as health_router
from routes.htmx_routes import router as htmx_router
from routes.pages_routes import router as pages_router
from routes.users_routes import router as users_router

__all__ = [
    "analytics_router",
    "auth_router",
    "certificates_router",
    "health_router",
    "htmx_router",
    "pages_router",
    "users_router",
]
