"""Webhook handler service for Clerk user sync events."""

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.webhook import ProcessedWebhookRepository
from repositories.user import UserRepository
from services.clerk import extract_github_username, extract_primary_email

async def handle_user_created(db: AsyncSession, data: dict) -> None:
    """Handle user.created webhook event.

    Creates or updates user record with data from Clerk.
    """
    user_id = data.get("id")
    if not user_id:
        return

    user_repo = UserRepository(db)
    existing_user = await user_repo.get_by_id(user_id)

    primary_email = extract_primary_email(data, f"{user_id}@unknown.local")
    github_username = extract_github_username(data)

    email = primary_email or f"{user_id}@unknown.local"

    if existing_user:
        await user_repo.update(
            existing_user,
            email=email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
            github_username=github_username,
        )
    else:
        await user_repo.create(
            user_id=user_id,
            email=email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
            github_username=github_username,
        )

async def handle_user_updated(db: AsyncSession, data: dict) -> None:
    """Handle user.updated webhook event.

    Updates existing user record or creates if not found.
    """
    user_id = data.get("id")
    if not user_id:
        return

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        await handle_user_created(db, data)
        return

    primary_email = extract_primary_email(data, user.email)
    github_username = extract_github_username(data)

    await user_repo.update(
        user,
        email=primary_email,
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        avatar_url=data.get("image_url"),
        github_username=github_username,
    )

async def handle_user_deleted(db: AsyncSession, data: dict) -> None:
    """Handle user.deleted webhook event.

    Hard deletes the user and relies on FK ON DELETE CASCADE
    to delete dependent rows (submissions, question_attempts, etc.).
    """
    user_id = data.get("id")
    if not user_id:
        return

    user_repo = UserRepository(db)
    await user_repo.delete(user_id)

async def handle_clerk_event(
    db: AsyncSession,
    *,
    svix_id: str,
    event_type: str,
    data: dict,
) -> str:
    """Handle a Clerk webhook event with idempotency.

    Returns:
        "already_processed" if the svix-id was already seen.
        "processed" otherwise.
    """
    webhook_repo = ProcessedWebhookRepository(db)
    is_first_time = await webhook_repo.try_mark_processed(svix_id, event_type)
    if not is_first_time:
        return "already_processed"

    if event_type == "user.created":
        await handle_user_created(db, data)
    elif event_type == "user.updated":
        await handle_user_updated(db, data)
    elif event_type == "user.deleted":
        await handle_user_deleted(db, data)

    return "processed"
