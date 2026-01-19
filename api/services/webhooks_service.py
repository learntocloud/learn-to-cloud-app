"""Webhook handler service for Clerk user sync events."""

from sqlalchemy.ext.asyncio import AsyncSession

from core.telemetry import add_custom_attribute, log_metric, track_operation
from repositories.user_repository import UserRepository
from repositories.webhook_repository import ProcessedWebhookRepository
from services.clerk_service import extract_github_username, extract_primary_email
from services.users_service import _normalize_github_username


async def handle_user_created(db: AsyncSession, data: dict) -> None:
    """Handle user.created webhook event.

    Creates or updates user record with data from Clerk using upsert.
    """
    user_id = data.get("id")
    if not user_id:
        return

    user_repo = UserRepository(db)

    primary_email = extract_primary_email(data, f"{user_id}@unknown.local")
    github_username = extract_github_username(data)
    normalized_github_username = _normalize_github_username(github_username)
    email = primary_email or f"{user_id}@unknown.local"

    await user_repo.upsert(
        user_id=user_id,
        email=email,
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        avatar_url=data.get("image_url"),
        github_username=normalized_github_username,
    )


async def handle_user_updated(db: AsyncSession, data: dict) -> None:
    """Handle user.updated webhook event.

    Updates existing user record or creates if not found using upsert.
    """
    user_id = data.get("id")
    if not user_id:
        return

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    primary_email = extract_primary_email(
        data, user.email if user else f"{user_id}@unknown.local"
    )
    github_username = extract_github_username(data)
    normalized_github_username = _normalize_github_username(github_username)

    await user_repo.upsert(
        user_id=user_id,
        email=primary_email or f"{user_id}@unknown.local",
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        avatar_url=data.get("image_url"),
        github_username=normalized_github_username,
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


@track_operation("webhook_processing")
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
    add_custom_attribute("webhook.event_type", event_type)
    add_custom_attribute("webhook.svix_id", svix_id)

    webhook_repo = ProcessedWebhookRepository(db)
    is_first_time = await webhook_repo.try_mark_processed(svix_id, event_type)
    if not is_first_time:
        log_metric("webhooks.deduplicated", 1, {"event_type": event_type})
        return "already_processed"

    if event_type == "user.created":
        await handle_user_created(db, data)
        log_metric("webhooks.user_created", 1)
    elif event_type == "user.updated":
        await handle_user_updated(db, data)
        log_metric("webhooks.user_updated", 1)
    elif event_type == "user.deleted":
        await handle_user_deleted(db, data)
        log_metric("webhooks.user_deleted", 1)

    log_metric("webhooks.processed", 1, {"event_type": event_type})
    return "processed"
