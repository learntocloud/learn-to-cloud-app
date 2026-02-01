"""Admin endpoints for metrics and trend analysis.

All endpoints require admin authentication.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request

from core import get_logger
from core.auth import UserId
from core.database import DbSession
from core.ratelimit import limiter
from schemas import BackfillRequest, BackfillResponse, TrendsResponse
from services.metrics_service import (
    BackfillRangeTooLargeError,
    InvalidDateRangeError,
    aggregate_daily_metrics,
    backfill_metrics,
    get_trends,
)
from services.users_service import get_or_create_user

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_admin(db: DbSession, user_id: str) -> None:
    """Verify user is admin, raise 403 if not."""
    user = await get_or_create_user(db, user_id)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get(
    "/trends",
    response_model=TrendsResponse,
    summary="Get trend analytics data",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
    },
)
@limiter.limit("30/minute")
async def get_trends_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSession,
    days: int = Query(default=30, ge=1, le=365, description="Days of history"),
) -> TrendsResponse:
    """Get trend data for admin dashboard.

    Returns daily metrics and summary statistics for the specified period.
    """
    await _require_admin(db, user_id)

    return await get_trends(db, days)


@router.post(
    "/trends/aggregate-today",
    response_model=dict,
    status_code=201,
    summary="Aggregate metrics for today",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
    },
)
@limiter.limit("5/minute")
async def aggregate_today_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSession,
) -> dict:
    """Manually trigger aggregation for today.

    Useful for testing or when the scheduled job hasn't run yet.
    """
    await _require_admin(db, user_id)

    today = datetime.now(UTC).date()
    await aggregate_daily_metrics(db, today)
    await db.commit()

    return {"status": "success", "date": today.isoformat()}


@router.post(
    "/trends/aggregate-yesterday",
    response_model=dict,
    status_code=201,
    summary="Aggregate metrics for yesterday",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
    },
)
@limiter.limit("5/minute")
async def aggregate_yesterday_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSession,
) -> dict:
    """Manually trigger aggregation for yesterday.

    The nightly job typically aggregates yesterday's data.
    """
    await _require_admin(db, user_id)

    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    await aggregate_daily_metrics(db, yesterday)
    await db.commit()

    return {"status": "success", "date": yesterday.isoformat()}


@router.post(
    "/trends/backfill",
    response_model=BackfillResponse,
    status_code=201,
    summary="Backfill metrics for date range",
    responses={
        400: {"description": "Invalid date range or range too large"},
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
    },
)
@limiter.limit("2/minute")
async def backfill_endpoint(
    request: Request,
    user_id: UserId,
    db: DbSession,
    backfill_request: BackfillRequest,
) -> BackfillResponse:
    """Backfill metrics for a date range.

    Useful for initial setup or recovering from data issues.
    Limited to 365 days per request.
    """
    await _require_admin(db, user_id)

    try:
        days_aggregated = await backfill_metrics(
            db,
            backfill_request.start_date,
            backfill_request.end_date,
        )
    except InvalidDateRangeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except BackfillRangeTooLargeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    return BackfillResponse(
        days_aggregated=days_aggregated,
        start_date=backfill_request.start_date,
        end_date=backfill_request.end_date,
    )
