"""FastAPI application for Learn to Cloud API."""

import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import fastapi
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
from core.middleware import (
    SecurityHeadersMiddleware,
    UserTrackingMiddleware,
)
from core.observability import configure_observability, instrument_app
from core.ratelimit import limiter, rate_limit_exceeded_handler
from routes import (
    analytics_router,
    auth_router,
    certificates_router,
    health_router,
    htmx_router,
    pages_router,
    users_router,
)
from services.deployed_api_verification_service import (
    close_deployed_api_client,
)
from services.github_hands_on_verification_service import (
    close_github_client,
)

# OTel must be configured before fastapi.FastAPI() is instantiated.
# Azure Monitor replaces fastapi.FastAPI at instrument time; module-level
# attribute lookup picks up the patched class.
# See: https://learn.microsoft.com/en-us/troubleshoot/azure/azure-monitor/
#      app-insights/telemetry/opentelemetry-troubleshooting-python
configure_observability()
configure_logging()
logger = logging.getLogger(__name__)

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
            digest = hashlib.md5(file_path.read_bytes()).hexdigest()[:8]
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


async def _background_warmup(app: fastapi.FastAPI) -> None:
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

    cmd = [
        sys.executable,
        "-c",
        (
            "from alembic import command; "
            "from alembic.config import Config; "
            "command.upgrade(Config('alembic.ini'), 'head')"
        ),
    ]
    cwd = Path(__file__).parent

    result = await asyncio.to_thread(
        lambda: subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=120
        )
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("migrations.failed", extra={"stderr": stderr})
        raise RuntimeError(f"Alembic migration failed:\n{stderr}")

    logger.info("migrations.complete")


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
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

app = fastapi.FastAPI(
    title="Learn to Cloud API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.enable_docs or _settings.debug else None,
    redoc_url="/redoc" if _settings.enable_docs or _settings.debug else None,
    openapi_url=("/openapi.json" if _settings.enable_docs or _settings.debug else None),
)

instrument_app(app)

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

templates.env.globals["static_url"] = _static_url


_favicon_ico = _static_dir / "favicon.ico"
_apple_touch_icon = _static_dir / "apple-touch-icon.png"
_icon_cache = "public, max-age=86400, immutable"


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico() -> FileResponse:
    """Serve favicon.ico from static assets."""
    return FileResponse(
        _favicon_ico,
        media_type="image/x-icon",
        headers={"Cache-Control": _icon_cache},
    )


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def apple_touch_icon() -> FileResponse:
    """Serve apple-touch-icon.png from static assets."""
    return FileResponse(
        _apple_touch_icon,
        media_type="image/png",
        headers={"Cache-Control": _icon_cache},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(certificates_router)
app.include_router(users_router)
app.include_router(analytics_router)
app.include_router(htmx_router)
# Must be last to avoid catching API routes
app.include_router(pages_router)
