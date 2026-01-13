"""Step progress tracking endpoints."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from shared.auth import UserId
from shared.database import DbSession
from shared.models import ActivityType, StepProgress, UserActivity
from shared.schemas import (
    StepCompleteRequest,
    StepProgressResponse,
    TopicStepProgressResponse,
)

from .users import get_or_create_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/steps", tags=["steps"])


@router.get("/{topic_id}", response_model=TopicStepProgressResponse)
async def get_topic_step_progress(
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
    await get_or_create_user(db, user_id)

    result = await db.execute(
        select(StepProgress.step_order)
        .where(
            StepProgress.user_id == user_id,
            StepProgress.topic_id == topic_id,
        )
        .order_by(StepProgress.step_order)
    )
    completed_steps = [row[0] for row in result.all()]

    # Calculate next unlocked step (first incomplete, or 1 if none done)
    # Steps are unlocked sequentially: 1, 2, 3, etc.
    if not completed_steps:
        next_unlocked = 1
    else:
        # Find the first gap or next after last completed
        max_completed = max(completed_steps)
        if max_completed < total_steps:
            next_unlocked = max_completed + 1
        else:
            next_unlocked = total_steps

    return TopicStepProgressResponse(
        topic_id=topic_id,
        completed_steps=completed_steps,
        total_steps=total_steps,
        next_unlocked_step=next_unlocked,
    )


@router.post("/complete", response_model=StepProgressResponse)
async def complete_step(
    request: StepCompleteRequest,
    user_id: UserId,
    db: DbSession,
) -> StepProgressResponse:
    """Mark a learning step as complete.
    
    Steps must be completed in order - you can only complete step N
    if steps 1 through N-1 are already complete.
    """
    await get_or_create_user(db, user_id)

    # Check if step is already complete
    existing = await db.execute(
        select(StepProgress).where(
            StepProgress.user_id == user_id,
            StepProgress.topic_id == request.topic_id,
            StepProgress.step_order == request.step_order,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Step already completed",
        )

    # Check that all previous steps are complete (sequential unlocking)
    if request.step_order > 1:
        result = await db.execute(
            select(StepProgress.step_order)
            .where(
                StepProgress.user_id == user_id,
                StepProgress.topic_id == request.topic_id,
            )
            .order_by(StepProgress.step_order)
        )
        completed_steps = set(row[0] for row in result.all())
        
        # Check all steps from 1 to step_order-1 are complete
        required_steps = set(range(1, request.step_order))
        if not required_steps.issubset(completed_steps):
            msg = (
                f"Must complete previous steps first. "
                f"Complete: {sorted(completed_steps)}, "
                f"required: {sorted(required_steps)}"
            )
            raise HTTPException(status_code=400, detail=msg)

    # Create the step progress record
    step_progress = StepProgress(
        user_id=user_id,
        topic_id=request.topic_id,
        step_order=request.step_order,
    )
    db.add(step_progress)

    # Log activity for streak tracking
    today = datetime.now(UTC).date()
    activity = UserActivity(
        user_id=user_id,
        activity_type=ActivityType.STEP_COMPLETE,
        activity_date=today,
        reference_id=f"{request.topic_id}:step{request.step_order}",
    )
    db.add(activity)

    await db.commit()
    await db.refresh(step_progress)

    return StepProgressResponse(
        topic_id=step_progress.topic_id,
        step_order=step_progress.step_order,
        completed_at=step_progress.completed_at,
    )


@router.delete("/{topic_id}/{step_order}")
async def uncomplete_step(
    topic_id: str,
    step_order: int,
    user_id: UserId,
    db: DbSession,
) -> dict:
    """Mark a learning step as incomplete (uncomplete it).
    
    Also removes any steps after this one (cascading uncomplete).
    """
    await get_or_create_user(db, user_id)

    # Delete this step and all subsequent steps
    result = await db.execute(
        delete(StepProgress).where(
            StepProgress.user_id == user_id,
            StepProgress.topic_id == topic_id,
            StepProgress.step_order >= step_order,
        )
    )
    
    await db.commit()
    
    return {
        "status": "success",
        "deleted_count": result.rowcount,
    }


@router.get("/user/all-status")
async def get_all_steps_status(
    user_id: UserId,
    db: DbSession,
) -> dict[str, list[int]]:
    """Get the status of all completed steps across all topics for the current user.

    Returns a dict mapping topic_id to list of completed step_order numbers.
    """
    await get_or_create_user(db, user_id)

    # Get all completed steps grouped by topic
    result = await db.execute(
        select(
            StepProgress.topic_id,
            StepProgress.step_order,
        )
        .where(StepProgress.user_id == user_id)
        .order_by(StepProgress.topic_id, StepProgress.step_order)
    )

    # Group by topic
    topic_steps: dict[str, list[int]] = {}
    for row in result.all():
        topic_id = row.topic_id
        if topic_id not in topic_steps:
            topic_steps[topic_id] = []
        topic_steps[topic_id].append(row.step_order)

    return topic_steps
