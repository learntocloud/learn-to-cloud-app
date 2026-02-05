"""Activity service for activity logging.

This module handles activity logging (the single point for recording user activities).

Routes should use this service for all activity-related business logic.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.telemetry import add_custom_attribute, log_business_event, track_operation
from models import ActivityType
from repositories.activity_repository import ActivityRepository
from schemas import ActivityResult


@track_operation("activity_logging")
async def log_activity(
    db: AsyncSession,
    user_id: str,
    activity_type: ActivityType,
    reference_id: str | None = None,
) -> ActivityResult:
    """Log a user activity for streak and heatmap tracking."""
    today = datetime.now(UTC).date()

    add_custom_attribute("activity.type", activity_type.value)

    activity_repo = ActivityRepository(db)
    activity = await activity_repo.log_activity(
        user_id=user_id,
        activity_type=activity_type,
        activity_date=today,
        reference_id=reference_id,
    )

    log_business_event("activities.logged", 1, {"type": activity_type.value})

    return ActivityResult(
        id=activity.id,
        activity_type=activity.activity_type,
        activity_date=activity.activity_date,
        reference_id=activity.reference_id,
        created_at=activity.created_at,
    )
