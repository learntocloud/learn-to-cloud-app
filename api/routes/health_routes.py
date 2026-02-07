"""Health check endpoints."""

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from core.database import (
    check_db_connection,
    comprehensive_health_check,
)
from core.ratelimit import limiter
from schemas import DetailedHealthResponse, HealthResponse, PoolStatusResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", service="learn-to-cloud-api")


@router.get("/health/detailed", response_model=DetailedHealthResponse)
@limiter.limit("30/minute")
async def health_detailed(request: Request) -> DetailedHealthResponse:
    """Detailed health check with component status.

    Returns status of:
    - database: Can execute queries
    - azure_auth: Token acquisition working (null if not using Azure)
    - pool: Connection pool metrics

    Always returns 200 - check individual component statuses for health.
    """
    result = await comprehensive_health_check(request.app.state.engine)

    pool_status = None
    if result["pool"] is not None:
        pool_status = PoolStatusResponse(
            pool_size=result["pool"].pool_size,
            checked_out=result["pool"].checked_out,
            overflow=result["pool"].overflow,
            checked_in=result["pool"].checked_in,
        )

    overall_status = "healthy" if result["database"] else "unhealthy"
    if result["azure_auth"] is False:
        overall_status = "unhealthy"

    return DetailedHealthResponse(
        status=overall_status,
        service="learn-to-cloud-api",
        database=result["database"],
        azure_auth=result["azure_auth"],
        pool=pool_status,
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
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
