"""Step progress tracking endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request

from core.auth import UserId
from core.database import DbSession
from core.ratelimit import limiter
from schemas import (
    StepCompleteRequest,
    StepProgressResponse,
    TopicStepProgressResponse,
)
from services.steps_service import (
    StepAlreadyCompletedError,
    StepInvalidStepOrderError,
    StepNotUnlockedError,
    StepUnknownTopicError,
    complete_step,
    get_topic_step_progress,
    uncomplete_step,
)
from services.users_service import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/steps", tags=["steps"])

ValidatedTopicId = Annotated[
    str,
    Path(max_length=100, pattern=r"^phase\d+-topic\d+$"),
]

ValidatedStepOrder = Annotated[int, Path(ge=1)]


@router.get("/{topic_id}", response_model=TopicStepProgressResponse)
@limiter.limit("60/minute")
async def get_topic_step_progress_endpoint(
    request: Request,
    topic_id: ValidatedTopicId,
    user_id: UserId,
    db: DbSession,
) -> TopicStepProgressResponse:
    """Get the step progress for a topic.

    Args:
        topic_id: The topic ID (e.g., "phase1-topic5")
    """
    user = await get_or_create_user(db, user_id)

    try:
        progress = await get_topic_step_progress(
            db,
            user_id,
            topic_id,
            is_admin=user.is_admin,
        )
    except StepUnknownTopicError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TopicStepProgressResponse(
        topic_id=progress.topic_id,
        completed_steps=progress.completed_steps,
        total_steps=progress.total_steps,
        next_unlocked_step=progress.next_unlocked_step,
    )


@router.post("/complete", response_model=StepProgressResponse)
@limiter.limit("60/minute")
async def complete_step_endpoint(
    request: Request,
    body: StepCompleteRequest,
    user_id: UserId,
    db: DbSession,
) -> StepProgressResponse:
    """Mark a learning step as complete.

    Steps must be completed in order - you can only complete step N
    if steps 1 through N-1 are already complete.
    """
    user = await get_or_create_user(db, user_id)

    try:
        result = await complete_step(
            db,
            user_id,
            body.topic_id,
            body.step_order,
            is_admin=user.is_admin,
        )
    except StepAlreadyCompletedError:
        raise HTTPException(status_code=400, detail="Step already completed")
    except StepNotUnlockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (StepUnknownTopicError, StepInvalidStepOrderError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StepProgressResponse(
        topic_id=result.topic_id,
        step_order=result.step_order,
        completed_at=result.completed_at,
    )


@router.delete("/{topic_id}/{step_order}")
@limiter.limit("60/minute")
async def uncomplete_step_endpoint(
    request: Request,
    topic_id: ValidatedTopicId,
    step_order: ValidatedStepOrder,
    user_id: UserId,
    db: DbSession,
) -> dict:
    """Mark a learning step as incomplete (uncomplete it).

    Also removes any steps after this one (cascading uncomplete).
    """
    await get_or_create_user(db, user_id)

    try:
        deleted_count = await uncomplete_step(db, user_id, topic_id, step_order)
    except (StepUnknownTopicError, StepInvalidStepOrderError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "deleted_count": deleted_count,
    }
