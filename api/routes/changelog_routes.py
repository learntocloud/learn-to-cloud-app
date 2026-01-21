"""Updates endpoint - this week's commits."""

from fastapi import APIRouter, Request

from core.ratelimit import limiter
from schemas import UpdatesResponse
from services.changelog_service import get_updates

router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get(
    "",
    response_model=UpdatesResponse,
    summary="Get this week's updates",
    responses={200: {"description": "Commits from the current week (since Monday)"}},
)
@limiter.limit("30/minute")
async def get_updates_data(request: Request) -> UpdatesResponse:
    """Get this week's commits.

    Returns commits since Monday of the current week.
    Results are cached for 5 minutes to avoid GitHub API rate limits.
    """
    data = await get_updates()
    return UpdatesResponse(**data)
