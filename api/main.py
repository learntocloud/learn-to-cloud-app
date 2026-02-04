"""FastAPI application for Learn to Cloud API."""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from core.auth import close_clerk_client, init_clerk_client
from core.config import get_settings
from core.copilot_client import close_copilot_client
from core.database import (
    create_engine,
    create_session_maker,
    dispose_engine,
    init_db,
)
from core.logger import configure_logging, get_logger
from core.ratelimit import limiter, rate_limit_exceeded_handler
from core.telemetry import RequestTimingMiddleware, SecurityHeadersMiddleware
from repositories.webhook_repository import ProcessedWebhookRepository
from routes import (
    certificates_router,
    clerk_router,
    dashboard_router,
    github_router,
    health_router,
    steps_router,
    users_router,
    webhooks_router,
)
from services.clerk_service import close_http_client
from services.github_hands_on_verification_service import close_github_client

_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "y", "on"}


def _run_db_migrations_on_startup_enabled() -> bool:
    return os.getenv("RUN_MIGRATIONS_ON_STARTUP", "").strip().lower() in _TRUE_VALUES


def _run_alembic_upgrade_head_sync() -> None:
    # Import lazily so Alembic is only required when migrations are enabled.
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    api_dir = Path(__file__).resolve().parent
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))
    command.upgrade(cfg, "head")


def _configure_azure_monitor_if_enabled() -> None:
    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.monitor.opentelemetry import configure_azure_monitor

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


# Configure structured logging BEFORE Azure Monitor
configure_logging()
logger = get_logger(__name__)

_configure_azure_monitor_if_enabled()


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for unhandled exceptions.

    Logs the error with request context and returns a generic JSON response.
    Never exposes internal details to clients.
    """
    logger.exception(
        "unhandled.exception",
        exc_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


async def _background_cleanup(app: FastAPI) -> None:
    """Background cleanup tasks that are safe to run after startup."""
    try:
        async with app.state.session_maker() as session:
            deleted = await ProcessedWebhookRepository(session).delete_older_than(
                days=7
            )
            await session.commit()
            if deleted > 0:
                logger.info("webhooks.cleanup", deleted_count=deleted)
    except Exception as e:
        logger.warning("webhooks.cleanup.failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB engine at startup, dispose on shutdown.

    Database connectivity is verified synchronously before the app accepts
    requests so that early traffic never hits an uninitialised pool.
    Clerk SDK init runs concurrently with DB verification to overlap the
    heavy import cost with the network round-trip.
    """
    app.state.engine = create_engine()
    app.state.session_maker = create_session_maker(app.state.engine)

    app.state.init_done = False
    app.state.init_error = None

    try:
        if _run_db_migrations_on_startup_enabled():
            logger.info("migrations.starting")
            await asyncio.to_thread(_run_alembic_upgrade_head_sync)
            logger.info("migrations.complete")

        # Run Clerk SDK init (heavy import) concurrently with DB verification
        clerk_task = asyncio.to_thread(init_clerk_client)
        db_task = init_db(app.state.engine)
        await asyncio.gather(clerk_task, db_task)

        app.state.init_done = True
        logger.info("init.complete")
    except Exception as e:
        app.state.init_error = str(e)
        logger.error("init.failed", error=str(e), exc_info=True)
        raise

    cleanup_task = asyncio.create_task(_background_cleanup(app))

    try:
        yield
    finally:
        close_clerk_client()
        await close_http_client()
        await close_github_client()
        await close_copilot_client()
        await dispose_engine(app.state.engine)

        try:
            if not cleanup_task.done():
                await cleanup_task
            else:
                cleanup_task.result()
        except Exception:
            logger.exception("cleanup.background.failed")


app = FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(RequestTimingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Duration-Ms"],
)

app.include_router(health_router)
app.include_router(clerk_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(github_router)
app.include_router(webhooks_router)
app.include_router(certificates_router)
app.include_router(steps_router)
