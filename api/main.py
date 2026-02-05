"""FastAPI application for Learn to Cloud API."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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
    warm_pool,
)
from core.logger import configure_logging, get_logger
from core.ratelimit import limiter, rate_limit_exceeded_handler
from core.telemetry import RequestTimingMiddleware, SecurityHeadersMiddleware
from core.wide_event import get_wide_event
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
from routes.clerk_routes import close_clerk_proxy_client
from services.clerk_service import close_http_client
from services.github_hands_on_verification_service import close_github_client


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
    event = get_wide_event()
    request_id = event.get("request_id", "unknown")
    logger.exception(
        "unhandled.exception",
        request_id=request_id,
        exc_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handler for request validation errors.

    Logs validation failures with request context for debugging
    and returns a consistent JSON error response.
    """
    if not isinstance(exc, RequestValidationError):
        return JSONResponse(status_code=500, content={"detail": "Unexpected error"})

    event = get_wide_event()
    request_id = event.get("request_id", "unknown")
    logger.warning(
        "request.validation_error",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        error_count=len(exc.errors()),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
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


async def _background_warmup(app: FastAPI) -> None:
    """Warm caches in the background after the app starts serving.

    Runs pool warming and content preloading concurrently so early
    requests benefit from warm caches without blocking startup.
    """
    from services.content_service import get_all_phases

    async def _warm_content() -> None:
        try:
            get_all_phases()
            logger.info("content.preloaded")
        except Exception as e:
            logger.warning("content.preload.failed", error=str(e))

    await asyncio.gather(
        warm_pool(app.state.engine),
        _warm_content(),
        return_exceptions=True,
    )


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

    # Fire-and-forget background tasks that run AFTER the app starts
    # serving requests.  These warm caches so that early requests are
    # faster, but they never block startup.
    cleanup_task = asyncio.create_task(_background_cleanup(app))
    warmup_task = asyncio.create_task(_background_warmup(app))

    try:
        yield
    finally:
        # Cancel background tasks *before* disposing the engine
        # so they don't try to use an already-closed connection pool.
        for task in (cleanup_task, warmup_task):
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("background.task.failed")

        close_clerk_client()
        await close_clerk_proxy_client()
        await close_http_client()
        await close_github_client()
        await close_copilot_client()
        await dispose_engine(app.state.engine)


_settings = get_settings()
_is_production = _settings.environment != "development"

app = FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
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
    expose_headers=["X-Request-Duration-Ms", "X-Request-Id"],
    max_age=600,
)

app.include_router(health_router)
app.include_router(clerk_router)
app.include_router(users_router)
app.include_router(dashboard_router)
app.include_router(github_router)
app.include_router(webhooks_router)
app.include_router(certificates_router)
app.include_router(steps_router)
