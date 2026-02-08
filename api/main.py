"""FastAPI application for Learn to Cloud API."""

import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# ── OTel must be configured BEFORE importing FastAPI ──────────────────
# Azure Monitor's FastAPI instrumentor monkey-patches FastAPI at import
# time. If FastAPI is imported first, requests won't appear in AppRequests.
# See: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-monitor/
#      app-insights/telemetry/opentelemetry-troubleshooting-python


def _configure_observability() -> None:
    """Set up Azure Monitor + Agent Framework observability if configured."""
    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        return

    try:
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
    except (ValueError, Exception) as exc:
        # Invalid connection string (e.g. placeholder instrumentation key)
        # — log warning and continue without Azure Monitor
        import logging

        logging.getLogger(__name__).warning(
            "azure.monitor.init.failed",
            extra={"error": str(exc)},
        )
        return

    # Enable Agent Framework built-in OTel tracing for LLM calls.
    # Skip if Azure Monitor already configured providers — calling
    # setup_observability() would override them and trigger
    # "Overriding of current TracerProvider" warnings.
    try:
        from opentelemetry.trace import get_tracer_provider

        provider = get_tracer_provider()
        already_configured = type(provider).__name__ != "ProxyTracerProvider"
        if not already_configured:
            from agent_framework.observability import setup_observability

            setup_observability()
    except (ImportError, Exception):
        pass


_configure_observability()

# ── Now safe to import FastAPI and everything else ────────────────────
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from core.auth import init_oauth  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.database import (  # noqa: E402
    create_engine,
    create_session_maker,
    dispose_engine,
    init_db,
    warm_pool,
)
from core.logger import configure_logging  # noqa: E402
from core.ratelimit import limiter, rate_limit_exceeded_handler  # noqa: E402
from core.telemetry import (  # noqa: E402
    SecurityHeadersMiddleware,
    UserTrackingMiddleware,
    add_user_span_processor,
)
from routes import (  # noqa: E402
    analytics_router,
    auth_router,
    certificates_router,
    health_router,
    htmx_router,
    pages_router,
    users_router,
)
from services.deployed_api_verification_service import (  # noqa: E402
    close_deployed_api_client,
)
from services.github_hands_on_verification_service import (  # noqa: E402
    close_github_client,
)

configure_logging()
logger = logging.getLogger(__name__)

# Jinja2 templates
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _build_static_file_hashes(static_dir: Path) -> dict[str, str]:
    """Compute short content hashes for static files (cache-busting)."""
    hashes: dict[str, str] = {}
    if not static_dir.exists():
        return hashes
    for file_path in static_dir.rglob("*"):
        if file_path.is_file():
            rel = file_path.relative_to(static_dir).as_posix()
            digest = hashlib.md5(file_path.read_bytes()).hexdigest()[:8]  # noqa: S324
            hashes[rel] = digest
    return hashes


_static_hashes: dict[str, str] = {}


def _static_url(path: str) -> str:
    """Return a cache-busted static URL, e.g. /static/css/styles.css?v=a1b2c3d4."""
    version = _static_hashes.get(path, "")
    if version:
        return f"/static/{path}?v={version}"
    return f"/static/{path}"


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


async def _run_alembic_migrations() -> None:
    """Run Alembic migrations in a subprocess.

    psycopg2's connection pool cleanup deadlocks inside
    asyncio.to_thread when uvloop is the event loop.  Running
    migrations as a subprocess avoids the issue entirely.
    """
    import subprocess
    import sys

    result = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-c",
            (
                "from alembic import command; "
                "from alembic.config import Config; "
                "command.upgrade(Config('alembic.ini'), 'head')"
            ),
        ],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("migrations.failed", extra={"stderr": stderr})
        raise RuntimeError(f"Alembic migration failed:\n{stderr}")

    logger.info("migrations.complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB engine at startup, dispose on shutdown."""
    app.state.engine = create_engine()
    app.state.session_maker = create_session_maker(app.state.engine)

    app.state.init_done = False
    app.state.init_error = None

    try:
        async with asyncio.timeout(60):
            oauth_task = asyncio.to_thread(init_oauth)
            db_task = init_db(app.state.engine)
            await asyncio.gather(oauth_task, db_task)

        async with asyncio.timeout(120):
            await _run_alembic_migrations()

        app.state.init_done = True
        logger.info("init.complete")
    except TimeoutError:
        logger.error(
            "init.timeout",
            extra={
                "init_done": app.state.init_done,
                "hint": "Startup hung — check DB connectivity and migration state",
            },
        )
        raise RuntimeError("Application startup timed out")
    except Exception as e:
        app.state.init_error = str(e)
        logger.error("init.failed: %s", e, exc_info=True)
        raise

    warmup_task = asyncio.create_task(_background_warmup(app))

    # Pre-compute analytics immediately, then refresh hourly.
    # Runs in background so startup isn't blocked.
    from services.analytics_service import analytics_refresh_loop

    analytics_task = asyncio.create_task(
        analytics_refresh_loop(app.state.session_maker)
    )

    try:
        yield
    finally:
        for task in (warmup_task, analytics_task):
            if not task.done():
                task.cancel()
            try:
                await task
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
app.add_middleware(UserTrackingMiddleware)

add_user_span_processor()

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

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    _static_hashes.update(_build_static_file_hashes(_static_dir))
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# Expose cache-busted URL helper to all Jinja2 templates
templates.env.globals["static_url"] = _static_url

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
