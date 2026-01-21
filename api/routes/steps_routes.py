"""Step progress tracking endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request

from core import get_logger
from core.auth import UserId
from core.database import DbSession
from core.ratelimit import limiter
from schemas import (
    StepCompleteRequest,
    StepProgressResponse,
    StepUncompleteResponse,
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
from services.users_service import ensure_user_exists, get_or_create_user

logger = get_logger(__name__)

router = APIRouter(prefix="/api/steps", tags=["steps"])

ValidatedTopicId = Annotated[
    str,
    Path(max_length=100, pattern=r"^phase\d+-topic\d+$"),
]

ValidatedStepOrder = Annotated[int, Path(ge=1)]


@router.post(
    "/complete",
    response_model=StepProgressResponse,
    status_code=201,
    responses={
        404: {"description": "Topic not found"},
        400: {
            "description": "Step already completed, not unlocked, or invalid step order"
        },
    },
)
@limiter.limit("30/minute")
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
    except StepUnknownTopicError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StepAlreadyCompletedError:
        raise HTTPException(status_code=400, detail="Step already completed")
    except StepNotUnlockedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StepInvalidStepOrderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StepProgressResponse(
        topic_id=result.topic_id,
        step_order=result.step_order,
        completed_at=result.completed_at,
    )


@router.get(
    "/{topic_id}",
    response_model=TopicStepProgressResponse,
    responses={404: {"description": "Topic not found"}},
)
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
        raise HTTPException(status_code=404, detail=str(e))

    return TopicStepProgressResponse(
        topic_id=progress.topic_id,
        completed_steps=progress.completed_steps,
        total_steps=progress.total_steps,
        next_unlocked_step=progress.next_unlocked_step,
    )


@router.delete(
    "/{topic_id}/{step_order}",
    response_model=StepUncompleteResponse,
    responses={
        404: {"description": "Topic not found"},
        400: {"description": "Invalid step order"},
    },
)
@limiter.limit("30/minute")
async def uncomplete_step_endpoint(
    request: Request,
    topic_id: ValidatedTopicId,
    step_order: ValidatedStepOrder,
    user_id: UserId,
    db: DbSession,
) -> StepUncompleteResponse:
    """Mark a learning step as incomplete (uncomplete it).

    Also removes any steps after this one (cascading uncomplete).
    """
    await ensure_user_exists(db, user_id)

    try:
        deleted_count = await uncomplete_step(db, user_id, topic_id, step_order)
    except StepUnknownTopicError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except StepInvalidStepOrderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return StepUncompleteResponse(
        status="success",
        deleted_count=deleted_count,
    )
