"""Health check endpoints."""

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from core.database import check_db_connection
from core.ratelimit import limiter
from schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", service="learn-to-cloud-api")


@router.get(
    "/ready",
    response_model=HealthResponse,
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
@limiter.limit("30/minute")
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
        await check_db_connection(request.app.state.engine)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from e

    return HealthResponse(status="ready", service="learn-to-cloud-api")
