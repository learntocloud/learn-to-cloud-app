"""FastAPI application for Learn to Cloud API."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

# Configure Azure Monitor OpenTelemetry (must be done before other imports use logging)
# Only enable if connection string is provided (Azure environment)
if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    from azure.monitor.opentelemetry import (  # type: ignore[import-not-found]
        configure_azure_monitor,
    )

    configure_azure_monitor(
        enable_live_metrics=True,
        instrumentation_options={
            "azure_sdk": {"enabled": True},
            "flask": {"enabled": False},
            "django": {"enabled": False},
            "fastapi": {"enabled": True},
            "psycopg2": {"enabled": False},
            "requests": {"enabled": True},
            "urllib": {"enabled": True},
            "urllib3": {"enabled": True},
        },
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded

from routes import (
    activity_router,
    certificates_router,
    checklist_router,
    github_router,
    health_router,
    questions_router,
    reflections_router,
    users_router,
    webhooks_router,
)
from routes.users import close_http_client
from shared.config import get_settings
from shared.database import cleanup_old_webhooks, init_db
from shared.ratelimit import limiter, rate_limit_exceeded_handler
from shared.telemetry import RequestTimingMiddleware, SecurityHeadersMiddleware

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
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
    app.state.init_done = False
    app.state.init_error = None

    init_task = asyncio.create_task(_background_init())

    def _record_init_result(task: asyncio.Task[None]) -> None:
        try:
            task.result()
            app.state.init_done = True
            app.state.init_error = None
        except Exception as e:
            # Store a string to avoid leaking exception objects across boundaries.
            app.state.init_done = False
            app.state.init_error = str(e)

    init_task.add_done_callback(_record_init_result)

    try:
        yield
    finally:
        # Close reusable clients
        await close_http_client()

        # Ensure init completes (or at least observe/log failures) before shutdown.
        try:
            if not init_task.done():
                await init_task
            else:
                init_task.result()
        except Exception:
            logger.exception("Background initialization failed")


app = FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# GZip compression for responses > 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# Security headers middleware (adds X-Content-Type-Options, X-Frame-Options, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Request timing middleware (adds performance tracking and X-Request-Duration-Ms header)
app.add_middleware(RequestTimingMiddleware)

# CORS middleware - uses centralized allowed_origins from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Duration-Ms"],  # Expose timing header to frontend
)

# Include routers
app.include_router(health_router)
app.include_router(users_router)
app.include_router(checklist_router)
app.include_router(github_router)
app.include_router(webhooks_router)
app.include_router(questions_router)
app.include_router(reflections_router)
app.include_router(activity_router)
app.include_router(certificates_router)
