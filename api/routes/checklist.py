"""Checklist progress endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from shared import (
    DbSession,
    UserId,
    ChecklistProgress,
    ProgressItem,
    UserProgressResponse,
    ChecklistToggleResponse,
)
from .users import get_or_create_user

router = APIRouter(prefix="/api", tags=["checklist"])


@router.get("/user/progress", response_model=UserProgressResponse)
async def get_user_progress(user_id: UserId, db: DbSession) -> UserProgressResponse:
    """Get all user progress items."""
    await get_or_create_user(db, user_id)

    result = await db.execute(
        select(ChecklistProgress).where(ChecklistProgress.user_id == user_id)
    )
    progress_items = result.scalars().all()

    return UserProgressResponse(
        user_id=user_id,
        items=[
            ProgressItem(
                checklist_item_id=p.checklist_item_id,
                is_completed=p.is_completed,
                completed_at=p.completed_at,
            )
            for p in progress_items
        ],
    )


@router.post("/checklist/{item_id}/toggle", response_model=ChecklistToggleResponse)
async def toggle_checklist_item(
    item_id: str, user_id: UserId, db: DbSession
) -> ChecklistToggleResponse:
    """Toggle a checklist item completion status."""
    try:
        phase_id = int(item_id.split("-")[0].replace("phase", ""))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid checklist item ID format")

    await get_or_create_user(db, user_id)

    result = await db.execute(
        select(ChecklistProgress).where(
            ChecklistProgress.user_id == user_id,
            ChecklistProgress.checklist_item_id == item_id,
        )
    )
    progress = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if not progress:
        progress = ChecklistProgress(
            user_id=user_id,
            checklist_item_id=item_id,
            phase_id=phase_id,
            is_completed=True,
            completed_at=now,
        )
        db.add(progress)
        is_completed = True
    else:
        progress.is_completed = not progress.is_completed
        progress.completed_at = now if progress.is_completed else None
        is_completed = progress.is_completed

    return ChecklistToggleResponse(success=True, item_id=item_id, is_completed=is_completed)
