"""Checklist progress endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from sqlalchemy import select

from shared.auth import UserId
from shared.database import DbSession
from shared.models import ChecklistProgress
from shared.schemas import (
    ChecklistToggleResponse,
    ProgressItem,
    UserProgressResponse,
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


# Validated item_id: e.g., "phase0-check1" or "phase1-topic1-check1"
ValidatedItemId = Annotated[
    str,
    Path(max_length=100, pattern=r"^phase\d+-.+$"),
]


@router.post("/checklist/{item_id}/toggle", response_model=ChecklistToggleResponse)
async def toggle_checklist_item(
    item_id: ValidatedItemId, user_id: UserId, db: DbSession
) -> ChecklistToggleResponse:
    """Toggle a checklist item completion status."""
    # Pattern already validates format, but extract phase_id safely
    phase_id = int(item_id.split("-")[0].replace("phase", ""))

    await get_or_create_user(db, user_id)

    result = await db.execute(
        select(ChecklistProgress).where(
            ChecklistProgress.user_id == user_id,
            ChecklistProgress.checklist_item_id == item_id,
        )
    )
    progress = result.scalar_one_or_none()

    now = datetime.now(UTC)

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

    await db.commit()

    return ChecklistToggleResponse(
        success=True, item_id=item_id, is_completed=is_completed
    )
