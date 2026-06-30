"""Health check endpoints."""

import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from learn_to_cloud_shared.core.database import check_db_connection
from learn_to_cloud_shared.schemas import HealthResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette import status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# api/alembic.ini, four directories up from this file (routes -> learn_to_cloud
# -> src -> api). Same relative depth in the devcontainer source tree and in
# the api-runtime Docker image, where PYTHONPATH=/app/src.
_ALEMBIC_INI = Path(__file__).parent.parent.parent.parent / "alembic.ini"


def get_code_alembic_head() -> str | None:
    """Resolve the Alembic head revision baked into this deployment's code.

    Returns None if the script directory can't be resolved, so schema-drift
    detection is best-effort and never blocks application startup.
    """
    try:
        script = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI)))
        return script.get_current_head()
    except Exception:
        logger.exception("health.alembic_head.resolve_failed")
        return None


async def _get_db_alembic_head(engine: AsyncEngine) -> str | None:
    """Fetch the Alembic revision currently recorded in the database."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
        await conn.rollback()
        return row[0] if row else None


@router.get("/health", summary="Health check")
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", service="learn-to-cloud-api")


@router.get(
    "/ready",
    summary="Readiness check",
    responses={
        503: {
            "description": "Service unavailable - init failed or DB unreachable",
            "content": {
                "application/json": {"example": {"detail": "Database unavailable"}}
            },
        }
    },
)
async def ready(request: Request) -> HealthResponse:
    """Readiness endpoint.

    Returns 200 only when:
    - Background initialization has completed successfully
    - The database is reachable
    """
    init_error = getattr(request.app.state, "init_error", None)
    if init_error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Initialization failed: {init_error}",
        )

    init_done = bool(getattr(request.app.state, "init_done", False))
    if not init_done:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Starting",
        )

    try:
        await check_db_connection(
            request.app.state.engine,
            request.app.state.settings.database,
        )
    except Exception as e:
        logger.warning("health.ready.db_unavailable", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from e

    # Schema drift is a paging signal, not a readiness failure: log a warning
    # for the Azure Monitor alert to pick up, but never fail this probe over
    # it. Failing here would just cycle pods without fixing the drift.
    code_head = getattr(request.app.state, "alembic_code_head", None)
    if code_head is not None:
        try:
            db_head = await _get_db_alembic_head(request.app.state.engine)
        except Exception as e:
            logger.warning(
                "health.ready.schema_drift_check_failed", extra={"error": str(e)}
            )
        else:
            if db_head != code_head:
                logger.warning(
                    "health.ready.schema_drift",
                    extra={"db_head": db_head, "code_head": code_head},
                )

    return HealthResponse(status="ready", service="learn-to-cloud-api")


@router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots_txt() -> str:
    """Serve robots.txt to stop crawlers generating 404s."""
    return "User-agent: *\nAllow: /\n"
