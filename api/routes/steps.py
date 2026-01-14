"""Step progress tracking endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from core.auth import UserId
from core.database import DbSession
from schemas import (
    StepCompleteRequest,
    StepProgressResponse,
    TopicStepProgressResponse,
)
from services.steps import (
    StepAlreadyCompletedError,
    StepNotUnlockedError,
    complete_step,
    get_all_user_steps,
    get_topic_step_progress,
    uncomplete_step,
)

from services.users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/steps", tags=["steps"])

@router.get("/{topic_id}", response_model=TopicStepProgressResponse)
async def get_topic_step_progress_endpoint(
    topic_id: str,
    total_steps: int,
    user_id: UserId,
    db: DbSession,
) -> TopicStepProgressResponse:
    """Get the step progress for a topic.
    
    Args:
        topic_id: The topic ID (e.g., "phase1-topic5")
        total_steps: Total number of steps in this topic (from frontend)
    """
    user = await get_or_create_user(db, user_id)

    progress = await get_topic_step_progress(
        db,
        user_id,
        topic_id,
        total_steps,
        is_admin=user.is_admin,
    )

    return TopicStepProgressResponse(
        topic_id=progress.topic_id,
        completed_steps=progress.completed_steps,
        total_steps=progress.total_steps,
        next_unlocked_step=progress.next_unlocked_step,
    )

@router.post("/complete", response_model=StepProgressResponse)
async def complete_step_endpoint(
    request: StepCompleteRequest,
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
            request.topic_id,
            request.step_order,
            is_admin=user.is_admin,
        )
    except StepAlreadyCompletedError:
        raise HTTPException(status_code=400, detail="Step already completed")
    except StepNotUnlockedError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StepProgressResponse(
        topic_id=result.topic_id,
        step_order=result.step_order,
        completed_at=result.completed_at,
    )

@router.delete("/{topic_id}/{step_order}")
async def uncomplete_step_endpoint(
    topic_id: str,
    step_order: int,
    user_id: UserId,
    db: DbSession,
) -> dict:
    """Mark a learning step as incomplete (uncomplete it).
    
    Also removes any steps after this one (cascading uncomplete).
    """
    await get_or_create_user(db, user_id)

    deleted_count = await uncomplete_step(db, user_id, topic_id, step_order)

    return {
        "status": "success",
        "deleted_count": deleted_count,
    }

@router.get("/user/all-status")
async def get_all_steps_status_endpoint(
    user_id: UserId,
    db: DbSession,
) -> dict[str, list[int]]:
    """Get the status of all completed steps across all topics for the current user.

    Returns a dict mapping topic_id to list of completed step_order numbers.
    """
    await get_or_create_user(db, user_id)

    return await get_all_user_steps(db, user_id)
