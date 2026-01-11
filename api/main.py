"""FastAPI application for Learn to Cloud API."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from shared import get_settings, init_db, cleanup_old_webhooks
from routes import (
    health_router,
    users_router,
    checklist_router,
    github_router,
    webhooks_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _background_init():
    """Background initialization tasks (non-blocking for faster cold start)."""
    await init_db()
    
    # Cleanup old processed webhooks (older than 7 days)
    try:
        deleted = await cleanup_old_webhooks(days=7)
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old processed webhook entries")
    except Exception as e:
        logger.warning(f"Failed to cleanup old webhooks: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database in background for faster cold start."""
    # Start init in background - don't block server startup
    # This allows the health endpoint to respond immediately
    init_task = asyncio.create_task(_background_init())
    
    yield
    
    # Ensure init completes before shutdown
    if not init_task.done():
        await init_task


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


# GZip compression for responses > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

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
