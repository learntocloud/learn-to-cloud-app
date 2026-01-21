"""Changelog endpoints."""

from fastapi import APIRouter, Request

from core.ratelimit import limiter
from schemas import ChangelogResponse
from services.changelog_service import get_changelog

router = APIRouter(prefix="/api/changelog", tags=["changelog"])


@router.get(
    "",
    response_model=ChangelogResponse,
    summary="Get weekly changelog",
    responses={200: {"description": "Weekly changelog grouped by week"}},
)
@limiter.limit("30/minute")
async def get_changelog_data(request: Request) -> ChangelogResponse:
    """Get the weekly changelog of commits.

    Returns commits grouped by week with metadata for display.
    Results are cached for 5 minutes to avoid GitHub API rate limits.
    """
    data = await get_changelog()
    return ChangelogResponse(**data)
