"""Clerk webhook endpoints."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from shared.config import get_settings
from shared.database import DbSession
from shared.models import ProcessedWebhook, User
from shared.schemas import WebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def extract_github_username(data: dict) -> str | None:
    """
    Extract GitHub username from Clerk webhook data.

    Clerk stores OAuth account info in 'external_accounts' array.
    Each account has 'provider' and 'username' fields.
    """
    external_accounts = data.get("external_accounts", [])

    return next(
        (
            account.get("username") or account.get("provider_user_id")
            for account in external_accounts
            if account.get("provider") in ("github", "oauth_github")
            and (account.get("username") or account.get("provider_user_id"))
        ),
        None,
    )


async def handle_user_created(db: AsyncSession, data: dict) -> None:
    """Handle user.created webhook event."""
    user_id = data.get("id")
    if not user_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    existing_user = result.scalar_one_or_none()

    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (
            e.get("email_address")
            for e in email_addresses
            if e.get("id") == data.get("primary_email_address_id")
        ),
        email_addresses[0].get("email_address")
        if email_addresses
        else f"{user_id}@unknown.local",
    )

    # Extract GitHub username from OAuth accounts
    github_username = extract_github_username(data)

    if existing_user:
        existing_user.email = primary_email
        existing_user.first_name = data.get("first_name")
        existing_user.last_name = data.get("last_name")
        existing_user.avatar_url = data.get("image_url")
        existing_user.github_username = github_username
        existing_user.updated_at = datetime.now(UTC)
    else:
        user = User(
            id=user_id,
            email=primary_email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
            github_username=github_username,
        )
        db.add(user)


async def handle_user_updated(db: AsyncSession, data: dict) -> None:
    """Handle user.updated webhook event."""
    user_id = data.get("id")
    if not user_id:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        await handle_user_created(db, data)
        return

    email_addresses = data.get("email_addresses", [])
    primary_email = next(
        (
            e.get("email_address")
            for e in email_addresses
            if e.get("id") == data.get("primary_email_address_id")
        ),
        email_addresses[0].get("email_address") if email_addresses else user.email,
    )

    # Extract GitHub username from OAuth accounts
    github_username = extract_github_username(data)

    user.email = primary_email
    user.first_name = data.get("first_name")
    user.last_name = data.get("last_name")
    user.avatar_url = data.get("image_url")
    user.github_username = github_username
    user.updated_at = datetime.now(UTC)


async def handle_user_deleted(db: AsyncSession, data: dict) -> None:
    """Handle user.deleted webhook event."""
    user_id = data.get("id")
    if not user_id:
        return

    # Hard delete: remove the user and rely on FK ON DELETE CASCADE to
    # delete dependent rows (github_submissions, question_attempts, etc.).
    await db.execute(delete(User).where(User.id == user_id))


@router.post("/clerk", response_model=WebhookResponse)
async def clerk_webhook(request: Request, db: DbSession) -> WebhookResponse:
    """Handle Clerk webhooks for user sync."""
    settings = get_settings()
    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id"),
        "svix-timestamp": request.headers.get("svix-timestamp"),
        "svix-signature": request.headers.get("svix-signature"),
    }

    if not all(headers.values()):
        raise HTTPException(status_code=400, detail="Missing webhook headers")

    # Type narrow: after the check above, all values are non-None
    verified_headers = {k: v for k, v in headers.items() if v is not None}

    if not settings.clerk_webhook_signing_secret:
        raise HTTPException(
            status_code=500,
            detail="Webhook signing secret not configured",
        )

    try:
        wh = Webhook(settings.clerk_webhook_signing_secret)
        event = wh.verify(payload, verified_headers)
    except WebhookVerificationError as e:
        logger.warning(
            f"Webhook verification failed: svix_id={headers.get('svix-id')}, "
            f"timestamp={headers.get('svix-timestamp')}, error={e}"
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook signature",
        )

    event_type = event.get("type") or "unknown"
    data = event.get("data", {})
    svix_id = verified_headers["svix-id"]

    # Idempotency under concurrency: acquire the svix-id by inserting it first.
    # If another request already inserted the same id, treat as already processed.
    processed = ProcessedWebhook(id=svix_id, event_type=event_type)
    db.add(processed)
    try:
        await db.flush()
    except IntegrityError:
        return WebhookResponse(status="already_processed")

    if event_type == "user.created":
        await handle_user_created(db, data)
    elif event_type == "user.updated":
        await handle_user_updated(db, data)
    elif event_type == "user.deleted":
        await handle_user_deleted(db, data)

    return WebhookResponse(status="processed", event_type=event_type)
