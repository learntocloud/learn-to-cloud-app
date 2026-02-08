"""FastAPI application for Learn to Cloud API."""

import asyncio
import logging
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
from core.logger import configure_logging
from core.ratelimit import limiter, rate_limit_exceeded_handler
from core.telemetry import SecurityHeadersMiddleware
from routes import (
    analytics_router,
    auth_router,
    certificates_router,
    health_router,
    htmx_router,
    pages_router,
    users_router,
)
from services.deployed_api_verification_service import close_deployed_api_client
from services.github_hands_on_verification_service import close_github_client


def _configure_observability() -> None:
    """Set up Azure Monitor + Agent Framework observability if configured."""
    if not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return

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

    # Enable Agent Framework built-in OTel tracing for LLM calls
    try:
        from agent_framework.observability import setup_observability

        setup_observability()
    except (ImportError, Exception):
        pass


# 1. Azure Monitor + OTel (adds LoggingHandler to root logger)
# 2. configure_logging() preserves OTel handler, adds stdout handler
_configure_observability()
configure_logging()
logger = logging.getLogger(__name__)

# Jinja2 templates
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for unhandled exceptions."""
    logger.exception(
        "unhandled.exception",
        extra={
            "exc_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handler for request validation errors."""
    if not isinstance(exc, RequestValidationError):
        return JSONResponse(status_code=500, content={"detail": "Unexpected error"})

    logger.warning(
        "request.validation_error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_count": len(exc.errors()),
        },
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


async def _background_warmup(app: FastAPI) -> None:
    """Warm caches in the background after the app starts serving."""
    from services.content_service import get_all_phases
    from services.progress_service import get_all_phase_ids

    async def _warm_content() -> None:
        try:
            get_all_phases()
            get_all_phase_ids()
            logger.info("content.preloaded")
        except Exception:
            logger.warning("content.preload.failed", exc_info=True)

    await asyncio.gather(
        warm_pool(app.state.engine),
        _warm_content(),
        return_exceptions=True,
    )


def _run_alembic_migrations() -> None:
    """Run Alembic migrations synchronously."""
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
    """Create DB engine at startup, dispose on shutdown."""
    app.state.engine = create_engine()
    app.state.session_maker = create_session_maker(app.state.engine)

    app.state.init_done = False
    app.state.init_error = None

    try:
        oauth_task = asyncio.to_thread(init_oauth)
        db_task = init_db(app.state.engine)
        await asyncio.gather(oauth_task, db_task)

        await asyncio.to_thread(_run_alembic_migrations)

        app.state.init_done = True
        logger.info("init.complete")
    except Exception as e:
        app.state.init_error = str(e)
        logger.error("init.failed: %s", e, exc_info=True)
        raise

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
    openapi_url=("/openapi.json" if _settings.enable_docs or _settings.debug else None),
)

app.state.templates = templates
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.session_secret_key,
    session_cookie="session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=_settings.require_https,
)

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)

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
app.include_router(analytics_router)

# HTMX routes (HTML fragments)
app.include_router(htmx_router)

# Page routes (HTML - must be last to avoid catching API routes)
app.include_router(pages_router)
