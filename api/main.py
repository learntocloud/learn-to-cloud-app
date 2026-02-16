"""FastAPI application for Learn to Cloud API."""

import asyncio
import hashlib
import logging
import re
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import fastapi
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

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
            digest = hashlib.md5(
                file_path.read_bytes(), usedforsecurity=False
            ).hexdigest()[:8]
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
        logger.error(
            "init.failed",
            extra={"error": str(e)},
            exc_info=True,
        )
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


_legacy_phase_path_re = re.compile(r"^/phase[-_]?(?P<phase_id>\d+)(?P<rest>/.*)?$")


def _normalize_legacy_slug(slug: str) -> str:
    slug = slug.lower()
    if slug.endswith(".html"):
        slug = slug.removesuffix(".html")
    return re.sub(r"[^a-z0-9]+", "", slug)


@lru_cache(maxsize=1)
def _topic_slug_aliases_by_phase() -> dict[str, dict[str, str]]:
    """Build a mapping of legacy topic slugs -> current topic slugs per phase.

    Note:
        Cached for the lifetime of the process. If content YAML changes, a server
        restart is required for this mapping to update.
    """
    # Deferred import to avoid circular dependency with services.content_service.
    from services.content_service import get_all_phases

    aliases: dict[str, dict[str, str]] = {}
    for phase in get_all_phases():
        phase_id = str(phase.id)
        phase_aliases: dict[str, str] = {}
        for topic_slug in phase.topic_slugs:
            phase_aliases[_normalize_legacy_slug(topic_slug)] = topic_slug
        aliases[phase_id] = phase_aliases

    # Known legacy slugs from older docs / bookmarks.
    manual_aliases: dict[str, dict[str, str]] = {
        "1": {
            "ctf": "ctf-lab",
            "versioncontrol": "developer-setup",
        },
        "2": {
            "networkingfundamentals": "fundamentals",
            "portsandprotocols": "protocols",
            "troubleshooting": "troubleshooting-lab",
        },
    }
    for phase_id, slug_map in manual_aliases.items():
        phase_aliases = aliases.setdefault(phase_id, {})
        for legacy_slug, canonical_slug in slug_map.items():
            phase_aliases[_normalize_legacy_slug(legacy_slug)] = canonical_slug
    return aliases


def _resolve_legacy_phase_redirect(path: str) -> str | None:
    """Return the canonical redirect path for a legacy /phaseN URL, or None."""
    match = _legacy_phase_path_re.match(path)
    if not match or path.startswith("/phase/"):
        return None

    phase_id = match.group("phase_id")
    rest = match.group("rest") or ""

    # Normalize phase roots (/phase1 and /phase1/) to /phase/1.
    if rest in ("", "/"):
        return f"/phase/{phase_id}"

    # Try to map /phaseN/<topic> to /phase/N/<topic-slug>; otherwise
    # fall back to the phase root so we don't redirect to a 404 topic.
    parts = rest.lstrip("/").split("/")
    legacy_topic = parts[0]
    # Filter empty segments so double-slashes are normalised away.
    remainder = [p for p in parts[1:] if p]

    topic_aliases = _topic_slug_aliases_by_phase().get(str(phase_id), {})
    canonical_topic = topic_aliases.get(_normalize_legacy_slug(legacy_topic))
    if canonical_topic:
        target_path = f"/phase/{phase_id}/{canonical_topic}"
        if remainder:
            target_path = f"{target_path}/{'/'.join(remainder)}"
        return target_path

    return f"/phase/{phase_id}"


class LegacyPhaseRedirectMiddleware:
    """Redirect legacy /phaseN URLs to canonical /phase/N URLs (308 Permanent).

    Registered as the outermost middleware so redirects are served before
    session or user-tracking middleware run — avoids creating sessions and
    tracking users for requests that will immediately redirect.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        target_path = _resolve_legacy_phase_redirect(path)

        if target_path is not None and target_path != path:
            query = scope.get("query_string", b"").decode("latin-1")
            target_url = target_path if not query else f"{target_path}?{query}"
            logger.info(
                "legacy_url.redirect",
                extra={
                    "from_path": path,
                    "to_path": target_path,
                    "query": query,
                    "status_code": 308,
                },
            )
            response = RedirectResponse(url=target_url, status_code=308)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


app.add_middleware(UserTrackingMiddleware)
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

# Outermost — runs before session/user-tracking to avoid wasted work on redirects.
app.add_middleware(LegacyPhaseRedirectMiddleware)

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
