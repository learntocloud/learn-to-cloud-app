"""Health check endpoints."""

from fastapi import APIRouter

from shared import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/", response_model=HealthResponse)
@router.get("/api", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", service="learn-to-cloud-api")
