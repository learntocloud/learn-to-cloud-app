"""API route modules."""

from learn_to_cloud.routes.auth_routes import router as auth_router
from learn_to_cloud.routes.health_routes import router as health_router
from learn_to_cloud.routes.htmx_routes import router as htmx_router
from learn_to_cloud.routes.pages_routes import router as pages_router
from learn_to_cloud.routes.users_routes import router as users_router

__all__ = [
    "auth_router",
    "health_router",
    "htmx_router",
    "pages_router",
    "users_router",
]
