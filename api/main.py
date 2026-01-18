"""FastAPI application for Learn to Cloud API."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.errors import RateLimitExceeded

from core.auth import close_clerk_client, init_clerk_client
from core.config import get_settings
from core.database import get_session_maker, init_db
from core.ratelimit import limiter, rate_limit_exceeded_handler
from core.telemetry import RequestTimingMiddleware, SecurityHeadersMiddleware
from repositories.webhook_repository import ProcessedWebhookRepository
from routes import (
    activity_router,
    certificates_router,
    dashboard_router,
    github_router,
    health_router,
    questions_router,
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


log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

_configure_azure_monitor_if_enabled()


async def _background_init():
    """Background initialization tasks (non-blocking for faster cold start)."""
    if _run_db_migrations_on_startup_enabled():
        logger.info("Running database migrations on startup...")
        await asyncio.to_thread(_run_alembic_upgrade_head_sync)
        logger.info("Database migrations complete")

    await init_db()

    try:
        session_maker = get_session_maker()
        async with session_maker() as session:
            deleted = await ProcessedWebhookRepository(session).delete_older_than(
                days=7
            )
            await session.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old processed webhook entries")
    except Exception as e:
        logger.warning(f"Failed to cleanup old webhooks: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database in background for faster cold start."""
    # Initialize Clerk client synchronously at startup
    init_clerk_client()

    app.state.init_done = False
    app.state.init_error = None

    init_task = asyncio.create_task(_background_init())

    def _record_init_result(task: asyncio.Task[None]) -> None:
        try:
            task.result()
            app.state.init_done = True
            app.state.init_error = None
            logger.info("Background initialization completed successfully")
        except Exception as e:
            app.state.init_done = False
            app.state.init_error = str(e)
            logger.error(f"Background initialization failed: {e}", exc_info=True)

    init_task.add_done_callback(_record_init_result)

    try:
        yield
    finally:
        close_clerk_client()
        await close_http_client()
        await close_github_client()

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

app.state.limiter = limiter
# ty has incomplete ParamSpec+Protocol support (astral-sh/ty#2382)
app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_exceeded_handler,  # ty: ignore[invalid-argument-type]
)

app.add_middleware(
    GZipMiddleware,  # ty: ignore[invalid-argument-type]
    minimum_size=500,
)

app.add_middleware(SecurityHeadersMiddleware)  # ty: ignore[invalid-argument-type]

app.add_middleware(RequestTimingMiddleware)  # ty: ignore[invalid-argument-type]

app.add_middleware(
    CORSMiddleware,  # ty: ignore[invalid-argument-type]
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Duration-Ms"],
)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(github_router)
app.include_router(webhooks_router)
app.include_router(questions_router)
app.include_router(activity_router)
app.include_router(certificates_router)
app.include_router(steps_router)
