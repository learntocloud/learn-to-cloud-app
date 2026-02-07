"""FastAPI application for Learn to Cloud API."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from core.auth import init_oauth
from core.config import get_settings
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
from routes import (
    auth_router,
    certificates_router,
    health_router,
    htmx_router,
    pages_router,
    users_router,
)
from services.deployed_api_verification_service import close_deployed_api_client
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

# Jinja2 templates
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


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


async def _background_warmup(app: FastAPI) -> None:
    """Warm caches in the background after the app starts serving.

    Runs pool warming and content preloading concurrently so early
    requests benefit from warm caches without blocking startup.
    """
    from services.content_service import get_all_phases
    from services.progress_service import get_all_phase_ids

    async def _warm_content() -> None:
        try:
            get_all_phases()
            get_all_phase_ids()  # triggers _build_phase_requirements()
            logger.info("content.preloaded")
        except Exception as e:
            logger.warning("content.preload.failed", error=str(e))

    await asyncio.gather(
        warm_pool(app.state.engine),
        _warm_content(),
        return_exceptions=True,
    )


def _run_alembic_migrations() -> None:
    """Run Alembic migrations synchronously.

    Called from lifespan via asyncio.to_thread(). Uses psycopg2 sync driver
    and advisory locks (handled by alembic/env.py) for multi-worker safety.
    """
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("migrations.complete")
    except Exception:
        logger.exception("migrations.failed")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB engine at startup, dispose on shutdown.

    Database connectivity is verified synchronously before the app accepts
    requests so that early traffic never hits an uninitialised pool.

    Runs Alembic migrations inline (not as an init container) because Azure
    Container Apps init containers don't have access to the managed identity
    sidecar needed for Entra ID database auth.
    """
    app.state.engine = create_engine()
    app.state.session_maker = create_session_maker(app.state.engine)

    app.state.init_done = False
    app.state.init_error = None

    try:
        # Initialize OAuth and DB concurrently
        oauth_task = asyncio.to_thread(init_oauth)
        db_task = init_db(app.state.engine)
        await asyncio.gather(oauth_task, db_task)

        # Run Alembic migrations in a thread (uses sync psycopg2 driver)
        await asyncio.to_thread(_run_alembic_migrations)

        app.state.init_done = True
        logger.info("init.complete")
    except Exception as e:
        app.state.init_error = str(e)
        logger.error("init.failed", error=str(e), exc_info=True)
        raise

    # Fire-and-forget background tasks that run AFTER the app starts
    # serving requests.  These warm caches so that early requests are
    # faster, but they never block startup.
    warmup_task = asyncio.create_task(_background_warmup(app))

    try:
        yield
    finally:
        if not warmup_task.done():
            warmup_task.cancel()
        try:
            await warmup_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("background.task.failed")

        await close_github_client()
        await close_deployed_api_client()
        await dispose_engine(app.state.engine)


_settings = get_settings()

app = FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.enable_docs or _settings.debug else None,
    redoc_url="/redoc" if _settings.enable_docs or _settings.debug else None,
    openapi_url="/openapi.json" if _settings.enable_docs or _settings.debug else None,
)

# Store templates on app state for access in route handlers
app.state.templates = templates

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Session middleware (signed cookies for auth)
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.session_secret_key,
    session_cookie="session",
    max_age=60 * 60 * 24 * 30,  # 30 days
    same_site="lax",
    https_only=_settings.require_https,
)

app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(RequestTimingMiddleware)

if _settings.debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-Duration-Ms", "X-Request-Id"],
        max_age=600,
    )

# Mount static files
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# API routes (JSON)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(certificates_router)
app.include_router(users_router)

# HTMX routes (HTML fragments)
app.include_router(htmx_router)

# Page routes (HTML - must be last to avoid catching API routes)
app.include_router(pages_router)
