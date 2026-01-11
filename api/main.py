"""FastAPI application for Learn to Cloud API."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared import get_settings, init_db
from routes import (
    health_router,
    users_router,
    checklist_router,
    github_router,
    webhooks_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan,
)


def _build_cors_origins() -> list[str]:
    """Build CORS origins list from settings."""
    settings = get_settings()
    origins = [
        "http://localhost:3000",
        "http://localhost:4280",
    ]
    if settings.frontend_url and settings.frontend_url not in origins:
        origins.append(settings.frontend_url)
    return origins


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(users_router)
app.include_router(checklist_router)
app.include_router(github_router)
app.include_router(webhooks_router)
