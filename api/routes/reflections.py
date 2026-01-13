"""Daily reflections endpoints with AI-generated greetings."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select

from shared.auth import UserId
from shared.database import DbSession
from shared.llm import generate_greeting
from shared.models import ActivityType, DailyReflection, UserActivity
from shared.schemas import (
    LatestGreetingResponse,
    ReflectionResponse,
    ReflectionSubmitRequest,
)

from .users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reflections", tags=["reflections"])

limiter = Limiter(key_func=get_remote_address)


@router.post("", response_model=ReflectionResponse)
@limiter.limit("5/minute")  # Rate limit for LLM calls
async def submit_reflection(
    request: Request,
    submission: ReflectionSubmitRequest,
    user_id: UserId,
    db: DbSession,
) -> ReflectionResponse:
    """Submit a daily reflection.

    The reflection will be saved and an AI greeting will be generated
    for the user's next visit.
    """
    user = await get_or_create_user(db, user_id)

    today = datetime.now(UTC).date()

    # Check if user already submitted a reflection today
    result = await db.execute(
        select(DailyReflection).where(
            DailyReflection.user_id == user_id,
            DailyReflection.reflection_date == today,
        )
    )
    existing = result.scalar_one_or_none()

    # Generate AI greeting
    try:
        ai_greeting = await generate_greeting(
            reflection_text=submission.reflection_text,
            user_first_name=user.first_name,
        )
    except Exception as e:
        logger.exception(f"Failed to generate greeting: {e}")
        # Still save reflection even if greeting generation fails
        ai_greeting = None

    if existing:
        # Update existing reflection for today
        existing.reflection_text = submission.reflection_text
        existing.ai_greeting = ai_greeting
        reflection = existing
    else:
        # Create new reflection
        reflection = DailyReflection(
            user_id=user_id,
            reflection_date=today,
            reflection_text=submission.reflection_text,
            ai_greeting=ai_greeting,
        )
        db.add(reflection)

        # Log activity for streak tracking (only for new reflections)
        activity = UserActivity(
            user_id=user_id,
            activity_type=ActivityType.REFLECTION,
            reference_id=f"reflection-{today.isoformat()}",
        )
        db.add(activity)

    await db.commit()
    await db.refresh(reflection)

    return ReflectionResponse(
        id=reflection.id,
        reflection_date=reflection.reflection_date,
        reflection_text=reflection.reflection_text,
        ai_greeting=reflection.ai_greeting,
        created_at=reflection.created_at,
    )


@router.get("/latest", response_model=LatestGreetingResponse)
async def get_latest_greeting(
    user_id: UserId,
    db: DbSession,
) -> LatestGreetingResponse:
    """Get the most recent AI-generated greeting for the user.

    This is typically shown on the dashboard when the user returns.
    """
    user = await get_or_create_user(db, user_id)

    # Get the most recent reflection with a greeting
    result = await db.execute(
        select(DailyReflection)
        .where(
            DailyReflection.user_id == user_id,
            DailyReflection.ai_greeting.isnot(None),
        )
        .order_by(DailyReflection.reflection_date.desc())
        .limit(1)
    )
    reflection = result.scalar_one_or_none()

    if not reflection:
        return LatestGreetingResponse(
            has_greeting=False,
            greeting=None,
            reflection_date=None,
            user_first_name=user.first_name,
        )

    return LatestGreetingResponse(
        has_greeting=True,
        greeting=reflection.ai_greeting,
        reflection_date=reflection.reflection_date,
        user_first_name=user.first_name,
    )


@router.get("/today", response_model=ReflectionResponse | None)
async def get_today_reflection(
    user_id: UserId,
    db: DbSession,
) -> ReflectionResponse | None:
    """Get today's reflection if one exists."""
    await get_or_create_user(db, user_id)

    today = datetime.now(UTC).date()

    result = await db.execute(
        select(DailyReflection).where(
            DailyReflection.user_id == user_id,
            DailyReflection.reflection_date == today,
        )
    )
    reflection = result.scalar_one_or_none()

    if not reflection:
        return None

    return ReflectionResponse(
        id=reflection.id,
        reflection_date=reflection.reflection_date,
        reflection_text=reflection.reflection_text,
        ai_greeting=reflection.ai_greeting,
        created_at=reflection.created_at,
    )


@router.get("/history")
async def get_reflection_history(
    user_id: UserId,
    db: DbSession,
    limit: int = 30,
) -> list[ReflectionResponse]:
    """Get the user's reflection history.

    Returns the most recent reflections, ordered by date descending.
    """
    await get_or_create_user(db, user_id)

    result = await db.execute(
        select(DailyReflection)
        .where(DailyReflection.user_id == user_id)
        .order_by(DailyReflection.reflection_date.desc())
        .limit(min(limit, 100))  # Cap at 100
    )
    reflections = result.scalars().all()

    return [
        ReflectionResponse(
            id=r.id,
            reflection_date=r.reflection_date,
            reflection_text=r.reflection_text,
            ai_greeting=r.ai_greeting,
            created_at=r.created_at,
        )
        for r in reflections
    ]
